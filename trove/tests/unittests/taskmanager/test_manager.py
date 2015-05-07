
# Copyright 2014 eBay Software Foundation
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

from mock import Mock, patch

from trove.taskmanager.manager import Manager
from trove.common.exception import TroveError
from proboscis.asserts import assert_equal
from trove.tests.unittests import trove_testtools


class TestManager(trove_testtools.TestCase):

    def setUp(self):
        super(TestManager, self).setUp()
        self.manager = Manager()

    def tearDown(self):
        super(TestManager, self).tearDown()
        self.manager = None

    def test_getattr_lookup(self):
        self.assertTrue(callable(self.manager.delete_cluster))
        self.assertTrue(callable(self.manager.mongodb_add_shard_cluster))

    def test_most_current_replica(self):
        master = Mock()
        master.id = 32

        def test_case(txn_list, selected_master):
            with patch.object(self.manager, '_get_replica_txns',
                              return_value=txn_list):
                result = self.manager._most_current_replica(master, None)
                assert_equal(result, selected_master)

        with self.assertRaisesRegexp(TroveError,
                                     'not all replicating from same'):
            test_case([['a', '2a99e-32bf', 2], ['b', '2a', 1]], None)

        test_case([['a', '2a99e-32bf', 2]], 'a')
        test_case([['a', '2a', 1], ['b', '2a', 2]], 'b')
        test_case([['a', '2a', 2], ['b', '2a', 1]], 'a')
        test_case([['a', '2a', 1], ['b', '2a', 1]], 'a')
        test_case([['a', None, 0]], 'a')
        test_case([['a', None, 0], ['b', '2a', 1]], 'b')
