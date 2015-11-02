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

from mock import DEFAULT, MagicMock, patch

from trove.common.context import TroveContext
from trove.guestagent import backup
from trove.guestagent.common import configuration
from trove.guestagent.common import operating_system
from trove.guestagent.datastore.experimental.redis import (
    service as redis_service)
from trove.guestagent.datastore.experimental.redis.manager import (
    Manager as RedisManager)
from trove.guestagent.volume import VolumeDevice
from trove.tests.unittests import trove_testtools


class RedisGuestAgentManagerTest(trove_testtools.TestCase):

    @patch.multiple(redis_service.RedisApp,
                    _build_admin_client=DEFAULT, _init_overrides_dir=DEFAULT)
    def setUp(self, *args, **kwargs):
        super(RedisGuestAgentManagerTest, self).setUp()
        self.patch_ope = patch('os.path.expanduser')
        self.mock_ope = self.patch_ope.start()
        self.addCleanup(self.patch_ope.stop)
        self.context = TroveContext()
        self.manager = RedisManager()
        self.packages = 'redis-server'
        self.origin_RedisAppStatus = redis_service.RedisAppStatus
        self.origin_start_redis = redis_service.RedisApp.start_redis
        self.origin_stop_redis = redis_service.RedisApp.stop_db
        self.origin_install_redis = redis_service.RedisApp._install_redis
        self.origin_install_if_needed = \
            redis_service.RedisApp.install_if_needed
        self.origin_format = VolumeDevice.format
        self.origin_mount = VolumeDevice.mount
        self.origin_mount_points = VolumeDevice.mount_points
        self.origin_restore = backup.restore
        self.patch_rs = patch(
            'trove.guestagent.datastore.experimental.redis.manager.'
            'REPLICATION_STRATEGY_CLASS')
        self.mock_rs_class = self.patch_rs.start()
        self.addCleanup(self.patch_rs.stop)
        self.patch_gfvs = patch(
            'trove.guestagent.dbaas.get_filesystem_volume_stats')
        self.mock_gfvs_class = self.patch_gfvs.start()
        self.addCleanup(self.patch_gfvs.stop)

        self.repl_datastore_manager = 'redis'
        self.repl_replication_strategy = 'RedisSyncReplication'

    def tearDown(self):
        super(RedisGuestAgentManagerTest, self).tearDown()
        redis_service.RedisAppStatus = self.origin_RedisAppStatus
        redis_service.RedisApp.stop_db = self.origin_stop_redis
        redis_service.RedisApp.start_redis = self.origin_start_redis
        redis_service.RedisApp._install_redis = self.origin_install_redis
        redis_service.RedisApp.install_if_needed = \
            self.origin_install_if_needed
        VolumeDevice.format = self.origin_format
        VolumeDevice.mount = self.origin_mount
        VolumeDevice.mount_points = self.origin_mount_points
        backup.restore = self.origin_restore

    def test_update_status(self):
        mock_status = MagicMock()
        self.manager._app.status = mock_status
        self.manager.update_status(self.context)
        mock_status.update.assert_any_call()

    def test_prepare_redis_not_installed(self):
        self._prepare_dynamic(is_redis_installed=False)

    def test_prepare_redis_with_snapshot(self):
        snapshot = {'replication_strategy': self.repl_replication_strategy,
                    'dataset': {'dataset_size': 1.0},
                    'config': None}
        self._prepare_dynamic(snapshot=snapshot)

    @patch.object(redis_service.RedisApp, 'get_working_dir',
                  MagicMock(return_value='/var/lib/redis'))
    def test_prepare_redis_from_backup(self):
        self._prepare_dynamic(backup_id='backup_id_123abc')

    @patch.multiple(redis_service.RedisApp,
                    apply_initial_guestagent_configuration=DEFAULT,
                    restart=DEFAULT,
                    install_if_needed=DEFAULT)
    @patch.object(operating_system, 'chown')
    @patch.object(configuration.ConfigurationManager, 'save_configuration')
    def _prepare_dynamic(self, save_configuration_mock, chown_mock,
                         apply_initial_guestagent_configuration, restart,
                         install_if_needed,
                         device_path='/dev/vdb', is_redis_installed=True,
                         backup_info=None, is_root_enabled=False,
                         mount_point='var/lib/redis', backup_id=None,
                         snapshot=None):

        backup_info = None
        if backup_id is not None:
            backup_info = {'id': backup_id,
                           'location': 'fake-location',
                           'type': 'RedisBackup',
                           'checksum': 'fake-checksum',
                           }

        # covering all outcomes is starting to cause trouble here
        mock_status = MagicMock()
        self.manager._app.status = mock_status
        self.manager._build_admin_client = MagicMock(return_value=MagicMock())
        redis_service.RedisApp.stop_db = MagicMock(return_value=None)
        redis_service.RedisApp.start_redis = MagicMock(return_value=None)
        mock_status.begin_install = MagicMock(return_value=None)
        VolumeDevice.format = MagicMock(return_value=None)
        VolumeDevice.mount = MagicMock(return_value=None)
        VolumeDevice.mount_points = MagicMock(return_value=[])
        backup.restore = MagicMock(return_value=None)
        mock_replication = MagicMock()
        mock_replication.enable_as_slave = MagicMock()
        self.mock_rs_class.return_value = mock_replication

        self.manager.prepare(self.context, self.packages,
                             None, '2048',
                             None, device_path=device_path,
                             mount_point=mount_point,
                             backup_info=backup_info,
                             overrides=None,
                             cluster_config=None,
                             snapshot=snapshot)

        mock_status.begin_install.assert_any_call()
        VolumeDevice.format.assert_any_call()
        install_if_needed.assert_any_call(self.packages)
        save_configuration_mock.assert_any_call(None)
        apply_initial_guestagent_configuration.assert_called_once_with()
        chown_mock.assert_any_call(mount_point, 'redis', 'redis', as_root=True)
        if backup_info:
            backup.restore.assert_called_once_with(self.context,
                                                   backup_info,
                                                   '/var/lib/redis')
        else:
            redis_service.RedisApp.restart.assert_any_call()

        if snapshot:
            self.assertEqual(1, mock_replication.enable_as_slave.call_count)
        else:
            self.assertEqual(0, mock_replication.enable_as_slave.call_count)

    @patch.object(redis_service.RedisApp, 'restart')
    def test_restart(self, redis_mock):
        self.manager.restart(self.context)
        redis_mock.assert_any_call()

    @patch.object(redis_service.RedisApp, 'stop_db')
    def test_stop_db(self, redis_mock):
        self.manager.stop_db(self.context)
        redis_mock.assert_any_call(do_not_start_on_reboot=False)

    @patch.object(redis_service.RedisApp, '_init_overrides_dir',
                  return_value='')
    @patch.object(backup, 'backup')
    @patch.object(configuration.ConfigurationManager, 'parse_configuration',
                  MagicMock(return_value={'dir': '/var/lib/redis',
                                          'dbfilename': 'dump.rdb'}))
    @patch.object(operating_system, 'chown')
    @patch.object(operating_system, 'create_directory')
    def test_create_backup(self, *mocks):
        backup.backup = MagicMock(return_value=None)
        RedisManager().create_backup(self.context, 'backup_id_123')
        backup.backup.assert_any_call(self.context, 'backup_id_123')

    def test_backup_required_for_replication(self):
        mock_replication = MagicMock()
        mock_replication.backup_required_for_replication = MagicMock()
        self.mock_rs_class.return_value = mock_replication

        self.manager.backup_required_for_replication(self.context)
        self.assertEqual(
            1, mock_replication.backup_required_for_replication.call_count)

    def test_attach_replica(self):
        mock_replication = MagicMock()
        mock_replication.enable_as_slave = MagicMock()
        self.mock_rs_class.return_value = mock_replication

        snapshot = {'replication_strategy': self.repl_replication_strategy,
                    'dataset': {'dataset_size': 1.0}}

        self.manager.attach_replica(self.context, snapshot, None)
        self.assertEqual(1, mock_replication.enable_as_slave.call_count)

    def test_detach_replica(self):
        mock_replication = MagicMock()
        mock_replication.detach_slave = MagicMock()
        self.mock_rs_class.return_value = mock_replication

        self.manager.detach_replica(self.context)
        self.assertEqual(1, mock_replication.detach_slave.call_count)

    def test_enable_as_master(self):
        mock_replication = MagicMock()
        mock_replication.enable_as_master = MagicMock()
        self.mock_rs_class.return_value = mock_replication

        self.manager.enable_as_master(self.context, None)
        self.assertEqual(mock_replication.enable_as_master.call_count, 1)

    def test_demote_replication_master(self):
        mock_replication = MagicMock()
        mock_replication.demote_master = MagicMock()
        self.mock_rs_class.return_value = mock_replication

        self.manager.demote_replication_master(self.context)
        self.assertEqual(1, mock_replication.demote_master.call_count)

    @patch.object(redis_service.RedisApp, 'make_read_only')
    def test_make_read_only(self, redis_mock):
        self.manager.make_read_only(self.context, 'ON')
        redis_mock.assert_any_call('ON')

    def test_cleanup_source_on_replica_detach(self):
        mock_replication = MagicMock()
        mock_replication.cleanup_source_on_replica_detach = MagicMock()
        self.mock_rs_class.return_value = mock_replication
        snapshot = {'replication_strategy': self.repl_replication_strategy,
                    'dataset': {'dataset_size': '1.0'}}

        self.manager.cleanup_source_on_replica_detach(self.context, snapshot)
        self.assertEqual(
            1, mock_replication.cleanup_source_on_replica_detach.call_count)

    def test_get_replication_snapshot(self):
        snapshot_id = None
        log_position = None
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
        replication_snapshot = (
            self.manager.get_replication_snapshot(self.context, snapshot_info,
                                                  replica_source_config))
        self.assertEqual(expected_replication_snapshot, replication_snapshot)
        self.assertEqual(1, mock_replication.enable_as_master.call_count)
        self.assertEqual(
            1, mock_replication.snapshot_for_replication.call_count)
        self.assertEqual(1, mock_replication.get_master_ref.call_count)

    def test_get_replica_context(self):
        master_ref = {
            'host': '1.2.3.4',
            'port': 3306
        }
        expected_info = {
            'master': master_ref,
        }
        mock_replication = MagicMock()
        mock_replication.get_replica_context = MagicMock(
            return_value=expected_info)
        self.mock_rs_class.return_value = mock_replication

        replica_info = self.manager.get_replica_context(self.context)
        self.assertEqual(1, mock_replication.get_replica_context.call_count)
        self.assertEqual(expected_info, replica_info)

    def test_get_last_txn(self):
        expected_host = '10.0.0.2'
        self.manager._get_master_host = MagicMock(return_value=expected_host)
        expected_txn_id = 199
        repl_info = {'role': 'master', 'master_repl_offset': expected_txn_id}
        self.manager._get_repl_info = MagicMock(return_value=repl_info)

        (host, txn_id) = self.manager.get_last_txn(self.context)
        self.manager._get_master_host.assert_any_call()
        self.manager._get_repl_info.assert_any_call()
        self.assertEqual(expected_host, host)
        self.assertEqual(expected_txn_id, txn_id)

    def test_get_latest_txn_id(self):
        expected_txn_id = 199
        repl_info = {'role': 'master', 'master_repl_offset': expected_txn_id}
        self.manager._get_repl_info = MagicMock(return_value=repl_info)
        latest_txn_id = self.manager.get_latest_txn_id(self.context)
        self.assertEqual(expected_txn_id, latest_txn_id)
        self.manager._get_repl_info.assert_any_call()

    def test_wait_for_txn(self):
        expected_txn_id = 199
        repl_info = {'role': 'master', 'master_repl_offset': expected_txn_id}
        self.manager._get_repl_info = MagicMock(return_value=repl_info)
        self.manager.wait_for_txn(self.context, expected_txn_id)
        self.manager._get_repl_info.assert_any_call()
