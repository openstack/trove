# Copyright 2015 Tesora Inc.
# All Rights Reserved.
#
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

from trove.guestagent.common import guestagent_utils
from trove.tests.unittests import trove_testtools


class TestGuestagentUtils(trove_testtools.TestCase):

    def test_update_dict(self):
        self.assertEqual({}, guestagent_utils.update_dict({}, {}))
        self.assertEqual({'key': 'value'},
                         guestagent_utils.update_dict({}, {'key': 'value'}))
        self.assertEqual({'key': 'value'},
                         guestagent_utils.update_dict({'key': 'value'}, {}))

        data = {'rpc_address': "0.0.0.0",
                'broadcast_rpc_address': '0.0.0.0',
                'listen_address': '0.0.0.0',
                'seed_provider': [{
                    'class_name':
                    'org.apache.cassandra.locator.SimpleSeedProvider',
                    'parameters': [{'seeds': '0.0.0.0'}]}]
                }

        updates = {'rpc_address': "127.0.0.1",
                   'seed_provider': {'parameters':
                                     {'seeds': '127.0.0.1'}
                                     }
                   }

        updated = guestagent_utils.update_dict(updates, data)

        expected = {'rpc_address': "127.0.0.1",
                    'broadcast_rpc_address': '0.0.0.0',
                    'listen_address': '0.0.0.0',
                    'seed_provider': [{
                        'class_name':
                        'org.apache.cassandra.locator.SimpleSeedProvider',
                        'parameters': [{'seeds': '127.0.0.1'}]}]
                    }

        self.assertEqual(expected, updated)

        updates = {'seed_provider':
                   [{'class_name':
                     'org.apache.cassandra.locator.SimpleSeedProvider'
                     }]
                   }

        updated = guestagent_utils.update_dict(updates, data)

        expected = {'rpc_address': "127.0.0.1",
                    'broadcast_rpc_address': '0.0.0.0',
                    'listen_address': '0.0.0.0',
                    'seed_provider': [{
                        'class_name':
                        'org.apache.cassandra.locator.SimpleSeedProvider'}]
                    }

        self.assertEqual(expected, updated)

        data = {'timeout': 0, 'save': [[900, 1], [300, 10]]}
        updates = {'save': [[900, 1], [300, 10], [60, 10000]]}
        updated = guestagent_utils.update_dict(updates, data)
        expected = {'timeout': 0, 'save': [[900, 1], [300, 10], [60, 10000]]}

        self.assertEqual(expected, updated)

    def test_build_file_path(self):
        self.assertEqual(
            'base_dir/base_name',
            guestagent_utils.build_file_path('base_dir', 'base_name'))

        self.assertEqual(
            'base_dir/base_name.ext1',
            guestagent_utils.build_file_path('base_dir', 'base_name', 'ext1'))

        self.assertEqual(
            'base_dir/base_name.ext1.ext2',
            guestagent_utils.build_file_path(
                'base_dir', 'base_name', 'ext1', 'ext2'))

    def test_flatten_expand_dict(self):
        self._assert_flatten_expand_dict({}, {})
        self._assert_flatten_expand_dict({'ns1': 1}, {'ns1': 1})
        self._assert_flatten_expand_dict(
            {'ns1': {'ns2a': {'ns3a': True, 'ns3b': False}, 'ns2b': 10}},
            {'ns1.ns2a.ns3a': True, 'ns1.ns2a.ns3b': False, 'ns1.ns2b': 10})

    def _assert_flatten_expand_dict(self, nested_dict, flattened_dict):
        self.assertEqual(
            flattened_dict, guestagent_utils.flatten_dict(nested_dict))
        self.assertEqual(
            nested_dict, guestagent_utils.expand_dict(flattened_dict))
