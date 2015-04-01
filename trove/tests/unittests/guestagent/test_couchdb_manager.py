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

import testtools
from mock import MagicMock
from mock import patch
from oslo_utils import netutils
from trove.common.context import TroveContext
from trove.common.instance import ServiceStatuses
from trove.guestagent import volume
from trove.guestagent.datastore.experimental.couchdb import (
    service as couchdb_service)
from trove.guestagent.datastore.experimental.couchdb import (
    manager as couchdb_manager)
from trove.guestagent import pkg as pkg


class GuestAgentCouchDBManagerTest(testtools.TestCase):

    def setUp(self):
        super(GuestAgentCouchDBManagerTest, self).setUp()
        self.real_status = couchdb_service.CouchDBAppStatus.set_status

        class FakeInstanceServiceStatus(object):
            status = ServiceStatuses.NEW

            def save(self):
                pass

        couchdb_service.CouchDBAppStatus.set_status = MagicMock(
            return_value=FakeInstanceServiceStatus())
        self.context = TroveContext()
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

    def test_update_status(self):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        self.manager.update_status(self.context)
        mock_status.update.assert_any_call()

    def _prepare_dynamic(self, packages,
                         config_content=None, device_path='/dev/vdb',
                         is_db_installed=True, backup_id=None, overrides=None):
        mock_status = MagicMock()
        mock_app = MagicMock()
        self.manager.appStatus = mock_status
        self.manager.app = mock_app

        mock_status.begin_install = MagicMock(return_value=None)
        mock_app.install_if_needed = MagicMock(return_value=None)
        pkg.Package.pkg_is_installed = MagicMock(return_value=is_db_installed)
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
                             mount_point="/var/lib/couchdb",
                             backup_info=None,
                             overrides=None,
                             cluster_config=None)

        # verification/assertion
        mock_status.begin_install.assert_any_call()
        mock_app.install_if_needed.assert_any_call(packages)
        mock_app.make_host_reachable.assert_any_call()
        mock_app.change_permissions.assert_any_call()

    def test_prepare_pkg(self):
        self._prepare_dynamic(['couchdb'])

    def test_prepare_no_pkg(self):
        self._prepare_dynamic([])

    def test_restart(self):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        with patch.object(couchdb_service.CouchDBApp, 'restart',
                          return_value=None):
            #invocation
            self.manager.restart(self.context)
            #verification/assertion
            couchdb_service.CouchDBApp.restart.assert_any_call()

    def test_stop_db(self):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        couchdb_service.CouchDBApp.stop_db = MagicMock(return_value=None)
        #invocation
        self.manager.stop_db(self.context)
        #verification/assertion
        couchdb_service.CouchDBApp.stop_db.assert_any_call(
            do_not_start_on_reboot=False)
