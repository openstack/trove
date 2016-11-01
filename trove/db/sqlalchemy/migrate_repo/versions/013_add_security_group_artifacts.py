# Copyright 2011 OpenStack Foundation
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

from trove.db.sqlalchemy.migrate_repo.schema import Boolean
from trove.db.sqlalchemy.migrate_repo.schema import create_tables
from trove.db.sqlalchemy.migrate_repo.schema import DateTime
from trove.db.sqlalchemy.migrate_repo.schema import Integer
from trove.db.sqlalchemy.migrate_repo.schema import String
from trove.db.sqlalchemy.migrate_repo.schema import Table


meta = MetaData()

security_groups = Table(
    'security_groups',
    meta,
    Column('id', String(length=36), primary_key=True, nullable=False),
    Column('name', String(length=255)),
    Column('description', String(length=255)),
    Column('user', String(length=255)),
    Column('tenant_id', String(length=255)),
    Column('created', DateTime()),
    Column('updated', DateTime()),
    Column('deleted', Boolean(), default=0),
    Column('deleted_at', DateTime()),
)

security_group_instance_associations = Table(
    'security_group_instance_associations',
    meta,
    Column('id', String(length=36), primary_key=True, nullable=False),
    Column('security_group_id', String(length=36),
           ForeignKey('security_groups.id', ondelete="CASCADE",
                      onupdate="CASCADE")),
    Column('instance_id', String(length=36),
           ForeignKey('instances.id', ondelete="CASCADE",
                      onupdate="CASCADE")),
    Column('created', DateTime()),
    Column('updated', DateTime()),
    Column('deleted', Boolean(), default=0),
    Column('deleted_at', DateTime()),
)

security_group_rules = Table(
    'security_group_rules',
    meta,
    Column('id', String(length=36), primary_key=True, nullable=False),
    Column('group_id', String(length=36),
           ForeignKey('security_groups.id', ondelete="CASCADE",
                      onupdate="CASCADE")),
    Column('parent_group_id', String(length=36),
           ForeignKey('security_groups.id', ondelete="CASCADE",
                      onupdate="CASCADE")),
    Column('protocol', String(length=255)),
    Column('from_port', Integer()),
    Column('to_port', Integer()),
    Column('cidr', String(length=255)),
    Column('created', DateTime()),
    Column('updated', DateTime()),
    Column('deleted', Boolean(), default=0),
    Column('deleted_at', DateTime()),
)


def upgrade(migrate_engine):
    meta.bind = migrate_engine
    Table(
        'instances',
        meta,
        autoload=True,
    )
    create_tables([security_groups, security_group_rules,
                   security_group_instance_associations])
