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

import testtools
from mockito import verify, when, unstub, any, mock, never
from testtools.matchers import Is, Equals, Not

from trove.common.context import TroveContext
from trove.guestagent import volume
from trove.guestagent.datastore.mysql.manager import Manager
import trove.guestagent.datastore.mysql.service as dbaas
from trove.guestagent.datastore.redis.manager import Manager as RedisManager
import trove.guestagent.datastore.redis.service as redis_service
import trove.guestagent.datastore.redis.system as redis_system
from trove.guestagent import backup
from trove.guestagent.volume import VolumeDevice
from trove.guestagent import pkg


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
        self.origin_stop_mysql = dbaas.MySqlApp.stop_db
        self.origin_start_mysql = dbaas.MySqlApp.start_mysql
        self.origin_pkg_is_installed = pkg.Package.pkg_is_installed
        self.origin_os_path_exists = os.path.exists

    def tearDown(self):
        super(GuestAgentManagerTest, self).tearDown()
        dbaas.MySqlAppStatus = self.origin_MySqlAppStatus
        os.path.exists = self.origin_os_path_exists
        volume.VolumeDevice.format = self.origin_format
        volume.VolumeDevice.migrate_data = self.origin_migrate_data
        volume.VolumeDevice.mount = self.origin_mount
        dbaas.MySqlApp.stop_db = self.origin_stop_mysql
        dbaas.MySqlApp.start_mysql = self.origin_start_mysql
        pkg.Package.pkg_is_installed = self.origin_pkg_is_installed
        os.path.exists = self.origin_os_path_exists
        unstub()

    def test_update_status(self):
        mock_status = mock()
        when(dbaas.MySqlAppStatus).get().thenReturn(mock_status)
        self.manager.update_status(self.context)
        verify(dbaas.MySqlAppStatus).get()
        verify(mock_status).update()

    def test_create_database(self):
        when(dbaas.MySqlAdmin).create_database(['db1']).thenReturn(None)
        self.manager.create_database(self.context, ['db1'])
        verify(dbaas.MySqlAdmin).create_database(['db1'])

    def test_create_user(self):
        when(dbaas.MySqlAdmin).create_user(['user1']).thenReturn(None)
        self.manager.create_user(self.context, ['user1'])
        verify(dbaas.MySqlAdmin).create_user(['user1'])

    def test_delete_database(self):
        databases = ['db1']
        when(dbaas.MySqlAdmin).delete_database(databases).thenReturn(None)
        self.manager.delete_database(self.context, databases)
        verify(dbaas.MySqlAdmin).delete_database(databases)

    def test_delete_user(self):
        user = ['user1']
        when(dbaas.MySqlAdmin).delete_user(user).thenReturn(None)
        self.manager.delete_user(self.context, user)
        verify(dbaas.MySqlAdmin).delete_user(user)

    def test_grant_access(self):
        username = "test_user"
        hostname = "test_host"
        databases = ["test_database"]
        when(dbaas.MySqlAdmin).grant_access(username,
                                            hostname,
                                            databases).thenReturn(None)

        self.manager.grant_access(self.context,
                                  username,
                                  hostname,
                                  databases)

        verify(dbaas.MySqlAdmin).grant_access(username, hostname, databases)

    def test_list_databases(self):
        when(dbaas.MySqlAdmin).list_databases(None, None,
                                              False).thenReturn(['database1'])
        databases = self.manager.list_databases(self.context)
        self.assertThat(databases, Not(Is(None)))
        self.assertThat(databases, Equals(['database1']))
        verify(dbaas.MySqlAdmin).list_databases(None, None, False)

    def test_list_users(self):
        when(dbaas.MySqlAdmin).list_users(None, None,
                                          False).thenReturn(['user1'])
        users = self.manager.list_users(self.context)
        self.assertThat(users, Equals(['user1']))
        verify(dbaas.MySqlAdmin).list_users(None, None, False)

    def test_get_users(self):
        username = ['user1']
        hostname = ['host']
        when(dbaas.MySqlAdmin).get_user(username,
                                        hostname).thenReturn(['user1'])
        users = self.manager.get_user(self.context, username, hostname)
        self.assertThat(users, Equals(['user1']))
        verify(dbaas.MySqlAdmin).get_user(username, hostname)

    def test_enable_root(self):
        when(dbaas.MySqlAdmin).enable_root().thenReturn('user_id_stuff')
        user_id = self.manager.enable_root(self.context)
        self.assertThat(user_id, Is('user_id_stuff'))
        verify(dbaas.MySqlAdmin).enable_root()

    def test_is_root_enabled(self):
        when(dbaas.MySqlAdmin).is_root_enabled().thenReturn(True)
        is_enabled = self.manager.is_root_enabled(self.context)
        self.assertThat(is_enabled, Is(True))
        verify(dbaas.MySqlAdmin).is_root_enabled()

    def test_create_backup(self):
        when(backup).backup(self.context, 'backup_id_123').thenReturn(None)
        # entry point
        Manager().create_backup(self.context, 'backup_id_123')
        # assertions
        verify(backup).backup(self.context, 'backup_id_123')

    def test_prepare_device_path_true(self):
        self._prepare_dynamic()

    def test_prepare_device_path_false(self):
        self._prepare_dynamic(device_path=None)

    def test_prepare_mysql_not_installed(self):
        self._prepare_dynamic(is_mysql_installed=False)

    def test_prepare_mysql_from_backup(self):
        self._prepare_dynamic(backup_id='backup_id_123abc')

    def test_prepare_mysql_from_backup_with_root(self):
        self._prepare_dynamic(backup_id='backup_id_123abc',
                              is_root_enabled=True)

    def _prepare_dynamic(self, device_path='/dev/vdb', is_mysql_installed=True,
                         backup_id=None, is_root_enabled=False,
                         overrides=None):

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
        mock_status = mock()
        when(dbaas.MySqlAppStatus).get().thenReturn(mock_status)
        when(mock_status).begin_install().thenReturn(None)
        when(VolumeDevice).format().thenReturn(None)
        when(VolumeDevice).migrate_data(any()).thenReturn(None)
        when(VolumeDevice).mount().thenReturn(None)
        when(dbaas.MySqlApp).stop_db().thenReturn(None)
        when(dbaas.MySqlApp).start_mysql().thenReturn(None)
        when(dbaas.MySqlApp).install_if_needed(any()).thenReturn(None)
        when(backup).restore(self.context,
                             backup_info,
                             '/var/lib/mysql').thenReturn(None)
        when(dbaas.MySqlApp).secure(any()).thenReturn(None)
        when(dbaas.MySqlApp).secure_root(any()).thenReturn(None)
        (when(pkg.Package).pkg_is_installed(any()).
         thenReturn(is_mysql_installed))
        when(dbaas.MySqlAdmin).is_root_enabled().thenReturn(is_root_enabled)
        when(dbaas.MySqlAdmin).create_user().thenReturn(None)
        when(dbaas.MySqlAdmin).create_database().thenReturn(None)

        when(os.path).exists(any()).thenReturn(True)
        # invocation
        self.manager.prepare(context=self.context,
                             packages=None,
                             memory_mb='2048',
                             databases=None,
                             users=None,
                             device_path=device_path,
                             mount_point='/var/lib/mysql',
                             backup_info=backup_info,
                             overrides=overrides)
        # verification/assertion
        verify(mock_status).begin_install()

        verify(VolumeDevice, times=COUNT).format()
        verify(dbaas.MySqlApp, times=COUNT).stop_db()
        verify(VolumeDevice, times=COUNT).migrate_data(
            any())
        if backup_info:
            verify(backup).restore(self.context, backup_info, '/var/lib/mysql')
        verify(dbaas.MySqlApp).install_if_needed(any())
        # We dont need to make sure the exact contents are there
        verify(dbaas.MySqlApp).secure(any(), overrides)
        verify(dbaas.MySqlAdmin, never).create_database()
        verify(dbaas.MySqlAdmin, never).create_user()
        verify(dbaas.MySqlApp).secure_root(secure_remote_root=any())


class RedisGuestAgentManagerTest(testtools.TestCase):

    def setUp(self):
        super(RedisGuestAgentManagerTest, self).setUp()
        self.context = TroveContext()
        self.manager = RedisManager()
        self.packages = 'redis-server'
        self.origin_RedisAppStatus = redis_service.RedisAppStatus
        self.origin_os_path_exists = os.path.exists
        self.origin_format = volume.VolumeDevice.format
        self.origin_migrate_data = volume.VolumeDevice.migrate_data
        self.origin_mount = volume.VolumeDevice.mount
        self.origin_stop_redis = redis_service.RedisApp.stop_db
        self.origin_start_redis = redis_service.RedisApp.start_redis
        self.origin_install_redis = redis_service.RedisApp._install_redis

    def tearDown(self):
        super(RedisGuestAgentManagerTest, self).tearDown()
        redis_service.RedisAppStatus = self.origin_RedisAppStatus
        os.path.exists = self.origin_os_path_exists
        volume.VolumeDevice.format = self.origin_format
        volume.VolumeDevice.migrate_data = self.origin_migrate_data
        volume.VolumeDevice.mount = self.origin_mount
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

    def test_prepare_device_path_true(self):
        self._prepare_dynamic()

    def test_prepare_device_path_false(self):
        self._prepare_dynamic(device_path=None)

    def test_prepare_redis_not_installed(self):
        self._prepare_dynamic(is_redis_installed=False)

    def _prepare_dynamic(self, device_path='/dev/vdb', is_redis_installed=True,
                         backup_info=None, is_root_enabled=False):

        # covering all outcomes is starting to cause trouble here
        dev_path = 1 if device_path else 0
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
        verify(VolumeDevice, times=dev_path).format()
        verify(VolumeDevice, times=dev_path).mount(redis_system.REDIS_BASE_DIR)
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
