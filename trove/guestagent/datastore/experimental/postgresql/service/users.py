# Copyright (c) 2013 OpenStack Foundation
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import itertools

from trove.common import cfg
from trove.common.i18n import _
from trove.guestagent.datastore.experimental.postgresql import pgutil
from trove.guestagent.datastore.experimental.postgresql.service.access import (
    PgSqlAccess)
from trove.openstack.common import log as logging

LOG = logging.getLogger(__name__)
CONF = cfg.CONF
IGNORE_USERS_LIST = CONF.get(CONF.datastore_manager).ignore_users


class PgSqlUsers(PgSqlAccess):
    """Mixin implementing the user CRUD API.

    This mixin has a dependency on the PgSqlAccess mixin.
    """

    def create_user(self, context, users):
        """Create users and grant privileges for the specified databases.

        The users parameter is a list of dictionaries in the following form:

            {"_name": "", "_password": "", "_databases": [{"_name": ""}, ...]}
        """
        for user in users:
            LOG.debug(
                "{guest_id}: Creating user {name} with password {password}."
                .format(
                    guest_id=CONF.guest_id,
                    name=user['_name'],
                    password=user['_password'],
                )
            )
            LOG.info(
                _("{guest_id}: Creating user {name} with password {password}.")
                .format(
                    guest_id=CONF.guest_id,
                    name=user['_name'],
                    password="<SANITIZED>",
                )
            )
            pgutil.psql(
                pgutil.UserQuery.create(
                    name=user['_name'],
                    password=user['_password'],
                ),
                timeout=30,
            )
            self.grant_access(
                context,
                user['_name'],
                None,
                [d['_name'] for d in user['_databases']],
            )

    def list_users(
            self,
            context,
            limit=None,
            marker=None,
            include_marker=False,
    ):
        """List all users on the instance along with their access permissions.

        Return value is a list of dictionaries in the following form:

            [{"_name": "", "_password": None, "_host": None,
              "_databases": [{"_name": ""}, ...]}, ...]
        """
        results = pgutil.query(
            pgutil.UserQuery.list(ignore=IGNORE_USERS_LIST),
            timeout=30,
        )
        # Convert results into dictionaries.
        results = (
            {
                '_name': r[0].strip(),
                '_password': None,
                '_host': None,
                '_databases': self.list_access(context, r[0], None),
            }
            for r in results
        )

        # Force __iter__ of generator until marker found.
        if marker is not None:
            try:
                item = results.next()
                while item['_name'] != marker:
                    item = results.next()
            except StopIteration:
                pass

        remainder = None
        if limit is not None:
            remainder = results
            results = itertools.islice(results, limit)

        results = tuple(results)

        next_marker = None
        if remainder is not None:
            try:
                next_marker = remainder.next()
            except StopIteration:
                pass

        return results, next_marker

    def delete_user(self, context, user):
        """Delete the specified user.

        The user parameter is a dictionary in the following form:

            {"_name": ""}
        """
        LOG.info(
            _("{guest_id}: Dropping user {name}.").format(
                guest_id=CONF.guest_id,
                name=user['_name'],
            )
        )
        pgutil.psql(
            pgutil.UserQuery.drop(name=user['_name']),
            timeout=30,
        )

    def get_user(self, context, username, hostname):
        """Return a single user matching the criteria.

        The username and hostname parameter are strings.

        The return value is a dictionary in the following form:

            {"_name": "", "_host": None, "_password": None,
             "_databases": [{"_name": ""}, ...]}

        Where "_databases" is a list of databases the user has access to.
        """
        results = pgutil.query(
            pgutil.UserQuery.get(name=username),
            timeout=30,
        )
        results = tuple(results)
        if len(results) < 1:
            return None

        return {
            "_name": results[0][0],
            "_host": None,
            "_password": None,
            "_databases": self.list_access(context, username, None),
        }

    def change_passwords(self, context, users):
        """Change the passwords of one or more existing users.

        The users parameter is a list of dictionaries in the following form:

            {"name": "", "password": ""}
        """
        for user in users:
            LOG.debug(
                "{guest_id}: Changing password for {user} to {password}."
                .format(
                    guest_id=CONF.guest_id,
                    user=user['name'],
                    password=user['password'],
                )
            )
            LOG.info(
                _("{guest_id}: Changing password for {user} to {password}.")
                .format(
                    guest_id=CONF.guest_id,
                    user=user['name'],
                    password="<SANITIZED>",
                )
            )
            pgutil.psql(
                pgutil.UserQuery.update_password(
                    user=user['name'],
                    password=user['password'],
                ),
                timeout=30,
            )

    def update_attributes(self, context, username, hostname, user_attrs):
        """Change the attributes of one existing user.

        The username and hostname parameters are strings.
        The user_attrs parameter is a dictionary in the following form:

            {"password": "", "name": ""}

        Each key/value pair in user_attrs is optional.
        """
        if user_attrs.get('password') is not None:
            self.change_passwords(
                context,
                (
                    {
                        "name": username,
                        "password": user_attrs['password'],
                    },
                ),
            )

        if user_attrs.get('name') is not None:
            access = self.list_access(context, username, None)
            LOG.info(
                _("{guest_id}: Changing username for {old} to {new}.").format(
                    guest_id=CONF.guest_id,
                    old=username,
                    new=user_attrs['name'],
                )
            )
            pgutil.psql(
                pgutil.psql.UserQuery.update_name(
                    old=username,
                    new=user_attrs['name'],
                ),
                timeout=30,
            )
            # Regrant all previous access after the name change.
            LOG.info(
                _("{guest_id}: Regranting permissions from {old} to {new}.")
                .format(
                    guest_id=CONF.guest_id,
                    old=username,
                    new=user_attrs['name'],
                )
            )
            self.grant_access(
                context,
                username=user_attrs['name'],
                hostname=None,
                databases=(db['_name'] for db in access)
            )
