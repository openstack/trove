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

from trove.db.sqlalchemy.migrate_repo.schema import Boolean
from trove.db.sqlalchemy.migrate_repo.schema import create_tables
from trove.db.sqlalchemy.migrate_repo.schema import DateTime
from trove.db.sqlalchemy.migrate_repo.schema import drop_tables
from trove.db.sqlalchemy.migrate_repo.schema import String
from trove.db.sqlalchemy.migrate_repo.schema import Table
from trove.db.sqlalchemy.migrate_repo.schema import Text


meta = MetaData()

instance_faults = Table(
    'instance_faults',
    meta,
    Column('id', String(length=64), primary_key=True, nullable=False),
    Column('instance_id', String(length=64),
           ForeignKey('instances.id', ondelete="CASCADE",
                      onupdate="CASCADE"), nullable=False),
    Column('message', String(length=255), nullable=False),
    Column('details', Text(length=65535), nullable=False),
    Column('created', DateTime(), nullable=False),
    Column('updated', DateTime(), nullable=False),
    Column('deleted', Boolean(), default=0, nullable=False),
    Column('deleted_at', DateTime()),
)


def upgrade(migrate_engine):
    meta.bind = migrate_engine
    Table('instances', meta, autoload=True)
    create_tables([instance_faults])


def downgrade(migrate_engine):
    meta.bind = migrate_engine
    drop_tables([instance_faults])
