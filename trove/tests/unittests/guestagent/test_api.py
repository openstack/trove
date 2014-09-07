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
from eventlet import Timeout
import mock
import testtools
from testtools.matchers import Is

import trove.common.context as context
from trove.common import exception
from trove.guestagent import api
from trove import rpc

REPLICATION_SNAPSHOT = {'master': {'id': '123', 'host': '192.168.0.1',
                                   'port': 3306},
                        'dataset': {},
                        'binlog_position': 'binpos'}

RPC_API_VERSION = '1.0'


def _mock_call_pwd_change(cmd, version=None, users=None):
    if users == 'dummy':
        return True
    else:
        raise BaseException("Test Failed")


def _mock_call(cmd, timeout, version=None, username=None, hostname=None,
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
        rpc.get_client = mock.Mock()
        self.guest = api.API(self.context, 0)
        self.guest._cast = _mock_call_pwd_change
        self.guest._call = _mock_call
        self.api = api.API(self.context, "instance-id-x23d2d")
        self._mock_rpc_client()

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
        self.assertEqual('guestagent.instance-id-x23d2d',
                         self.api._get_routing_key())

    def test_create_user(self):
        self.api.create_user('test_user')

        self._verify_rpc_prepare_before_cast()
        self._verify_cast('create_user', users='test_user')

    def test_api_cast_exception(self):
        self.call_context.cast.side_effect = IOError('host down')
        self.assertRaises(exception.GuestError, self.api.create_user,
                          'test_user')

    def test_api_call_exception(self):
        self.call_context.call.side_effect = IOError('host_down')
        self.assertRaises(exception.GuestError, self.api.list_users)

    def test_api_call_timeout(self):
        self.call_context.call.side_effect = Timeout()
        self.assertRaises(exception.GuestTimeout, self.api.restart)

    def test_list_users(self):
        exp_resp = ['user1', 'user2', 'user3']
        self.call_context.call.return_value = exp_resp

        resp = self.api.list_users()

        self._verify_rpc_prepare_before_call()
        self._verify_call('list_users', limit=None, marker=None,
                          include_marker=False)
        self.assertEqual(exp_resp, resp)

    def test_delete_user(self):
        self.api.delete_user('test_user')

        self._verify_rpc_prepare_before_cast()
        self._verify_cast('delete_user', user='test_user')

    def test_create_database(self):
        databases = ['db1', 'db2', 'db3']
        self.api.create_database(databases)

        self._verify_rpc_prepare_before_cast()
        self.call_context.cast.assert_called_once_with(
            self.context, "create_database", databases=databases)

    def test_list_databases(self):
        exp_resp = ['db1', 'db2', 'db3']
        self.call_context.call.return_value = exp_resp

        resp = self.api.list_databases(
            limit=1, marker=2, include_marker=False)

        self._verify_rpc_prepare_before_call()
        self._verify_call("list_databases", limit=1, marker=2,
                          include_marker=False)
        self.assertEqual(exp_resp, resp)

    def test_delete_database(self):
        self.api.delete_database('test_database_name')

        self._verify_rpc_prepare_before_cast()
        self._verify_cast("delete_database", database='test_database_name')

    def test_enable_root(self):
        self.call_context.call.return_value = True

        resp = self.api.enable_root()

        self._verify_rpc_prepare_before_call()
        self._verify_call('enable_root')
        self.assertThat(resp, Is(True))

    def test_disable_root(self):
        self.call_context.call.return_value = True

        resp = self.api.disable_root()

        self._verify_rpc_prepare_before_call()
        self._verify_call('disable_root')
        self.assertThat(resp, Is(True))

    def test_is_root_enabled(self):
        self.call_context.call.return_value = False

        resp = self.api.is_root_enabled()

        self._verify_rpc_prepare_before_call()
        self._verify_call('is_root_enabled')
        self.assertThat(resp, Is(False))

    def test_get_hwinfo(self):
        self.call_context.call.return_value = '[blah]'

        resp = self.api.get_hwinfo()

        self._verify_rpc_prepare_before_call()
        self._verify_call('get_hwinfo')
        self.assertThat(resp, Is('[blah]'))

    def test_get_diagnostics(self):
        self.call_context.call.return_value = '[all good]'

        resp = self.api.get_diagnostics()

        self._verify_rpc_prepare_before_call()
        self._verify_call('get_diagnostics')
        self.assertThat(resp, Is('[all good]'))

    def test_restart(self):
        self.api.restart()

        self._verify_rpc_prepare_before_call()
        self._verify_call('restart')

    def test_start_db_with_conf_changes(self):
        self.api.start_db_with_conf_changes(None)

        self._verify_rpc_prepare_before_call()
        self._verify_call('start_db_with_conf_changes', config_contents=None)

    def test_stop_db(self):
        self.api.stop_db(do_not_start_on_reboot=False)

        self._verify_rpc_prepare_before_call()
        self._verify_call('stop_db', do_not_start_on_reboot=False)

    def test_get_volume_info(self):
        exp_resp = {'fake': 'resp'}
        self.call_context.call.return_value = exp_resp

        resp = self.api.get_volume_info()

        self._verify_rpc_prepare_before_call()
        self._verify_call('get_filesystem_stats', fs_path=None)
        self.assertThat(resp, Is(exp_resp))

    def test_update_guest(self):
        self.api.update_guest()

        self._verify_rpc_prepare_before_call()
        self._verify_call('update_guest')

    def test_create_backup(self):
        self.api.create_backup({'id': '123'})

        self._verify_rpc_prepare_before_cast()
        self._verify_cast('create_backup', backup_info={'id': '123'})

    def test_update_overrides(self):
        self.api.update_overrides('123')

        self._verify_rpc_prepare_before_cast()
        self._verify_cast('update_overrides', overrides='123', remove=False)

    def test_apply_overrides(self):
        self.api.apply_overrides('123')

        self._verify_rpc_prepare_before_cast()
        self._verify_cast('apply_overrides', overrides='123')

    def test_get_replication_snapshot(self):
        # execute
        self.api.get_replication_snapshot({})
        # verify
        self._verify_rpc_prepare_before_call()
        self._verify_call('get_replication_snapshot', snapshot_info={},
                          replica_source_config=None)

    def test_attach_replication_slave(self):
        # execute
        self.api.attach_replication_slave(REPLICATION_SNAPSHOT)
        # verify
        self._verify_rpc_prepare_before_cast()
        self._verify_cast('attach_replication_slave',
                          snapshot=REPLICATION_SNAPSHOT, slave_config=None)

    def test_detach_replica(self):
        # execute
        self.api.detach_replica()
        # verify
        self._verify_rpc_prepare_before_call()
        self._verify_call('detach_replica')

    def test_demote_replication_master(self):
        # execute
        self.api.demote_replication_master()
        # verify
        self._verify_rpc_prepare_before_call()
        self._verify_call('demote_replication_master')

    def test_prepare(self):
        self.api._create_guest_queue = mock.Mock()
        self.api.prepare('2048', 'package1', 'db1', 'user1', '/dev/vdt',
                         '/mnt/opt', None, 'cont', '1-2-3-4',
                         'override', {'id': '2-3-4-5'})

        self._verify_rpc_prepare_before_cast()
        self._verify_cast(
            'prepare', packages=['package1'], databases='db1',
            memory_mb='2048', users='user1', device_path='/dev/vdt',
            mount_point='/mnt/opt', backup_info=None,
            config_contents='cont', root_password='1-2-3-4',
            overrides='override', cluster_config={'id': '2-3-4-5'})

    def test_prepare_with_backup(self):
        self.api._create_guest_queue = mock.Mock()
        backup = {'id': 'backup_id_123'}
        self.api.prepare('2048', 'package1', 'db1', 'user1', '/dev/vdt',
                         '/mnt/opt', backup, 'cont', '1-2-3-4',
                         'overrides', {"id": "2-3-4-5"})

        self._verify_rpc_prepare_before_cast()
        self._verify_cast(
            'prepare', packages=['package1'], databases='db1',
            memory_mb='2048', users='user1', device_path='/dev/vdt',
            mount_point='/mnt/opt', backup_info=backup,
            config_contents='cont', root_password='1-2-3-4',
            overrides='overrides', cluster_config={'id': '2-3-4-5'})

    def test_upgrade(self):
        instance_version = "v1.0.1"
        location = "http://swift/trove-guestagent-v1.0.1.tar.gz"
        # execute
        self.api.upgrade(instance_version, location)
        # verify
        self._verify_rpc_prepare_before_cast()
        self._verify_cast(
            'upgrade', instance_version=instance_version,
            location=location, metadata=None)

    def _verify_rpc_prepare_before_call(self):
        self.api.client.prepare.assert_called_once_with(
            version=RPC_API_VERSION, timeout=mock.ANY)

    def _verify_rpc_prepare_before_cast(self):
        self.api.client.prepare.assert_called_once_with(
            version=RPC_API_VERSION)

    def _verify_cast(self, *args, **kwargs):
        self.call_context.cast.assert_called_once_with(self.context, *args,
                                                       **kwargs)

    def _verify_call(self, *args, **kwargs):
        self.call_context.call.assert_called_once_with(self.context, *args,
                                                       **kwargs)

    def _mock_rpc_client(self):
        self.call_context = mock.Mock()
        self.api.client.prepare = mock.Mock(return_value=self.call_context)
        self.call_context.call = mock.Mock()
        self.call_context.cast = mock.Mock()


class ApiStrategyTest(testtools.TestCase):

    @mock.patch('trove.guestagent.api.API.__init__',
                mock.Mock(return_value=None))
    def test_guest_client(self):
        from trove.common.remote import guest_client
        client = guest_client(mock.Mock(), mock.Mock(), 'mongodb')
        self.assertFalse(hasattr(client, 'add_config_servers2'))
        self.assertTrue(callable(client.add_config_servers))
