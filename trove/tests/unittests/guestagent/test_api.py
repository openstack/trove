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
import oslo_messaging as messaging
from oslo_messaging.rpc.client import RemoteError
from testtools.matchers import Is

import trove.common.context as context
from trove.common import exception
from trove.common.remote import guest_client
from trove.guestagent import api
from trove import rpc
from trove.tests.unittests import trove_testtools

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
    # To check get_user, list_access, grant_access, revoke_access in cmd.
    if cmd in ('get_user', 'list_access', 'grant_access', 'revoke_access'):
        return True
    else:
        raise BaseException("Test Failed")


class ApiTest(trove_testtools.TestCase):
    @mock.patch.object(rpc, 'get_client')
    def setUp(self, *args):
        super(ApiTest, self).setUp()
        self.context = context.TroveContext()
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

    def test_update_attributes(self):
        self.api.update_attributes('test_user', '%', {'name': 'new_user'})

        self._verify_rpc_prepare_before_cast()
        self._verify_cast('update_attributes', username='test_user',
                          hostname='%', user_attrs={'name': 'new_user'})

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

    def test_api_cast_remote_error(self):
        self.call_context.cast.side_effect = RemoteError('Error')
        self.assertRaises(exception.GuestError, self.api.delete_database,
                          'test_db')

    def test_api_call_remote_error(self):
        self.call_context.call.side_effect = RemoteError('Error')
        self.assertRaises(exception.GuestError, self.api.stop_db)

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

    def test_rpc_ping(self):
        # execute
        self.api.rpc_ping()
        # verify
        self._verify_rpc_prepare_before_call()
        self._verify_call('rpc_ping')

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

    def test_reset_configuration(self):
        # execute
        self.api.reset_configuration({'config_contents': 'some junk'})
        # verify
        self._verify_rpc_prepare_before_call()
        self._verify_call('reset_configuration',
                          configuration={'config_contents': 'some junk'})

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

    def test_unmount_volume(self):
        # execute
        self.api.unmount_volume('/dev/vdb', '/var/lib/mysql')
        # verify
        self._verify_rpc_prepare_before_call()
        self._verify_call('unmount_volume', device_path='/dev/vdb',
                          mount_point='/var/lib/mysql')

    def test_mount_volume(self):
        # execute
        self.api.mount_volume('/dev/vdb', '/var/lib/mysql')
        # verify
        self._verify_rpc_prepare_before_call()
        self._verify_call('mount_volume', device_path='/dev/vdb',
                          mount_point='/var/lib/mysql')

    def test_resize_fs(self):
        # execute
        self.api.resize_fs('/dev/vdb', '/var/lib/mysql')
        # verify
        self._verify_rpc_prepare_before_call()
        self._verify_call('resize_fs', device_path='/dev/vdb',
                          mount_point='/var/lib/mysql')

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
        self._verify_call('detach_replica', for_failover=False)

    def test_get_replica_context(self):
        # execute
        self.api.get_replica_context()
        # verify
        self._verify_rpc_prepare_before_call()
        self._verify_call('get_replica_context')

    def test_attach_replica(self):
        # execute
        self.api.attach_replica(REPLICATION_SNAPSHOT, slave_config=None)
        # verify
        self._verify_rpc_prepare_before_call()
        self._verify_call('attach_replica',
                          replica_info=REPLICATION_SNAPSHOT, slave_config=None)

    def test_make_read_only(self):
        # execute
        self.api.make_read_only(True)
        # verify
        self._verify_rpc_prepare_before_call()
        self._verify_call('make_read_only', read_only=True)

    def test_enable_as_master(self):
        # execute
        self.api.enable_as_master({})
        # verify
        self._verify_rpc_prepare_before_call()
        self._verify_call('enable_as_master', replica_source_config={})

    def test_get_txn_count(self):
        # execute
        self.api.get_txn_count()
        # verify
        self._verify_rpc_prepare_before_call()
        self._verify_call('get_txn_count')

    def test_get_last_txn(self):
        # execute
        self.api.get_last_txn()
        # verify
        self._verify_rpc_prepare_before_call()
        self._verify_call('get_last_txn')

    def test_get_latest_txn_id(self):
        # execute
        self.api.get_latest_txn_id()
        # verify
        self._verify_rpc_prepare_before_call()
        self._verify_call('get_latest_txn_id')

    def test_wait_for_txn(self):
        # execute
        self.api.wait_for_txn("")
        # verify
        self._verify_rpc_prepare_before_call()
        self._verify_call('wait_for_txn', txn="")

    def test_cleanup_source_on_replica_detach(self):
        # execute
        self.api.cleanup_source_on_replica_detach({'replication_user':
                                                   'test_user'})
        # verify
        self._verify_rpc_prepare_before_call()
        self._verify_call('cleanup_source_on_replica_detach',
                          replica_info={'replication_user': 'test_user'})

    def test_demote_replication_master(self):
        # execute
        self.api.demote_replication_master()
        # verify
        self._verify_rpc_prepare_before_call()
        self._verify_call('demote_replication_master')

    @mock.patch.object(messaging, 'Target')
    @mock.patch.object(rpc, 'get_server')
    def test_prepare(self, *args):
        self.api.prepare('2048', 'package1', 'db1', 'user1', '/dev/vdt',
                         '/mnt/opt', None, 'cont', '1-2-3-4',
                         'override', {'id': '2-3-4-5'})

        self._verify_rpc_prepare_before_cast()
        self._verify_cast(
            'prepare', packages=['package1'], databases='db1',
            memory_mb='2048', users='user1', device_path='/dev/vdt',
            mount_point='/mnt/opt', backup_info=None,
            config_contents='cont', root_password='1-2-3-4',
            overrides='override', cluster_config={'id': '2-3-4-5'},
            snapshot=None)

    @mock.patch.object(messaging, 'Target')
    @mock.patch.object(rpc, 'get_server')
    def test_prepare_with_backup(self, *args):
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
            overrides='overrides', cluster_config={'id': '2-3-4-5'},
            snapshot=None)

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


class ApiStrategyTest(trove_testtools.TestCase):

    @mock.patch('trove.guestagent.api.API.__init__',
                mock.Mock(return_value=None))
    def test_guest_client_mongodb(self):
        client = guest_client(mock.Mock(), mock.Mock(), 'mongodb')
        self.assertFalse(hasattr(client, 'add_config_servers2'))
        self.assertTrue(callable(client.add_config_servers))

    @mock.patch('trove.guestagent.api.API.__init__',
                mock.Mock(return_value=None))
    def test_guest_client_vertica(self):
        client = guest_client(mock.Mock(), mock.Mock(), 'vertica')
        self.assertFalse(hasattr(client, 'get_public_keys2'))
        self.assertTrue(callable(client.get_public_keys))
