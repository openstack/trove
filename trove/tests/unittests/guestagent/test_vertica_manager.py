#Copyright [2015] Hewlett-Packard Development Company, L.P.
#Licensed under the Apache License, Version 2.0 (the "License");
#you may not use this file except in compliance with the License.
#You may obtain a copy of the License at
#
#http://www.apache.org/licenses/LICENSE-2.0
#
#Unless required by applicable law or agreed to in writing, software
#distributed under the License is distributed on an "AS IS" BASIS,
#WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#See the License for the specific language governing permissions and
#limitations under the License.

import testtools
from mock import MagicMock
from trove.common.context import TroveContext
from trove.guestagent import volume
from trove.guestagent.datastore.experimental.vertica.manager import Manager
from trove.guestagent.datastore.experimental.vertica.service import VerticaApp
from trove.guestagent.volume import VolumeDevice


class GuestAgentManagerTest(testtools.TestCase):
    def setUp(self):
        super(GuestAgentManagerTest, self).setUp()
        self.context = TroveContext()
        self.manager = Manager()
        self.origin_format = volume.VolumeDevice.format
        self.origin_migrate_data = volume.VolumeDevice.migrate_data
        self.origin_mount = volume.VolumeDevice.mount
        self.origin_unmount = volume.VolumeDevice.unmount
        self.origin_mount_points = volume.VolumeDevice.mount_points
        self.origin_set_read = volume.VolumeDevice.set_readahead_size
        self.origin_install_vertica = VerticaApp.install_vertica
        self.origin_create_db = VerticaApp.create_db
        self.origin_stop_db = VerticaApp.stop_db
        self.origin_start_db = VerticaApp.start_db
        self.origin_restart = VerticaApp.restart
        self.origin_install_if = VerticaApp.install_if_needed
        self.origin_complete_install = VerticaApp.complete_install_or_restart

    def tearDown(self):
        super(GuestAgentManagerTest, self).tearDown()
        volume.VolumeDevice.format = self.origin_format
        volume.VolumeDevice.migrate_data = self.origin_migrate_data
        volume.VolumeDevice.mount = self.origin_mount
        volume.VolumeDevice.unmount = self.origin_unmount
        volume.VolumeDevice.mount_points = self.origin_mount_points
        volume.VolumeDevice.set_readahead_size = self.origin_set_read
        VerticaApp.create_db = self.origin_create_db
        VerticaApp.install_vertica = self.origin_install_vertica
        VerticaApp.stop_db = self.origin_stop_db
        VerticaApp.start_db = self.origin_start_db
        VerticaApp.restart = self.origin_restart
        VerticaApp.install_if_needed = self.origin_install_if
        VerticaApp.complete_install_or_restart = self.origin_complete_install

    def test_update_status(self):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        self.manager.update_status(self.context)
        mock_status.update.assert_any_call()

    def _prepare_dynamic(self, packages,
                         config_content='MockContent', device_path='/dev/vdb',
                         backup_id=None,
                         overrides=None, is_mounted=False):
        # covering all outcomes is starting to cause trouble here
        expected_vol_count = 1 if device_path else 0
        if not backup_id:
            backup_info = {'id': backup_id,
                           'location': 'fake-location',
                           'type': 'InnoBackupEx',
                           'checksum': 'fake-checksum',
                           }

        mock_status = MagicMock()
        self.manager.appStatus = mock_status

        mock_status.begin_install = MagicMock(return_value=None)
        path_exists_function = MagicMock(return_value=True)
        volume.VolumeDevice.format = MagicMock(return_value=None)
        volume.VolumeDevice.migrate_data = MagicMock(return_value=None)
        volume.VolumeDevice.mount = MagicMock(return_value=None)
        mount_points = []
        if is_mounted:
            mount_points = ['/mnt']
        VolumeDevice.mount_points = MagicMock(return_value=mount_points)
        VolumeDevice.unmount = MagicMock(return_value=None)

        VerticaApp.install_if_needed = MagicMock(return_value=None)
        VerticaApp.install_vertica = MagicMock(return_value=None)
        VerticaApp.create_db = MagicMock(return_value=None)
        VerticaApp.prepare_for_install_vertica = MagicMock(return_value=None)
        VerticaApp.complete_install_or_restart = MagicMock(return_value=None)
        # invocation
        self.manager.prepare(context=self.context, packages=packages,
                             config_contents=config_content,
                             databases=None,
                             memory_mb='2048', users=None,
                             device_path=device_path,
                             mount_point="/var/lib/vertica",
                             backup_info=backup_info,
                             overrides=None,
                             cluster_config=None,
                             path_exists_function=path_exists_function)

        self.assertEqual(VolumeDevice.format.call_count, expected_vol_count)
        self.assertEqual(VolumeDevice.migrate_data.call_count,
                         expected_vol_count)
        self.assertEqual(VolumeDevice.mount_points.call_count,
                         expected_vol_count)
        if is_mounted:
            self.assertEqual(VolumeDevice.unmount.call_count, 1)
        else:
            self.assertEqual(VolumeDevice.unmount.call_count, 0)

        VerticaApp.install_if_needed.assert_any_call(packages)
        VerticaApp.prepare_for_install_vertica.assert_any_call()
        VerticaApp.install_vertica.assert_any_call()
        VerticaApp.create_db.assert_any_call()
        VerticaApp.complete_install_or_restart.assert_any_call()

    def test_prepare_pkg(self):
        self._prepare_dynamic(['vertica'])

    def test_prepare_no_pkg(self):
        self._prepare_dynamic([])

    def test_restart(self):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        VerticaApp.restart = MagicMock(return_value=None)
        #invocation
        self.manager.restart(self.context)
        #verification/assertion
        VerticaApp.restart.assert_any_call()

    def test_stop_db(self):
        mock_status = MagicMock()
        self.manager.appStatus = mock_status
        VerticaApp.stop_db = MagicMock(return_value=None)
        #invocation
        self.manager.stop_db(self.context)
        #verification/assertion
        VerticaApp.stop_db.assert_any_call(do_not_start_on_reboot=False)
