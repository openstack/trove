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

from trove.common.policies.base import PATH_CONFIGS, PATH_CONFIG

rules = [
    policy.DocumentedRuleDefault(
        name='configuration:create',
        check_str='rule:admin_or_owner',
        description='Create a configuration group.',
        operations=[
            {
                'path': PATH_CONFIGS,
                'method': 'POST'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='configuration:delete',
        check_str='rule:admin_or_owner',
        description='Delete a configuration group.',
        operations=[
            {
                'path': PATH_CONFIG,
                'method': 'DELETE'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='configuration:index',
        check_str='rule:admin_or_owner',
        description='List all configuration groups.',
        operations=[
            {
                'path': PATH_CONFIGS,
                'method': 'GET'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='configuration:show',
        check_str='rule:admin_or_owner',
        description='Get informations of a configuration group.',
        operations=[
            {
                'path': PATH_CONFIG,
                'method': 'GET'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='configuration:instances',
        check_str='rule:admin_or_owner',
        description='List all instances which a configuration group '
                    'has be assigned to.',
        operations=[
            {
                'path': PATH_CONFIG + '/instances',
                'method': 'GET'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='configuration:update',
        check_str='rule:admin_or_owner',
        description='Update a configuration group(the configuration '
                    'group will be replaced completely).',
        operations=[
            {
                'path': PATH_CONFIG,
                'method': 'PUT'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='configuration:edit',
        check_str='rule:admin_or_owner',
        description='Patch a configuration group.',
        operations=[
            {
                'path': PATH_CONFIG,
                'method': 'PATCH'
            }
        ])
]


def list_rules():
    return rules
