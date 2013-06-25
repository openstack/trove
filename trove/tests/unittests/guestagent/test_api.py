#    Copyright 2012 OpenStack Foundation
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
from mockito import when
from mockito import any
from mockito import verify
from mockito import unstub
from mockito import mock
from mockito import verifyZeroInteractions
from mockito import never
import mockito.matchers
import testtools
from testtools.matchers import KeysEqual, Is
from trove.guestagent import models as agent_models
import trove.db.models as db_models
from trove.common import exception
from trove.guestagent import api
import trove.openstack.common.rpc as rpc


class ApiTest(testtools.TestCase):
    def setUp(self):
        super(ApiTest, self).setUp()
        self.FAKE_ID = 'instance-id-x23d2d'
        self.api = api.API(mock(), self.FAKE_ID)
        when(rpc).call(any(), any(), any(), any(int)).thenRaise(
            ValueError('Unexpected Rpc Invocation'))
        when(rpc).cast(any(), any(), any()).thenRaise(
            ValueError('Unexpected Rpc Invocation'))

    def tearDown(self):
        super(ApiTest, self).tearDown()
        unstub()

    def test_delete_queue(self):
        self.skipTest("find out if this delete_queue function is needed "
                      "anymore, Bug#1097482")

    def test_get_routing_key(self):
        self.assertEqual('guestagent.' + self.FAKE_ID,
                         self.api._get_routing_key())

    def test_check_for_heartbeat_positive(self):
        when(db_models.DatabaseModelBase).find_by(
            instance_id=any()).thenReturn('agent')
        when(agent_models.AgentHeartBeat).is_active('agent').thenReturn(True)
        self.assertTrue(self.api._check_for_hearbeat())

    def test_check_for_heartbeat_exception(self):
        # TODO (juice) maybe it would be ok to extend the test to validate
        # the is_active method on the heartbeat
        when(db_models.DatabaseModelBase).find_by(instance_id=any()).thenRaise(
            exception.ModelNotFoundError)
        when(agent_models.AgentHeartBeat).is_active(any()).thenReturn(None)

        self.assertRaises(exception.GuestTimeout, self.api._check_for_hearbeat)

        verify(agent_models.AgentHeartBeat, times=0).is_active(any())

    def test_check_for_heartbeat_negative(self):
        # TODO (juice) maybe it would be ok to extend the test to validate
        # the is_active method on the heartbeat
        when(db_models.DatabaseModelBase).find_by(
            instance_id=any()).thenReturn('agent')
        when(agent_models.AgentHeartBeat).is_active(any()).thenReturn(False)
        self.assertRaises(exception.GuestTimeout, self.api._check_for_hearbeat)

    def test_create_user(self):
        exp_msg = RpcMsgMatcher('create_user', 'users')
        self._mock_rpc_cast(exp_msg)
        self.api.create_user('test_user')
        self._verify_rpc_cast(exp_msg)

    def test_rpc_cast_exception(self):
        exp_msg = RpcMsgMatcher('create_user', 'users')
        when(rpc).cast(any(), any(), exp_msg).thenRaise(IOError('host down'))

        with testtools.ExpectedException(exception.GuestError, '.* host down'):
            self.api.create_user('test_user')

        self._verify_rpc_cast(exp_msg)

    def test_list_users(self):
        exp_msg = RpcMsgMatcher('list_users', 'limit', 'marker',
                                'include_marker')
        exp_resp = ['user1', 'user2', 'user3']
        self._mock_rpc_call(exp_msg, exp_resp)
        act_resp = self.api.list_users()
        self.assertThat(act_resp, Is(exp_resp))
        self._verify_rpc_call(exp_msg)

    def test_rpc_call_exception(self):
        exp_msg = RpcMsgMatcher('list_users', 'limit', 'marker',
                                'include_marker')
        when(rpc).call(any(), any(), exp_msg, any(int)).thenRaise(
            IOError('host down'))

        with testtools.ExpectedException(exception.GuestError,
                                         'An error occurred.*'):
            self.api.list_users()

        self._verify_rpc_call(exp_msg)

    def test_delete_user(self):
        exp_msg = RpcMsgMatcher('delete_user', 'user')
        self._mock_rpc_cast(exp_msg)
        self.api.delete_user('test_user')
        self._mock_rpc_cast(exp_msg)

    def test_create_database(self):
        exp_msg = RpcMsgMatcher('create_database', 'databases')
        self._mock_rpc_cast(exp_msg)
        self.api.create_database(['db1', 'db2', 'db3'])
        self._verify_rpc_cast(exp_msg)

    def test_list_databases(self):
        exp_msg = RpcMsgMatcher('list_databases', 'limit', 'marker',
                                'include_marker')
        exp_resp = ['db1', 'db2', 'db3']
        self._mock_rpc_call(exp_msg, exp_resp)
        resp = self.api.list_databases(limit=1, marker=2,
                                       include_marker=False)
        self.assertThat(resp, Is(exp_resp))
        self._verify_rpc_call(exp_msg)

    def test_delete_database(self):
        exp_msg = RpcMsgMatcher('delete_database', 'database')
        self._mock_rpc_cast(exp_msg)
        self.api.delete_database('test_database_name')
        self._verify_rpc_cast(exp_msg)

    def test_enable_root(self):
        exp_msg = RpcMsgMatcher('enable_root')
        self._mock_rpc_call(exp_msg, True)
        self.assertThat(self.api.enable_root(), Is(True))
        self._verify_rpc_call(exp_msg)

    def test_disable_root(self):
        exp_msg = RpcMsgMatcher('disable_root')
        self._mock_rpc_call(exp_msg, True)
        self.assertThat(self.api.disable_root(), Is(True))
        self._verify_rpc_call(exp_msg)

    def test_is_root_enabled(self):
        exp_msg = RpcMsgMatcher('is_root_enabled')
        self._mock_rpc_call(exp_msg, False)
        self.assertThat(self.api.is_root_enabled(), Is(False))
        self._verify_rpc_call(exp_msg)

    def test_get_hwinfo(self):
        exp_msg = RpcMsgMatcher('get_hwinfo')
        self._mock_rpc_call(exp_msg)
        self.api.get_hwinfo()
        self._verify_rpc_call(exp_msg)

    def test_get_diagnostics(self):
        exp_msg = RpcMsgMatcher('get_diagnostics')
        self._mock_rpc_call(exp_msg)
        self.api.get_diagnostics()
        self._verify_rpc_call(exp_msg)

    def test_restart(self):
        exp_msg = RpcMsgMatcher('restart')
        self._mock_rpc_call(exp_msg)
        self.api.restart()
        self._verify_rpc_call(exp_msg)

    def test_start_db_with_conf_changes(self):
        exp_msg = RpcMsgMatcher('start_db_with_conf_changes',
                                'updated_memory_size')
        self._mock_rpc_call(exp_msg)
        self.api.start_db_with_conf_changes('512')
        self._verify_rpc_call(exp_msg)

    def test_stop_db(self):
        exp_msg = RpcMsgMatcher('stop_db', 'do_not_start_on_reboot')
        self._mock_rpc_call(exp_msg)
        self.api.stop_db(do_not_start_on_reboot=False)
        self._verify_rpc_call(exp_msg)

    def test_get_volume_info(self):
        fake_resp = {'fake': 'resp'}
        exp_msg = RpcMsgMatcher('get_filesystem_stats', 'fs_path')
        self._mock_rpc_call(exp_msg, fake_resp)
        self.assertThat(self.api.get_volume_info(), Is(fake_resp))
        self._verify_rpc_call(exp_msg)

    def test_update_guest(self):
        exp_msg = RpcMsgMatcher('update_guest')
        self._mock_rpc_call(exp_msg)
        self.api.update_guest()
        self._verify_rpc_call(exp_msg)

    def test_create_backup(self):
        exp_msg = RpcMsgMatcher('create_backup', 'backup_id')
        self._mock_rpc_cast(exp_msg)
        self.api.create_backup('123')
        self._verify_rpc_cast(exp_msg)

    def _verify_rpc_connection_and_cast(self, rpc, mock_conn, exp_msg):
        verify(rpc).create_connection(new=True)
        verify(mock_conn).create_consumer(self.api._get_routing_key(), None,
                                          fanout=False)
        verify(rpc).cast(any(), any(), exp_msg)

    def test_prepare(self):
        mock_conn = mock()
        when(rpc).create_connection(new=True).thenReturn(mock_conn)
        when(mock_conn).create_consumer(any(), any(), any()).thenReturn(None)
        exp_msg = RpcMsgMatcher('prepare', 'memory_mb', 'databases', 'users',
                                'device_path', 'mount_point', 'backup_id')

        when(rpc).cast(any(), any(), exp_msg).thenReturn(None)

        self.api.prepare('2048', 'db1', 'user1', '/dev/vdt', '/mnt/opt',
                         'bkup-1232')

        self._verify_rpc_connection_and_cast(rpc, mock_conn, exp_msg)

    def test_prepare_with_backup(self):
        mock_conn = mock()
        when(rpc).create_connection(new=True).thenReturn(mock_conn)
        when(mock_conn).create_consumer(any(), any(), any()).thenReturn(None)
        exp_msg = RpcMsgMatcher('prepare', 'memory_mb', 'databases', 'users',
                                'device_path', 'mount_point', 'backup_id')
        when(rpc).cast(any(), any(), exp_msg).thenReturn(None)

        self.api.prepare('2048', 'db1', 'user1', '/dev/vdt', '/mnt/opt',
                         'backup_id_123')

        self._verify_rpc_connection_and_cast(rpc, mock_conn, exp_msg)

    def test_upgrade(self):
        mock_conn = mock()
        when(rpc).create_connection(new=True).thenReturn(mock_conn)
        when(mock_conn).create_consumer(any(), any(), any()).thenReturn(None)
        exp_msg = RpcMsgMatcher('upgrade')
        when(rpc).cast(any(), any(), exp_msg).thenReturn(None)

        self.api.upgrade()

        self._verify_rpc_connection_and_cast(rpc, mock_conn, exp_msg)

    def test_rpc_cast_with_consumer_exception(self):
        mock_conn = mock()
        when(rpc).create_connection(new=True).thenRaise(IOError('host down'))
        exp_msg = RpcMsgMatcher('prepare', 'memory_mb', 'databases', 'users',
                                'device_path', 'mount_point')

        with testtools.ExpectedException(exception.GuestError, '.* host down'):
            self.api.prepare('2048', 'db1', 'user1', '/dev/vdt', '/mnt/opt')

        verify(rpc).create_connection(new=True)
        verifyZeroInteractions(mock_conn)
        verify(rpc, never).cast(any(), any(), exp_msg)

    def _mock_rpc_call(self, exp_msg, resp=None):
        rpc.common = mock()
        when(rpc).call(any(), any(), exp_msg, any(int)).thenReturn(resp)

    def _verify_rpc_call(self, exp_msg):
        verify(rpc).call(any(), any(), exp_msg, any(int))

    def _mock_rpc_cast(self, exp_msg):
        when(rpc).cast(any(), any(), exp_msg).thenReturn(None)

    def _verify_rpc_cast(self, exp_msg):
        verify(rpc).cast(any(), any(), exp_msg)


class CastWithConsumerTest(testtools.TestCase):
    def setUp(self):
        super(CastWithConsumerTest, self).setUp()
        self.api = api.API(mock(), 'instance-id-x23d2d')

    def tearDown(self):
        super(CastWithConsumerTest, self).tearDown()
        unstub()

    def test__cast_with_consumer(self):
        mock_conn = mock()
        when(rpc).create_connection(new=True).thenReturn(mock_conn)
        when(mock_conn).create_consumer(any(), any(), any()).thenReturn(None)
        when(rpc).cast(any(), any(), any()).thenReturn(None)

        self.api._cast_with_consumer('fake_method_name', fake_param=1)

        verify(rpc).create_connection(new=True)
        verify(mock_conn).create_consumer(any(), None, fanout=False)
        verify(rpc).cast(any(), any(), any())


class RpcMsgMatcher(mockito.matchers.Matcher):
    def __init__(self, method, *args_dict):
        self.wanted_method = method
        self.wanted_dict = KeysEqual('version', 'method', 'args', 'namespace')
        self.args_dict = KeysEqual(*args_dict)

    def matches(self, arg):
        if self.wanted_method != arg['method']:
            raise Exception("Method does not match: %s != %s" %
                            (self.wanted_method, arg['method']))
            #return False
        if self.wanted_dict.match(arg) or self.args_dict.match(arg['args']):
            raise Exception("Args do not match: %s != %s" %
                            (self.args_dict, arg['args']))
            #return False
        return True

    def __repr__(self):
        return "<Dict: %s>" % self.wanted_dict
