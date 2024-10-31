# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Add Datastore Version Registry Extension


Revision ID: 5c68b4fb3cd1
Revises: 906cffda7b29
Create Date: 2024-04-30 13:59:10.690895
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy.sql import table, column
from sqlalchemy import text, Column
from sqlalchemy import String, Text

from trove.common.constants import REGISTRY_EXT_DEFAULTS

# revision identifiers, used by Alembic.
revision: str = '5c68b4fb3cd1'
down_revision: Union[str, None] = '906cffda7b29'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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


def upgrade() -> None:
    bind = op.get_bind()

    # 1. select id and manager from datastore_versions table
    connection = op.get_bind()
    # add columns before proceeding
    op.add_column("datastore_versions", Column('registry_ext', Text(),
                                               nullable=True))
    op.add_column("datastore_versions", Column('repl_strategy', Text(),
                                               nullable=True))
    for dsv_id, dsv_manager in connection.execute(
            text("select id, manager from datastore_versions")):
        registry_ext = REGISTRY_EXT_DEFAULTS.get(dsv_manager, '')
        repl_strategy = "%(repl_namespace)s.%(repl_strategy)s" % {
            'repl_namespace': repl_namespaces.get(dsv_manager, ''),
            'repl_strategy': repl_strategies.get(dsv_manager, '')
        }
        ds_versions_table = table(
            "datastore_versions",
            column("id", String),
            column("registry_ext", String),
            column("repl_strategy", String))
        op.execute(
            ds_versions_table.update()
            .where(ds_versions_table.c.id == dsv_id)
            .values({"registry_ext": registry_ext,
                     "repl_strategy": repl_strategy})
        )

    if bind.engine.name != "sqlite":
        op.alter_column("datastore_versions", "registry_ext", nullable=False,
                        existing_type=Text)
        op.alter_column("datastore_versions", "repl_strategy", nullable=False,
                        existing_type=Text)
    else:
        with op.batch_alter_table('datastore_versions') as bo:
            bo.alter_column("registry_ext", nullable=False,
                            existing_type=Text)
            bo.alter_column("repl_strategy", nullable=False,
                            existing_type=Text)


def downgrade() -> None:
    pass
