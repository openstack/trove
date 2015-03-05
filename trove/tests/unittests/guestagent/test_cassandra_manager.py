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
from trove.common.context import TroveContext
from trove.common.instance import ServiceStatuses
from trove.guestagent import volume
from trove.guestagent.common import operating_system
from trove.guestagent.datastore.experimental.cassandra import (
    service as cass_service)
from trove.guestagent.datastore.experimental.cassandra import (
    manager as cass_manager)
from trove.guestagent import pkg as pkg


class GuestAgentCassandraDBManagerTest(testtools.TestCase):

    def setUp(self):
        super(GuestAgentCassandraDBManagerTest, self).setUp()
        self.real_status = cass_service.CassandraAppStatus.set_status

        class FakeInstanceServiceStatus(object):
            status = ServiceStatuses.NEW

            def save(self):
                pass

        cass_service.CassandraAppStatus.set_status = MagicMock(
            return_value=FakeInstanceServiceStatus())
        self.context = TroveContext()
        self.manager = cass_manager.Manager()
        self.pkg = cass_service.packager
        self.real_db_app_status = cass_service.CassandraAppStatus
        self.origin_os_path_exists = os.path.exists
        self.origin_format = volume.VolumeDevice.format
        self.origin_migrate_data = volume.VolumeDevice.migrate_data
        self.origin_mount = volume.VolumeDevice.mount
        self.origin_mount_points = volume.VolumeDevice.mount_points
        self.origin_stop_db = cass_service.CassandraApp.stop_db
        self.origin_start_db = cass_service.CassandraApp.start_db
        self.origin_install_db = cass_service.CassandraApp._install_db
        self.original_get_ip = operating_system.get_ip_address
        self.orig_make_host_reachable = (
            cass_service.CassandraApp.make_host_reachable)

    def tearDown(self):
        super(GuestAgentCassandraDBManagerTest, self).tearDown()
        cass_service.packager = self.pkg
        cass_service.CassandraAppStatus.set_status = self.real_db_app_status
        os.path.exists = self.origin_os_path_exists
        volume.VolumeDevice.format = self.origin_format
        volume.VolumeDevice.migrate_data = self.origin_migrate_data
        volume.VolumeDevice.mount = self.origin_mount
        volume.VolumeDevice.mount_points = self.origin_mount_points
        cass_service.CassandraApp.stop_db = self.origin_stop_db
        cass_service.CassandraApp.start_db = self.origin_start_db
        cass_service.CassandraApp._install_db = self.origin_install_db
        operating_system.get_ip_address = self.original_get_ip
        cass_service.CassandraApp.make_host_reachable = (
            self.orig_make_host_reachable)

    def test_update_status(self):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        self.manager.update_status(self.context)
        mock_status.update.assert_any_call()

    def test_prepare_pkg(self):
        self._prepare_dynamic(['cassandra'])

    def test_prepare_no_pkg(self):
        self._prepare_dynamic([])

    def test_prepare_db_not_installed(self):
        self._prepare_dynamic([], is_db_installed=False)

    def test_prepare_db_not_installed_no_package(self):
        self._prepare_dynamic([],
                              is_db_installed=True)

    def _prepare_dynamic(self, packages,
                         config_content='MockContent', device_path='/dev/vdb',
                         is_db_installed=True, backup_id=None,
                         is_root_enabled=False,
                         overrides=None):
        # covering all outcomes is starting to cause trouble here
        if not backup_id:
            backup_info = {'id': backup_id,
                           'location': 'fake-location',
                           'type': 'InnoBackupEx',
                           'checksum': 'fake-checksum',
                           }

        mock_status = MagicMock()
        mock_app = MagicMock()
        self.manager.appStatus = mock_status
        self.manager.app = mock_app

        mock_status.begin_install = MagicMock(return_value=None)
        mock_app.install_if_needed = MagicMock(return_value=None)
        pkg.Package.pkg_is_installed = MagicMock(return_value=is_db_installed)
        mock_app.init_storage_structure = MagicMock(return_value=None)
        mock_app.write_config = MagicMock(return_value=None)
        mock_app.make_host_reachable = MagicMock(return_value=None)
        mock_app.restart = MagicMock(return_value=None)
        mock_app.start_db = MagicMock(return_value=None)
        mock_app.stop_db = MagicMock(return_value=None)
        os.path.exists = MagicMock(return_value=True)
        volume.VolumeDevice.format = MagicMock(return_value=None)
        volume.VolumeDevice.migrate_data = MagicMock(return_value=None)
        volume.VolumeDevice.mount = MagicMock(return_value=None)
        volume.VolumeDevice.mount_points = MagicMock(return_value=[])

        # invocation
        self.manager.prepare(context=self.context, packages=packages,
                             config_contents=config_content,
                             databases=None,
                             memory_mb='2048', users=None,
                             device_path=device_path,
                             mount_point="/var/lib/cassandra",
                             backup_info=backup_info,
                             overrides=None,
                             cluster_config=None)

        # verification/assertion
        mock_status.begin_install.assert_any_call()
        mock_app.install_if_needed.assert_any_call(packages)
        mock_app.init_storage_structure.assert_any_call('/var/lib/cassandra')
        mock_app.make_host_reachable.assert_any_call()
        mock_app.start_db.assert_any_call()
        mock_app.stop_db.assert_any_call()
