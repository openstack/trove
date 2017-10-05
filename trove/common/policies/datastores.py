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
    PATH_DATASTORES, PATH_DATASTORE,
    PATH_VERSIONS)

rules = [
    policy.DocumentedRuleDefault(
        name='datastore:index',
        check_str='',
        description='List all datastores.',
        operations=[
            {
                'path': PATH_DATASTORES,
                'method': 'GET'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='datastore:show',
        check_str='',
        description='Get informations of a datastore.',
        operations=[
            {
                'path': PATH_DATASTORE,
                'method': 'GET'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='datastore:version_show',
        check_str='',
        description='Get a version of a datastore by the version id.',
        operations=[
            {
                'path': PATH_DATASTORE + '/versions/{version}',
                'method': 'GET'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='datastore:version_show_by_uuid',
        check_str='',
        description='Get a version of a datastore by the version id'
                    '(without providing the datastore id).',
        operations=[
            {
                'path': PATH_VERSIONS + '/{version}',
                'method': 'GET'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='datastore:version_index',
        check_str='',
        description='Get all versions of a datastore.',
        operations=[
            {
                'path': PATH_DATASTORE + '/versions',
                'method': 'GET'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='datastore:list_associated_flavors',
        check_str='',
        description='List all flavors associated with a datastore version.',
        operations=[
            {
                'path': PATH_DATASTORE + '/versions/{version}/flavors',
                'method': 'GET'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='datastore:list_associated_volume_types',
        check_str='',
        description='List all volume-types associated with '
                    'a datastore version.',
        operations=[
            {
                'path': PATH_DATASTORE + '/versions/{version}/volume-types',
                'method': 'GET'
            }
        ])
]


def list_rules():
    return rules
