#    Copyright (c) 2014 Rackspace Hosting
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

from sqlalchemy import ForeignKey
from sqlalchemy.schema import Column
from sqlalchemy.schema import MetaData
from sqlalchemy.schema import UniqueConstraint

from trove.db.sqlalchemy.migrate_repo.schema import Boolean
from trove.db.sqlalchemy.migrate_repo.schema import create_tables
from trove.db.sqlalchemy.migrate_repo.schema import String
from trove.db.sqlalchemy.migrate_repo.schema import Table


meta = MetaData()

capabilities = Table(
    'capabilities',
    meta,
    Column('id', String(36), primary_key=True, nullable=False),
    Column('name', String(255), unique=True),
    Column('description', String(255), nullable=False),
    Column('enabled', Boolean())
)


capability_overrides = Table(
    'capability_overrides',
    meta,
    Column('id', String(36), primary_key=True, nullable=False),
    Column('datastore_version_id', String(36),
           ForeignKey('datastore_versions.id')),
    Column('capability_id', String(36), ForeignKey('capabilities.id')),
    Column('enabled', Boolean()),
    UniqueConstraint('datastore_version_id', 'capability_id',
                     name='idx_datastore_capabilities_enabled')
)


def upgrade(migrate_engine):
    meta.bind = migrate_engine
    Table('datastores', meta, autoload=True)
    Table('datastore_versions', meta, autoload=True)
    create_tables([capabilities, capability_overrides])
