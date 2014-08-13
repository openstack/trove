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
from sqlalchemy.exc import OperationalError
from sqlalchemy.schema import Column
from sqlalchemy.schema import Index
from sqlalchemy.schema import MetaData

from trove.db.sqlalchemy.migrate_repo.schema import Boolean
from trove.db.sqlalchemy.migrate_repo.schema import create_tables
from trove.db.sqlalchemy.migrate_repo.schema import DateTime
from trove.db.sqlalchemy.migrate_repo.schema import Integer
from trove.db.sqlalchemy.migrate_repo.schema import String
from trove.db.sqlalchemy.migrate_repo.schema import Table
from trove.openstack.common import log as logging

logger = logging.getLogger('trove.db.sqlalchemy.migrate_repo.schema')

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

    # since the downgrade is a no-op, an upgrade after a downgrade will
    # cause an exception because the tables already exist
    # we will catch that case and log an info message
    try:
        create_tables([clusters])

        instances.create_column(Column('cluster_id', String(36),
                                       ForeignKey("clusters.id")))
        instances.create_column(Column('shard_id', String(36)))
        instances.create_column(Column('type', String(64)))

        cluster_id_idx = Index("instances_cluster_id", instances.c.cluster_id)
        cluster_id_idx.create()
    except OperationalError as e:
        logger.info(e)


def downgrade(migrate_engine):
    meta.bind = migrate_engine
    # not dropping the table on a rollback because the cluster
    # assets will still exist
