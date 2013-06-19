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

from trove.db.sqlalchemy.migrate_repo.schema import create_tables
from trove.db.sqlalchemy.migrate_repo.schema import DateTime
from trove.db.sqlalchemy.migrate_repo.schema import drop_tables
from trove.db.sqlalchemy.migrate_repo.schema import Integer
from trove.db.sqlalchemy.migrate_repo.schema import String
from trove.db.sqlalchemy.migrate_repo.schema import Table


meta = MetaData()

quotas = Table('quotas', meta,
               Column('id', String(36),
                      primary_key=True, nullable=False),
               Column('created', DateTime()),
               Column('updated', DateTime()),
               Column('tenant_id', String(36)),
               Column('resource', String(length=255), nullable=False),
               Column('hard_limit', Integer()),
               UniqueConstraint('tenant_id', 'resource'))

quota_usages = Table('quota_usages', meta,
                     Column('id', String(36),
                            primary_key=True, nullable=False),
                     Column('created', DateTime()),
                     Column('updated', DateTime()),
                     Column('tenant_id', String(36)),
                     Column('in_use', Integer(), default=0),
                     Column('reserved', Integer(), default=0),
                     Column('resource', String(length=255), nullable=False),
                     UniqueConstraint('tenant_id', 'resource'))

reservations = Table('reservations', meta,
                     Column('created', DateTime()),
                     Column('updated', DateTime()),
                     Column('id', String(36),
                            primary_key=True, nullable=False),
                     Column('usage_id', String(36)),
                     Column('delta', Integer(), nullable=False),
                     Column('status', String(length=36)))


def upgrade(migrate_engine):
    meta.bind = migrate_engine
    create_tables([quotas, quota_usages, reservations])


def downgrade(migrate_engine):
    meta.bind = migrate_engine
    drop_tables([quotas, quota_usages, reservations])
