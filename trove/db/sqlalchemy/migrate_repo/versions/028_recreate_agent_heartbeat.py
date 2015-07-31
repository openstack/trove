# Copyright 2014 Hewlett-Packard Development Company, L.P.
#
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

from oslo_log import log as logging
from sqlalchemy.exc import OperationalError
from sqlalchemy.schema import Column
from sqlalchemy.schema import MetaData

from trove.db.sqlalchemy.migrate_repo.schema import Boolean
from trove.db.sqlalchemy.migrate_repo.schema import create_tables
from trove.db.sqlalchemy.migrate_repo.schema import DateTime
from trove.db.sqlalchemy.migrate_repo.schema import drop_tables
from trove.db.sqlalchemy.migrate_repo.schema import String
from trove.db.sqlalchemy.migrate_repo.schema import Table


logger = logging.getLogger('trove.db.sqlalchemy.migrate_repo.schema')


def upgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine

    # new table with desired columns, indexes, and constraints
    new_agent_heartbeats = Table(
        'agent_heartbeats', meta,
        Column('id', String(36), primary_key=True, nullable=False),
        Column('instance_id', String(36),
               nullable=False, unique=True, index=True),
        Column('guest_agent_version', String(255), index=True),
        Column('deleted', Boolean(), index=True),
        Column('deleted_at', DateTime()),
        Column('updated_at', DateTime(), nullable=False))

    # original table from migration 005_heartbeat.py
    previous_agent_heartbeats = Table('agent_heartbeats', meta, autoload=True)

    try:
        drop_tables([previous_agent_heartbeats])
    except OperationalError as e:
        logger.warn("This table may have been dropped by some other means.")
        logger.warn(e)

    create_tables([new_agent_heartbeats])


def downgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine

    # new table with desired columns, indexes, and constraints
    new_agent_heartbeats = Table('agent_heartbeats', meta, autoload=True)

    try:
        drop_tables([new_agent_heartbeats])
    except OperationalError as e:
        logger.warn("This table may have been dropped by some other means.")
        logger.warn(e)

    # reset the migrate_engine
    meta = MetaData()
    meta.bind = migrate_engine

    # original table from migration 005_heartbeat.py
    previous_agent_heartbeats = Table(
        'agent_heartbeats', meta, Column('id', String(36), primary_key=True,
                                         nullable=False),
        Column('instance_id', String(36), nullable=False),
        Column('updated_at', DateTime()), extend_existing=True)

    create_tables([previous_agent_heartbeats])
