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
    PATH_INSTANCES, PATH_DATABASES, PATH_DATABASE)

rules = [
    policy.DocumentedRuleDefault(
        name='instance:extension:database:create',
        check_str='rule:admin_or_owner',
        description='Create a set of Schemas',
        operations=[
            {
                'path': PATH_DATABASES,
                'method': 'POST'
            },
            # we also check this when creating instances with
            # databases specified.
            {
                'path': PATH_INSTANCES,
                'method': 'POST'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='instance:extension:database:delete',
        check_str='rule:admin_or_owner',
        description='Delete a schema from a database.',
        operations=[
            {
                'path': PATH_DATABASE,
                'method': 'DELETE'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='instance:extension:database:index',
        check_str='rule:admin_or_owner',
        description='List all schemas from a database.',
        operations=[
            {
                'path': PATH_DATABASES,
                'method': 'GET'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='instance:extension:database:show',
        check_str='rule:admin_or_owner',
        description='Get informations of a schema'
                    '(Currently Not Implemented).',
        operations=[
            {
                'path': PATH_DATABASE,
                'method': 'GET'
            }
        ])
]


def list_rules():
    return rules
