#    Copyright [2015] Hewlett-Packard Development Company, L.P.
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

from mock import MagicMock
from mock import patch
import testtools

from trove.common.context import TroveContext
from trove.guestagent.datastore.experimental.pxc.manager import Manager
import trove.guestagent.datastore.experimental.pxc.service as dbaas


class GuestAgentManagerTest(testtools.TestCase):

    def setUp(self):
        super(GuestAgentManagerTest, self).setUp()
        self.manager = Manager()
        self.context = TroveContext()
        self.patcher_rs = patch(
            'trove.guestagent.strategies.replication.get_instance')
        self.mock_rs_class = self.patcher_rs.start()

    def tearDown(self):
        super(GuestAgentManagerTest, self).tearDown()
        self.patcher_rs.stop()

    def test_install_cluster(self):
        mock_status = MagicMock()
        dbaas.PXCAppStatus.get = MagicMock(return_value=mock_status)

        dbaas.PXCApp.install_cluster = MagicMock(return_value=None)

        replication_user = "repuser"
        configuration = "configuration"
        bootstrap = True
        self.manager.install_cluster(self.context, replication_user,
                                     configuration, bootstrap)
        dbaas.PXCAppStatus.get.assert_any_call()
        dbaas.PXCApp.install_cluster.assert_called_with(
            replication_user, configuration, bootstrap)

    def test_reset_admin_password(self):
        mock_status = MagicMock()
        dbaas.PXCAppStatus.get = MagicMock(return_value=mock_status)

        dbaas.PXCApp.reset_admin_password = MagicMock(return_value=None)

        admin_password = "password"
        self.manager.reset_admin_password(self.context, admin_password)
        dbaas.PXCAppStatus.get.assert_any_call()
        dbaas.PXCApp.reset_admin_password.assert_called_with(
            admin_password)
