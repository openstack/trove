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

from trove.common.policies.base import (
    PATH_INSTANCES, PATH_INSTANCE, PATH_INSTANCE_ACTION)


rules = [
    policy.DocumentedRuleDefault(
        name='instance:create',
        check_str='rule:admin_or_owner',
        description='Create a database instance.',
        operations=[
            {
                'path': PATH_INSTANCES,
                'method': 'POST'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='instance:delete',
        check_str='rule:admin_or_owner',
        description='Delete a database instance.',
        operations=[
            {
                'path': PATH_INSTANCE,
                'method': 'DELETE'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='instance:force_delete',
        check_str='rule:admin_or_owner',
        description='Forcibly delete a database instance.',
        operations=[
            {
                'path': PATH_INSTANCE,
                'method': 'DELETE'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='instance:index',
        check_str='rule:admin_or_owner',
        description='List database instances.',
        operations=[
            {
                'path': PATH_INSTANCES,
                'method': 'GET'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='instance:show',
        check_str='rule:admin_or_owner',
        description='Get details of a specific database instance.',
        operations=[
            {
                'path': PATH_INSTANCE,
                'method': 'GET'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='instance:update',
        check_str='rule:admin_or_owner',
        description='Update a database instance to '
                    'attach/detach configuration',
        operations=[
            {
                'path': PATH_INSTANCE,
                'method': 'PUT'
            },
            # we also check this when creating instances with
            # a configuration group specified.
            {
                'path': PATH_INSTANCES,
                'method': 'POST'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='instance:edit',
        check_str='rule:admin_or_owner',
        description='Updates the instance to set or '
                    'unset one or more attributes.',
        operations=[
            {
                'path': PATH_INSTANCE,
                'method': 'PATCH'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='instance:restart',
        check_str='rule:admin_or_owner',
        description='Restart a database instance.',
        operations=[
            {
                'path': PATH_INSTANCE_ACTION + ' (restart)',
                'method': 'POST'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='instance:resize_volume',
        check_str='rule:admin_or_owner',
        description='Resize a database instance volume.',
        operations=[
            {
                'path': PATH_INSTANCE_ACTION + ' (resize)',
                'method': 'POST'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='instance:resize_flavor',
        check_str='rule:admin_or_owner',
        description='Resize a database instance flavor.',
        operations=[
            {
                'path': PATH_INSTANCE_ACTION + ' (resize)',
                'method': 'POST'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='instance:reset_status',
        check_str='rule:admin',
        description='Reset the status of a database instance to ERROR.',
        operations=[
            {
                'path': PATH_INSTANCE_ACTION + ' (reset_status)',
                'method': 'POST'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='instance:promote_to_replica_source',
        check_str='rule:admin_or_owner',
        description='Promote instance to replica source.',
        operations=[
            {
                'path': PATH_INSTANCE_ACTION + ' (promote_to_replica_source)',
                'method': 'POST'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='instance:eject_replica_source',
        check_str='rule:admin_or_owner',
        description='Eject the replica source from its replica set.',
        operations=[
            {
                'path': PATH_INSTANCE_ACTION + ' (eject_replica_source)',
                'method': 'POST'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='instance:configuration',
        check_str='rule:admin_or_owner',
        description='Get the default configuration template '
                    'applied to the instance.',
        operations=[
            {
                'path': PATH_INSTANCE + '/configuration',
                'method': 'GET'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='instance:guest_log_list',
        check_str='rule:admin_or_owner',
        description='Get all informations about all logs '
                    'of a database instance.',
        operations=[
            {
                'path': PATH_INSTANCE + '/log',
                'method': 'GET'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='instance:backups',
        check_str='rule:admin_or_owner',
        description='Get all backups of a database instance.',
        operations=[
            {
                'path': PATH_INSTANCE + '/backups',
                'method': 'GET'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='instance:module_list',
        check_str='rule:admin_or_owner',
        description='Get informations about modules on a database instance.',
        operations=[
            {
                'path': PATH_INSTANCE + '/modules',
                'method': 'GET'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='instance:module_apply',
        check_str='rule:admin_or_owner',
        description='Apply modules to a database instance.',
        operations=[
            {
                'path': PATH_INSTANCE + '/modules',
                'method': 'POST'
            },
            # we also check this when creating instances with
            # modules specified.
            {
                'path': PATH_INSTANCES,
                'method': 'POST'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='instance:module_remove',
        check_str='rule:admin_or_owner',
        description='Remove a module from a database instance.',
        operations=[
            {
                'path': PATH_INSTANCE + '/modules/{module_id}',
                'method': 'DELETE'
            }
        ])
]


def list_rules():
    return rules
