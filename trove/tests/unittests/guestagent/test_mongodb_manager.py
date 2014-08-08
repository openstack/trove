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
from mock import patch
from trove.common import utils
from trove.common.context import TroveContext
from trove.guestagent import volume
from trove.guestagent.datastore.mongodb import service as mongo_service
from trove.guestagent.datastore.mongodb import manager as mongo_manager
from trove.guestagent.volume import VolumeDevice


class GuestAgentMongoDBManagerTest(testtools.TestCase):

    def setUp(self):
        super(GuestAgentMongoDBManagerTest, self).setUp()
        self.context = TroveContext()
        self.manager = mongo_manager.Manager()
        self.origin_MongoDbAppStatus = mongo_service.MongoDbAppStatus
        self.origin_os_path_exists = os.path.exists
        self.origin_format = volume.VolumeDevice.format
        self.origin_migrate_data = volume.VolumeDevice.migrate_data
        self.origin_mount = volume.VolumeDevice.mount
        self.origin_mount_points = volume.VolumeDevice.mount_points
        self.origin_stop_db = mongo_service.MongoDBApp.stop_db
        self.origin_start_db = mongo_service.MongoDBApp.start_db
        self.orig_exec_with_to = utils.execute_with_timeout

    def tearDown(self):
        super(GuestAgentMongoDBManagerTest, self).tearDown()
        mongo_service.MongoDbAppStatus = self.origin_MongoDbAppStatus
        os.path.exists = self.origin_os_path_exists
        volume.VolumeDevice.format = self.origin_format
        volume.VolumeDevice.migrate_data = self.origin_migrate_data
        volume.VolumeDevice.mount = self.origin_mount
        volume.VolumeDevice.mount_points = self.origin_mount_points
        mongo_service.MongoDBApp.stop_db = self.origin_stop_db
        mongo_service.MongoDBApp.start_db = self.origin_start_db
        utils.execute_with_timeout = self.orig_exec_with_to

    def test_update_status(self):
        self.manager.status = MagicMock()
        self.manager.update_status(self.context)
        self.manager.status.update.assert_any_call()

    def test_prepare_from_backup(self):
        self._prepare_dynamic(backup_id='backup_id_123abc')

    def _prepare_dynamic(self, device_path='/dev/vdb', is_db_installed=True,
                         backup_id=None):

        # covering all outcomes is starting to cause trouble here
        backup_info = {'id': backup_id,
                       'location': 'fake-location',
                       'type': 'MongoDBDump',
                       'checksum': 'fake-checksum'} if backup_id else None

        mock_status = MagicMock()
        mock_app = MagicMock()
        self.manager.status = mock_status
        self.manager.app = mock_app

        mock_status.begin_install = MagicMock(return_value=None)
        volume.VolumeDevice.format = MagicMock(return_value=None)
        volume.VolumeDevice.migrate_data = MagicMock(return_value=None)
        volume.VolumeDevice.mount = MagicMock(return_value=None)
        volume.VolumeDevice.mount_points = MagicMock(return_value=[])

        mock_app.stop_db = MagicMock(return_value=None)
        mock_app.start_db = MagicMock(return_value=None)
        mock_app.clear_storage = MagicMock(return_value=None)
        os.path.exists = MagicMock(return_value=is_db_installed)

        with patch.object(utils, 'execute_with_timeout'):
            # invocation
            self.manager.prepare(context=self.context, databases=None,
                                 packages=['package'],
                                 memory_mb='2048', users=None,
                                 device_path=device_path,
                                 mount_point='/var/lib/mongodb',
                                 backup_info=backup_info)

        # verification/assertion
        mock_status.begin_install.assert_any_call()
        mock_app.install_if_needed.assert_any_call(['package'])
        mock_app.stop_db.assert_any_call()
        VolumeDevice.format.assert_any_call()
        VolumeDevice.migrate_data.assert_any_call('/var/lib/mongodb')
