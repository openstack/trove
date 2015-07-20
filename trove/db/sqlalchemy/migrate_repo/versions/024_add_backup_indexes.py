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

from oslo_log import log as logging
from sqlalchemy.exc import OperationalError
from sqlalchemy.schema import Index
from sqlalchemy.schema import MetaData

from trove.db.sqlalchemy.migrate_repo.schema import Table

logger = logging.getLogger('trove.db.sqlalchemy.migrate_repo.schema')


def upgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine

    backups = Table('backups', meta, autoload=True)
    backups_instance_id_idx = Index("backups_instance_id",
                                    backups.c.instance_id)
    backups_deleted_idx = Index("backups_deleted", backups.c.deleted)

    try:
        backups_instance_id_idx.create()
    except OperationalError as e:
        logger.info(e)

    try:
        backups_deleted_idx.create()
    except OperationalError as e:
        logger.info(e)


def downgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine

    backups = Table('backups', meta, autoload=True)
    backups_instance_id_idx = Index("backups_instance_id",
                                    backups.c.instance_id)
    backups_deleted_idx = Index("backups_deleted", backups.c.deleted)

    meta.bind = migrate_engine
    backups_instance_id_idx.drop()
    backups_deleted_idx.drop()
