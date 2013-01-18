#    Copyright 2012 OpenStack LLC
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
#    under the License
import testtools
from mock import Mock, MagicMock
from reddwarf.openstack.common import rpc
from reddwarf.openstack.common.rpc import proxy
from reddwarf.openstack.common.rpc import impl_kombu as kombu
from reddwarf.guestagent import models as agent_models
from reddwarf.common import exception
from reddwarf.guestagent import api


class ApiTest(testtools.TestCase):

    def setUp(self):
        super(ApiTest, self).setUp()
        self.api = api.API(Mock, Mock)
        self.origin_rpc_call = proxy.RpcProxy.call
        proxy.RpcProxy.call = Mock()
        self.rpc_call = proxy.RpcProxy.call

        self.origin_rpc_cast = proxy.RpcProxy.cast
        proxy.RpcProxy.cast = Mock()
        self.rpc_cast = proxy.RpcProxy.cast

        self.origin_object = agent_models.AgentHeartBeat.find_by
        agent_models.AgentHeartBeat.find_by = Mock()
        self.origin_is_active = agent_models.AgentHeartBeat.is_active

        self.origin_api_id = self.api.id

    def tearDown(self):
        super(ApiTest, self).tearDown()
        proxy.RpcProxy.call = self.origin_rpc_call
        proxy.RpcProxy.cast = self.origin_rpc_cast

        agent_models.AgentHeartBeat.is_active = self.origin_is_active
        agent_models.AgentHeartBeat.find_by = self.origin_object

        self.api.id = self.origin_api_id

    def test__call(self):
        self.api._call(Mock, Mock)
        self.assertEqual(1, self.rpc_call.call_count)

    def test__cast(self):
        self.api._cast(Mock)
        self.assertEqual(1, self.rpc_cast.call_count)

    def test_delete_queue(self):
        self.skipTest("find out if this delete_queue function is needed "
                      "anymore, Bug#1097482")

    def test_get_routing_key(self):
        FAKE_ID = '123456'
        self.api.id = FAKE_ID
        self.assertEqual('guestagent.' + FAKE_ID,
                         self.api._get_routing_key())

    def test_check_for_heartbeat_positive(self):
        agent_models.AgentHeartBeat.is_active = MagicMock(return_value=True)
        self.assertTrue(self.api._check_for_hearbeat())

    def test_check_for_heartbeat_negative(self):
        agent_models.AgentHeartBeat.is_active = MagicMock(return_value=False)
        self.assertRaises(exception.GuestTimeout, self.api._check_for_hearbeat)

    def test_create_user(self):
        self.api.create_user(Mock)
        self.assertEqual(1, self.rpc_cast.call_count)

    def test_list_users(self):
        self.api.list_users()
        self.assertEqual(1, self.rpc_call.call_count)

    def test_delete_user(self):
        self.api.delete_user(Mock)
        self.assertEqual(1, self.rpc_cast.call_count)

    def test_create_database(self):
        self.api.create_database(Mock)
        self.assertEqual(1, self.rpc_cast.call_count)

    def test_list_databases(self):
        self.api.list_databases()
        self.assertEqual(1, self.rpc_call.call_count)

    def test_delete_database(self):
        self.api.delete_database(Mock)
        self.assertEqual(1, self.rpc_cast.call_count)

    def test_enable_root(self):
        self.api.enable_root()
        self.assertEqual(1, self.rpc_call.call_count)

    def test_disable_root(self):
        self.api.disable_root()
        self.assertEqual(1, self.rpc_call.call_count)

    def test_is_root_enabled(self):
        self.api.is_root_enabled()
        self.assertEqual(1, self.rpc_call.call_count)

    def test_get_hwinfo(self):
        self.api.get_hwinfo()
        self.assertEqual(1, self.rpc_call.call_count)

    def test_get_diagnostics(self):
        self.api.get_diagnostics()
        self.assertEqual(1, self.rpc_call.call_count)

    def test_restart(self):
        self.api.restart()
        self.assertEqual(1, self.rpc_call.call_count)

    def test_start_mysql_with_conf_changes(self):
        self.api.start_mysql_with_conf_changes(Mock)
        self.assertEqual(1, self.rpc_call.call_count)

    def test_stop_mysql(self):
        self.api.stop_mysql()
        self.assertEqual(1, self.rpc_call.call_count)

    def test_get_volume_info(self):
        self.api.get_volume_info()
        self.assertEqual(1, self.rpc_call.call_count)

    def test_update_guest(self):
        self.api.update_guest()
        self.assertEqual(1, self.rpc_call.call_count)


class CastWithConsumerTest(testtools.TestCase):
    def setUp(self):
        super(CastWithConsumerTest, self).setUp()
        self.api = api.API(Mock, Mock)
        self.origin_get_routing_key = self.api._get_routing_key
        self.origin_create_consumer = kombu.Connection.create_consumer
        self.origin_close = kombu.Connection.close
        self.origin_create_connection = rpc.create_connection

    def tearDown(self):
        super(CastWithConsumerTest, self).tearDown()
        self.api._get_routing_key = self.origin_get_routing_key
        kombu.Connection.create_consumer = self.origin_create_consumer
        kombu.Connection.close = self.origin_close
        rpc.create_connection = self.origin_create_connection

    def test__cast_with_consumer(self):
        self.api._get_routing_key = Mock()
        self.api._cast = Mock()
        kombu.Connection.create_consumer = Mock()
        kombu.Connection.close = Mock()
        rpc.create_connection = MagicMock(return_value=kombu.Connection)

        self.api._cast_with_consumer(Mock)

        self.assertEqual(1, kombu.Connection.create_consumer.call_count)
        self.assertEqual(1, kombu.Connection.close.call_count)
        self.assertEqual(1, self.api._get_routing_key.call_count)
        self.assertEqual(1, rpc.create_connection.call_count)


class OtherTests(testtools.TestCase):
    def setUp(self):
        super(OtherTests, self).setUp()
        self.api = api.API(Mock, Mock)
        self.origin_cast_with_consumer = self.api._cast_with_consumer

    def tearDown(self):
        super(OtherTests, self).tearDown()
        self.api._cast_with_consumer = self.origin_cast_with_consumer

    def test_prepare(self):
        self.api._cast_with_consumer = Mock()
        self.api.prepare(Mock, Mock, Mock)
        self.assertEqual(1, self.api._cast_with_consumer.call_count)

    def test_upgrade(self):
        self.api._cast_with_consumer = Mock()
        self.api.upgrade()
        self.assertEqual(1, self.api._cast_with_consumer.call_count)
