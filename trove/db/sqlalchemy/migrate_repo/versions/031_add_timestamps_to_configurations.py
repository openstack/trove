# Copyright 2014 Rackspace Hosting
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

from trove.db.sqlalchemy.migrate_repo.schema import Table
from trove.db.sqlalchemy.migrate_repo.schema import DateTime


def upgrade(migrate_engine):
    meta = MetaData(bind=migrate_engine)
    configurations = Table('configurations', meta, autoload=True)
    created = Column('created', DateTime())
    updated = Column('updated', DateTime())
    configurations.create_column(created)
    configurations.create_column(updated)


def downgrade(migrate_engine):
    meta = MetaData(bind=migrate_engine)
    configurations = Table('configurations', meta, autoload=True)
    configurations.drop_column('created')
    configurations.drop_column('updated')
