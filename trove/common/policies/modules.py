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

from trove.common.policies.base import PATH_MODULES, PATH_MODULE

rules = [
    policy.DocumentedRuleDefault(
        name='module:create',
        check_str='rule:admin_or_owner',
        description='Create a module.',
        operations=[
            {
                'path': PATH_MODULES,
                'method': 'POST'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='module:delete',
        check_str='rule:admin_or_owner',
        description='Delete a module.',
        operations=[
            {
                'path': PATH_MODULE,
                'method': 'DELETE'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='module:index',
        check_str='rule:admin_or_owner',
        description='List all modules.',
        operations=[
            {
                'path': PATH_MODULES,
                'method': 'GET'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='module:show',
        check_str='rule:admin_or_owner',
        description='Get informations of a module.',
        operations=[
            {
                'path': PATH_MODULE,
                'method': 'GET'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='module:instances',
        check_str='rule:admin_or_owner',
        description='List all instances to which a module is applied.',
        operations=[
            {
                'path': PATH_MODULE + '/instances',
                'method': 'GET'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='module:update',
        check_str='rule:admin_or_owner',
        description='Update a module.',
        operations=[
            {
                'path': PATH_MODULE,
                'method': 'PUT'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='module:reapply',
        check_str='rule:admin_or_owner',
        description='Reapply a module to all instances.',
        operations=[
            {
                'path': PATH_MODULE + '/instances',
                'method': 'PUT'
            }
        ])
]


def list_rules():
    return rules
