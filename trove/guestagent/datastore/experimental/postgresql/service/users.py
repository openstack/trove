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

from oslo_log import log as logging

from trove.common import cfg
from trove.common import exception
from trove.common.i18n import _
from trove.common.notification import EndNotification
from trove.common import utils
from trove.guestagent.common import guestagent_utils
from trove.guestagent.datastore.experimental.postgresql import pgutil
from trove.guestagent.datastore.experimental.postgresql.service.access import (
    PgSqlAccess)
from trove.guestagent.db import models
from trove.guestagent.db.models import PostgreSQLSchema

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class PgSqlUsers(PgSqlAccess):
    """Mixin implementing the user CRUD API.

    This mixin has a dependency on the PgSqlAccess mixin.
    """

    @property
    def ADMIN_USER(self):
        """Trove's administrative user."""
        return 'os_admin'

    @property
    def ADMIN_OPTIONS(self):
        """Default set of options of an administrative account."""
        return [
            'SUPERUSER',
            'CREATEDB',
            'CREATEROLE',
            'INHERIT',
            'REPLICATION',
            'LOGIN']

    def _create_admin_user(self, context, databases=None):
        """Create an administrative user for Trove.
        Force password encryption.
        """
        password = utils.generate_random_password()
        os_admin = models.PostgreSQLUser(self.ADMIN_USER, password)
        if databases:
            os_admin.databases.extend([db.serialize() for db in databases])
        self._create_user(context, os_admin, True, *self.ADMIN_OPTIONS)

    def create_user(self, context, users):
        """Create users and grant privileges for the specified databases.

        The users parameter is a list of serialized Postgres users.
        """
        with EndNotification(context):
            for user in users:
                self._create_user(
                    context,
                    models.PostgreSQLUser.deserialize_user(user), None)

    def _create_user(self, context, user, encrypt_password=None, *options):
        """Create a user and grant privileges for the specified databases.

        :param user:              User to be created.
        :type user:               PostgreSQLUser

        :param encrypt_password:  Store passwords encrypted if True.
                                  Fallback to configured default
                                  behavior if None.
        :type encrypt_password:   boolean

        :param options:           Other user options.
        :type options:            list
        """
        LOG.info(
            _("{guest_id}: Creating user {user} {with_clause}.")
            .format(
                guest_id=CONF.guest_id,
                user=user.name,
                with_clause=pgutil.UserQuery._build_with_clause(
                    '<SANITIZED>',
                    encrypt_password,
                    *options
                ),
            )
        )
        pgutil.psql(
            pgutil.UserQuery.create(
                user.name,
                user.password,
                encrypt_password,
                *options
            ),
            timeout=30,
        )
        self._grant_access(
            context, user.name,
            [PostgreSQLSchema.deserialize_schema(db) for db in user.databases])

    def _grant_access(self, context, username, databases):
        self.grant_access(
            context,
            username,
            None,
            [db.name for db in databases],
        )

    def list_users(
            self,
            context,
            limit=None,
            marker=None,
            include_marker=False,
    ):
        """List all users on the instance along with their access permissions.
        Return a paginated list of serialized Postgres users.
        """
        return guestagent_utils.serialize_list(
            self._get_users(context),
            limit=limit, marker=marker, include_marker=include_marker)

    def _get_users(self, context):
        """Return all non-system Postgres users on the instance."""
        results = pgutil.query(
            pgutil.UserQuery.list(ignore=cfg.get_ignored_users()),
            timeout=30,
        )
        return [self._build_user(context, row[0].strip()) for row in results]

    def _build_user(self, context, username):
        """Build a model representation of a Postgres user.
        Include all databases it has access to.
        """
        user = models.PostgreSQLUser(username)
        dbs = self.list_access(context, username, None)
        for d in dbs:
            user.databases.append(d)
        return user

    def delete_user(self, context, user):
        """Delete the specified user.
        """
        with EndNotification(context):
            self._drop_user(models.PostgreSQLUser.deserialize_user(user))

    def _drop_user(self, user):
        """Drop a given Postgres user.

        :param user:              User to be dropped.
        :type user:               PostgreSQLUser
        """
        LOG.info(
            _("{guest_id}: Dropping user {name}.").format(
                guest_id=CONF.guest_id,
                name=user.name,
            )
        )
        pgutil.psql(
            pgutil.UserQuery.drop(name=user.name),
            timeout=30,
        )

    def get_user(self, context, username, hostname):
        """Return a serialized representation of a user with a given name.
        """
        user = self._find_user(context, username)
        return user.serialize() if user is not None else None

    def _find_user(self, context, username):
        """Lookup a user with a given username.
        Return a new Postgres user instance or raise if no match is found.
        """
        results = pgutil.query(
            pgutil.UserQuery.get(name=username),
            timeout=30,
        )

        if results:
            return self._build_user(context, username)

        return None

    def user_exists(self, username):
        """Return whether a given user exists on the instance."""
        results = pgutil.query(
            pgutil.UserQuery.get(name=username),
            timeout=30,
        )

        return bool(results)

    def change_passwords(self, context, users):
        """Change the passwords of one or more existing users.
        The users parameter is a list of serialized Postgres users.
        """
        with EndNotification(context):
            for user in users:
                self.alter_user(
                    context,
                    models.PostgreSQLUser.deserialize_user(user), None)

    def alter_user(self, context, user, encrypt_password=None, *options):
        """Change the password and options of an existing users.

        :param user:              User to be altered.
        :type user:               PostgreSQLUser

        :param encrypt_password:  Store passwords encrypted if True.
                                  Fallback to configured default
                                  behavior if None.
        :type encrypt_password:   boolean

        :param options:           Other user options.
        :type options:            list
        """
        LOG.info(
            _("{guest_id}: Altering user {user} {with_clause}.")
            .format(
                guest_id=CONF.guest_id,
                user=user.name,
                with_clause=pgutil.UserQuery._build_with_clause(
                    '<SANITIZED>',
                    encrypt_password,
                    *options
                ),
            )
        )
        pgutil.psql(
            pgutil.UserQuery.alter_user(
                user.name,
                user.password,
                encrypt_password,
                *options),
            timeout=30,
        )

    def update_attributes(self, context, username, hostname, user_attrs):
        """Change the attributes of one existing user.

        The username and hostname parameters are strings.
        The user_attrs parameter is a dictionary in the following form:

            {"password": "", "name": ""}

        Each key/value pair in user_attrs is optional.
        """
        with EndNotification(context):
            user = self._build_user(context, username)
            new_username = user_attrs.get('name')
            new_password = user_attrs.get('password')

            if new_username is not None:
                self._rename_user(context, user, new_username)
                # Make sure we can retrieve the renamed user.
                user = self._find_user(context, new_username)
                if user is None:
                    raise exception.TroveError(_(
                        "Renamed user %s could not be found on the instance.")
                        % new_username)

            if new_password is not None:
                user.password = new_password
                self.alter_user(context, user)

    def _rename_user(self, context, user, new_username):
        """Rename a given Postgres user and transfer all access to the
        new name.

        :param user:              User to be renamed.
        :type user:               PostgreSQLUser
        """
        LOG.info(
            _("{guest_id}: Changing username for {old} to {new}.").format(
                guest_id=CONF.guest_id,
                old=user.name,
                new=new_username,
            )
        )
        # PostgreSQL handles the permission transfer itself.
        pgutil.psql(
            pgutil.UserQuery.update_name(
                old=user.name,
                new=new_username,
            ),
            timeout=30,
        )
