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
    PATH_INSTANCES, PATH_USERS, PATH_USER)

rules = [
    policy.DocumentedRuleDefault(
        name='instance:extension:user:create',
        check_str='rule:admin_or_owner',
        description='Create users for a database instance.',
        operations=[
            {
                'path': PATH_USERS,
                'method': 'POST'
            },
            # we also check this when creating instances with
            # users specified.
            {
                'path': PATH_INSTANCES,
                'method': 'POST'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='instance:extension:user:delete',
        check_str='rule:admin_or_owner',
        description='Delete a user from a database instance.',
        operations=[
            {
                'path': PATH_USER,
                'method': 'DELETE'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='instance:extension:user:index',
        check_str='rule:admin_or_owner',
        description='Get all users of a database instance.',
        operations=[
            {
                'path': PATH_USERS,
                'method': 'GET'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='instance:extension:user:show',
        check_str='rule:admin_or_owner',
        description='Get the information of a single user '
                    'of a database instance.',
        operations=[
            {
                'path': PATH_USER,
                'method': 'GET'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='instance:extension:user:update',
        check_str='rule:admin_or_owner',
        description='Update attributes for a user of a database instance.',
        operations=[
            {
                'path': PATH_USER,
                'method': 'PUT'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='instance:extension:user:update_all',
        check_str='rule:admin_or_owner',
        description='Update the password for one or more users '
                    'a database instance.',
        operations=[
            {
                'path': PATH_USERS,
                'method': 'PUT'
            }
        ])
]


def list_rules():
    return rules
