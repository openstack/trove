# Copyright 2013 OpenStack Foundation
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

from trove.db.sqlalchemy.migrate_repo.schema import String
from trove.db.sqlalchemy.migrate_repo.schema import Table
from trove.db.sqlalchemy import utils as db_utils


def upgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine
    backups = Table('backups', meta, autoload=True)
    Table('datastore_versions', meta, autoload=True)
    datastore_version_id = Column('datastore_version_id', String(36),
                                  ForeignKey('datastore_versions.id'))
    backups.create_column(datastore_version_id)


def downgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine
    backups = Table('backups', meta, autoload=True)
    datastore_versions = Table('datastore_versions', meta, autoload=True)
    constraint_names = db_utils.get_foreign_key_constraint_names(
        engine=migrate_engine,
        table='backups',
        columns=['datastore_version_id'],
        ref_table='datastore_versions',
        ref_columns=['id'])
    db_utils.drop_foreign_key_constraints(
        constraint_names=constraint_names,
        columns=[backups.c.datastore_version_id],
        ref_columns=[datastore_versions.c.id])
    backups.drop_column('datastore_version_id')
