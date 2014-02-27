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
from mock import Mock
from mockito import verify, when, unstub, any, mock
from trove.common.context import TroveContext
from trove.common.instance import ServiceStatuses
from trove.guestagent import volume
from trove.guestagent.common import operating_system
from trove.guestagent.datastore.cassandra import service as cass_service
from trove.guestagent.datastore.cassandra import manager as cass_manager
from trove.guestagent import pkg


class GuestAgentCassandraDBManagerTest(testtools.TestCase):

    def setUp(self):
        super(GuestAgentCassandraDBManagerTest, self).setUp()
        self.real_status = cass_service.CassandraAppStatus.set_status

        class FakeInstanceServiceStatus(object):
            status = ServiceStatuses.NEW

            def save(self):
                pass

        cass_service.CassandraAppStatus.set_status = Mock(
            return_value=FakeInstanceServiceStatus())
        self.context = TroveContext()
        self.manager = cass_manager.Manager()
        self.pkg = cass_service.packager
        self.real_db_app_status = cass_service.CassandraAppStatus
        self.origin_os_path_exists = os.path.exists
        self.origin_format = volume.VolumeDevice.format
        self.origin_migrate_data = volume.VolumeDevice.migrate_data
        self.origin_mount = volume.VolumeDevice.mount
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
        cass_service.CassandraApp.stop_db = self.origin_stop_db
        cass_service.CassandraApp.start_db = self.origin_start_db
        cass_service.CassandraApp._install_db = self.origin_install_db
        operating_system.get_ip_address = self.original_get_ip
        cass_service.CassandraApp.make_host_reachable = (
            self.orig_make_host_reachable)
        unstub()

    def test_update_status(self):
        mock_status = mock()
        self.manager.appStatus = mock_status
        self.manager.update_status(self.context)
        verify(mock_status).update()

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
                         config_content=any(), device_path='/dev/vdb',
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

        mock_status = mock()
        self.manager.appStatus = mock_status
        when(mock_status).begin_install().thenReturn(None)

        mock_app = mock()
        self.manager.app = mock_app

        when(mock_app).install_if_needed(packages).thenReturn(None)
        (when(pkg.Package).pkg_is_installed(any()).
         thenReturn(is_db_installed))
        when(mock_app).init_storage_structure(any()).thenReturn(None)
        when(mock_app).write_config(config_content).thenReturn(None)
        when(mock_app).make_host_reachable().thenReturn(None)
        when(mock_app).restart().thenReturn(None)
        when(os.path).exists(any()).thenReturn(True)

        when(volume.VolumeDevice).format().thenReturn(None)
        when(volume.VolumeDevice).migrate_data(any()).thenReturn(None)
        when(volume.VolumeDevice).mount().thenReturn(None)

        # invocation
        self.manager.prepare(context=self.context, packages=packages,
                             config_contents=config_content,
                             databases=None,
                             memory_mb='2048', users=None,
                             device_path=device_path,
                             mount_point="/var/lib/cassandra",
                             backup_info=backup_info,
                             overrides=None)
        # verification/assertion
        verify(mock_status).begin_install()
        verify(mock_app).install_if_needed(packages)
        verify(mock_app).init_storage_structure(any())
        verify(mock_app).make_host_reachable()
        verify(mock_app).restart()
