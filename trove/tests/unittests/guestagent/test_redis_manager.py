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
from mockito import verify, when, unstub, any, mock
from trove.common.context import TroveContext
from trove.guestagent.datastore.redis.manager import Manager as RedisManager
import trove.guestagent.datastore.redis.service as redis_service
from trove.guestagent import backup
from trove.guestagent.volume import VolumeDevice


class RedisGuestAgentManagerTest(testtools.TestCase):

    def setUp(self):
        super(RedisGuestAgentManagerTest, self).setUp()
        self.context = TroveContext()
        self.manager = RedisManager()
        self.packages = 'redis-server'
        self.origin_RedisAppStatus = redis_service.RedisAppStatus
        self.origin_stop_redis = redis_service.RedisApp.stop_db
        self.origin_start_redis = redis_service.RedisApp.start_redis
        self.origin_install_redis = redis_service.RedisApp._install_redis

    def tearDown(self):
        super(RedisGuestAgentManagerTest, self).tearDown()
        redis_service.RedisAppStatus = self.origin_RedisAppStatus
        redis_service.RedisApp.stop_db = self.origin_stop_redis
        redis_service.RedisApp.start_redis = self.origin_start_redis
        redis_service.RedisApp._install_redis = self.origin_install_redis
        unstub()

    def test_update_status(self):
        mock_status = mock()
        when(redis_service.RedisAppStatus).get().thenReturn(mock_status)
        self.manager.update_status(self.context)
        verify(redis_service.RedisAppStatus).get()
        verify(mock_status).update()

    def test_prepare_redis_not_installed(self):
        self._prepare_dynamic(is_redis_installed=False)

    def _prepare_dynamic(self, device_path='/dev/vdb', is_redis_installed=True,
                         backup_info=None, is_root_enabled=False,
                         mount_point='var/lib/redis'):

        # covering all outcomes is starting to cause trouble here
        mock_status = mock()
        when(redis_service.RedisAppStatus).get().thenReturn(mock_status)
        when(mock_status).begin_install().thenReturn(None)
        when(VolumeDevice).format().thenReturn(None)
        when(VolumeDevice).mount().thenReturn(None)
        when(redis_service.RedisApp).start_redis().thenReturn(None)
        when(redis_service.RedisApp).install_if_needed().thenReturn(None)
        when(backup).restore(self.context, backup_info).thenReturn(None)
        when(redis_service.RedisApp).write_config(any()).thenReturn(None)
        when(redis_service.RedisApp).complete_install_or_restart(
            any()).thenReturn(None)
        self.manager.prepare(self.context, self.packages,
                             None, '2048',
                             None, device_path=device_path,
                             mount_point='/var/lib/redis',
                             backup_info=backup_info)
        verify(redis_service.RedisAppStatus, times=2).get()
        verify(mock_status).begin_install()
        verify(VolumeDevice).format()
        verify(redis_service.RedisApp).install_if_needed(self.packages)
        verify(redis_service.RedisApp).write_config(None)
        verify(redis_service.RedisApp).complete_install_or_restart()

    def test_restart(self):
        mock_status = mock()
        when(redis_service.RedisAppStatus).get().thenReturn(mock_status)
        when(redis_service.RedisApp).restart().thenReturn(None)
        self.manager.restart(self.context)
        verify(redis_service.RedisAppStatus).get()
        verify(redis_service.RedisApp).restart()

    def test_stop_db(self):
        mock_status = mock()
        when(redis_service.RedisAppStatus).get().thenReturn(mock_status)
        when(redis_service.RedisApp).stop_db(do_not_start_on_reboot=
                                             False).thenReturn(None)
        self.manager.stop_db(self.context)
        verify(redis_service.RedisAppStatus).get()
        verify(redis_service.RedisApp).stop_db(do_not_start_on_reboot=False)
