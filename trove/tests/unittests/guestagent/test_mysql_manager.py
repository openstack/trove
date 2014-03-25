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
from mock import MagicMock
from testtools.matchers import Is, Equals, Not
from trove.common.context import TroveContext
from trove.guestagent import volume
from trove.guestagent.datastore.mysql.manager import Manager
import trove.guestagent.datastore.mysql.service as dbaas
from trove.guestagent import backup
from trove.guestagent.volume import VolumeDevice
from trove.guestagent import pkg as pkg


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
        mock_status = MagicMock()

        dbaas.MySqlAppStatus.get = MagicMock(return_value=mock_status)
        mock_status.begin_install = MagicMock(return_value=None)
        VolumeDevice.format = MagicMock(return_value=None)
        VolumeDevice.migrate_data = MagicMock(return_value=None)
        VolumeDevice.mount = MagicMock(return_value=None)
        dbaas.MySqlApp.stop_db = MagicMock(return_value=None)
        dbaas.MySqlApp.start_mysql = MagicMock(return_value=None)
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

        os.path.exists = MagicMock(return_value=True)
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
        mock_status.begin_install.assert_any_call()

        self.assertEqual(VolumeDevice.format.call_count, COUNT)
        self.assertEqual(VolumeDevice.migrate_data.call_count, COUNT)
        self.assertEqual(dbaas.MySqlApp.stop_db.call_count, COUNT)
        if backup_info:
            backup.restore.assert_any_call(self.context,
                                           backup_info,
                                           '/var/lib/mysql')
        dbaas.MySqlApp.install_if_needed.assert_any_call(None)
        # We dont need to make sure the exact contents are there
        dbaas.MySqlApp.secure.assert_any_call(None, None)
        self.assertFalse(dbaas.MySqlAdmin.create_database.called)
        self.assertFalse(dbaas.MySqlAdmin.create_user.called)
        dbaas.MySqlApp.secure_root.assert_any_call(
            secure_remote_root=not is_root_enabled)
