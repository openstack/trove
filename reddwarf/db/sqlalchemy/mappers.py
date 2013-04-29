# vim: tabstop=4 shiftwidth=4 softtabstop=4

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
from sqlalchemy import Table
from sqlalchemy import orm
from sqlalchemy.orm import exc as orm_exc


def map(engine, models):
    meta = MetaData()
    meta.bind = engine
    if mapping_exists(models['instance']):
        return

    orm.mapper(models['instance'], Table('instances', meta, autoload=True))
    orm.mapper(models['root_enabled_history'],
               Table('root_enabled_history', meta, autoload=True))
    orm.mapper(models['service_image'],
               Table('service_images', meta, autoload=True))
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
    orm.mapper(models['security_group'],
               Table('security_groups', meta, autoload=True))
    orm.mapper(models['security_group_rule'],
               Table('security_group_rules', meta, autoload=True))
    orm.mapper(models['security_group_instance_association'],
               Table('security_group_instance_associations', meta,
                     autoload=True))


def mapping_exists(model):
    try:
        orm.class_mapper(model)
        return True
    except orm_exc.UnmappedClassError:
        return False
