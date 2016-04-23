# Copyright 2014 eBay Software Foundation
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
from sqlalchemy.schema import Index
from sqlalchemy.schema import MetaData

from trove.db.sqlalchemy.migrate_repo.schema import Boolean
from trove.db.sqlalchemy.migrate_repo.schema import create_tables
from trove.db.sqlalchemy.migrate_repo.schema import DateTime
from trove.db.sqlalchemy.migrate_repo.schema import drop_tables
from trove.db.sqlalchemy.migrate_repo.schema import Integer
from trove.db.sqlalchemy.migrate_repo.schema import String
from trove.db.sqlalchemy.migrate_repo.schema import Table
from trove.db.sqlalchemy import utils as db_utils


meta = MetaData()

clusters = Table(
    'clusters',
    meta,
    Column('id', String(36), primary_key=True, nullable=False),
    Column('created', DateTime(), nullable=False),
    Column('updated', DateTime(), nullable=False),
    Column('name', String(255), nullable=False),
    Column('task_id', Integer(), nullable=False),
    Column('tenant_id', String(36), nullable=False),
    Column("datastore_version_id", String(36),
           ForeignKey('datastore_versions.id'), nullable=False),
    Column('deleted', Boolean()),
    Column('deleted_at', DateTime()),
    Index("clusters_tenant_id", "tenant_id"),
    Index("clusters_deleted", "deleted"),)


def upgrade(migrate_engine):
    meta.bind = migrate_engine
    Table('datastores', meta, autoload=True)
    Table('datastore_versions', meta, autoload=True)
    instances = Table('instances', meta, autoload=True)
    create_tables([clusters])
    instances.create_column(Column('cluster_id', String(36),
                                   ForeignKey("clusters.id")))
    instances.create_column(Column('shard_id', String(36)))
    instances.create_column(Column('type', String(64)))
    cluster_id_idx = Index("instances_cluster_id", instances.c.cluster_id)
    cluster_id_idx.create()


def downgrade(migrate_engine):
    meta.bind = migrate_engine

    datastore_versions = Table('datastore_versions', meta, autoload=True)
    constraint_names = db_utils.get_foreign_key_constraint_names(
        engine=migrate_engine,
        table='clusters',
        columns=['datastore_version_id'],
        ref_table='datastore_versions',
        ref_columns=['id'])
    db_utils.drop_foreign_key_constraints(
        constraint_names=constraint_names,
        columns=[clusters.c.datastore_version_id],
        ref_columns=[datastore_versions.c.id])

    instances = Table('instances', meta, autoload=True)
    constraint_names = db_utils.get_foreign_key_constraint_names(
        engine=migrate_engine,
        table='instances',
        columns=['cluster_id'],
        ref_table='clusters',
        ref_columns=['id'])
    db_utils.drop_foreign_key_constraints(
        constraint_names=constraint_names,
        columns=[instances.c.cluster_id],
        ref_columns=[clusters.c.id])

    instances.drop_column('cluster_id')
    instances.drop_column('shard_id')
    instances.drop_column('type')

    drop_tables([clusters])
