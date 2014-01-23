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

from sqlalchemy.schema import MetaData
from sqlalchemy.sql.expression import select
from trove.common import cfg
from trove.datastore.models import DBDatastore
from trove.datastore.models import DBDatastoreVersion
from trove.db.sqlalchemy import session
from trove.db.sqlalchemy.migrate_repo.schema import Table
from trove.instance.models import DBInstance

CONF = cfg.CONF
meta = MetaData()


def upgrade(migrate_engine):
    meta.bind = migrate_engine

    instance_table = Table('instances', meta, autoload=True)

    session.configure_db(CONF)

    instances = DBInstance.find_all(datastore_version_id=None)
    if instances.count() > 0:
        datastore = DBDatastore.get_by(manager="mysql")
        datastore = datastore or DBDatastore.create(
            name="Legacy MySQL",
            manager="mysql",
        )

        image_table = Table('service_images', meta, autoload=True)
        image = select(
            columns=["id", "image_id", "service_name"],
            from_obj=image_table,
            whereclause="service_name='mysql'",
            limit=1
        ).execute().fetchone()

        image_id = "00000000-0000-0000-0000-000000000000"
        if image:
            image_id = image.image_id

        version = DBDatastoreVersion.create(
            datastore_id=datastore.id,
            name="Unknown Legacy Version",
            image_id=image_id,
            active=False,
        )

        for instance in instances:
            instance.update_db(datastore_version_id=version.id)

    instance_table.c.datastore_version_id.alter(nullable=False)


def downgrade(migrate_engine):
    meta.bind = migrate_engine

    instance_table = Table('instances', meta, autoload=True)
    instance_table.c.datastore_version_id.alter(nullable=True)
