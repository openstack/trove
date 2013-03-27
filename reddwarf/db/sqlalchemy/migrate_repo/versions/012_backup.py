#Copyright [2013] Hewlett-Packard Development Company, L.P.

#Licensed under the Apache License, Version 2.0 (the "License");
#you may not use this file except in compliance with the License.
#You may obtain a copy of the License at
#
#http://www.apache.org/licenses/LICENSE-2.0
#
#Unless required by applicable law or agreed to in writing, software
#distributed under the License is distributed on an "AS IS" BASIS,
#WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#See the License for the specific language governing permissions and
#limitations under the License.

from sqlalchemy.schema import Column
from sqlalchemy.schema import MetaData
from sqlalchemy.schema import UniqueConstraint

from reddwarf.db.sqlalchemy.migrate_repo.schema import create_tables
from reddwarf.db.sqlalchemy.migrate_repo.schema import DateTime
from reddwarf.db.sqlalchemy.migrate_repo.schema import drop_tables
from reddwarf.db.sqlalchemy.migrate_repo.schema import Float
from reddwarf.db.sqlalchemy.migrate_repo.schema import String
from reddwarf.db.sqlalchemy.migrate_repo.schema import Table
from reddwarf.db.sqlalchemy.migrate_repo.schema import Boolean

meta = MetaData()

backups = Table('backups', meta,
                Column('id', String(36), primary_key=True, nullable=False),
                Column('name', String(255), nullable=False),
                Column('description', String(512)),
                Column('location', String(1024)),
                Column('backup_type', String(32)),
                Column('size', Float()),
                Column('tenant_id', String(36)),
                Column('state', String(32), nullable=False),
                Column('instance_id', String(36)),
                Column('backup_timestamp', DateTime()),
                Column('deleted', Boolean()),
                Column('created', DateTime()),
                Column('updated', DateTime()),
                Column('deleted_at', DateTime()))


def upgrade(migrate_engine):
    meta.bind = migrate_engine
    create_tables([backups, ])


def downgrade(migrate_engine):
    meta.bind = migrate_engine
    drop_tables([backups, ])
