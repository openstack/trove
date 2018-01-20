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

from trove.common.policies.base import PATH_FLAVORS, PATH_FLAVOR

rules = [
    policy.DocumentedRuleDefault(
        name='flavor:index',
        check_str='',
        description='List all flavors.',
        operations=[
            {
                'path': PATH_FLAVORS,
                'method': 'GET'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='flavor:show',
        check_str='',
        description='Get information of a flavor.',
        operations=[
            {
                'path': PATH_FLAVOR,
                'method': 'GET'
            }
        ])
]


def list_rules():
    return rules
