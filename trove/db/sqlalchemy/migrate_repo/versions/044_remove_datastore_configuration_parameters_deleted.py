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

from trove.db.sqlalchemy.migrate_repo.schema import Table

meta = MetaData()


def upgrade(migrate_engine):
    meta.bind = migrate_engine

    ds_config_param = Table('datastore_configuration_parameters', meta,
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
