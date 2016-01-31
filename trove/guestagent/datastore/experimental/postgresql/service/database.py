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

from oslo_log import log as logging

from trove.common import cfg
from trove.common.i18n import _
from trove.guestagent.datastore.experimental.postgresql import pgutil

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class PgSqlDatabase(object):

    def __init__(self, *args, **kwargs):
        super(PgSqlDatabase, self).__init__(*args, **kwargs)

    def create_database(self, context, databases):
        """Create the list of specified databases.

        The databases parameter is a list of dictionaries in the following
        form:

            {"_name": "", "_character_set": "", "_collate": ""}

        Encoding and collation values are validated in
        trove.guestagent.db.models.
        """
        for database in databases:
            encoding = database.get('_character_set')
            collate = database.get('_collate')
            LOG.info(
                _("{guest_id}: Creating database {name}.").format(
                    guest_id=CONF.guest_id,
                    name=database['_name'],
                )
            )
            pgutil.psql(
                pgutil.DatabaseQuery.create(
                    name=database['_name'],
                    encoding=encoding,
                    collation=collate,
                ),
                timeout=30,
            )

    def delete_database(self, context, database):
        """Delete the specified database.

        The database parameter is a dictionary in the following form:

            {"_name": ""}
        """
        LOG.info(
            _("{guest_id}: Dropping database {name}.").format(
                guest_id=CONF.guest_id,
                name=database['_name'],
            )
        )
        pgutil.psql(
            pgutil.DatabaseQuery.drop(name=database['_name']),
            timeout=30,
        )

    def list_databases(
            self,
            context,
            limit=None,
            marker=None,
            include_marker=False,
    ):
        """List databases created on this instance.

        Return value is a list of dictionaries in the following form:

            [{"_name": "", "_character_set": "", "_collate": ""}, ...]
        """
        results = pgutil.query(
            pgutil.DatabaseQuery.list(ignore=cfg.get_ignored_dbs(
                manager='postgresql')),
            timeout=30,
        )
        # Convert results to dictionaries.
        results = (
            {'_name': r[0].strip(), '_character_set': r[1], '_collate': r[2]}
            for r in results
        )
        # Force __iter__ of generator until marker found.
        if marker is not None:
            try:
                item = next(results)
                while item['_name'] != marker:
                    item = next(results)
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
                next_marker = next(remainder)
            except StopIteration:
                pass

        return results, next_marker
