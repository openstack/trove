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

import testtools
from mock import Mock
from mockito import verify, when, unstub, any, mock
from trove.common.context import TroveContext
from trove.guestagent import volume
from trove.guestagent.common import operating_system
from trove.guestagent.datastore.couchbase import service as couch_service
from trove.guestagent.datastore.couchbase import manager as couch_manager


class GuestAgentCouchbaseManagerTest(testtools.TestCase):

    def setUp(self):
        super(GuestAgentCouchbaseManagerTest, self).setUp()
        self.context = TroveContext()
        self.manager = couch_manager.Manager()
        self.packages = 'couchbase-server'
        self.origin_CouchbaseAppStatus = couch_service.CouchbaseAppStatus
        self.origin_format = volume.VolumeDevice.format
        self.origin_mount = volume.VolumeDevice.mount
        self.origin_stop_db = couch_service.CouchbaseApp.stop_db
        self.origin_start_db = couch_service.CouchbaseApp.start_db
        operating_system.get_ip_address = Mock()

    def tearDown(self):
        super(GuestAgentCouchbaseManagerTest, self).tearDown()
        couch_service.CouchbaseAppStatus = self.origin_CouchbaseAppStatus
        volume.VolumeDevice.format = self.origin_format
        volume.VolumeDevice.mount = self.origin_mount
        couch_service.CouchbaseApp.stop_db = self.origin_stop_db
        couch_service.CouchbaseApp.start_db = self.origin_start_db
        unstub()

    def test_update_status(self):
        mock_status = mock()
        self.manager.appStatus = mock_status
        self.manager.update_status(self.context)
        verify(mock_status).update()

    def test_prepare_device_path_true(self):
        self._prepare_dynamic()

    def _prepare_dynamic(self, device_path='/dev/vdb', is_db_installed=True,
                         backup_info=None):
        mock_status = mock()
        self.manager.appStatus = mock_status
        when(mock_status).begin_install().thenReturn(None)
        when(volume.VolumeDevice).format().thenReturn(None)
        when(volume.VolumeDevice).mount().thenReturn(None)
        when(couch_service.CouchbaseApp).install_if_needed().thenReturn(None)
        when(couch_service.CouchbaseApp).complete_install_or_restart(
            any()).thenReturn(None)
        #invocation
        self.manager.prepare(self.context, self.packages, None, 2048,
                             None, device_path=device_path,
                             mount_point='/var/lib/couchbase',
                             backup_info=backup_info)
        #verification/assertion
        verify(mock_status).begin_install()
        verify(couch_service.CouchbaseApp).install_if_needed(self.packages)
        verify(couch_service.CouchbaseApp).complete_install_or_restart()

    def test_restart(self):
        mock_status = mock()
        self.manager.appStatus = mock_status
        when(couch_service.CouchbaseApp).restart().thenReturn(None)
        #invocation
        self.manager.restart(self.context)
        #verification/assertion
        verify(couch_service.CouchbaseApp).restart()

    def test_stop_db(self):
        mock_status = mock()
        self.manager.appStatus = mock_status
        when(couch_service.CouchbaseApp).stop_db(
            do_not_start_on_reboot=False).thenReturn(None)
        #invocation
        self.manager.stop_db(self.context)
        #verification/assertion
        verify(couch_service.CouchbaseApp).stop_db(
            do_not_start_on_reboot=False)
