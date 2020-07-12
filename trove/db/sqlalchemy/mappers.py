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

from sqlalchemy import MetaData
from sqlalchemy import orm
from sqlalchemy.orm import exc as orm_exc
from sqlalchemy import Table


def map(engine, models):
    meta = MetaData()
    meta.bind = engine
    if mapping_exists(models['instances']):
        return

    orm.mapper(models['instances'], Table('instances', meta, autoload=True))
    orm.mapper(models['instance_faults'],
               Table('instance_faults', meta, autoload=True))
    orm.mapper(models['root_enabled_history'],
               Table('root_enabled_history', meta, autoload=True))
    orm.mapper(models['datastores'],
               Table('datastores', meta, autoload=True))
    orm.mapper(models['datastore_versions'],
               Table('datastore_versions', meta, autoload=True))
    orm.mapper(models['datastore_version_metadata'],
               Table('datastore_version_metadata', meta, autoload=True))
    orm.mapper(models['capabilities'],
               Table('capabilities', meta, autoload=True))
    orm.mapper(models['capability_overrides'],
               Table('capability_overrides', meta, autoload=True))
    orm.mapper(models['service_statuses'],
               Table('service_statuses', meta, autoload=True))
    orm.mapper(models['dns_records'],
               Table('dns_records', meta, autoload=True))
    orm.mapper(models['agent_heartbeats'],
               Table('agent_heartbeats', meta, autoload=True))
    orm.mapper(models['quotas'],
               Table('quotas', meta, autoload=True))
    orm.mapper(models['quota_usages'],
               Table('quota_usages', meta, autoload=True))
    orm.mapper(models['reservations'],
               Table('reservations', meta, autoload=True))
    orm.mapper(models['backups'],
               Table('backups', meta, autoload=True))
    orm.mapper(models['backup_strategy'],
               Table('backup_strategy', meta, autoload=True))
    orm.mapper(models['security_groups'],
               Table('security_groups', meta, autoload=True))
    orm.mapper(models['security_group_rules'],
               Table('security_group_rules', meta, autoload=True))
    orm.mapper(models['security_group_instance_associations'],
               Table('security_group_instance_associations', meta,
                     autoload=True))
    orm.mapper(models['configurations'],
               Table('configurations', meta, autoload=True))
    orm.mapper(models['configuration_parameters'],
               Table('configuration_parameters', meta, autoload=True))
    orm.mapper(models['conductor_lastseen'],
               Table('conductor_lastseen', meta, autoload=True))
    orm.mapper(models['clusters'],
               Table('clusters', meta, autoload=True))
    orm.mapper(models['datastore_configuration_parameters'],
               Table('datastore_configuration_parameters', meta,
                     autoload=True))
    orm.mapper(models['modules'],
               Table('modules', meta, autoload=True))
    orm.mapper(models['instance_modules'],
               Table('instance_modules', meta, autoload=True))


def mapping_exists(model):
    try:
        orm.class_mapper(model)
        return True
    except orm_exc.UnmappedClassError:
        return False
