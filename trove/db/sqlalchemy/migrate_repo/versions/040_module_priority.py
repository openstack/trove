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

from sqlalchemy.schema import Column
from sqlalchemy.schema import MetaData
from sqlalchemy.sql.expression import update

from trove.db.sqlalchemy.migrate_repo.schema import Boolean
from trove.db.sqlalchemy.migrate_repo.schema import Integer
from trove.db.sqlalchemy.migrate_repo.schema import Table
from trove.db.sqlalchemy.migrate_repo.schema import Text


COLUMN_NAME_1 = 'priority_apply'
COLUMN_NAME_2 = 'apply_order'
COLUMN_NAME_3 = 'is_admin'


def upgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine
    modules = Table('modules', meta, autoload=True)
    is_nullable = True if migrate_engine.name == "sqlite" else False
    column = Column(COLUMN_NAME_1, Boolean(), nullable=is_nullable, default=0)
    modules.create_column(column)
    column = Column(COLUMN_NAME_2, Integer(), nullable=is_nullable, default=5)
    modules.create_column(column)
    column = Column(COLUMN_NAME_3, Boolean(), nullable=is_nullable, default=0)
    modules.create_column(column)
    modules.c.contents.alter(Text(length=4294967295))
    # mark all non-visible, auto-apply and all-tenant modules as is_admin
    update(table=modules,
           values=dict(is_admin=1),
           whereclause="visible=0 or auto_apply=1 or tenant_id is null"
           ).execute()
