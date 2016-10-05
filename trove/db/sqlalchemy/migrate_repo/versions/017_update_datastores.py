# Copyright 2012 OpenStack Foundation
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

from trove.db.sqlalchemy.migrate_repo.schema import String
from trove.db.sqlalchemy.migrate_repo.schema import Table


def migrate_datastore_manager(datastores, datastore_versions):
    versions = select([datastore_versions]).execute()
    for ds_v in versions:
        ds = select([datastores]).\
            where(datastores.c.id == ds_v.datastore_id).\
            execute().fetchone()
        datastore_versions.update().\
            where(datastore_versions.c.id == ds_v.id).\
            values(manager=ds.manager).\
            execute()


def upgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine

    datastores = Table('datastores', meta, autoload=True)
    datastore_versions = Table('datastore_versions', meta, autoload=True)

    # add column to datastore_versions
    manager = Column('manager', String(255))
    datastore_versions.create_column(manager)
    migrate_datastore_manager(datastores, datastore_versions)

    # drop column from datastores
    datastores.drop_column('manager')
