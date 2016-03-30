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
from sqlalchemy.sql.expression import delete
from sqlalchemy.sql.expression import insert
from sqlalchemy.sql.expression import select
from sqlalchemy.sql.expression import update

from trove.common import cfg
from trove.db.sqlalchemy.migrate_repo.schema import Table
from trove.db.sqlalchemy import utils as db_utils

CONF = cfg.CONF
LEGACY_IMAGE_ID = "00000000-0000-0000-0000-000000000000"
LEGACY_DATASTORE_ID = "10000000-0000-0000-0000-000000000001"
LEGACY_VERSION_ID = "20000000-0000-0000-0000-000000000002"
meta = MetaData()


def create_legacy_version(datastores_table,
                          datastore_versions_table,
                          image_id):
    insert(
        table=datastores_table,
        values=dict(id=LEGACY_DATASTORE_ID, name="Legacy MySQL")
    ).execute()

    insert(
        table=datastore_versions_table,
        values=dict(id=LEGACY_VERSION_ID,
                    datastore_id=LEGACY_DATASTORE_ID,
                    name="Unknown Legacy Version",
                    image_id=image_id,
                    packages="",
                    active=False,
                    manager="mysql")
    ).execute()

    return LEGACY_VERSION_ID


def find_image(service_name):
    image_table = Table('service_images', meta, autoload=True)
    image = select(
        columns=["id", "image_id", "service_name"],
        from_obj=image_table,
        whereclause="service_name='%s'" % service_name,
        limit=1
    ).execute().fetchone()

    if image:
        return image.id
    return LEGACY_IMAGE_ID


def has_instances_wo_datastore_version(instances_table):
    instance = select(
        columns=["id"],
        from_obj=instances_table,
        whereclause="datastore_version_id is NULL",
        limit=1
    ).execute().fetchone()

    return instance is not None


def find_all_instances_wo_datastore_version(instances_table):
    instances = select(
        columns=["id"],
        from_obj=instances_table,
        whereclause="datastore_version_id is NULL"
    ).execute()

    return instances


def upgrade(migrate_engine):
    meta.bind = migrate_engine

    instance_table = Table('instances', meta, autoload=True)
    datastore_versions_table = Table('datastore_versions',
                                     meta,
                                     autoload=True)

    if has_instances_wo_datastore_version(instance_table):
        instances = find_all_instances_wo_datastore_version(instance_table)
        image_id = find_image("mysql")

        datastores_table = Table('datastores',
                                 meta,
                                 autoload=True)

        version_id = create_legacy_version(datastores_table,
                                           datastore_versions_table,
                                           image_id)
        for instance in instances:
            update(
                table=instance_table,
                whereclause="id='%s'" % instance.id,
                values=dict(datastore_version_id=version_id)
            ).execute()

    constraint_names = db_utils.get_foreign_key_constraint_names(
        engine=migrate_engine,
        table='instances',
        columns=['datastore_version_id'],
        ref_table='datastore_versions',
        ref_columns=['id'])
    db_utils.drop_foreign_key_constraints(
        constraint_names=constraint_names,
        columns=[instance_table.c.datastore_version_id],
        ref_columns=[datastore_versions_table.c.id])

    instance_table.c.datastore_version_id.alter(nullable=False)

    db_utils.create_foreign_key_constraints(
        constraint_names=constraint_names,
        columns=[instance_table.c.datastore_version_id],
        ref_columns=[datastore_versions_table.c.id])


def downgrade(migrate_engine):
    meta.bind = migrate_engine

    instance_table = Table('instances', meta, autoload=True)

    instance_table.c.datastore_version_id.alter(nullable=True)

    update(
        table=instance_table,
        whereclause="datastore_version_id='%s'" % LEGACY_VERSION_ID,
        values=dict(datastore_version_id=None)
    ).execute()

    datastores_table = Table('datastores',
                             meta,
                             autoload=True)
    datastore_versions_table = Table('datastore_versions',
                                     meta,
                                     autoload=True)

    delete(
        table=datastore_versions_table,
        whereclause="id='%s'" % LEGACY_VERSION_ID
    ).execute()
    delete(
        table=datastores_table,
        whereclause="id='%s'" % LEGACY_DATASTORE_ID
    ).execute()
