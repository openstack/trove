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

import os

from mock import MagicMock
from mock import patch
from proboscis.asserts import assert_equal
import testtools
from testtools.matchers import Is, Equals, Not

from trove.common.context import TroveContext
from trove.common.exception import InsufficientSpaceForReplica
from trove.common.exception import ProcessExecutionError
from trove.common import instance as rd_instance
from trove.guestagent import backup
from trove.guestagent.common import operating_system
from trove.guestagent.datastore.mysql.manager import Manager
import trove.guestagent.datastore.mysql.service as dbaas
from trove.guestagent import dbaas as base_dbaas
from trove.guestagent import pkg as pkg
from trove.guestagent import volume
from trove.guestagent.volume import VolumeDevice


class GuestAgentManagerTest(testtools.TestCase):
    def setUp(self):
        super(GuestAgentManagerTest, self).setUp()
        self.context = TroveContext()
        self.manager = Manager()
        self.origin_MySqlAppStatus = dbaas.MySqlAppStatus
        self.origin_os_path_exists = os.path.exists
        self.origin_format = volume.VolumeDevice.format
        self.origin_migrate_data = volume.VolumeDevice.migrate_data
        self.origin_mount = volume.VolumeDevice.mount
        self.origin_unmount = volume.VolumeDevice.unmount
        self.origin_mount_points = volume.VolumeDevice.mount_points
        self.origin_stop_mysql = dbaas.MySqlApp.stop_db
        self.origin_start_mysql = dbaas.MySqlApp.start_mysql
        self.origin_update_overrides = dbaas.MySqlApp.update_overrides
        self.origin_pkg_is_installed = pkg.Package.pkg_is_installed
        self.origin_os_path_exists = os.path.exists
        self.origin_chown = operating_system.chown
        # set up common mock objects, etc. for replication testing
        self.patcher_gfvs = patch(
            'trove.guestagent.dbaas.get_filesystem_volume_stats')
        self.patcher_rs = patch(
            'trove.guestagent.datastore.mysql.manager.'
            'REPLICATION_STRATEGY_CLASS')
        self.mock_gfvs_class = self.patcher_gfvs.start()
        self.mock_rs_class = self.patcher_rs.start()
        self.repl_datastore_manager = 'mysql'
        self.repl_replication_strategy = 'MysqlGTIDReplication'

    def tearDown(self):
        super(GuestAgentManagerTest, self).tearDown()
        dbaas.MySqlAppStatus = self.origin_MySqlAppStatus
        os.path.exists = self.origin_os_path_exists
        volume.VolumeDevice.format = self.origin_format
        volume.VolumeDevice.migrate_data = self.origin_migrate_data
        volume.VolumeDevice.mount = self.origin_mount
        volume.VolumeDevice.unmount = self.origin_unmount
        volume.VolumeDevice.mount_points = self.origin_mount_points
        dbaas.MySqlApp.stop_db = self.origin_stop_mysql
        dbaas.MySqlApp.start_mysql = self.origin_start_mysql
        dbaas.MySqlApp.update_overrides = self.origin_update_overrides
        operating_system.chown = self.origin_chown
        pkg.Package.pkg_is_installed = self.origin_pkg_is_installed
        os.path.exists = self.origin_os_path_exists
        # teardown the replication mock objects
        self.patcher_gfvs.stop()
        self.patcher_rs.stop()

    def test_update_status(self):
        mock_status = MagicMock()
        dbaas.MySqlAppStatus.get = MagicMock(return_value=mock_status)
        self.manager.update_status(self.context)
        dbaas.MySqlAppStatus.get.assert_any_call()
        mock_status.update.assert_any_call()

    def test_create_database(self):
        dbaas.MySqlAdmin.create_database = MagicMock(return_value=None)
        self.manager.create_database(self.context, ['db1'])
        dbaas.MySqlAdmin.create_database.assert_any_call(['db1'])

    def test_create_user(self):
        dbaas.MySqlAdmin.create_user = MagicMock(return_value=None)
        self.manager.create_user(self.context, ['user1'])
        dbaas.MySqlAdmin.create_user.assert_any_call(['user1'])

    def test_delete_database(self):
        databases = ['db1']
        dbaas.MySqlAdmin.delete_database = MagicMock(return_value=None)
        self.manager.delete_database(self.context, databases)
        dbaas.MySqlAdmin.delete_database.assert_any_call(databases)

    def test_delete_user(self):
        user = ['user1']
        dbaas.MySqlAdmin.delete_user = MagicMock(return_value=None)
        self.manager.delete_user(self.context, user)
        dbaas.MySqlAdmin.delete_user.assert_any_call(user)

    def test_grant_access(self):
        username = "test_user"
        hostname = "test_host"
        databases = ["test_database"]
        dbaas.MySqlAdmin.grant_access = MagicMock(return_value=None)
        self.manager.grant_access(self.context,
                                  username,
                                  hostname,
                                  databases)

        dbaas.MySqlAdmin.grant_access.assert_any_call(username,
                                                      hostname,
                                                      databases)

    def test_list_databases(self):
        dbaas.MySqlAdmin.list_databases = MagicMock(return_value=['database1'])
        databases = self.manager.list_databases(self.context)
        self.assertThat(databases, Not(Is(None)))
        self.assertThat(databases, Equals(['database1']))
        dbaas.MySqlAdmin.list_databases.assert_any_call(None, None, False)

    def test_list_users(self):
        dbaas.MySqlAdmin.list_users = MagicMock(return_value=['user1'])
        users = self.manager.list_users(self.context)
        self.assertThat(users, Equals(['user1']))
        dbaas.MySqlAdmin.list_users.assert_any_call(None, None, False)

    def test_get_users(self):
        username = ['user1']
        hostname = ['host']
        dbaas.MySqlAdmin.get_user = MagicMock(return_value=['user1'])
        users = self.manager.get_user(self.context, username, hostname)
        self.assertThat(users, Equals(['user1']))
        dbaas.MySqlAdmin.get_user.assert_any_call(username, hostname)

    def test_enable_root(self):
        dbaas.MySqlAdmin.enable_root = MagicMock(return_value='user_id_stuff')
        user_id = self.manager.enable_root(self.context)
        self.assertThat(user_id, Is('user_id_stuff'))
        dbaas.MySqlAdmin.enable_root.assert_any_call()

    def test_is_root_enabled(self):
        dbaas.MySqlAdmin.is_root_enabled = MagicMock(return_value=True)
        is_enabled = self.manager.is_root_enabled(self.context)
        self.assertThat(is_enabled, Is(True))
        dbaas.MySqlAdmin.is_root_enabled.assert_any_call()

    def test_create_backup(self):
        backup.backup = MagicMock(return_value=None)
        # entry point
        Manager().create_backup(self.context, 'backup_id_123')
        # assertions
        backup.backup.assert_any_call(self.context, 'backup_id_123')

    def test_prepare_device_path_true(self):
        self._prepare_dynamic()

    def test_prepare_device_path_false(self):
        self._prepare_dynamic(device_path=None)

    def test_prepare_device_path_mounted(self):
        self._prepare_dynamic(is_mounted=True)

    def test_prepare_mysql_not_installed(self):
        self._prepare_dynamic(is_mysql_installed=False)

    def test_prepare_mysql_from_backup(self):
        self._prepare_dynamic(backup_id='backup_id_123abc')

    def test_prepare_mysql_from_backup_with_root(self):
        self._prepare_dynamic(backup_id='backup_id_123abc',
                              is_root_enabled=True)

    def test_prepare_mysql_with_root_password(self):
        self._prepare_dynamic(root_password='some_password')

    def test_prepare_mysql_with_users_and_databases(self):
        self._prepare_dynamic(databases=['db1'], users=['user1'])

    def test_prepare_mysql_with_snapshot(self):
        snapshot = {'replication_strategy': self.repl_replication_strategy,
                    'dataset': {'dataset_size': 1.0},
                    'config': None}
        self._prepare_dynamic(snapshot=snapshot)

    def _prepare_dynamic(self, device_path='/dev/vdb', is_mysql_installed=True,
                         backup_id=None, is_root_enabled=False,
                         root_password=None, overrides=None, is_mounted=False,
                         databases=None, users=None, snapshot=None):
        # covering all outcomes is starting to cause trouble here
        COUNT = 1 if device_path else 0
        backup_info = None
        if backup_id is not None:
            backup_info = {'id': backup_id,
                           'location': 'fake-location',
                           'type': 'InnoBackupEx',
                           'checksum': 'fake-checksum',
                           }

        # TODO(juice): this should stub an instance of the MySqlAppStatus
        mock_status = MagicMock()

        dbaas.MySqlAppStatus.get = MagicMock(return_value=mock_status)
        mock_status.begin_install = MagicMock(return_value=None)
        VolumeDevice.format = MagicMock(return_value=None)
        VolumeDevice.migrate_data = MagicMock(return_value=None)
        VolumeDevice.mount = MagicMock(return_value=None)
        mount_points = []
        if is_mounted:
            mount_points = ['/mnt']
        VolumeDevice.mount_points = MagicMock(return_value=mount_points)
        VolumeDevice.unmount = MagicMock(return_value=None)
        set_data_dir_patcher = patch.object(dbaas.MySqlApp, 'set_data_dir',
                                            return_value='/var/lib/mysql')
        self.addCleanup(set_data_dir_patcher.stop)
        set_data_dir_patcher.start()
        dbaas.MySqlApp.stop_db = MagicMock(return_value=None)
        dbaas.MySqlApp.start_mysql = MagicMock(return_value=None)
        dbaas.MySqlApp.update_overrides = MagicMock(return_value=None)
        dbaas.MySqlApp.install_if_needed = MagicMock(return_value=None)
        backup.restore = MagicMock(return_value=None)
        dbaas.MySqlApp.secure = MagicMock(return_value=None)
        dbaas.MySqlApp.secure_root = MagicMock(return_value=None)
        pkg.Package.pkg_is_installed = MagicMock(
            return_value=is_mysql_installed)
        dbaas.MySqlAdmin.is_root_enabled = MagicMock(
            return_value=is_root_enabled)
        dbaas.MySqlAdmin.create_user = MagicMock(return_value=None)
        dbaas.MySqlAdmin.create_database = MagicMock(return_value=None)
        dbaas.MySqlAdmin.enable_root = MagicMock(return_value=None)
        operating_system.chown = MagicMock(return_value=None)
        os.path.exists = MagicMock(return_value=True)
        mock_replication = MagicMock()
        mock_replication.enable_as_slave = MagicMock()
        self.mock_rs_class.return_value = mock_replication
        # invocation
        self.manager.prepare(context=self.context,
                             packages=None,
                             memory_mb='2048',
                             databases=databases,
                             users=users,
                             device_path=device_path,
                             mount_point='/var/lib/mysql',
                             backup_info=backup_info,
                             root_password=root_password,
                             overrides=overrides,
                             cluster_config=None,
                             snapshot=snapshot)

        # verification/assertion
        mock_status.begin_install.assert_any_call()

        self.assertEqual(COUNT, VolumeDevice.format.call_count)
        self.assertEqual(COUNT, VolumeDevice.migrate_data.call_count)
        self.assertEqual(COUNT, VolumeDevice.mount_points.call_count)
        self.assertEqual(COUNT, dbaas.MySqlApp.stop_db.call_count)
        if is_mounted:
            self.assertEqual(1, VolumeDevice.unmount.call_count)
        else:
            self.assertEqual(0, VolumeDevice.unmount.call_count)
        if backup_info:
            backup.restore.assert_any_call(self.context,
                                           backup_info,
                                           '/var/lib/mysql/data')
        dbaas.MySqlApp.install_if_needed.assert_any_call(None)
        # We don't need to make sure the exact contents are there
        dbaas.MySqlApp.secure.assert_any_call(None, None)
        dbaas.MySqlApp.secure_root.assert_any_call(
            secure_remote_root=not is_root_enabled)

        if root_password:
            dbaas.MySqlAdmin.enable_root.assert_any_call(root_password)
        if databases:
            dbaas.MySqlAdmin.create_database.assert_any_call(databases)
        else:
            self.assertFalse(dbaas.MySqlAdmin.create_database.called)

        if users:
            dbaas.MySqlAdmin.create_user.assert_any_call(users)
        else:
            self.assertFalse(dbaas.MySqlAdmin.create_user.called)

        if snapshot:
            self.assertEqual(1, mock_replication.enable_as_slave.call_count)
        else:
            self.assertEqual(0, mock_replication.enable_as_slave.call_count)

    def test_get_replication_snapshot(self):
        mock_status = MagicMock()
        dbaas.MySqlAppStatus.get = MagicMock(return_value=mock_status)

        snapshot_id = 'my_snapshot_id'
        log_position = 123456789
        master_ref = 'my_master'
        used_size = 1.0
        total_size = 2.0

        mock_replication = MagicMock()
        mock_replication.enable_as_master = MagicMock()
        mock_replication.snapshot_for_replication = MagicMock(
            return_value=(snapshot_id, log_position))
        mock_replication.get_master_ref = MagicMock(
            return_value=master_ref)
        self.mock_rs_class.return_value = mock_replication
        self.mock_gfvs_class.return_value = (
            {'used': used_size, 'total': total_size})

        expected_replication_snapshot = {
            'dataset': {
                'datastore_manager': self.repl_datastore_manager,
                'dataset_size': used_size,
                'volume_size': total_size,
                'snapshot_id': snapshot_id
            },
            'replication_strategy': self.repl_replication_strategy,
            'master': master_ref,
            'log_position': log_position
        }

        snapshot_info = None
        replica_source_config = None
        # entry point
        replication_snapshot = (
            self.manager.get_replication_snapshot(self.context, snapshot_info,
                                                  replica_source_config))
        # assertions
        self.assertEqual(expected_replication_snapshot, replication_snapshot)
        self.assertEqual(1, mock_replication.enable_as_master.call_count)
        self.assertEqual(
            1, mock_replication.snapshot_for_replication.call_count)
        self.assertEqual(1, mock_replication.get_master_ref.call_count)

    def test_attach_replication_slave_valid(self):
        mock_status = MagicMock()
        dbaas.MySqlAppStatus.get = MagicMock(return_value=mock_status)

        total_size = 2.0
        dataset_size = 1.0

        mock_replication = MagicMock()
        mock_replication.enable_as_slave = MagicMock()
        self.mock_rs_class.return_value = mock_replication
        self.mock_gfvs_class.return_value = {'total': total_size}

        snapshot = {'replication_strategy': self.repl_replication_strategy,
                    'dataset': {'dataset_size': dataset_size}}

        # entry point
        self.manager.attach_replica(self.context, snapshot, None)
        # assertions
        self.assertEqual(1, mock_replication.enable_as_slave.call_count)

    def test_attach_replication_slave_invalid(self):
        mock_status = MagicMock()
        dbaas.MySqlAppStatus.get = MagicMock(return_value=mock_status)

        total_size = 2.0
        dataset_size = 3.0

        mock_replication = MagicMock()
        mock_replication.enable_as_slave = MagicMock()
        self.mock_rs_class.return_value = mock_replication
        self.mock_gfvs_class.return_value = {'total': total_size}

        snapshot = {'replication_strategy': self.repl_replication_strategy,
                    'dataset': {'dataset_size': dataset_size}}

        # entry point
        self.assertRaises(InsufficientSpaceForReplica,
                          self.manager.attach_replica,
                          self.context, snapshot, None)
        # assertions
        self.assertEqual(0, mock_replication.enable_as_slave.call_count)

    def test_detach_replica(self):
        mock_status = MagicMock()
        dbaas.MySqlAppStatus.get = MagicMock(return_value=mock_status)

        mock_replication = MagicMock()
        mock_replication.detach_slave = MagicMock()
        self.mock_rs_class.return_value = mock_replication

        # entry point
        self.manager.detach_replica(self.context)
        # assertions
        self.assertEqual(1, mock_replication.detach_slave.call_count)

    def test_demote_replication_master(self):
        mock_status = MagicMock()
        dbaas.MySqlAppStatus.get = MagicMock(return_value=mock_status)

        mock_replication = MagicMock()
        mock_replication.demote_master = MagicMock()
        self.mock_rs_class.return_value = mock_replication

        # entry point
        self.manager.demote_replication_master(self.context)
        # assertions
        self.assertEqual(1, mock_replication.demote_master.call_count)

    def test_get_master_UUID(self):
        app = dbaas.MySqlApp(None)

        def test_case(slave_status, expected_value):
            with patch.object(dbaas.MySqlApp, '_get_slave_status',
                              return_value=slave_status):
                assert_equal(app._get_master_UUID(), expected_value)

        test_case({'Master_UUID': '2a5b-2064-32fb'}, '2a5b-2064-32fb')
        test_case({'Master_UUID': ''}, None)
        test_case({}, None)

    def test_get_last_txn(self):

        def test_case(gtid_list, expected_value):
            with patch.object(dbaas.MySqlApp, '_get_gtid_executed',
                              return_value=gtid_list):
                txn = self.manager.get_last_txn(self.context)
                assert_equal(txn, expected_value)

        with patch.object(dbaas.MySqlApp, '_get_slave_status',
                          return_value={'Master_UUID': '2a5b-2064-32fb'}):
            test_case('2a5b-2064-32fb:1', ('2a5b-2064-32fb', 1))
            test_case('2a5b-2064-32fb:1-5', ('2a5b-2064-32fb', 5))
            test_case('2a5b-2064-32fb:1,4b4-23:5', ('2a5b-2064-32fb', 1))
            test_case('4b4-23:5,2a5b-2064-32fb:1', ('2a5b-2064-32fb', 1))
            test_case('4b-23:5,2a5b-2064-32fb:1,25:3-4', ('2a5b-2064-32fb', 1))
            test_case('4b4-23:1-5,2a5b-2064-32fb:1-10', ('2a5b-2064-32fb', 10))

        with patch.object(dbaas.MySqlApp, '_get_slave_status',
                          return_value={'Master_UUID': ''}):
            test_case('2a5b-2064-32fb:1', (None, 0))

        with patch.object(dbaas.MySqlApp, '_get_slave_status',
                          return_value={}):
            test_case('2a5b-2064-32fb:1', (None, 0))

    def test_rpc_ping(self):
        self.assertTrue(self.manager.rpc_ping(self.context))

    def test_change_passwords(self):
        dbaas.MySqlAdmin.change_passwords = MagicMock(return_value=None)
        self.manager.change_passwords(
            self.context, [{'name': 'test_user', 'password': 'testpwd'}])
        dbaas.MySqlAdmin.change_passwords.assert_any_call(
            [{'name': 'test_user', 'password': 'testpwd'}])

    def test_update_attributes(self):
        dbaas.MySqlAdmin.update_attributes = MagicMock(return_value=None)
        self.manager.update_attributes(self.context, 'test_user', '%',
                                       {'password': 'testpwd'})
        dbaas.MySqlAdmin.update_attributes.assert_any_call('test_user', '%',
                                                           {'password':
                                                            'testpwd'})

    def test_reset_configuration(self):
        dbaas.MySqlAppStatus.get = MagicMock(return_value=MagicMock())
        dbaas.MySqlApp.reset_configuration = MagicMock(return_value=None)
        configuration = {'config_contents': 'some junk'}
        self.manager.reset_configuration(self.context, configuration)
        dbaas.MySqlAppStatus.get.assert_any_call()
        dbaas.MySqlApp.reset_configuration.assert_any_call({'config_contents':
                                                            'some junk'})

    def test_revoke_access(self):
        dbaas.MySqlAdmin.revoke_access = MagicMock(return_value=None)
        self.manager.revoke_access(self.context, 'test_user', '%', 'test_db')
        dbaas.MySqlAdmin.revoke_access.assert_any_call('test_user', '%',
                                                       'test_db')

    def test_list_access(self):
        dbaas.MySqlAdmin.list_access = MagicMock(return_value=['database1'])
        access = self.manager.list_access(self.context, 'test_user', '%')
        self.assertEqual(['database1'], access)
        dbaas.MySqlAdmin.list_access.assert_any_call('test_user', '%')

    def test_restart(self):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        dbaas.MySqlAppStatus.get = MagicMock(return_value=mock_status)
        dbaas.MySqlApp.restart = MagicMock(return_value=None)
        self.manager.restart(self.context)
        dbaas.MySqlAppStatus.get.assert_any_call()
        dbaas.MySqlApp.restart.assert_any_call()

    def test_start_db_with_conf_changes(self):
        mock_status = MagicMock()
        configuration = {'config_contents': 'some junk'}
        self.manager.appStatus = mock_status
        dbaas.MySqlAppStatus.get = MagicMock(return_value=mock_status)
        dbaas.MySqlApp.start_db_with_conf_changes = MagicMock(
            return_value=None)
        self.manager.start_db_with_conf_changes(self.context, configuration)
        dbaas.MySqlAppStatus.get.assert_any_call()
        dbaas.MySqlApp.start_db_with_conf_changes.assert_any_call(
            {'config_contents': 'some junk'})

    def test_stop_db(self):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        dbaas.MySqlAppStatus.get = MagicMock(return_value=mock_status)
        dbaas.MySqlApp.stop_db = MagicMock(return_value=None)
        self.manager.stop_db(self.context)
        dbaas.MySqlAppStatus.get.assert_any_call()
        dbaas.MySqlApp.stop_db.assert_any_call(do_not_start_on_reboot=False)

    def test_get_filesystem_stats(self):
        with patch.object(base_dbaas, 'get_filesystem_volume_stats'):
            self.manager.get_filesystem_stats(self.context, '/var/lib/mysql')
            base_dbaas.get_filesystem_volume_stats.assert_any_call(
                '/var/lib/mysql')

    def test_mount_volume(self):
        with patch.object(volume.VolumeDevice, 'mount', return_value=None):
            self.manager.mount_volume(self.context,
                                      device_path='/dev/vdb',
                                      mount_point='/var/lib/mysql')
            test_mount = volume.VolumeDevice.mount.call_args_list[0]
            test_mount.assert_called_with('/var/lib/mysql', False)

    def test_unmount_volume(self):
        with patch.object(volume.VolumeDevice, 'unmount', return_value=None):
            self.manager.unmount_volume(self.context, device_path='/dev/vdb')
            test_unmount = volume.VolumeDevice.unmount.call_args_list[0]
            test_unmount.assert_called_with('/var/lib/mysql')

    def test_resize_fs(self):
        with patch.object(volume.VolumeDevice, 'resize_fs', return_value=None):
            self.manager.resize_fs(self.context, device_path='/dev/vdb')
            test_resize_fs = volume.VolumeDevice.resize_fs.call_args_list[0]
            test_resize_fs.assert_called_with('/var/lib/mysql')

    def test_update_overrides(self):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        dbaas.MySqlAppStatus.get = MagicMock(return_value=mock_status)
        dbaas.MySqlApp.remove_overrides = MagicMock(return_value=None)
        dbaas.MySqlApp.update_overrides = MagicMock(return_value=None)
        self.manager.update_overrides(self.context, 'something_overrides')
        dbaas.MySqlAppStatus.get.assert_any_call()
        dbaas.MySqlApp.remove_overrides.assert_not_called()
        dbaas.MySqlApp.update_overrides.assert_any_call('something_overrides')

    def test_update_overrides_with_remove(self):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        dbaas.MySqlAppStatus.get = MagicMock(return_value=mock_status)
        dbaas.MySqlApp.remove_overrides = MagicMock(return_value=None)
        dbaas.MySqlApp.update_overrides = MagicMock(return_value=None)
        self.manager.update_overrides(self.context, 'something_overrides',
                                      True)
        dbaas.MySqlAppStatus.get.assert_any_call()
        dbaas.MySqlApp.remove_overrides.assert_any_call()
        dbaas.MySqlApp.update_overrides.assert_any_call('something_overrides')

    def test_apply_overrides(self):
        mock_status = MagicMock()
        override = {'some_key': 'some value'}
        self.manager.appStatus = mock_status
        dbaas.MySqlAppStatus.get = MagicMock(return_value=mock_status)
        dbaas.MySqlApp.apply_overrides = MagicMock(return_value=None)
        self.manager.apply_overrides(self.context, override)
        dbaas.MySqlAppStatus.get.assert_any_call()
        dbaas.MySqlApp.apply_overrides.assert_any_call({'some_key':
                                                        'some value'})

    def test_get_txn_count(self):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        dbaas.MySqlAppStatus.get = MagicMock(return_value=mock_status)
        dbaas.MySqlApp.get_txn_count = MagicMock(return_value=(9879))
        txn_count = self.manager.get_txn_count(self.context)
        self.assertEqual(9879, txn_count)
        dbaas.MySqlAppStatus.get.assert_any_call()
        dbaas.MySqlApp.get_txn_count.assert_any_call()

    def test_get_latest_txn_id(self):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        dbaas.MySqlAppStatus.get = MagicMock(return_value=mock_status)
        dbaas.MySqlApp.get_latest_txn_id = MagicMock(
            return_value=('2a5b-2064-32fb:1'))
        latest_txn_id = self.manager.get_latest_txn_id(self.context)
        self.assertEqual('2a5b-2064-32fb:1', latest_txn_id)
        dbaas.MySqlAppStatus.get.assert_any_call()
        dbaas.MySqlApp.get_latest_txn_id.assert_any_call()

    def test_wait_for_txn(self):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        dbaas.MySqlAppStatus.get = MagicMock(return_value=mock_status)
        dbaas.MySqlApp.wait_for_txn = MagicMock(return_value=None)
        self.manager.wait_for_txn(self.context, '4b4-23:5,2a5b-2064-32fb:1')
        dbaas.MySqlAppStatus.get.assert_any_call()
        dbaas.MySqlApp.wait_for_txn.assert_any_call('4b4-23:5,2a5b-2064-32fb:1'
                                                    )

    def test_make_read_only(self):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        dbaas.MySqlAppStatus.get = MagicMock(return_value=mock_status)
        dbaas.MySqlApp.make_read_only = MagicMock(return_value=None)
        self.manager.make_read_only(self.context, 'ON')
        dbaas.MySqlAppStatus.get.assert_any_call()
        dbaas.MySqlApp.make_read_only.assert_any_call('ON')

    def test_cleanup_source_on_replica_detach(self):
        mock_replication = MagicMock()
        mock_replication.cleanup_source_on_replica_detach = MagicMock()
        self.mock_rs_class.return_value = mock_replication
        snapshot = {'replication_strategy': self.repl_replication_strategy,
                    'dataset': {'dataset_size': '1.0'}}

        # entry point
        self.manager.cleanup_source_on_replica_detach(self.context, snapshot)
        # assertions
        self.assertEqual(
            1, mock_replication.cleanup_source_on_replica_detach.call_count)

    def test_get_replica_context(self):
        replication_user = {
            'name': 'repl_user',
            'password': 'repl_pwd'
        }
        master_ref = {
            'host': '1.2.3.4',
            'port': 3306
        }
        rep_info = {
            'master': master_ref,
            'log_position': {
                'replication_user': replication_user
            }
        }
        mock_replication = MagicMock()
        mock_replication.get_replica_context = MagicMock(return_value=rep_info)
        self.mock_rs_class.return_value = mock_replication

        # entry point
        replica_info = self.manager.get_replica_context(self.context)
        # assertions
        self.assertEqual(1, mock_replication.get_replica_context.call_count)
        self.assertEqual(rep_info, replica_info)

    def test_enable_as_master(self):
        mock_replication = MagicMock()
        mock_replication.enable_as_master = MagicMock()
        self.mock_rs_class.return_value = mock_replication

        # entry point
        self.manager.enable_as_master(self.context, None)
        # assertions
        self.assertEqual(mock_replication.enable_as_master.call_count, 1)

    def test__perform_restore(self):
        backup_info = {'id': 'backup_id_123abc',
                       'location': 'fake-location',
                       'type': 'InnoBackupEx',
                       'checksum': 'fake-checksum',
                       }
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        dbaas.MySqlAppStatus.get = MagicMock(return_value=mock_status)
        app = dbaas.MySqlApp(dbaas.MySqlAppStatus.get())
        backup.restore = MagicMock(side_effect=ProcessExecutionError)
        self.assertRaises(ProcessExecutionError,
                          self.manager._perform_restore, backup_info,
                          self.context, '/var/lib/mysql', app)
        app.status.set_status.assert_called_with(
            rd_instance.ServiceStatuses.FAILED)
