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
from trove.common.i18n import _
from trove.common.notification import EndNotification
from trove.common import pagination
from trove.guestagent.datastore.experimental.postgresql import pgutil
from trove.guestagent.db import models

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class PgSqlDatabase(object):

    def __init__(self, *args, **kwargs):
        super(PgSqlDatabase, self).__init__(*args, **kwargs)

    def create_database(self, context, databases):
        """Create the list of specified databases.

        The databases parameter is a list of serialized Postgres databases.
        """
        with EndNotification(context):
            for database in databases:
                self._create_database(
                    context,
                    models.PostgreSQLSchema.deserialize_schema(database))

    def _create_database(self, context, database):
        """Create a database.

        :param database:          Database to be created.
        :type database:           PostgreSQLSchema
        """
        LOG.info(
            _("{guest_id}: Creating database {name}.").format(
                guest_id=CONF.guest_id,
                name=database.name,
            )
        )
        pgutil.psql(
            pgutil.DatabaseQuery.create(
                name=database.name,
                encoding=database.character_set,
                collation=database.collate,
            ),
            timeout=30,
        )

    def delete_database(self, context, database):
        """Delete the specified database.
        """
        with EndNotification(context):
            self._drop_database(
                models.PostgreSQLSchema.deserialize_schema(database))

    def _drop_database(self, database):
        """Drop a given Postgres database.

        :param database:          Database to be dropped.
        :type database:           PostgreSQLSchema
        """
        LOG.info(
            _("{guest_id}: Dropping database {name}.").format(
                guest_id=CONF.guest_id,
                name=database.name,
            )
        )
        pgutil.psql(
            pgutil.DatabaseQuery.drop(name=database.name),
            timeout=30,
        )

    def list_databases(
            self,
            context,
            limit=None,
            marker=None,
            include_marker=False,
    ):
        """List all databases on the instance.
        Return a paginated list of serialized Postgres databases.
        """
        page, next_name = pagination.paginate_object_list(
            self._get_databases(), 'name', limit, marker, include_marker)
        return [db.serialize() for db in page], next_name

    def _get_databases(self):
        """Return all non-system Postgres databases on the instance."""
        results = pgutil.query(
            pgutil.DatabaseQuery.list(ignore=cfg.get_ignored_dbs()),
            timeout=30,
        )
        return [models.PostgreSQLSchema(
            row[0].strip(), character_set=row[1], collate=row[2])
            for row in results]
