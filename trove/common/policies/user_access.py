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

from trove.common.policies.base import PATH_ACCESSES, PATH_ACCESS

rules = [
    policy.DocumentedRuleDefault(
        name='instance:extension:user_access:update',
        check_str='rule:admin_or_owner',
        description='Grant access for a user to one or more databases.',
        operations=[
            {
                'path': PATH_ACCESSES,
                'method': 'PUT'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='instance:extension:user_access:delete',
        check_str='rule:admin_or_owner',
        description='Revoke access for a user to a databases.',
        operations=[
            {
                'path': PATH_ACCESS,
                'method': 'DELETE'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='instance:extension:user_access:index',
        check_str='rule:admin_or_owner',
        description='Get permissions of a user',
        operations=[
            {
                'path': PATH_ACCESSES,
                'method': 'GET'
            }
        ])
]


def list_rules():
    return rules
