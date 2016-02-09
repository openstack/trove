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

from trove.common.context import TroveContext
from trove.guestagent.datastore.experimental.pxc.manager import Manager
import trove.guestagent.datastore.experimental.pxc.service as dbaas
from trove.tests.unittests import trove_testtools


class GuestAgentManagerTest(trove_testtools.TestCase):

    def setUp(self):
        super(GuestAgentManagerTest, self).setUp()
        self.manager = Manager()
        self.context = TroveContext()
        self.patcher_rs = patch(
            'trove.guestagent.strategies.replication.get_instance')
        self.mock_rs_class = self.patcher_rs.start()

        status_patcher = patch.object(dbaas.PXCAppStatus, 'get',
                                      return_value=MagicMock())
        self.addCleanup(status_patcher.stop)
        self.status_get_mock = status_patcher.start()

    def tearDown(self):
        super(GuestAgentManagerTest, self).tearDown()
        self.patcher_rs.stop()

    @patch.object(dbaas.PXCApp, 'install_cluster')
    def test_install_cluster(self, install_cluster_mock):
        replication_user = "repuser"
        configuration = "configuration"
        bootstrap = True
        self.manager.install_cluster(self.context, replication_user,
                                     configuration, bootstrap)
        self.status_get_mock.assert_any_call()
        install_cluster_mock.assert_called_with(
            replication_user, configuration, bootstrap)

    @patch.object(dbaas.PXCApp, 'reset_admin_password')
    def test_reset_admin_password(self, reset_admin_pwd):
        admin_password = "password"
        self.manager.reset_admin_password(self.context, admin_password)
        self.status_get_mock.assert_any_call()
        reset_admin_pwd.assert_called_with(admin_password)

    @patch.object(dbaas.PXCApp, 'get_cluster_context')
    def test_get_cluster_context(self, get_cluster_ctxt):
        get_cluster_ctxt.return_value = {'cluster': 'info'}
        self.manager.get_cluster_context(self.context)
        self.status_get_mock.assert_any_call()
        get_cluster_ctxt.assert_any_call()

    @patch.object(dbaas.PXCApp, 'write_cluster_configuration_overrides')
    def test_write_cluster_configuration_overrides(self, conf_overries):
        cluster_configuration = "cluster_configuration"
        self.manager.write_cluster_configuration_overrides(
            self.context, cluster_configuration)
        self.status_get_mock.assert_any_call()
        conf_overries.assert_called_with(cluster_configuration)
