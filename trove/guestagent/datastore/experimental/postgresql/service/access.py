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
from trove.guestagent.datastore.experimental.postgresql import pgutil
from trove.guestagent.db import models

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class PgSqlAccess(object):
    """Mixin implementing the user-access API calls."""

    def grant_access(self, context, username, hostname, databases):
        """Give a user permission to use a given database.

        The username and hostname parameters are strings.
        The databases parameter is a list of strings representing the names of
        the databases to grant permission on.
        """
        for database in databases:
            LOG.info(
                _("{guest_id}: Granting user ({user}) access to database "
                    "({database}).").format(
                        guest_id=CONF.guest_id,
                        user=username,
                        database=database,)
            )
            pgutil.psql(
                pgutil.AccessQuery.grant(
                    user=username,
                    database=database,
                ),
                timeout=30,
            )

    def revoke_access(self, context, username, hostname, database):
        """Revoke a user's permission to use a given database.

        The username and hostname parameters are strings.
        The database parameter is a string representing the name of the
        database.
        """
        LOG.info(
            _("{guest_id}: Revoking user ({user}) access to database"
                "({database}).").format(
                    guest_id=CONF.guest_id,
                    user=username,
                    database=database,)
        )
        pgutil.psql(
            pgutil.AccessQuery.revoke(
                user=username,
                database=database,
            ),
            timeout=30,
        )

    def list_access(self, context, username, hostname):
        """List database for which the given user as access.
        Return a list of serialized Postgres databases.
        """

        if self.user_exists(username):
            return [db.serialize() for db in self._get_databases_for(username)]

        raise exception.UserNotFound(username)

    def _get_databases_for(self, username):
        """Return all Postgres databases accessible by a given user."""
        results = pgutil.query(
            pgutil.AccessQuery.list(user=username),
            timeout=30,
        )
        return [models.PostgreSQLSchema(
            row[0].strip(), character_set=row[1], collate=row[2])
            for row in results]
