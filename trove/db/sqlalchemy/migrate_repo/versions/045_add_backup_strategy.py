# Copyright 2020 Catalyst Cloud
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

from sqlalchemy.schema import Column
from sqlalchemy.schema import Index
from sqlalchemy.schema import MetaData
from sqlalchemy.schema import UniqueConstraint

from trove.db.sqlalchemy.migrate_repo.schema import create_tables
from trove.db.sqlalchemy.migrate_repo.schema import DateTime
from trove.db.sqlalchemy.migrate_repo.schema import String
from trove.db.sqlalchemy.migrate_repo.schema import Table

meta = MetaData()

backup_strategy = Table(
    'backup_strategy',
    meta,
    Column('id', String(36), primary_key=True, nullable=False),
    Column('tenant_id', String(36), nullable=False),
    Column('instance_id', String(36), nullable=False, default=''),
    Column('backend', String(255), nullable=False),
    Column('swift_container', String(255), nullable=True),
    Column('created', DateTime()),
    UniqueConstraint(
        'tenant_id', 'instance_id',
        name='UQ_backup_strategy_tenant_id_instance_id'),
    Index("backup_strategy_tenant_id_instance_id", "tenant_id", "instance_id"),
)


def upgrade(migrate_engine):
    meta.bind = migrate_engine
    create_tables([backup_strategy])
