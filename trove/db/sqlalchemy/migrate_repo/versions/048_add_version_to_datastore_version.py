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

from migrate.changeset.constraint import UniqueConstraint
from sqlalchemy import text
from sqlalchemy.schema import Column
from sqlalchemy.schema import MetaData
from sqlalchemy.sql.expression import select
from sqlalchemy.sql.expression import update

from trove.db.sqlalchemy import utils as db_utils
from trove.db.sqlalchemy.migrate_repo.schema import String
from trove.db.sqlalchemy.migrate_repo.schema import Table


def upgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine

    ds_table = Table('datastores', meta, autoload=True)
    ds_version_table = Table('datastore_versions', meta, autoload=True)
    ds_version_table.create_column(
        Column('version', String(255), nullable=True))

    ds_versions = select(
        columns=[text("id"), text("name")],
        from_obj=ds_version_table
    ).execute()

    # Use 'name' value as init 'version' value
    for version in ds_versions:
        update(
            table=ds_version_table,
            whereclause=text("id='%s'" % version.id),
            values=dict(version=version.name)
        ).execute()

    # Change unique constraint, need to drop the foreign key first and add back
    # later
    constraint_names = db_utils.get_foreign_key_constraint_names(
        engine=migrate_engine,
        table='datastore_versions',
        columns=['datastore_id'],
        ref_table='datastores',
        ref_columns=['id'])
    db_utils.drop_foreign_key_constraints(
        constraint_names=constraint_names,
        columns=[ds_version_table.c.datastore_id],
        ref_columns=[ds_table.c.id])

    UniqueConstraint('datastore_id', 'name', name='ds_versions',
                     table=ds_version_table).drop()
    UniqueConstraint('datastore_id', 'name', 'version', name='ds_versions',
                     table=ds_version_table).create()

    db_utils.create_foreign_key_constraints(
        constraint_names=constraint_names,
        columns=[ds_version_table.c.datastore_id],
        ref_columns=[ds_table.c.id])
