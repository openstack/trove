# Copyright 2015 IBM Corp.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from mock import DEFAULT
from mock import MagicMock
from mock import patch
from testtools.matchers import Is, Equals, Not

from trove.common.instance import ServiceStatuses
from trove.guestagent import backup
from trove.guestagent.common import configuration
from trove.guestagent.common.configuration import ImportOverrideStrategy
from trove.guestagent.common import operating_system
from trove.guestagent.datastore.experimental.db2 import (
    manager as db2_manager)
from trove.guestagent.datastore.experimental.db2 import (
    service as db2_service)
from trove.guestagent import pkg as pkg
from trove.guestagent import volume
from trove.tests.unittests.guestagent.test_datastore_manager import \
    DatastoreManagerTest


class GuestAgentDB2ManagerTest(DatastoreManagerTest):

    @patch.object(ImportOverrideStrategy, '_initialize_import_directory')
    @patch.multiple(operating_system, exists=DEFAULT, write_file=DEFAULT,
                    chown=DEFAULT, chmod=DEFAULT)
    @patch.object(db2_service.DB2App, 'process_default_dbm_config')
    def setUp(self, *arg, **kwargs):
        super(GuestAgentDB2ManagerTest, self).setUp('db2')
        self.real_status = db2_service.DB2AppStatus.set_status

        class FakeInstanceServiceStatus(object):
            status = ServiceStatuses.NEW

            def save(self):
                pass

        db2_service.DB2AppStatus.set_status = MagicMock(
            return_value=FakeInstanceServiceStatus())
        self.manager = db2_manager.Manager()
        self.real_db_app_status = db2_service.DB2AppStatus
        self.origin_format = volume.VolumeDevice.format
        self.origin_mount = volume.VolumeDevice.mount
        self.origin_mount_points = volume.VolumeDevice.mount_points
        self.origin_stop_db = db2_service.DB2App.stop_db
        self.origin_start_db = db2_service.DB2App.start_db
        self.orig_change_ownership = (db2_service.DB2App.change_ownership)
        self.orig_create_databases = db2_service.DB2Admin.create_database
        self.orig_list_databases = db2_service.DB2Admin.list_databases
        self.orig_delete_database = db2_service.DB2Admin.delete_database
        self.orig_create_users = db2_service.DB2Admin.create_user
        self.orig_list_users = db2_service.DB2Admin.list_users
        self.orig_delete_user = db2_service.DB2Admin.delete_user
        self.orig_update_hostname = db2_service.DB2App.update_hostname
        self.orig_backup_restore = backup.restore
        self.orig_init_config = db2_service.DB2App.init_config
        self.orig_update_overrides = db2_service.DB2App.update_overrides
        self.orig_remove_overrides = db2_service.DB2App.remove_overrides

    def tearDown(self):
        super(GuestAgentDB2ManagerTest, self).tearDown()
        db2_service.DB2AppStatus.set_status = self.real_db_app_status
        volume.VolumeDevice.format = self.origin_format
        volume.VolumeDevice.mount = self.origin_mount
        volume.VolumeDevice.mount_points = self.origin_mount_points
        db2_service.DB2App.stop_db = self.origin_stop_db
        db2_service.DB2App.start_db = self.origin_start_db
        db2_service.DB2App.change_ownership = self.orig_change_ownership
        db2_service.DB2Admin.create_database = self.orig_create_databases
        db2_service.DB2Admin.create_user = self.orig_create_users
        db2_service.DB2Admin.create_database = self.orig_create_databases
        db2_service.DB2Admin.list_databases = self.orig_list_databases
        db2_service.DB2Admin.delete_database = self.orig_delete_database
        db2_service.DB2Admin.create_user = self.orig_create_users
        db2_service.DB2Admin.list_users = self.orig_list_users
        db2_service.DB2Admin.delete_user = self.orig_delete_user
        db2_service.DB2App.update_hostname = self.orig_update_hostname
        backup.restore = self.orig_backup_restore
        db2_service.DB2App.init_config = self.orig_init_config
        db2_service.DB2App.update_overrides = self.orig_update_overrides
        db2_service.DB2App.remove_overrides = self.orig_remove_overrides

    def test_update_status(self):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        self.manager.update_status(self.context)
        mock_status.update.assert_any_call()

    def test_prepare_device_path_true(self):
        self._prepare_dynamic()

    def test_prepare_device_path_false(self):
        self._prepare_dynamic(device_path=None)

    def test_prepare_database(self):
        self._prepare_dynamic(databases=['db1'])

    def test_prepare_from_backup(self):
        self._prepare_dynamic(['db2'], backup_id='123backup')

    @patch.object(configuration.ConfigurationManager, 'save_configuration')
    def _prepare_dynamic(self, packages=None, databases=None, users=None,
                         config_content='MockContent', device_path='/dev/vdb',
                         is_db_installed=True, backup_id=None, overrides=None):

        backup_info = {'id': backup_id,
                       'location': 'fake-location',
                       'type': 'DB2Backup',
                       'checksum': 'fake-checksum'} if backup_id else None

        mock_status = MagicMock()
        mock_app = MagicMock()
        self.manager.appStatus = mock_status
        self.manager.app = mock_app

        mock_status.begin_install = MagicMock(return_value=None)
        mock_app.change_ownership = MagicMock(return_value=None)
        mock_app.restart = MagicMock(return_value=None)
        mock_app.start_db = MagicMock(return_value=None)
        mock_app.stop_db = MagicMock(return_value=None)
        volume.VolumeDevice.format = MagicMock(return_value=None)
        volume.VolumeDevice.mount = MagicMock(return_value=None)
        volume.VolumeDevice.mount_points = MagicMock(return_value=[])
        db2_service.DB2Admin.create_user = MagicMock(return_value=None)
        db2_service.DB2Admin.create_database = MagicMock(return_value=None)
        backup.restore = MagicMock(return_value=None)

        with patch.object(pkg.Package, 'pkg_is_installed',
                          return_value=MagicMock(
                              return_value=is_db_installed)):
            self.manager.prepare(context=self.context, packages=packages,
                                 config_contents=config_content,
                                 databases=databases,
                                 memory_mb='2048', users=users,
                                 device_path=device_path,
                                 mount_point="/home/db2inst1/db2inst1",
                                 backup_info=backup_info,
                                 overrides=None,
                                 cluster_config=None)

        mock_status.begin_install.assert_any_call()
        self.assertEqual(1, mock_app.change_ownership.call_count)
        if databases:
            self.assertTrue(db2_service.DB2Admin.create_database.called)
        else:
            self.assertFalse(db2_service.DB2Admin.create_database.called)

        if users:
            self.assertTrue(db2_service.DB2Admin.create_user.called)
        else:
            self.assertFalse(db2_service.DB2Admin.create_user.called)

        if backup_id:
            backup.restore.assert_any_call(self.context,
                                           backup_info,
                                           '/home/db2inst1/db2inst1')
        self.assertTrue(
            self.manager.configuration_manager.save_configuration.called
        )

    def test_restart(self):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        with patch.object(db2_service.DB2App, 'restart',
                          return_value=None) as restart_mock:
            # invocation
            self.manager.restart(self.context)
            # verification/assertion
            restart_mock.assert_any_call()

    def test_stop_db(self):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        db2_service.DB2App.stop_db = MagicMock(return_value=None)
        self.manager.stop_db(self.context)
        db2_service.DB2App.stop_db.assert_any_call(
            do_not_start_on_reboot=False)

    def test_start_db_with_conf_changes(self):
        with patch.object(db2_service.DB2App, 'start_db_with_conf_changes'):
            self.manager.start_db_with_conf_changes(self.context, 'something')
            db2_service.DB2App.start_db_with_conf_changes.assert_any_call(
                'something')

    def test_create_database(self):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        db2_service.DB2Admin.create_database = MagicMock(return_value=None)
        self.manager.create_database(self.context, ['db1'])
        db2_service.DB2Admin.create_database.assert_any_call(['db1'])

    def test_create_user(self):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        db2_service.DB2Admin.create_user = MagicMock(return_value=None)
        self.manager.create_user(self.context, ['user1'])
        db2_service.DB2Admin.create_user.assert_any_call(['user1'])

    def test_delete_database(self):
        databases = ['db1']
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        db2_service.DB2Admin.delete_database = MagicMock(return_value=None)
        self.manager.delete_database(self.context, databases)
        db2_service.DB2Admin.delete_database.assert_any_call(databases)

    def test_delete_user(self):
        user = ['user1']
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        db2_service.DB2Admin.delete_user = MagicMock(return_value=None)
        self.manager.delete_user(self.context, user)
        db2_service.DB2Admin.delete_user.assert_any_call(user)

    def test_list_databases(self):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        db2_service.DB2Admin.list_databases = MagicMock(
            return_value=['database1'])
        databases = self.manager.list_databases(self.context)
        self.assertThat(databases, Not(Is(None)))
        self.assertThat(databases, Equals(['database1']))
        db2_service.DB2Admin.list_databases.assert_any_call(None, None, False)

    def test_list_users(self):
        db2_service.DB2Admin.list_users = MagicMock(return_value=['user1'])
        users = self.manager.list_users(self.context)
        self.assertThat(users, Equals(['user1']))
        db2_service.DB2Admin.list_users.assert_any_call(None, None, False)

    @patch.object(db2_service.DB2Admin, 'get_user',
                  return_value=MagicMock(return_value=['user1']))
    def test_get_users(self, get_user_mock):
        username = ['user1']
        hostname = ['host']
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        users = self.manager.get_user(self.context, username, hostname)
        self.assertThat(users, Equals(get_user_mock.return_value))
        get_user_mock.assert_any_call(username, hostname)

    def test_rpc_ping(self):
        output = self.manager.rpc_ping(self.context)
        self.assertTrue(output)

    def test_update_update_overrides(self):
        configuration = {"DIAGSIZE": 50}
        db2_service.DB2App.update_overrides = MagicMock()
        self.manager.update_overrides(self.context, configuration, False)
        db2_service.DB2App.update_overrides.assert_any_call(self.context,
                                                            configuration)

    def test_reset_update_overrides(self):
        configuration = {}
        db2_service.DB2App.remove_overrides = MagicMock()
        self.manager.update_overrides(self.context, configuration, True)
        db2_service.DB2App.remove_overrides.assert_any_call()
