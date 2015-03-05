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

import uuid
from trove.common import cfg
from trove.guestagent.datastore.experimental.postgresql import pgutil
from trove.openstack.common import log as logging

LOG = logging.getLogger(__name__)
CONF = cfg.CONF
IGNORE_USERS_LIST = CONF.get(CONF.datastore_manager).ignore_users


class PgSqlRoot(object):
    """Mixin that provides the root-enable API."""

    def is_root_enabled(self, context):
        """Return True if there is a superuser account enabled.

        This ignores the built-in superuser of postgres and the potential
        system administration superuser of os_admin.
        """
        results = pgutil.query(
            pgutil.UserQuery.list_root(ignore=IGNORE_USERS_LIST),
            timeout=30,
        )
        # Reduce iter of iters to iter of single values.
        results = (r[0] for r in results)
        return len(tuple(results)) > 0

    def enable_root(self, context, root_password=None):
        """Create a root user or reset the root user password.

        The default superuser for PgSql is postgres, but that account is used
        for administration. Instead, this method will create a new user called
        root that also has superuser privileges.

        If no root_password is given then a random UUID will be used for the
        superuser password.

        Return value is a dictionary in the following form:

            {"_name": "root", "_password": ""}
        """
        user = {
            "_name": "root",
            "_password": root_password or str(uuid.uuid4()),
        }
        LOG.debug(
            "{guest_id}: Creating root user with password {password}.".format(
                guest_id=CONF.guest_id,
                password=user['_password'],
            )
        )
        query = pgutil.UserQuery.create(
            name=user['_name'],
            password=user['_password'],
        )
        if self.is_root_enabled(context):
            query = pgutil.UserQuery.update_password(
                name=user['_name'],
                password=user['_password'],
            )
        pgutil.psql(query, timeout=30)
        return user
