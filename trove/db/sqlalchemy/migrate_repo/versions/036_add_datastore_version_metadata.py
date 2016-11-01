# Copyright 2015 Rackspace
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

from sqlalchemy import ForeignKey
from sqlalchemy.schema import Column
from sqlalchemy.schema import MetaData
from sqlalchemy.schema import UniqueConstraint

from trove.db.sqlalchemy.migrate_repo.schema import Boolean
from trove.db.sqlalchemy.migrate_repo.schema import create_tables
from trove.db.sqlalchemy.migrate_repo.schema import DateTime
from trove.db.sqlalchemy.migrate_repo.schema import String
from trove.db.sqlalchemy.migrate_repo.schema import Table

meta = MetaData()

datastore_version_metadata = Table(
    'datastore_version_metadata',
    meta,
    Column('id', String(36), primary_key=True, nullable=False),
    Column(
        'datastore_version_id',
        String(36),
        ForeignKey('datastore_versions.id', ondelete='CASCADE'),
    ),
    Column('key', String(128), nullable=False),
    Column('value', String(128)),
    Column('created', DateTime(), nullable=False),
    Column('deleted', Boolean(), nullable=False, default=False),
    Column('deleted_at', DateTime()),
    Column('updated_at', DateTime()),
    UniqueConstraint(
        'datastore_version_id', 'key', 'value',
        name='UQ_datastore_version_metadata_datastore_version_id_key_value')
)


def upgrade(migrate_engine):
    meta.bind = migrate_engine
    # Load the datastore_versions table into the session.
    # creates datastore_version_metadata table
    Table('datastore_versions', meta, autoload=True)
    create_tables([datastore_version_metadata])
