# Copyright 2016 Tesora, Inc.
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
#

from sqlalchemy import ForeignKey
from sqlalchemy.schema import Column
from sqlalchemy.schema import MetaData
from sqlalchemy.schema import UniqueConstraint

from trove.db.sqlalchemy.migrate_repo.schema import Boolean
from trove.db.sqlalchemy.migrate_repo.schema import create_tables
from trove.db.sqlalchemy.migrate_repo.schema import DateTime
from trove.db.sqlalchemy.migrate_repo.schema import String
from trove.db.sqlalchemy.migrate_repo.schema import Table
from trove.db.sqlalchemy.migrate_repo.schema import Text


meta = MetaData()

modules = Table(
    'modules',
    meta,
    Column('id', String(length=64), primary_key=True, nullable=False),
    Column('name', String(length=255), nullable=False),
    Column('type', String(length=255), nullable=False),
    Column('contents', Text(length=16777215), nullable=False),
    Column('description', String(length=255)),
    Column('tenant_id', String(length=64), nullable=True),
    Column('datastore_id', String(length=64), nullable=True),
    Column('datastore_version_id', String(length=64), nullable=True),
    Column('auto_apply', Boolean(), default=0, nullable=False),
    Column('visible', Boolean(), default=1, nullable=False),
    Column('live_update', Boolean(), default=0, nullable=False),
    Column('md5', String(length=32), nullable=False),
    Column('created', DateTime(), nullable=False),
    Column('updated', DateTime(), nullable=False),
    Column('deleted', Boolean(), default=0, nullable=False),
    Column('deleted_at', DateTime()),
    UniqueConstraint(
        'type', 'tenant_id', 'datastore_id', 'datastore_version_id',
        'name', 'deleted_at',
        name='UQ_type_tenant_datastore_datastore_version_name'),
)

instance_modules = Table(
    'instance_modules',
    meta,
    Column('id', String(length=64), primary_key=True, nullable=False),
    Column('instance_id', String(length=64),
           ForeignKey('instances.id', ondelete="CASCADE",
                      onupdate="CASCADE"), nullable=False),
    Column('module_id', String(length=64),
           ForeignKey('modules.id', ondelete="CASCADE",
                      onupdate="CASCADE"), nullable=False),
    Column('md5', String(length=32), nullable=False),
    Column('created', DateTime(), nullable=False),
    Column('updated', DateTime(), nullable=False),
    Column('deleted', Boolean(), default=0, nullable=False),
    Column('deleted_at', DateTime()),
)


def upgrade(migrate_engine):
    meta.bind = migrate_engine
    Table('instances', meta, autoload=True)
    create_tables([modules, instance_modules])
