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
from sqlalchemy.orm import registry
from sqlalchemy import Table

mapper_registry = registry()


def map(engine, models):
    meta = MetaData()
    meta.bind = engine
    if mapping_exists(models['instances']):
        return

    mapper_registry.map_imperatively(models['instances'],
                                     Table('instances', meta,
                                           autoload_with=engine))
    mapper_registry.map_imperatively(models['instance_faults'],
                                     Table('instance_faults', meta,
                                           autoload_with=engine))
    mapper_registry.map_imperatively(models['root_enabled_history'],
                                     Table('root_enabled_history', meta,
                                           autoload_with=engine))
    mapper_registry.map_imperatively(models['datastores'],
                                     Table('datastores', meta,
                                           autoload_with=engine))
    mapper_registry.map_imperatively(models['datastore_versions'],
                                     Table('datastore_versions', meta,
                                           autoload_with=engine))
    mapper_registry.map_imperatively(models['datastore_version_metadata'],
                                     Table('datastore_version_metadata',
                                           meta, autoload_with=engine))
    mapper_registry.map_imperatively(models['capabilities'],
                                     Table('capabilities', meta,
                                           autoload_with=engine))
    mapper_registry.map_imperatively(models['capability_overrides'],
                                     Table('capability_overrides', meta,
                                           autoload_with=engine))
    mapper_registry.map_imperatively(models['service_statuses'],
                                     Table('service_statuses', meta,
                                           autoload_with=engine))
    mapper_registry.map_imperatively(models['dns_records'],
                                     Table('dns_records', meta,
                                           autoload_with=engine))
    mapper_registry.map_imperatively(models['agent_heartbeats'],
                                     Table('agent_heartbeats', meta,
                                           autoload_with=engine))
    mapper_registry.map_imperatively(models['quotas'],
                                     Table('quotas', meta,
                                           autoload_with=engine))
    mapper_registry.map_imperatively(models['quota_usages'],
                                     Table('quota_usages', meta,
                                           autoload_with=engine))
    mapper_registry.map_imperatively(models['reservations'],
                                     Table('reservations', meta,
                                           autoload_with=engine))
    mapper_registry.map_imperatively(models['backups'],
                                     Table('backups', meta,
                                           autoload_with=engine))
    mapper_registry.map_imperatively(models['backup_strategy'],
                                     Table('backup_strategy', meta,
                                           autoload_with=engine))
    mapper_registry.map_imperatively(models['security_groups'],
                                     Table('security_groups', meta,
                                           autoload_with=engine))
    mapper_registry.map_imperatively(models['security_group_rules'],
                                     Table('security_group_rules', meta,
                                           autoload_with=engine))
    mapper_registry.map_imperatively(
        models['security_group_instance_associations'],
        Table('security_group_instance_associations', meta,
              autoload_with=engine))
    mapper_registry.map_imperatively(models['configurations'],
                                     Table('configurations', meta,
                                           autoload_with=engine))
    mapper_registry.map_imperatively(models['configuration_parameters'],
                                     Table('configuration_parameters',
                                           meta, autoload_with=engine))
    mapper_registry.map_imperatively(models['conductor_lastseen'],
                                     Table('conductor_lastseen', meta,
                                           autoload_with=engine))
    mapper_registry.map_imperatively(models['clusters'],
                                     Table('clusters', meta,
                                           autoload_with=engine))
    mapper_registry.map_imperatively(
        models['datastore_configuration_parameters'],
        Table('datastore_configuration_parameters', meta,
              autoload_with=engine))
    mapper_registry.map_imperatively(models['modules'],
                                     Table('modules', meta,
                                           autoload_with=engine))
    mapper_registry.map_imperatively(models['instance_modules'],
                                     Table('instance_modules', meta,
                                           autoload_with=engine))


def mapping_exists(model):
    try:
        orm.class_mapper(model)
        return True
    except orm_exc.UnmappedClassError:
        return False
