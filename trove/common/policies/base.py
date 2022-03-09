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

from oslo_policy import policy

PATH_BASE = '/v1.0/{account_id}'

PATH_INSTANCES = PATH_BASE + '/instances'
PATH_INSTANCES_DETAIL = PATH_INSTANCES + '/detail'
PATH_INSTANCE = PATH_INSTANCES + '/{instance_id}'
PATH_INSTANCE_ACTION = PATH_INSTANCE + '/action'
PATH_USERS = PATH_INSTANCE + '/users'
PATH_USER = PATH_USERS + '/{user}'
PATH_ACCESSES = PATH_USER + '/databases'
PATH_ACCESS = PATH_ACCESSES + '/{database}'
PATH_DATABASES = PATH_INSTANCE + '/databases'
PATH_DATABASE = PATH_DATABASES + '/{database}'

PATH_CLUSTERS = PATH_BASE + '/clusters'
PATH_CLUSTER = PATH_CLUSTERS + '/{cluster}'
PATH_CLUSTER_INSTANCES = PATH_CLUSTER + '/instances'
PATH_CLUSTER_INSTANCE = PATH_CLUSTER_INSTANCES + '/{instance}'

PATH_BACKUPS = PATH_BASE + '/backups'
PATH_BACKUP = PATH_BACKUPS + '/{backup}'

PATH_BACKUP_STRATEGIES = PATH_BASE + '/backup_strategies'

PATH_CONFIGS = PATH_BASE + '/configurations'
PATH_CONFIG = PATH_CONFIGS + '/{config}'

PATH_DATASTORES = PATH_BASE + '/datastores'
PATH_DATASTORE = PATH_DATASTORES + '/{datastore}'
PATH_VERSIONS = PATH_DATASTORES + '/versions'

PATH_FLAVORS = PATH_BASE + '/flavors'
PATH_FLAVOR = PATH_FLAVORS + '/{flavor}'

PATH_LIMITS = PATH_BASE + '/limits'

PATH_MODULES = PATH_BASE + '/modules'
PATH_MODULE = PATH_MODULES + '/{module}'

rules = [
    policy.RuleDefault(
        'admin',
        'role:admin or is_admin:True',
        description='Must be an administrator.'),
    policy.RuleDefault(
        'admin_or_owner',
        'rule:admin or project_id:%(tenant)s',
        description='Must be an administrator or owner of the object.'),
    policy.RuleDefault(
        'default',
        'rule:admin_or_owner',
        description='Must be an administrator or owner of the object.')
]


def list_rules():
    return rules
