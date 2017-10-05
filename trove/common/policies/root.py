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

from trove.common.policies.base import PATH_INSTANCE, PATH_CLUSTER

rules = [
    policy.DocumentedRuleDefault(
        name='instance:extension:root:create',
        check_str='rule:admin_or_owner',
        description='Enable the root user of a database instance.',
        operations=[
            {
                'path': PATH_INSTANCE + '/root',
                'method': 'POST'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='instance:extension:root:delete',
        check_str='rule:admin_or_owner',
        description='Disable the root user of a database instance.',
        operations=[
            {
                'path': PATH_INSTANCE + '/root',
                'method': 'DELETE'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='instance:extension:root:index',
        check_str='rule:admin_or_owner',
        description='Show whether the root user of a database '
                    'instance has been ever enabled.',
        operations=[
            {
                'path': PATH_INSTANCE + '/root',
                'method': 'GET'
            }
        ]),

    policy.DocumentedRuleDefault(
        name='cluster:extension:root:create',
        check_str='rule:admin_or_owner',
        description='Enable the root user of the instances in a cluster.',
        operations=[
            {
                'path': PATH_CLUSTER + '/root',
                'method': 'POST'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='cluster:extension:root:delete',
        check_str='rule:admin_or_owner',
        description='Enable the root user of the instances in a cluster.',
        operations=[
            {
                'path': PATH_CLUSTER + '/root',
                'method': 'DELETE'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='cluster:extension:root:index',
        check_str='rule:admin_or_owner',
        description='Disable the root of the instances in a cluster.',
        operations=[
            {
                'path': PATH_CLUSTER + '/root',
                'method': 'GET'
            }
        ])
]


def list_rules():
    return rules
