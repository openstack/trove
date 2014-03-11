# Copyright 2014 OpenStack Foundation
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

from sqlalchemy.exc import OperationalError
from sqlalchemy.schema import MetaData
from sqlalchemy.schema import Index
from trove.openstack.common import log as logging

from trove.db.sqlalchemy.migrate_repo.schema import Table

logger = logging.getLogger('trove.db.sqlalchemy.migrate_repo.schema')


def upgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine

    service_statuses = Table('service_statuses', meta, autoload=True)
    idx = Index("service_statuses_instance_id", service_statuses.c.instance_id)

    try:
        idx.create()
    except OperationalError as e:
        logger.info(e)


def downgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine

    service_statuses = Table('service_statuses', meta, autoload=True)
    idx = Index("service_statuses_instance_id", service_statuses.c.instance_id)
    idx.drop()
