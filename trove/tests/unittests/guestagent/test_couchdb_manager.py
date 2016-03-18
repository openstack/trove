# Copyright 2015 IBM Corp.
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
from oslo_utils import netutils
from testtools.matchers import Is, Equals, Not

from trove.common.instance import ServiceStatuses
from trove.guestagent import backup
from trove.guestagent.datastore.experimental.couchdb import (
    manager as couchdb_manager)
from trove.guestagent.datastore.experimental.couchdb import (
    service as couchdb_service)
from trove.guestagent import pkg as pkg
from trove.guestagent import volume
from trove.tests.unittests import trove_testtools


class GuestAgentCouchDBManagerTest(trove_testtools.TestCase):

    def setUp(self):
        super(GuestAgentCouchDBManagerTest, self).setUp()
        self.real_status = couchdb_service.CouchDBAppStatus.set_status

        class FakeInstanceServiceStatus(object):
            status = ServiceStatuses.NEW

            def save(self):
                pass

        couchdb_service.CouchDBAppStatus.set_status = MagicMock(
            return_value=FakeInstanceServiceStatus())
        self.context = trove_testtools.TroveTestContext(self)
        self.manager = couchdb_manager.Manager()
        self.pkg = couchdb_service.packager
        self.real_db_app_status = couchdb_service.CouchDBAppStatus
        self.origin_os_path_exists = os.path.exists
        self.origin_format = volume.VolumeDevice.format
        self.origin_migrate_data = volume.VolumeDevice.migrate_data
        self.origin_mount = volume.VolumeDevice.mount
        self.origin_mount_points = volume.VolumeDevice.mount_points
        self.origin_stop_db = couchdb_service.CouchDBApp.stop_db
        self.origin_start_db = couchdb_service.CouchDBApp.start_db
        self.original_get_ip = netutils.get_my_ipv4
        self.orig_make_host_reachable = (
            couchdb_service.CouchDBApp.make_host_reachable)
        self.orig_backup_restore = backup.restore
        self.orig_create_users = couchdb_service.CouchDBAdmin.create_user
        self.orig_delete_user = couchdb_service.CouchDBAdmin.delete_user
        self.orig_list_users = couchdb_service.CouchDBAdmin.list_users
        self.orig_get_user = couchdb_service.CouchDBAdmin.get_user
        self.orig_grant_access = couchdb_service.CouchDBAdmin.grant_access
        self.orig_revoke_access = couchdb_service.CouchDBAdmin.revoke_access
        self.orig_list_access = couchdb_service.CouchDBAdmin.list_access
        self.orig_enable_root = couchdb_service.CouchDBAdmin.enable_root
        self.orig_is_root_enabled = (
            couchdb_service.CouchDBAdmin.is_root_enabled)
        self.orig_create_databases = (
            couchdb_service.CouchDBAdmin.create_database)
        self.orig_list_databases = couchdb_service.CouchDBAdmin.list_databases
        self.orig_delete_database = (
            couchdb_service.CouchDBAdmin.delete_database)

    def tearDown(self):
        super(GuestAgentCouchDBManagerTest, self).tearDown()
        couchdb_service.packager = self.pkg
        couchdb_service.CouchDBAppStatus.set_status = self.real_db_app_status
        os.path.exists = self.origin_os_path_exists
        volume.VolumeDevice.format = self.origin_format
        volume.VolumeDevice.migrate_data = self.origin_migrate_data
        volume.VolumeDevice.mount = self.origin_mount
        volume.VolumeDevice.mount_points = self.origin_mount_points
        couchdb_service.CouchDBApp.stop_db = self.origin_stop_db
        couchdb_service.CouchDBApp.start_db = self.origin_start_db
        netutils.get_my_ipv4 = self.original_get_ip
        couchdb_service.CouchDBApp.make_host_reachable = (
            self.orig_make_host_reachable)
        backup.restore = self.orig_backup_restore
        couchdb_service.CouchDBAdmin.create_user = self.orig_create_users
        couchdb_service.CouchDBAdmin.delete_user = self.orig_delete_user
        couchdb_service.CouchDBAdmin.list_users = self.orig_list_users
        couchdb_service.CouchDBAdmin.get_user = self.orig_get_user
        couchdb_service.CouchDBAdmin.grant_access = self.orig_grant_access
        couchdb_service.CouchDBAdmin.revoke_access = self.orig_revoke_access
        couchdb_service.CouchDBAdmin.list_access = self.orig_list_access
        couchdb_service.CouchDBAdmin.enable_root = self.orig_enable_root
        couchdb_service.CouchDBAdmin.is_root_enabled = (
            self.orig_is_root_enabled)
        couchdb_service.CouchDBAdmin.create_database = (
            self.orig_create_databases)
        couchdb_service.CouchDBAdmin.list_databases = self.orig_list_databases
        couchdb_service.CouchDBAdmin.delete_database = (
            self.orig_delete_database)

    def test_update_status(self):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        self.manager.update_status(self.context)
        mock_status.update.assert_any_call()

    def _prepare_dynamic(self, packages=None, databases=None,
                         config_content=None, device_path='/dev/vdb',
                         is_db_installed=True, backup_id=None,
                         overrides=None):
        mock_status = MagicMock()
        mock_app = MagicMock()
        self.manager.appStatus = mock_status
        self.manager.app = mock_app
        mount_point = '/var/lib/couchdb'

        mock_status.begin_install = MagicMock(return_value=None)
        mock_app.install_if_needed = MagicMock(return_value=None)
        mock_app.make_host_reachable = MagicMock(return_value=None)
        mock_app.restart = MagicMock(return_value=None)
        mock_app.start_db = MagicMock(return_value=None)
        mock_app.stop_db = MagicMock(return_value=None)
        os.path.exists = MagicMock(return_value=True)
        volume.VolumeDevice.format = MagicMock(return_value=None)
        volume.VolumeDevice.migrate_data = MagicMock(return_value=None)
        volume.VolumeDevice.mount = MagicMock(return_value=None)
        volume.VolumeDevice.mount_points = MagicMock(return_value=[])
        backup.restore = MagicMock(return_value=None)

        backup_info = {'id': backup_id,
                       'location': 'fake-location',
                       'type': 'CouchDBBackup',
                       'checksum': 'fake-checksum'} if backup_id else None

        couchdb_service.CouchDBAdmin.create_database = MagicMock(
            return_value=None)
        couchdb_service.CouchDBAdmin.create_user = MagicMock(return_value=None)

        with patch.object(pkg.Package, 'pkg_is_installed',
                          return_value=MagicMock(
                              return_value=is_db_installed)):
            self.manager.prepare(context=self.context, packages=packages,
                                 config_contents=config_content,
                                 databases=databases,
                                 memory_mb='2048', users=None,
                                 device_path=device_path,
                                 mount_point=mount_point,
                                 backup_info=backup_info,
                                 overrides=None,
                                 cluster_config=None)
        # verification/assertion
        mock_status.begin_install.assert_any_call()
        mock_app.install_if_needed.assert_any_call(packages)
        mock_app.make_host_reachable.assert_any_call()
        mock_app.change_permissions.assert_any_call()
        if backup_id:
            backup.restore.assert_any_call(self.context,
                                           backup_info,
                                           mount_point)

    def test_prepare_pkg(self):
        self._prepare_dynamic(['couchdb'])

    def test_prepare_no_pkg(self):
        self._prepare_dynamic([])

    def test_prepare_from_backup(self):
        self._prepare_dynamic(['couchdb'], backup_id='123abc456')

    def test_prepare_database(self):
        self._prepare_dynamic(databases=['db1'])

    def test_restart(self):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        with patch.object(couchdb_service.CouchDBApp, 'restart',
                          return_value=None):
            # invocation
            self.manager.restart(self.context)
            # verification/assertion
            couchdb_service.CouchDBApp.restart.assert_any_call()

    def test_stop_db(self):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        couchdb_service.CouchDBApp.stop_db = MagicMock(return_value=None)
        # invocation
        self.manager.stop_db(self.context)
        # verification/assertion
        couchdb_service.CouchDBApp.stop_db.assert_any_call(
            do_not_start_on_reboot=False)

    def test_reset_configuration(self):
        try:
            configuration = {'config_contents': 'some junk'}
            self.manager.reset_configuration(self.context, configuration)
        except Exception:
            self.fail("reset_configuration raised exception unexpectedly.")

    def test_rpc_ping(self):
        output = self.manager.rpc_ping(self.context)
        self.assertTrue(output)

    def test_create_user(self):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        couchdb_service.CouchDBAdmin.create_user = MagicMock(return_value=None)
        self.manager.create_user(self.context, ['user1'])
        couchdb_service.CouchDBAdmin.create_user.assert_any_call(['user1'])

    def test_delete_user(self):
        user = ['user1']
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        couchdb_service.CouchDBAdmin.delete_user = MagicMock(return_value=None)
        self.manager.delete_user(self.context, user)
        couchdb_service.CouchDBAdmin.delete_user.assert_any_call(user)

    def test_list_users(self):
        couchdb_service.CouchDBAdmin.list_users = MagicMock(
            return_value=['user1'])
        users = self.manager.list_users(self.context)
        self.assertThat(users, Equals(['user1']))
        couchdb_service.CouchDBAdmin.list_users.assert_any_call(
            None, None, False)

    def test_get_user(self):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        couchdb_service.CouchDBAdmin.get_user = MagicMock(
            return_value=['user1'])
        self.manager.get_user(self.context, 'user1', None)
        couchdb_service.CouchDBAdmin.get_user.assert_any_call(
            'user1', None)

    def test_grant_access(self):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        couchdb_service.CouchDBAdmin.grant_access = MagicMock(
            return_value=None)
        self.manager.grant_access(self.context, 'user1', None, ['db1'])
        couchdb_service.CouchDBAdmin.grant_access.assert_any_call(
            'user1', ['db1'])

    def test_revoke_access(self):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        couchdb_service.CouchDBAdmin.revoke_access = MagicMock(
            return_value=None)
        self.manager.revoke_access(self.context, 'user1', None, ['db1'])
        couchdb_service.CouchDBAdmin.revoke_access.assert_any_call(
            'user1', ['db1'])

    def test_list_access(self):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        couchdb_service.CouchDBAdmin.list_access = MagicMock(
            return_value=['user1'])
        self.manager.list_access(self.context, 'user1', None)
        couchdb_service.CouchDBAdmin.list_access.assert_any_call(
            'user1', None)

    def test_enable_root(self):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        couchdb_service.CouchDBAdmin.enable_root = MagicMock(
            return_value=True)
        result = self.manager.enable_root(self.context)
        self.assertThat(result, Equals(True))

    def test_is_root_enabled(self):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        couchdb_service.CouchDBAdmin.is_root_enabled = MagicMock(
            return_value=True)
        result = self.manager.is_root_enabled(self.context)
        self.assertThat(result, Equals(True))

    def test_create_databases(self):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        couchdb_service.CouchDBAdmin.create_database = MagicMock(
            return_value=None)
        self.manager.create_database(self.context, ['db1'])
        couchdb_service.CouchDBAdmin.create_database.assert_any_call(['db1'])

    def test_delete_database(self):
        databases = ['db1']
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        couchdb_service.CouchDBAdmin.delete_database = MagicMock(
            return_value=None)
        self.manager.delete_database(self.context, databases)
        couchdb_service.CouchDBAdmin.delete_database.assert_any_call(
            databases)

    def test_list_databases(self):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        couchdb_service.CouchDBAdmin.list_databases = MagicMock(
            return_value=['database1'])
        databases = self.manager.list_databases(self.context)
        self.assertThat(databases, Not(Is(None)))
        self.assertThat(databases, Equals(['database1']))
        couchdb_service.CouchDBAdmin.list_databases.assert_any_call(
            None, None, False)
