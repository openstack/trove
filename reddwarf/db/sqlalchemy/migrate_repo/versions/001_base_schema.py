# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack LLC.
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

from reddwarf.db.sqlalchemy.migrate_repo.schema import Boolean
from reddwarf.db.sqlalchemy.migrate_repo.schema import create_tables
from reddwarf.db.sqlalchemy.migrate_repo.schema import DateTime
from reddwarf.db.sqlalchemy.migrate_repo.schema import drop_tables
from reddwarf.db.sqlalchemy.migrate_repo.schema import Integer
from reddwarf.db.sqlalchemy.migrate_repo.schema import BigInteger
from reddwarf.db.sqlalchemy.migrate_repo.schema import String
from reddwarf.db.sqlalchemy.migrate_repo.schema import Table


meta = MetaData()

instances = Table(
    'instances',
    meta,
    Column('id', String(36), primary_key=True, nullable=False),
    Column('created', DateTime()),
    Column('updated', DateTime()),
    Column('name', String(255)),
    Column('hostname', String(255)),
    Column('compute_instance_id', String(36)),
    Column('task_id', Integer()),
    Column('task_description', String(32)),
    Column('task_start_time', DateTime()),
    Column('volume_id', String(36)))


def upgrade(migrate_engine):
    meta.bind = migrate_engine
    create_tables([instances])


def downgrade(migrate_engine):
    meta.bind = migrate_engine
    drop_tables([instances])
