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

from trove.guestagent.datastore.experimental.postgresql import pgutil
from trove.guestagent.datastore.experimental.postgresql.service.users import (
    PgSqlUsers)
from trove.guestagent.db import models


class PgSqlRoot(PgSqlUsers):
    """Mixin that provides the root-enable API."""

    def __init__(self, *args, **kwargs):
        super(PgSqlRoot, self).__init__(*args, **kwargs)

    def is_root_enabled(self, context):
        """Return True if there is a superuser account enabled.
        """
        results = pgutil.query(
            pgutil.UserQuery.list_root(),
            timeout=30,
        )

        # There should be only one superuser (Trove's administrative account).
        return len(results) > 1 or (results[0][0] != self.ADMIN_USER)

# TODO(pmalik): For future use by 'root-disable'.
#     def disable_root(self, context):
#         """Generate a new random password for the public superuser account.
#         Do not disable its access rights. Once enabled the account should
#         stay that way.
#         """
#         self.enable_root(context)

    def enable_root(self, context, root_password=None):
        """Create a superuser user or reset the superuser password.

        The default PostgreSQL administration account is 'postgres'.
        This account always exists and cannot be removed.
        Its attributes and access can however be altered.

        Clients can connect from the localhost or remotely via TCP/IP:

        Local clients (e.g. psql) can connect from a preset *system* account
        called 'postgres'.
        This system account has no password and is *locked* by default,
        so that it can be used by *local* users only.
        It should *never* be enabled (or its password set)!!!
        That would just open up a new attack vector on the system account.

        Remote clients should use a build-in *database* account of the same
        name. It's password can be changed using the "ALTER USER" statement.

        Access to this account is disabled by Trove exposed only once the
        superuser access is requested.
        Trove itself creates its own administrative account.

            {"_name": "postgres", "_password": "<secret>"}
        """
        user = models.PostgreSQLRootUser(password=root_password)
        query = pgutil.UserQuery.alter_user(
            user.name,
            user.password,
            None,
            *self.ADMIN_OPTIONS
        )
        pgutil.psql(query, timeout=30)
        return user.serialize()

    def disable_root(self, context):
        """Generate a new random password for the public superuser account.
        Do not disable its access rights. Once enabled the account should
        stay that way.
        """
        self.enable_root(context)

    def enable_root_with_password(self, context, root_password=None):
        return self.enable_root(context, root_password)
