# Copyright 2014 OpenStack Foundation
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

from migrate.changeset import UniqueConstraint
from oslo_log import log as logging
from sqlalchemy.exc import OperationalError
from sqlalchemy.schema import MetaData

from trove.db.sqlalchemy.migrate_repo.schema import Table

logger = logging.getLogger('trove.db.sqlalchemy.migrate_repo.schema')


def upgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine
    datastore_versions = Table('datastore_versions', meta, autoload=True)

    # drop the unique index on the name column - unless we are
    # using sqlite - it doesn't support dropping unique constraints
    uc = None
    if migrate_engine.name == "mysql":
        uc = UniqueConstraint('name', table=datastore_versions, name='name')
    elif migrate_engine.name == "postgresql":
        uc = UniqueConstraint('name', table=datastore_versions,
                              name='datastore_versions_name_key')
    if uc:
        try:
            uc.drop()
        except OperationalError as e:
            logger.info(e)


def downgrade(migrate_engine):
    # we aren't going to recreate the index in this case for 2 reasons:
    # 1. this column being unique was a bug in the first place
    # 2. adding a unique index to a column that has duplicates will fail
    pass
