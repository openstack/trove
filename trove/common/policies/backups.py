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

from trove.common.policies.base import PATH_BACKUPS, PATH_BACKUP

rules = [
    policy.DocumentedRuleDefault(
        name='backup:create',
        check_str='rule:admin_or_owner',
        description='Create a backup of a database instance.',
        operations=[
            {
                'path': PATH_BACKUPS,
                'method': 'POST'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='backup:delete',
        check_str='rule:admin_or_owner',
        description='Delete a backup of a database instance.',
        operations=[
            {
                'path': PATH_BACKUP,
                'method': 'DELETE'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='backup:index',
        check_str='rule:admin_or_owner',
        description='List all backups.',
        operations=[
            {
                'path': PATH_BACKUPS,
                'method': 'GET'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='backup:show',
        check_str='rule:admin_or_owner',
        description='Get informations of a backup.',
        operations=[
            {
                'path': PATH_BACKUP,
                'method': 'GET'
            }
        ])
]


def list_rules():
    return rules
