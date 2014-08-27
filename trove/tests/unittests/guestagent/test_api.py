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
import mock
import testtools
from testtools.matchers import KeysEqual, Is

import trove.common.context as context
from trove.common import exception
from trove.guestagent import api
import trove.openstack.common.rpc as rpc
import trove.common.rpc as trove_rpc

REPLICATION_SNAPSHOT = {'master': {'id': '123', 'host': '192.168.0.1',
                                   'port': 3306},
                        'dataset': {},
                        'binlog_position': 'binpos'}


def _mock_call_pwd_change(cmd, users=None):
    if users == 'dummy':
        return True
    else:
        raise BaseException("Test Failed")


def _mock_call(cmd, timerout, username=None, hostname=None,
               database=None, databases=None):
    #To check get_user, list_access, grant_access, revoke_access in cmd.
    if cmd in ('get_user', 'list_access', 'grant_access', 'revoke_access'):
        return True
    else:
        raise BaseException("Test Failed")


class ApiTest(testtools.TestCase):
    def setUp(self):
        super(ApiTest, self).setUp()
        self.context = context.TroveContext()
        self.guest = api.API(self.context, 0)
        self.guest._cast = _mock_call_pwd_change
        self.guest._call = _mock_call
        self.FAKE_ID = 'instance-id-x23d2d'
        self.api = api.API(self.context, self.FAKE_ID)

    def test_change_passwords(self):
        self.assertIsNone(self.guest.change_passwords("dummy"))

    def test_get_user(self):
        self.assertTrue(self.guest.get_user("dummyname", "dummyhost"))

    def test_list_access(self):
        self.assertTrue(self.guest.list_access("dummyname", "dummyhost"))

    def test_grant_access(self):
        self.assertTrue(self.guest.grant_access("dumname", "dumhost", "dumdb"))

    def test_revoke_access(self):
        self.assertTrue(self.guest.revoke_access("dumname", "dumhost",
                                                 "dumdb"))

    def test_get_routing_key(self):
        self.assertEqual('guestagent.' + self.FAKE_ID,
                         self.api._get_routing_key())

    @mock.patch('trove.guestagent.models.AgentHeartBeat')
    def test_check_for_heartbeat_positive(self, mock_agent):
        self.assertTrue(self.api._check_for_hearbeat())

    @mock.patch('trove.guestagent.models.AgentHeartBeat')
    def test_check_for_heartbeat_exception(self, mock_agent):
        # TODO(juice): maybe it would be ok to extend the test to validate
        # the is_active method on the heartbeat
        mock_agent.find_by.side_effect = exception.ModelNotFoundError("Uh Oh!")
        # execute
        self.assertRaises(exception.GuestTimeout, self.api._check_for_hearbeat)
        # validate
        self.assertEqual(mock_agent.is_active.call_count, 0)

    @mock.patch('trove.guestagent.models.AgentHeartBeat')
    def test_check_for_heartbeat_negative(self, mock_agent):
        # TODO(juice): maybe it would be ok to extend the test to validate
        # the is_active method on the heartbeat
        mock_agent.is_active.return_value = False
        self.assertRaises(exception.GuestTimeout, self.api._check_for_hearbeat)

    def test_delete_queue(self):
        trove_rpc.delete_queue = mock.Mock()
        # execute
        self.api.delete_queue()
        # verify
        trove_rpc.delete_queue.assert_called_with(self.context, mock.ANY)

    def test_create_user(self):
        rpc.cast = mock.Mock()
        exp_msg = RpcMsgMatcher('create_user', 'users')
        self.api.create_user('test_user')
        self._verify_rpc_cast(exp_msg, rpc.cast)

    def test_rpc_cast_exception(self):
        rpc.cast = mock.Mock(side_effect=IOError('host down'))
        exp_msg = RpcMsgMatcher('create_user', 'users')
        # execute
        with testtools.ExpectedException(exception.GuestError, '.* host down'):
            self.api.create_user('test_user')
        # verify
        self._verify_rpc_cast(exp_msg, rpc.cast)

    def test_list_users(self):
        exp_resp = ['user1', 'user2', 'user3']
        rpc.call = mock.Mock(return_value=exp_resp)
        exp_msg = RpcMsgMatcher('list_users', 'limit', 'marker',
                                'include_marker')
        # execute
        act_resp = self.api.list_users()
        # verify
        self.assertThat(act_resp, Is(exp_resp))
        self._verify_rpc_call(exp_msg, rpc.call)

    def test_rpc_call_exception(self):
        rpc.call = mock.Mock(side_effect=IOError('host_down'))
        exp_msg = RpcMsgMatcher('list_users', 'limit', 'marker',
                                'include_marker')
        # execute
        with testtools.ExpectedException(exception.GuestError,
                                         'An error occurred.*'):
            self.api.list_users()
        # verify
        self._verify_rpc_call(exp_msg, rpc.call)

    def test_delete_user(self):
        rpc.cast = mock.Mock()
        exp_msg = RpcMsgMatcher('delete_user', 'user')
        # execute
        self.api.delete_user('test_user')
        # verify
        self._verify_rpc_cast(exp_msg, rpc.cast)

    def test_create_database(self):
        rpc.cast = mock.Mock()
        exp_msg = RpcMsgMatcher('create_database', 'databases')
        # execute
        self.api.create_database(['db1', 'db2', 'db3'])
        # verify
        self._verify_rpc_cast(exp_msg, rpc.cast)

    def test_list_databases(self):
        exp_resp = ['db1', 'db2', 'db3']
        rpc.call = mock.Mock(return_value=exp_resp)
        exp_msg = RpcMsgMatcher('list_databases', 'limit', 'marker',
                                'include_marker')
        # execute
        resp = self.api.list_databases(limit=1, marker=2,
                                       include_marker=False)
        # verify
        self.assertThat(resp, Is(exp_resp))
        self._verify_rpc_call(exp_msg, rpc.call)

    def test_delete_database(self):
        rpc.cast = mock.Mock()
        exp_msg = RpcMsgMatcher('delete_database', 'database')
        # execute
        self.api.delete_database('test_database_name')
        # verify
        self._verify_rpc_cast(exp_msg, rpc.cast)

    def test_enable_root(self):
        rpc.call = mock.Mock(return_value=True)
        exp_msg = RpcMsgMatcher('enable_root')
        # execute
        self.assertThat(self.api.enable_root(), Is(True))
        # verify
        self._verify_rpc_call(exp_msg, rpc.call)

    def test_disable_root(self):
        rpc.call = mock.Mock(return_value=True)
        exp_msg = RpcMsgMatcher('disable_root')
        # execute
        self.assertThat(self.api.disable_root(), Is(True))
        # verify
        self._verify_rpc_call(exp_msg, rpc.call)

    def test_is_root_enabled(self):
        rpc.call = mock.Mock(return_value=False)
        exp_msg = RpcMsgMatcher('is_root_enabled')
        # execute
        self.assertThat(self.api.is_root_enabled(), Is(False))
        # verify
        self._verify_rpc_call(exp_msg, rpc.call)

    def test_get_hwinfo(self):
        rpc.call = mock.Mock(return_value='[blah]')
        exp_msg = RpcMsgMatcher('get_hwinfo')
        # execute
        self.assertThat(self.api.get_hwinfo(), Is('[blah]'))
        # verify
        self._verify_rpc_call(exp_msg, rpc.call)

    def test_get_diagnostics(self):
        rpc.call = mock.Mock(spec=rpc, return_value='[all good]')
        exp_msg = RpcMsgMatcher('get_diagnostics')
        # execute
        self.assertThat(self.api.get_diagnostics(), Is('[all good]'))
        # verify
        self._verify_rpc_call(exp_msg, rpc.call)

    def test_restart(self):
        rpc.call = mock.Mock()
        exp_msg = RpcMsgMatcher('restart')
        # execute
        self.api.restart()
        # verify
        self._verify_rpc_call(exp_msg, rpc.call)

    def test_start_db_with_conf_changes(self):
        rpc.call = mock.Mock()
        exp_msg = RpcMsgMatcher('start_db_with_conf_changes',
                                'config_contents')
        # execute
        self.api.start_db_with_conf_changes(None)
        # verify
        self._verify_rpc_call(exp_msg, rpc.call)

    def test_stop_db(self):
        rpc.call = mock.Mock()
        exp_msg = RpcMsgMatcher('stop_db', 'do_not_start_on_reboot')
        # execute
        self.api.stop_db(do_not_start_on_reboot=False)
        # verify
        self._verify_rpc_call(exp_msg, rpc.call)

    def test_get_volume_info(self):
        fake_resp = {'fake': 'resp'}
        rpc.call = mock.Mock(return_value=fake_resp)
        exp_msg = RpcMsgMatcher('get_filesystem_stats', 'fs_path')
        # execute
        self.assertThat(self.api.get_volume_info(), Is(fake_resp))
        # verify
        self._verify_rpc_call(exp_msg, rpc.call)

    def test_update_guest(self):
        rpc.call = mock.Mock()
        exp_msg = RpcMsgMatcher('update_guest')
        # execute
        self.api.update_guest()
        # verify
        self._verify_rpc_call(exp_msg, rpc.call)

    def test_create_backup(self):
        rpc.cast = mock.Mock()
        exp_msg = RpcMsgMatcher('create_backup', 'backup_info')
        # execute
        self.api.create_backup({'id': '123'})
        # verify
        self._verify_rpc_cast(exp_msg, rpc.cast)

    def test_update_overrides(self):
        rpc.cast = mock.Mock()
        exp_msg = RpcMsgMatcher('update_overrides', 'overrides', 'remove')
        # execute
        self.api.update_overrides('123')
        # verify
        self._verify_rpc_cast(exp_msg, rpc.cast)

    def test_apply_overrides(self):
        rpc.cast = mock.Mock()
        exp_msg = RpcMsgMatcher('apply_overrides', 'overrides')
        # execute
        self.api.apply_overrides('123')
        # verify
        self._verify_rpc_cast(exp_msg, rpc.cast)

    def test_get_replication_snapshot(self):
        exp_resp = REPLICATION_SNAPSHOT
        rpc.call = mock.Mock(return_value=exp_resp)
        exp_msg = RpcMsgMatcher('get_replication_snapshot', 'snapshot_info')
        # execute
        self.api.get_replication_snapshot({})
        # verify
        self._verify_rpc_call(exp_msg, rpc.call)

    def test_attach_replication_slave(self):
        rpc.cast = mock.Mock()
        exp_msg = RpcMsgMatcher('attach_replication_slave',
                                'snapshot', 'slave_config')
        # execute
        self.api.attach_replication_slave(REPLICATION_SNAPSHOT)
        # verify
        self._verify_rpc_cast(exp_msg, rpc.cast)

    def test_detach_replication_slave(self):
        rpc.call = mock.Mock()
        exp_msg = RpcMsgMatcher('detach_replication_slave')
        # execute
        self.api.detach_replication_slave()
        # verify
        self._verify_rpc_call(exp_msg, rpc.call)

    def test_demote_replication_master(self):
        rpc.call = mock.Mock()
        exp_msg = RpcMsgMatcher('demote_replication_master')
        # execute
        self.api.demote_replication_master()
        # verify
        self._verify_rpc_call(exp_msg, rpc.call)

    def _verify_rpc_connection_and_cast(self, rpc, mock_conn, exp_msg):
        rpc.create_connection.assert_called_with(new=True)
        mock_conn.create_consumer.assert_called_with(
            self.api._get_routing_key(), None, fanout=False)
        rpc.cast.assert_called_with(mock.ANY, mock.ANY, exp_msg)

    def test_prepare(self):
        mock_conn = mock.Mock()
        rpc.create_connection = mock.Mock(return_value=mock_conn)
        rpc.cast = mock.Mock()
        exp_msg = RpcMsgMatcher('prepare', 'memory_mb', 'packages',
                                'databases', 'users', 'device_path',
                                'mount_point', 'backup_info',
                                'config_contents', 'root_password',
                                'overrides')
        # execute
        self.api.prepare('2048', 'package1', 'db1', 'user1', '/dev/vdt',
                         '/mnt/opt', 'bkup-1232', 'cont', '1-2-3-4',
                         'override')
        # verify
        self._verify_rpc_connection_and_cast(rpc, mock_conn, exp_msg)

    def test_prepare_with_backup(self):
        mock_conn = mock.Mock()
        rpc.create_connection = mock.Mock(return_value=mock_conn)
        rpc.cast = mock.Mock()
        exp_msg = RpcMsgMatcher('prepare', 'memory_mb', 'packages',
                                'databases', 'users', 'device_path',
                                'mount_point', 'backup_info',
                                'config_contents', 'root_password',
                                'overrides')
        bkup = {'id': 'backup_id_123'}
        # execute
        self.api.prepare('2048', 'package1', 'db1', 'user1', '/dev/vdt',
                         '/mnt/opt', bkup, 'cont', '1-2-3-4',
                         'overrides')
        # verify
        self._verify_rpc_connection_and_cast(rpc, mock_conn, exp_msg)

    def test_upgrade(self):
        instance_version = "v1.0.1"
        strategy = "pip"
        location = "http://swift/trove-guestagent-v1.0.1.tar.gz"

        mock_conn = mock.Mock()
        rpc.create_connection = mock.Mock(return_value=mock_conn)
        rpc.cast = mock.Mock()
        exp_msg = RpcMsgMatcher(
            'upgrade', 'instance_version', 'location', 'metadata')

        # execute
        self.api.upgrade(instance_version, strategy, location)

        # verify
        self._verify_rpc_cast(exp_msg, rpc.cast)

    def test_rpc_cast_with_consumer_exception(self):
        mock_conn = mock.Mock()
        rpc.create_connection = mock.Mock(side_effect=IOError('host down'))
        rpc.cast = mock.Mock()
        # execute
        with testtools.ExpectedException(exception.GuestError, '.* host down'):
            self.api.prepare('2048', 'package1', 'db1', 'user1', '/dev/vdt',
                             '/mnt/opt')
        # verify
        rpc.create_connection.assert_called_with(new=True)
        self.assertThat(mock_conn.call_count, Is(0))
        self.assertThat(rpc.cast.call_count, Is(0))

    def _verify_rpc_call(self, exp_msg, mock_call=None):
        mock_call.assert_called_with(self.context, mock.ANY, exp_msg,
                                     mock.ANY)

    def _verify_rpc_cast(self, exp_msg, mock_cast=None):
        mock_cast.assert_called_with(mock.ANY,
                                     mock.ANY, exp_msg)


class CastWithConsumerTest(testtools.TestCase):
    def setUp(self):
        super(CastWithConsumerTest, self).setUp()
        self.context = context.TroveContext()
        self.api = api.API(self.context, 'instance-id-x23d2d')

    def test_cast_with_consumer(self):
        mock_conn = mock.Mock()
        rpc.create_connection = mock.Mock(return_value=mock_conn)
        rpc.cast = mock.Mock()
        # execute
        self.api._cast_with_consumer('fake_method_name', fake_param=1)
        # verify
        rpc.create_connection.assert_called_with(new=True)
        mock_conn.create_consumer.assert_called_with(mock.ANY, None,
                                                     fanout=False)
        rpc.cast.assert_called_with(self.context, mock.ANY, mock.ANY)


class RpcMsgMatcher(object):
    def __init__(self, method, *args_dict):
        self.wanted_method = method
        self.wanted_dict = KeysEqual('version', 'method', 'args', 'namespace')
        args_dict = args_dict or [{}]
        self.args_dict = KeysEqual(*args_dict)

    def __eq__(self, arg):
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
