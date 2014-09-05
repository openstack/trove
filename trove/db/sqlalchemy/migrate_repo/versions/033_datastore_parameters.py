# Copyright 2014 Rackspace
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

from trove.db.sqlalchemy.migrate_repo.schema import create_tables
from trove.db.sqlalchemy.migrate_repo.schema import drop_tables
from trove.db.sqlalchemy.migrate_repo.schema import DateTime
from trove.db.sqlalchemy.migrate_repo.schema import Boolean
from trove.db.sqlalchemy.migrate_repo.schema import String
from trove.db.sqlalchemy.migrate_repo.schema import Table


meta = MetaData()


datastore_configuration_parameters = Table(
    'datastore_configuration_parameters',
    meta,
    Column('id', String(36), primary_key=True, nullable=False),
    Column('name', String(128), primary_key=True, nullable=False),
    Column('datastore_version_id', String(36),
           ForeignKey("datastore_versions.id"),
           primary_key=True, nullable=False),
    Column('restart_required', Boolean(), nullable=False, default=False),
    Column('max_size', String(40)),
    Column('min_size', String(40)),
    Column('data_type', String(128), nullable=False),
    Column('deleted', Boolean()),
    Column('deleted_at', DateTime()),
    UniqueConstraint(
        'datastore_version_id', 'name',
        name='UQ_datastore_configuration_parameters_datastore_version_id_name')
)


def upgrade(migrate_engine):
    meta.bind = migrate_engine
    Table('datastore_versions', meta, autoload=True)
    create_tables([datastore_configuration_parameters])


def downgrade(migrate_engine):
    meta.bind = migrate_engine
    drop_tables([datastore_configuration_parameters])
