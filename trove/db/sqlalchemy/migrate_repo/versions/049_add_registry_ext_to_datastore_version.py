# Copyright 2023 Bizfly Cloud
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

from sqlalchemy.schema import Column
from sqlalchemy.schema import MetaData
from sqlalchemy.sql.expression import select
from sqlalchemy.sql.expression import update
from sqlalchemy import text

from trove.common.constants import REGISTRY_EXT_DEFAULTS
from trove.db.sqlalchemy.migrate_repo.schema import Table
from trove.db.sqlalchemy.migrate_repo.schema import Text


repl_namespaces = {
    "mariadb": "trove.guestagent.strategies.replication.mariadb_gtid",
    "mongodb":
        "trove.guestagent.strategies.replication.experimental.mongo_impl",
    "mysql": "trove.guestagent.strategies.replication.mysql_gtid",
    "percona": "trove.guestagent.strategies.replication.mysql_gtid",
    "postgresql": "trove.guestagent.strategies.replication.postgresql",
    "pxc": "trove.guestagent.strategies.replication.mysql_gtid",
    "redis": "trove.guestagent.strategies.replication.experimental.redis_sync",

}

repl_strategies = {
    "mariadb": "MariaDBGTIDReplication",
    "mongodb": "Replication",
    "mysql": "MysqlGTIDReplication",
    "percona": "MysqlGTIDReplication",
    "postgresql": "PostgresqlReplicationStreaming",
    "pxc": "MysqlGTIDReplication",
    "redis": "RedisSyncReplication",

}


def upgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine

    ds_version = Table('datastore_versions', meta, autoload=True)
    ds_version.create_column(Column('registry_ext', Text(), nullable=True))
    ds_version.create_column(Column('repl_strategy', Text(), nullable=True))

    ds_versions = select(
        columns=[text("id"), text("manager")],
        from_obj=ds_version
    ).execute()
    # Use 'name' value as init 'version' value
    for version in ds_versions:
        registry_ext = REGISTRY_EXT_DEFAULTS.get(version.manager, '')
        repl_strategy = "%(repl_namespace)s.%(repl_strategy)s" % {
            'repl_namespace': repl_namespaces.get(version.manager, ''),
            'repl_strategy': repl_strategies.get(version.manager, '')
        }
        update(
            table=ds_version,
            whereclause=text("id='%s'" % version.id),
            values=dict(
                registry_ext=registry_ext,
                repl_strategy=repl_strategy)
        ).execute()

    ds_version.c.registry_ext.alter(nullable=False)
    ds_version.c.repl_strategy.alter(nullable=False)
