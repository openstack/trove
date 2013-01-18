#    Copyright 2012 OpenStack LLC
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
#    under the License

from reddwarf.guestagent.manager import Manager
from reddwarf.guestagent import dbaas
from reddwarf.guestagent import volume
import testtools
from mock import Mock, MagicMock


class GuestAgentManagerTest(testtools.TestCase):

    def setUp(self):
        super(GuestAgentManagerTest, self).setUp()
        self.context = Mock()
        self.manager = Manager()

    def tearDown(self):
        super(GuestAgentManagerTest, self).tearDown()

    def test_update_status(self):
        dbaas.MySqlAppStatus.get = MagicMock()
        self.manager.update_status(self.context)
        self.assertEqual(1, dbaas.MySqlAppStatus.get.call_count)

    def test_update_status_2(self):
        self._setUp_MySqlAppStatus_get()
        dbaas.MySqlAppStatus.update = MagicMock()
        self.manager.update_status(self.context)
        self.assertEqual(1, dbaas.MySqlAppStatus.update.call_count)

    def test_create_database(self):
        databases = Mock()
        dbaas.MySqlAdmin.create_database = MagicMock()
        self.manager.create_database(self.context, databases)
        self.assertEqual(1, dbaas.MySqlAdmin.create_database.call_count)

    def test_create_user(self):
        users = Mock()
        dbaas.MySqlAdmin.create_user = MagicMock()
        self.manager.create_user(self.context, users)
        self.assertEqual(1, dbaas.MySqlAdmin.create_user.call_count)

    def test_delete_database(self):
        databases = Mock()
        dbaas.MySqlAdmin.delete_database = MagicMock()
        self.manager.delete_database(self.context, databases)
        self.assertEqual(1, dbaas.MySqlAdmin.delete_database.call_count)

    def test_delete_user(self):
        user = Mock()
        dbaas.MySqlAdmin.delete_user = MagicMock()
        self.manager.delete_user(self.context, user)
        self.assertEqual(1, dbaas.MySqlAdmin.delete_user.call_count)

    def test_list_databases(self):
        dbaas.MySqlAdmin.list_databases = MagicMock()
        self.manager.list_databases(self.context)
        self.assertEqual(1, dbaas.MySqlAdmin.list_databases.call_count)

    def test_list_users(self):
        dbaas.MySqlAdmin.list_users = MagicMock()
        self.manager.list_users(self.context)
        self.assertEqual(1, dbaas.MySqlAdmin.list_users.call_count)

    def test_enable_root(self):
        dbaas.MySqlAdmin.enable_root = MagicMock()
        self.manager.enable_root(self.context)
        self.assertEqual(1, dbaas.MySqlAdmin.enable_root.call_count)

    def test_is_root_enabled(self):
        dbaas.MySqlAdmin.is_root_enabled = MagicMock()
        self.manager.is_root_enabled(self.context)
        self.assertEqual(1, dbaas.MySqlAdmin.is_root_enabled.call_count)

    def test_prepare_device_path_true(self):
        self._prepare_dynamic()

    def test_prepare_device_path_false(self):
        self._prepare_dynamic(has_device_path=False)

    def test_prepare_mysql_not_installed(self):
        self._prepare_dynamic(is_mysql_installed=False)

    def _prepare_dynamic(self, has_device_path=True, is_mysql_installed=True):

        if has_device_path:
            COUNT = 1
        else:
            COUNT = 0

        if is_mysql_installed:
            SEC_COUNT = 1
        else:
            SEC_COUNT = 0

        self._setUp_MySqlAppStatus_get()
        dbaas.MySqlAppStatus.begin_mysql_install = MagicMock()
        origin_format = volume.VolumeDevice.format
        volume.VolumeDevice.format = MagicMock()

        origin_is_installed, origin_stop_mysql, origin_migrate_data =\
            self._prepare_mysql_is_installed(is_mysql_installed)

        origin_mount = volume.VolumeDevice.mount
        volume.VolumeDevice.mount = MagicMock()

        dbaas.MySqlApp.start_mysql = MagicMock()
        dbaas.MySqlApp.install_and_secure = MagicMock()

        Manager.create_database = MagicMock()
        Manager.create_user = MagicMock()
        self.manager.prepare(self.context, Mock, Mock, Mock, has_device_path)

        self.assertEqual(1,
                         dbaas.MySqlAppStatus.begin_mysql_install.call_count)

        self.assertEqual(COUNT, volume.VolumeDevice.format.call_count)
        self.assertEqual(COUNT, dbaas.MySqlApp.is_installed.call_count)

        self.assertEqual(COUNT * SEC_COUNT,
                         dbaas.MySqlApp.stop_mysql.call_count)

        self.assertEqual(COUNT * SEC_COUNT,
                         volume.VolumeDevice.migrate_data.call_count)

        self.assertEqual(COUNT * SEC_COUNT,
                         dbaas.MySqlApp.start_mysql.call_count)

        self.assertEqual(1, dbaas.MySqlApp.install_and_secure.call_count)
        self.assertEqual(1, Manager.create_database.call_count)
        self.assertEqual(1, Manager.create_user.call_count)

        volume.VolumeDevice.format = origin_format
        volume.VolumeDevice.migrate_data = origin_migrate_data
        dbaas.MySqlApp.is_installed = origin_is_installed
        dbaas.MySqlApp.stop_mysql = origin_stop_mysql
        volume.VolumeDevice.mount = origin_mount

    def _prepare_mysql_is_installed(self, is_installed=True):
        origin_is_installed = dbaas.MySqlApp.is_installed
        origin_stop_mysql = dbaas.MySqlApp.stop_mysql
        origin_migrate_data = volume.VolumeDevice.migrate_data
        dbaas.MySqlApp.is_installed = MagicMock(return_value=is_installed)
        dbaas.MySqlApp.stop_mysql = MagicMock()
        volume.VolumeDevice.migrate_data = MagicMock()
        return origin_is_installed, origin_stop_mysql, origin_migrate_data

    def test_restart(self):
        self._setUp_MySqlAppStatus_get()
        dbaas.MySqlApp.restart = MagicMock()
        self.manager.restart(self.context)
        self.assertEqual(1, dbaas.MySqlApp.restart.call_count)

    def test_start_mysql_with_conf_changes(self):
        updated_mem_size = Mock()
        self._setUp_MySqlAppStatus_get()
        dbaas.MySqlApp.start_mysql_with_conf_changes = MagicMock()
        self.manager.start_mysql_with_conf_changes(self.context,
                                                   updated_mem_size)
        self.assertEqual(1, dbaas.MySqlApp.
                         start_mysql_with_conf_changes.call_count)

    def test_stop_mysql(self):
        self._setUp_MySqlAppStatus_get()
        dbaas.MySqlApp.stop_mysql = MagicMock()
        self.manager.stop_mysql(self.context)
        self.assertEqual(1, dbaas.MySqlApp.stop_mysql.call_count)

    def _setUp_MySqlAppStatus_get(self):
        dbaas.MySqlAppStatus = Mock
        dbaas.MySqlAppStatus.get = MagicMock(return_value=dbaas.MySqlAppStatus)
