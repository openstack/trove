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

import testtools
from mock import MagicMock
from trove.common.context import TroveContext
from trove.guestagent.datastore.redis.manager import Manager as RedisManager
import trove.guestagent.datastore.redis.service as redis_service
from trove.guestagent import backup
from trove.guestagent.common import operating_system
from trove.guestagent.volume import VolumeDevice


class RedisGuestAgentManagerTest(testtools.TestCase):

    def setUp(self):
        super(RedisGuestAgentManagerTest, self).setUp()
        self.context = TroveContext()
        self.manager = RedisManager()
        self.packages = 'redis-server'
        self.origin_RedisAppStatus = redis_service.RedisAppStatus
        self.origin_start_redis = redis_service.RedisApp.start_redis
        self.origin_stop_redis = redis_service.RedisApp.stop_db
        self.origin_install_redis = redis_service.RedisApp._install_redis
        self.origin_write_config = redis_service.RedisApp.write_config
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
        redis_service.RedisApp.write_config = self.origin_write_config
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
        self.manager.appStatus = mock_status
        redis_service.RedisAppStatus.get = MagicMock(return_value=mock_status)
        self.manager.update_status(self.context)
        redis_service.RedisAppStatus.get.assert_any_call()
        mock_status.update.assert_any_call()

    def test_prepare_redis_not_installed(self):
        self._prepare_dynamic(is_redis_installed=False)

    def _prepare_dynamic(self, device_path='/dev/vdb', is_redis_installed=True,
                         backup_info=None, is_root_enabled=False,
                         mount_point='var/lib/redis'):

        # covering all outcomes is starting to cause trouble here
        mock_status = MagicMock()
        redis_service.RedisAppStatus.get = MagicMock(return_value=mock_status)
        redis_service.RedisApp.start_redis = MagicMock(return_value=None)
        redis_service.RedisApp.install_if_needed = MagicMock(return_value=None)
        redis_service.RedisApp.write_config = MagicMock(return_value=None)
        operating_system.update_owner = MagicMock(return_value=None)
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

        self.assertEqual(redis_service.RedisAppStatus.get.call_count, 2)
        mock_status.begin_install.assert_any_call()
        VolumeDevice.format.assert_any_call()
        redis_service.RedisApp.install_if_needed.assert_any_call(self.packages)
        redis_service.RedisApp.write_config.assert_any_call(None)
        operating_system.update_owner.assert_any_call(
            'redis', 'redis', mount_point)
        redis_service.RedisApp.restart.assert_any_call()

    def test_restart(self):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        redis_service.RedisAppStatus.get = MagicMock(return_value=mock_status)
        redis_service.RedisApp.restart = MagicMock(return_value=None)
        self.manager.restart(self.context)
        redis_service.RedisAppStatus.get.assert_any_call()
        redis_service.RedisApp.restart.assert_any_call()

    def test_stop_db(self):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        redis_service.RedisAppStatus.get = MagicMock(return_value=mock_status)
        redis_service.RedisApp.stop_db = MagicMock(return_value=None)
        self.manager.stop_db(self.context)
        redis_service.RedisAppStatus.get.assert_any_call()
        redis_service.RedisApp.stop_db.assert_any_call(
            do_not_start_on_reboot=False)
