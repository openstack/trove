# Copyright 2012 OpenStack Foundation
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
from trove.db.sqlalchemy.migrate_repo.schema import drop_tables
from trove.db.sqlalchemy.migrate_repo.schema import Integer
from trove.db.sqlalchemy.migrate_repo.schema import BigInteger
from trove.db.sqlalchemy.migrate_repo.schema import String
from trove.db.sqlalchemy.migrate_repo.schema import Table


meta = MetaData()


datastores = Table(
    'datastores',
    meta,
    Column('id', String(36), primary_key=True, nullable=False),
    Column('name', String(255), unique=True),
    Column('manager', String(255), nullable=False),
    Column('default_version_id', String(36)),
)


datastore_versions = Table(
    'datastore_versions',
    meta,
    Column('id', String(36), primary_key=True, nullable=False),
    Column('datastore_id', String(36), ForeignKey('datastores.id')),
    Column('name', String(255), unique=True),
    Column('image_id', String(36), nullable=False),
    Column('packages', String(511)),
    Column('active', Boolean(), nullable=False),
    UniqueConstraint('datastore_id', 'name', name='ds_versions')
)


def upgrade(migrate_engine):
    meta.bind = migrate_engine
    create_tables([datastores, datastore_versions])
    instances = Table('instances', meta, autoload=True)
    datastore_version_id = Column('datastore_version_id', String(36),
                                  ForeignKey('datastore_versions.id'))
    instances.create_column(datastore_version_id)
    instances.drop_column('service_type')
    # Table 'service_images' is deprecated since this version.
    # Leave it for few releases.
    #drop_tables([service_images])


def downgrade(migrate_engine):
    meta.bind = migrate_engine
    drop_tables([datastores, datastore_versions])
    instances = Table('instances', meta, autoload=True)
    instances.drop_column('datastore_version_id')
    service_type = Column('service_type', String(36))
    instances.create_column(service_type)
    instances.update().values({'service_type': 'mysql'}).execute()
