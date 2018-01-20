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

from trove.common.policies.base import PATH_DATASTORE, PATH_VERSIONS

rules = [
    policy.DocumentedRuleDefault(
        name='configuration-parameter:index',
        check_str='rule:admin_or_owner',
        description='List all parameters bind to a datastore version.',
        operations=[
            {
                'path': PATH_DATASTORE + '/versions/{version}/parameters',
                'method': 'GET'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='configuration-parameter:show',
        check_str='rule:admin_or_owner',
        description='Get a paramter of a datastore version.',
        operations=[
            {
                'path': (PATH_DATASTORE +
                         '/versions/{version}/parameters/{param}'),
                'method': 'GET'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='configuration-parameter:index_by_version',
        check_str='rule:admin_or_owner',
        description='List all paramters bind to a datastore version by '
                    'the id of the version(datastore is not provided).',
        operations=[
            {
                'path': PATH_VERSIONS + '/{version}/paramters',
                'method': 'GET'
            }
        ]),
    policy.DocumentedRuleDefault(
        name='configuration-parameter:show_by_version',
        check_str='rule:admin_or_owner',
        description='Get a paramter of a datastore version by it names and '
                    'the id of the version(datastore is not provided).',
        operations=[
            {
                'path': PATH_VERSIONS + '/{version}/paramters/{param}',
                'method': 'GET'
            }
        ])
]


def list_rules():
    return rules
