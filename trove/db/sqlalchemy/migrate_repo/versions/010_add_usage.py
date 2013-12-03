# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack Foundation
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

from trove.db.sqlalchemy.migrate_repo.schema import create_tables
from trove.db.sqlalchemy.migrate_repo.schema import DateTime
from trove.db.sqlalchemy.migrate_repo.schema import drop_tables
from trove.db.sqlalchemy.migrate_repo.schema import Integer
from trove.db.sqlalchemy.migrate_repo.schema import String
from trove.db.sqlalchemy.migrate_repo.schema import Table


meta = MetaData()


usage_events = Table(
    'usage_events',
    meta,
    Column('id', String(36), primary_key=True, nullable=False),
    Column('instance_name', String(36)),
    Column('tenant_id', String(36)),
    Column('nova_instance_id', String(36)),
    Column('instance_size', Integer()),
    Column('nova_volume_id', String(36)),
    Column('volume_size', Integer()),
    Column('end_time', DateTime()),
    Column('updated', DateTime()))


def upgrade(migrate_engine):
    meta.bind = migrate_engine
    create_tables([usage_events])


def downgrade(migrate_engine):
    meta.bind = migrate_engine
    drop_tables([usage_events])
