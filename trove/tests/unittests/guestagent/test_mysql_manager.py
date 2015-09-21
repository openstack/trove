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

from mock import DEFAULT
from mock import MagicMock
from mock import patch
from proboscis.asserts import assert_equal
from testtools.matchers import Is, Equals, Not

from trove.common.exception import InsufficientSpaceForReplica
from trove.common.exception import ProcessExecutionError
from trove.common import instance as rd_instance
from trove.guestagent import backup
from trove.guestagent.common import operating_system
# TODO(atomic77) The test cases should be made configurable
# to make it easier to test the various derived datastores.
from trove.guestagent.datastore.mysql.manager import Manager
import trove.guestagent.datastore.mysql.service as dbaas
from trove.guestagent import dbaas as base_dbaas
from trove.guestagent import pkg as pkg
from trove.guestagent import volume
from trove.guestagent.volume import VolumeDevice
from trove.tests.unittests import trove_testtools


class GuestAgentManagerTest(trove_testtools.TestCase):

    def setUp(self):
        super(GuestAgentManagerTest, self).setUp()
        self.context = trove_testtools.TroveTestContext(self)
        self.replication_strategy = 'MysqlGTIDReplication'
        self.patch_rs = patch(
            'trove.guestagent.strategies.replication.get_strategy',
            return_value=self.replication_strategy)
        self.mock_rs = self.patch_rs.start()
        self.addCleanup(self.patch_rs.stop)
        self.manager = Manager()
        self.origin_MySqlAppStatus = dbaas.MySqlAppStatus.get
        self.origin_os_path_exists = os.path.exists
        self.origin_format = volume.VolumeDevice.format
        self.origin_migrate_data = volume.VolumeDevice.migrate_data
        self.origin_mount = volume.VolumeDevice.mount
        self.origin_unmount = volume.VolumeDevice.unmount
        self.origin_mount_points = volume.VolumeDevice.mount_points
        self.origin_stop_mysql = dbaas.MySqlApp.stop_db
        self.origin_start_mysql = dbaas.MySqlApp.start_mysql
        self.origin_update_overrides = dbaas.MySqlApp.update_overrides
        self.origin_install_if_needed = dbaas.MySqlApp.install_if_needed
        self.origin_secure = dbaas.MySqlApp.secure
        self.origin_secure_root = dbaas.MySqlApp.secure_root
        self.origin_pkg_is_installed = pkg.Package.pkg_is_installed
        self.origin_os_path_exists = os.path.exists
        self.origin_chown = operating_system.chown
        # set up common mock objects, etc. for replication testing
        self.patcher_gfvs = patch(
            'trove.guestagent.dbaas.get_filesystem_volume_stats')
        self.patcher_rs = patch(
            'trove.guestagent.strategies.replication.get_instance')
        self.mock_gfvs_class = self.patcher_gfvs.start()
        self.mock_rs_class = self.patcher_rs.start()

    def tearDown(self):
        super(GuestAgentManagerTest, self).tearDown()
        dbaas.MySqlAppStatus.get = self.origin_MySqlAppStatus
        os.path.exists = self.origin_os_path_exists
        volume.VolumeDevice.format = self.origin_format
        volume.VolumeDevice.migrate_data = self.origin_migrate_data
        volume.VolumeDevice.mount = self.origin_mount
        volume.VolumeDevice.unmount = self.origin_unmount
        volume.VolumeDevice.mount_points = self.origin_mount_points
        dbaas.MySqlApp.stop_db = self.origin_stop_mysql
        dbaas.MySqlApp.start_mysql = self.origin_start_mysql
        dbaas.MySqlApp.update_overrides = self.origin_update_overrides
        dbaas.MySqlApp.install_if_needed = self.origin_install_if_needed
        dbaas.MySqlApp.secure = self.origin_secure
        dbaas.MySqlApp.secure_root = self.origin_secure_root
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

    @patch.object(dbaas.MySqlAdmin, 'create_database')
    def test_create_database(self, create_db_mock):
        self.manager.create_database(self.context, ['db1'])
        create_db_mock.assert_any_call(['db1'])

    @patch.object(dbaas.MySqlAdmin, 'create_user')
    def test_create_user(self, create_user_mock):
        self.manager.create_user(self.context, ['user1'])
        create_user_mock.assert_any_call(['user1'])

    @patch.object(dbaas.MySqlAdmin, 'delete_database')
    def test_delete_database(self, delete_database_mock):
        databases = ['db1']
        self.manager.delete_database(self.context, databases)
        delete_database_mock.assert_any_call(databases)

    @patch.object(dbaas.MySqlAdmin, 'delete_user')
    def test_delete_user(self, delete_user_mock):
        user = ['user1']
        self.manager.delete_user(self.context, user)
        delete_user_mock.assert_any_call(user)

    @patch.object(dbaas.MySqlAdmin, 'grant_access')
    def test_grant_access(self, grant_access_mock):
        username = "test_user"
        hostname = "test_host"
        databases = ["test_database"]
        self.manager.grant_access(self.context,
                                  username,
                                  hostname,
                                  databases)

        grant_access_mock.assert_any_call(username,
                                          hostname,
                                          databases)

    @patch.object(dbaas.MySqlAdmin, 'list_databases',
                  return_value=['database1'])
    def test_list_databases(self, list_databases_mock):
        databases = self.manager.list_databases(self.context)
        self.assertThat(databases, Not(Is(None)))
        self.assertThat(databases, Equals(list_databases_mock.return_value))
        list_databases_mock.assert_any_call(None, None, False)

    @patch.object(dbaas.MySqlAdmin, 'list_users', return_value=['user1'])
    def test_list_users(self, list_users_mock):
        users = self.manager.list_users(self.context)
        self.assertThat(users, Equals(list_users_mock.return_value))
        dbaas.MySqlAdmin.list_users.assert_any_call(None, None, False)

    @patch.object(dbaas.MySqlAdmin, 'get_user', return_value=['user1'])
    def test_get_users(self, get_user_mock):
        username = ['user1']
        hostname = ['host']
        users = self.manager.get_user(self.context, username, hostname)
        self.assertThat(users, Equals(get_user_mock.return_value))
        get_user_mock.assert_any_call(username, hostname)

    @patch.object(dbaas.MySqlAdmin, 'enable_root',
                  return_value='user_id_stuff')
    def test_enable_root(self, enable_root_mock):
        user_id = self.manager.enable_root(self.context)
        self.assertThat(user_id, Is(enable_root_mock.return_value))
        enable_root_mock.assert_any_call()

    @patch.object(dbaas.MySqlAdmin, 'disable_root')
    def test_disable_root(self, disable_root_mock):
        self.manager.disable_root(self.context)
        disable_root_mock.assert_any_call()

    @patch.object(dbaas.MySqlAdmin, 'is_root_enabled', return_value=True)
    def test_is_root_enabled(self, is_root_enabled_mock):
        is_enabled = self.manager.is_root_enabled(self.context)
        self.assertThat(is_enabled, Is(is_root_enabled_mock.return_value))
        is_root_enabled_mock.assert_any_call()

    @patch.object(backup, 'backup')
    def test_create_backup(self, backup_mock):
        # entry point
        Manager().create_backup(self.context, 'backup_id_123')
        # assertions
        backup_mock.assert_any_call(self.context, 'backup_id_123')

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
        snapshot = {'replication_strategy': self.replication_strategy,
                    'dataset': {'dataset_size': 1.0},
                    'config': None}
        total_size = snapshot['dataset']['dataset_size'] + 1
        self.mock_gfvs_class.return_value = {'total': total_size}
        self._prepare_dynamic(snapshot=snapshot)

    @patch.multiple(dbaas.MySqlAdmin,
                    create_user=DEFAULT,
                    create_database=DEFAULT,
                    enable_root=DEFAULT)
    @patch.object(backup, 'restore')
    def _prepare_dynamic(self, restore_mock, create_user, create_database,
                         enable_root,
                         device_path='/dev/vdb',
                         is_mysql_installed=True,
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
        dbaas.MySqlApp.secure = MagicMock(return_value=None)
        dbaas.MySqlApp.secure_root = MagicMock(return_value=None)
        pkg.Package.pkg_is_installed = MagicMock(
            return_value=is_mysql_installed)
        operating_system.chown = MagicMock(return_value=None)
        os.path.exists = MagicMock(return_value=True)
        mock_replication = MagicMock()
        mock_replication.enable_as_slave = MagicMock()
        self.mock_rs_class.return_value = mock_replication

        with patch.object(dbaas.MySqlAdmin, 'is_root_enabled',
                          return_value=is_root_enabled):
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
            restore_mock.assert_any_call(self.context,
                                         backup_info,
                                         '/var/lib/mysql/data')
        dbaas.MySqlApp.install_if_needed.assert_any_call(None)
        # We don't need to make sure the exact contents are there
        dbaas.MySqlApp.secure.assert_any_call(None)
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
                'datastore_manager': self.manager.manager,
                'dataset_size': used_size,
                'volume_size': total_size,
                'snapshot_id': snapshot_id
            },
            'replication_strategy': self.replication_strategy,
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

        snapshot = {'replication_strategy': self.replication_strategy,
                    'dataset': {'dataset_size': dataset_size}}

        # entry point
        self.manager.attach_replica(self.context, snapshot, None)
        # assertions
        self.assertEqual(1, mock_replication.enable_as_slave.call_count)

    @patch('trove.guestagent.datastore.mysql_common.manager.LOG')
    def test_attach_replication_slave_invalid(self, *args):
        mock_status = MagicMock()
        dbaas.MySqlAppStatus.get = MagicMock(return_value=mock_status)

        total_size = 2.0
        dataset_size = 3.0

        mock_replication = MagicMock()
        mock_replication.enable_as_slave = MagicMock()
        self.mock_rs_class.return_value = mock_replication
        self.mock_gfvs_class.return_value = {'total': total_size}

        snapshot = {'replication_strategy': self.replication_strategy,
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

    @patch.object(dbaas.MySqlAdmin, 'change_passwords')
    def test_change_passwords(self, change_passwords_mock):
        self.manager.change_passwords(
            self.context, [{'name': 'test_user', 'password': 'testpwd'}])
        change_passwords_mock.assert_any_call(
            [{'name': 'test_user', 'password': 'testpwd'}])

    @patch.object(dbaas.MySqlAdmin, 'update_attributes')
    def test_update_attributes(self, update_attr_mock):
        self.manager.update_attributes(self.context, 'test_user', '%',
                                       {'password': 'testpwd'})
        update_attr_mock.assert_any_call('test_user', '%',
                                         {'password':
                                          'testpwd'})

    @patch.object(dbaas.MySqlApp, 'reset_configuration')
    def test_reset_configuration(self, reset_config_mock):
        dbaas.MySqlAppStatus.get = MagicMock(return_value=MagicMock())
        configuration = {'config_contents': 'some junk'}
        self.manager.reset_configuration(self.context, configuration)
        dbaas.MySqlAppStatus.get.assert_any_call()
        reset_config_mock.assert_any_call({'config_contents': 'some junk'})

    @patch.object(dbaas.MySqlAdmin, 'revoke_access')
    def test_revoke_access(self, revoke_access_mock):
        self.manager.revoke_access(self.context, 'test_user', '%', 'test_db')
        revoke_access_mock.assert_any_call('test_user', '%', 'test_db')

    @patch.object(dbaas.MySqlAdmin, 'list_access', return_value=['database1'])
    def test_list_access(self, list_access_mock):
        access = self.manager.list_access(self.context, 'test_user', '%')
        self.assertEqual(list_access_mock.return_value, access)
        list_access_mock.assert_any_call('test_user', '%')

    @patch.object(dbaas.MySqlApp, 'restart')
    def test_restart(self, restart_mock):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        dbaas.MySqlAppStatus.get = MagicMock(return_value=mock_status)
        self.manager.restart(self.context)
        dbaas.MySqlAppStatus.get.assert_any_call()
        restart_mock.assert_any_call()

    @patch.object(dbaas.MySqlApp, 'start_db_with_conf_changes')
    def test_start_db_with_conf_changes(self, start_db_mock):
        mock_status = MagicMock()
        configuration = {'config_contents': 'some junk'}
        self.manager.appStatus = mock_status
        dbaas.MySqlAppStatus.get = MagicMock(return_value=mock_status)
        self.manager.start_db_with_conf_changes(self.context, configuration)
        dbaas.MySqlAppStatus.get.assert_any_call()
        start_db_mock.assert_any_call({'config_contents': 'some junk'})

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

    @patch.object(dbaas.MySqlApp, 'remove_overrides')
    def test_update_overrides(self, remove_config_mock):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        dbaas.MySqlAppStatus.get = MagicMock(return_value=mock_status)
        dbaas.MySqlApp.update_overrides = MagicMock(return_value=None)
        self.manager.update_overrides(self.context, 'something_overrides')
        dbaas.MySqlAppStatus.get.assert_any_call()
        remove_config_mock.assert_not_called()
        dbaas.MySqlApp.update_overrides.assert_any_call('something_overrides')

    @patch.object(dbaas.MySqlApp, 'remove_overrides')
    def test_update_overrides_with_remove(self, remove_overrides_mock):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        dbaas.MySqlAppStatus.get = MagicMock(return_value=mock_status)
        dbaas.MySqlApp.update_overrides = MagicMock(return_value=None)
        self.manager.update_overrides(self.context, 'something_overrides',
                                      True)
        dbaas.MySqlAppStatus.get.assert_any_call()
        remove_overrides_mock.assert_any_call()
        dbaas.MySqlApp.update_overrides.assert_any_call('something_overrides')

    @patch.object(dbaas.MySqlApp, 'apply_overrides')
    def test_apply_overrides(self, apply_overrides_mock):
        mock_status = MagicMock()
        override = {'some_key': 'some value'}
        self.manager.appStatus = mock_status
        dbaas.MySqlAppStatus.get = MagicMock(return_value=mock_status)
        self.manager.apply_overrides(self.context, override)
        dbaas.MySqlAppStatus.get.assert_any_call()
        apply_overrides_mock.assert_any_call({'some_key': 'some value'})

    @patch.object(dbaas.MySqlApp, 'get_txn_count', return_value=(9879))
    def test_get_txn_count(self, get_txn_count_mock):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        dbaas.MySqlAppStatus.get = MagicMock(return_value=mock_status)
        txn_count = self.manager.get_txn_count(self.context)
        self.assertEqual(get_txn_count_mock.return_value, txn_count)
        dbaas.MySqlAppStatus.get.assert_any_call()
        get_txn_count_mock.assert_any_call()

    @patch.object(dbaas.MySqlApp, 'get_latest_txn_id',
                  return_value=('2a5b-2064-32fb:1'))
    def test_get_latest_txn_id(self, get_latest_txn_id_mock):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        dbaas.MySqlAppStatus.get = MagicMock(return_value=mock_status)
        latest_txn_id = self.manager.get_latest_txn_id(self.context)
        self.assertEqual(get_latest_txn_id_mock.return_value, latest_txn_id)
        dbaas.MySqlAppStatus.get.assert_any_call()
        get_latest_txn_id_mock.assert_any_call()

    @patch.object(dbaas.MySqlApp, 'wait_for_txn')
    def test_wait_for_txn(self, wait_for_txn_mock):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        dbaas.MySqlAppStatus.get = MagicMock(return_value=mock_status)
        self.manager.wait_for_txn(self.context, '4b4-23:5,2a5b-2064-32fb:1')
        dbaas.MySqlAppStatus.get.assert_any_call()
        wait_for_txn_mock.assert_any_call('4b4-23:5,2a5b-2064-32fb:1')

    @patch.object(dbaas.MySqlApp, 'make_read_only')
    def test_make_read_only(self, make_read_only_mock):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        dbaas.MySqlAppStatus.get = MagicMock(return_value=mock_status)
        self.manager.make_read_only(self.context, 'ON')
        dbaas.MySqlAppStatus.get.assert_any_call()
        make_read_only_mock.assert_any_call('ON')

    def test_cleanup_source_on_replica_detach(self):
        mock_replication = MagicMock()
        mock_replication.cleanup_source_on_replica_detach = MagicMock()
        self.mock_rs_class.return_value = mock_replication
        snapshot = {'replication_strategy': self.replication_strategy,
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

    @patch('trove.guestagent.datastore.mysql_common.manager.LOG')
    def test__perform_restore(self, *args):
        backup_info = {'id': 'backup_id_123abc',
                       'location': 'fake-location',
                       'type': 'InnoBackupEx',
                       'checksum': 'fake-checksum',
                       }
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        dbaas.MySqlAppStatus.get = MagicMock(return_value=mock_status)
        app = dbaas.MySqlApp(dbaas.MySqlAppStatus.get())
        with patch.object(backup, 'restore',
                          side_effect=ProcessExecutionError):
            self.assertRaises(ProcessExecutionError,
                              self.manager._perform_restore, backup_info,
                              self.context, '/var/lib/mysql', app)
            app.status.set_status.assert_called_with(
                rd_instance.ServiceStatuses.FAILED)
