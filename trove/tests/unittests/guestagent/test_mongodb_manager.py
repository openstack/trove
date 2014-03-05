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
from mockito import verify, when, unstub, any, mock
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
        self.origin_stop_db = mongo_service.MongoDBApp.stop_db
        self.origin_start_db = mongo_service.MongoDBApp.start_db

    def tearDown(self):
        super(GuestAgentMongoDBManagerTest, self).tearDown()
        mongo_service.MongoDbAppStatus = self.origin_MongoDbAppStatus
        os.path.exists = self.origin_os_path_exists
        volume.VolumeDevice.format = self.origin_format
        volume.VolumeDevice.migrate_data = self.origin_migrate_data
        volume.VolumeDevice.mount = self.origin_mount
        mongo_service.MongoDBApp.stop_db = self.origin_stop_db
        mongo_service.MongoDBApp.start_db = self.origin_start_db
        unstub()

    def test_update_status(self):
        self.manager.status = mock()
        self.manager.update_status(self.context)
        verify(self.manager.status).update()

    def test_prepare_from_backup(self):
        self._prepare_dynamic(backup_id='backup_id_123abc')

    def _prepare_dynamic(self, device_path='/dev/vdb', is_db_installed=True,
                         backup_id=None):

        # covering all outcomes is starting to cause trouble here
        backup_info = {'id': backup_id,
                       'location': 'fake-location',
                       'type': 'MongoDBDump',
                       'checksum': 'fake-checksum'} if backup_id else None

        mock_status = mock()
        self.manager.status = mock_status
        when(mock_status).begin_install().thenReturn(None)

        when(VolumeDevice).format().thenReturn(None)
        when(VolumeDevice).migrate_data(any()).thenReturn(None)
        when(VolumeDevice).mount().thenReturn(None)

        mock_app = mock()
        self.manager.app = mock_app
        when(mock_app).stop_db().thenReturn(None)
        when(mock_app).start_db().thenReturn(None)
        when(mock_app).clear_storage().thenReturn(None)
        when(os.path).exists(any()).thenReturn(is_db_installed)

        # invocation
        self.manager.prepare(context=self.context, databases=None,
                             packages=['package'],
                             memory_mb='2048', users=None,
                             device_path=device_path,
                             mount_point='/var/lib/mongodb',
                             backup_info=backup_info)
        # verification/assertion
        verify(mock_status).begin_install()
        verify(VolumeDevice).format()
        verify(mock_app).stop_db()
        verify(VolumeDevice).migrate_data(any())
        verify(mock_app).install_if_needed(any())
