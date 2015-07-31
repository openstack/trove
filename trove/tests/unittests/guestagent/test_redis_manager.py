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
import testtools

from trove.common.context import TroveContext
from trove.guestagent import backup
from trove.guestagent.common.configuration import ConfigurationManager
from trove.guestagent.common import operating_system
from trove.guestagent.datastore.experimental.redis import (
    service as redis_service)
from trove.guestagent.datastore.experimental.redis.manager import (
    Manager as RedisManager)
from trove.guestagent.volume import VolumeDevice


class RedisGuestAgentManagerTest(testtools.TestCase):

    @patch.multiple(redis_service.RedisApp,
                    _build_admin_client=DEFAULT, _init_overrides_dir=DEFAULT)
    def setUp(self, *args, **kwargs):
        super(RedisGuestAgentManagerTest, self).setUp()
        self.context = TroveContext()
        self.manager = RedisManager()
        self.packages = 'redis-server'
        self.origin_RedisAppStatus = redis_service.RedisAppStatus
        self.origin_start_redis = redis_service.RedisApp.start_redis
        self.origin_stop_redis = redis_service.RedisApp.stop_db
        self.origin_install_redis = redis_service.RedisApp._install_redis
        self.origin_install_if_needed = \
            redis_service.RedisApp.install_if_needed
        self.origin_complete_install_or_restart = \
            redis_service.RedisApp.complete_install_or_restart
        self.origin_format = VolumeDevice.format
        self.origin_mount = VolumeDevice.mount
        self.origin_mount_points = VolumeDevice.mount_points
        self.origin_restore = backup.restore

    def tearDown(self):
        super(RedisGuestAgentManagerTest, self).tearDown()
        redis_service.RedisAppStatus = self.origin_RedisAppStatus
        redis_service.RedisApp.stop_db = self.origin_stop_redis
        redis_service.RedisApp.start_redis = self.origin_start_redis
        redis_service.RedisApp._install_redis = self.origin_install_redis
        redis_service.RedisApp.install_if_needed = \
            self.origin_install_if_needed
        redis_service.RedisApp.complete_install_or_restart = \
            self.origin_complete_install_or_restart
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

    @patch.multiple(redis_service.RedisApp,
                    apply_initial_guestagent_configuration=DEFAULT)
    @patch.object(ConfigurationManager, 'save_configuration')
    def _prepare_dynamic(self, save_configuration_mock,
                         apply_initial_guestagent_configuration,
                         device_path='/dev/vdb', is_redis_installed=True,
                         backup_info=None, is_root_enabled=False,
                         mount_point='var/lib/redis'):

        # covering all outcomes is starting to cause trouble here
        mock_status = MagicMock()
        self.manager._app.status = mock_status
        self.manager._build_admin_client = MagicMock(return_value=MagicMock())
        redis_service.RedisApp.start_redis = MagicMock(return_value=None)
        redis_service.RedisApp.install_if_needed = MagicMock(return_value=None)
        operating_system.chown = MagicMock(return_value=None)
        redis_service.RedisApp.restart = MagicMock(return_value=None)
        mock_status.begin_install = MagicMock(return_value=None)
        VolumeDevice.format = MagicMock(return_value=None)
        VolumeDevice.mount = MagicMock(return_value=None)
        VolumeDevice.mount_points = MagicMock(return_value=[])
        backup.restore = MagicMock(return_value=None)

        self.manager.prepare(self.context, self.packages,
                             None, '2048',
                             None, device_path=device_path,
                             mount_point=mount_point,
                             backup_info=backup_info,
                             overrides=None,
                             cluster_config=None)

        mock_status.begin_install.assert_any_call()
        VolumeDevice.format.assert_any_call()
        redis_service.RedisApp.install_if_needed.assert_any_call(self.packages)
        save_configuration_mock.assert_any_call(None)
        apply_initial_guestagent_configuration.assert_called_once_with()
        operating_system.chown.assert_any_call(
            mount_point, 'redis', 'redis', as_root=True)
        redis_service.RedisApp.restart.assert_any_call()

    def test_restart(self):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        redis_service.RedisAppStatus.get = MagicMock(return_value=mock_status)
        redis_service.RedisApp.restart = MagicMock(return_value=None)
        self.manager.restart(self.context)
        redis_service.RedisApp.restart.assert_any_call()

    def test_stop_db(self):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        redis_service.RedisAppStatus.get = MagicMock(return_value=mock_status)
        redis_service.RedisApp.stop_db = MagicMock(return_value=None)
        self.manager.stop_db(self.context)
        redis_service.RedisApp.stop_db.assert_any_call(
            do_not_start_on_reboot=False)
