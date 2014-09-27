# Copyright Tesora, Inc. 2014
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
from sqlalchemy.schema import MetaData
from sqlalchemy.schema import ForeignKey

from trove.db.sqlalchemy.migrate_repo.schema import String
from trove.db.sqlalchemy.migrate_repo.schema import Table
from trove.db.sqlalchemy import utils as db_utils


COLUMN_NAME = 'slave_of_id'


def upgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine
    instances = Table('instances', meta, autoload=True)
    instances.create_column(
        Column(COLUMN_NAME, String(36), ForeignKey('instances.id')),
        nullable=True)


def downgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine
    instances = Table('instances', meta, autoload=True)
    constraint_names = db_utils.get_foreign_key_constraint_names(
        engine=migrate_engine,
        table='instances',
        columns=[COLUMN_NAME],
        ref_table='instances',
        ref_columns=['id'])
    db_utils.drop_foreign_key_constraints(
        constraint_names=constraint_names,
        columns=[instances.c.slave_of_id],
        ref_columns=[instances.c.id])
    instances.drop_column(COLUMN_NAME)
