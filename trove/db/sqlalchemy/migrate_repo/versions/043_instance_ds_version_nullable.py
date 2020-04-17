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

from sqlalchemy.schema import MetaData
from sqlalchemy import text

from trove.db.sqlalchemy.migrate_repo.schema import Table
from trove.db.sqlalchemy import utils as db_utils

meta = MetaData()


def upgrade(migrate_engine):
    meta.bind = migrate_engine

    instance_table = Table('instances', meta, autoload=True)
    datastore_versions_table = Table('datastore_versions',
                                     meta,
                                     autoload=True)

    constraint_names = db_utils.get_foreign_key_constraint_names(
        engine=migrate_engine,
        table='instances',
        columns=[text('datastore_version_id')],
        ref_table='datastore_versions',
        ref_columns=[text('id')])
    db_utils.drop_foreign_key_constraints(
        constraint_names=constraint_names,
        columns=[instance_table.c.datastore_version_id],
        ref_columns=[datastore_versions_table.c.id])

    # Make datastore_version_id nullable so that this field could be set to
    # NULL when instance is deleted.
    instance_table.c.datastore_version_id.alter(nullable=True)

    db_utils.create_foreign_key_constraints(
        constraint_names=constraint_names,
        columns=[instance_table.c.datastore_version_id],
        ref_columns=[datastore_versions_table.c.id])
