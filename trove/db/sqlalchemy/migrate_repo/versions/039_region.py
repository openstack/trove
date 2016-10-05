# Copyright 2016 Tesora Inc.
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

from oslo_log import log as logging
from sqlalchemy.schema import Column
from sqlalchemy.schema import MetaData

from trove.common import cfg
from trove.db.sqlalchemy.migrate_repo.schema import String
from trove.db.sqlalchemy.migrate_repo.schema import Table


CONF = cfg.CONF
logger = logging.getLogger('trove.db.sqlalchemy.migrate_repo.schema')

meta = MetaData()


def upgrade(migrate_engine):
    meta.bind = migrate_engine
    instances = Table('instances', meta, autoload=True)
    instances.create_column(Column('region_id', String(255)))
    instances.update().values(region_id=CONF.os_region_name).execute()
