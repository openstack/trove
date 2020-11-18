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
import sqlalchemy
from sqlalchemy import schema

from trove.db.sqlalchemy.migrate_repo import schema as trove_schema

meta = schema.MetaData()


def upgrade(migrate_engine):
    meta.bind = migrate_engine

    ds_config_param = trove_schema.Table('datastore_configuration_parameters',
                                         meta,
                                         autoload=True)

    # Remove records with deleted=1
    if 'deleted' in ds_config_param.c:
        ds_config_param.delete(). \
            where(ds_config_param.c.deleted == 1). \
            execute()

        # Delete columns deleted and deleted_at
        if migrate_engine.name != "sqlite":
            ds_config_param.drop_column('deleted')
            ds_config_param.drop_column('deleted_at')
        else:
            # It is not possible to remove a column from a table in SQLite.
            # SQLite is just for testing, so we re-create the table.
            ds_config_param.drop()
            meta.clear()
            trove_schema.Table('datastore_versions', meta, autoload=True)
            new_table = trove_schema.Table(
                'datastore_configuration_parameters',
                meta,
                schema.Column('id', trove_schema.String(36),
                              primary_key=True, nullable=False),
                schema.Column('name', trove_schema.String(128),
                              primary_key=True, nullable=False),
                schema.Column('datastore_version_id', trove_schema.String(36),
                              sqlalchemy.ForeignKey("datastore_versions.id"),
                              primary_key=True, nullable=False),
                schema.Column('restart_required', trove_schema.Boolean(),
                              nullable=False, default=False),
                schema.Column('max_size', trove_schema.String(40)),
                schema.Column('min_size', trove_schema.String(40)),
                schema.Column('data_type', trove_schema.String(128),
                              nullable=False),
                schema.UniqueConstraint(
                    'datastore_version_id', 'name',
                    name=('UQ_datastore_configuration_parameters_datastore_'
                          'version_id_name')
                )
            )
            trove_schema.create_tables([new_table])
