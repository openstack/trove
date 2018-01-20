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
    PATH_CLUSTERS, PATH_CLUSTER,
    PATH_CLUSTER_INSTANCE)

rules = [
    policy.DocumentedRuleDefault(
        name='cluster:create',
        check_str='rule:admin_or_owner',
        description='Create a cluster.',
        operations=[
            {
                'path': PATH_CLUSTERS,
                'method': 'POST'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='cluster:delete',
        check_str='rule:admin_or_owner',
        description='Delete a cluster.',
        operations=[
            {
                'path': PATH_CLUSTER,
                'method': 'DELETE'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='cluster:force_delete',
        check_str='rule:admin_or_owner',
        description='Forcibly delete a cluster.',
        operations=[
            {
                'path': PATH_CLUSTER + ' (reset-status)',
                'method': 'POST'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='cluster:index',
        check_str='rule:admin_or_owner',
        description='List all clusters',
        operations=[
            {
                'path': PATH_CLUSTERS,
                'method': 'GET'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='cluster:show',
        check_str='rule:admin_or_owner',
        description='Get informations of a cluster.',
        operations=[
            {
                'path': PATH_CLUSTER,
                'method': 'GET'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='cluster:show_instance',
        check_str='rule:admin_or_owner',
        description='Get informations of a instance in a cluster.',
        operations=[
            {
                'path': PATH_CLUSTER_INSTANCE,
                'method': 'GET'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='cluster:action',
        check_str='rule:admin_or_owner',
        description='Commit an action against a cluster',
        operations=[
            {
                'path': PATH_CLUSTER,
                'method': 'POST'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='cluster:reset-status',
        check_str='rule:admin',
        description='Reset the status of a cluster to NONE.',
        operations=[
            {
                'path': PATH_CLUSTER + ' (reset-status)',
                'method': 'POST'
            }
        ])
]


def list_rules():
    return rules
