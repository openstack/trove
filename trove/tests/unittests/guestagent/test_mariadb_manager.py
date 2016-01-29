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
from trove.guestagent.datastore.experimental.mariadb import (
    manager as mariadb_manager)
from trove.guestagent.datastore.experimental.mariadb import (
    service as mariadb_service)
from trove.guestagent.datastore.mysql_common import service as mysql_service


class GuestAgentManagerTest(testtools.TestCase):

    def setUp(self):
        super(GuestAgentManagerTest, self).setUp()
        self.manager = mariadb_manager.Manager()
        self.context = TroveContext()
        patcher_rs = patch(
            'trove.guestagent.strategies.replication.get_instance')
        patcher_rs.start()
        self.addCleanup(patcher_rs.stop)

    @patch.object(mysql_service.BaseMySqlAppStatus, 'get',
                  new_callable=MagicMock)
    @patch.object(mariadb_service.MariaDBApp, 'install_cluster',
                  new_callable=MagicMock)
    def test_install_cluster(self, install_cluster, app_status_get):
        install_cluster.return_value = MagicMock()
        app_status_get.return_value = None

        replication_user = "repuser"
        configuration = "configuration"
        bootstrap = True
        self.manager.install_cluster(self.context, replication_user,
                                     configuration, bootstrap)
        app_status_get.assert_any_call()
        install_cluster.assert_called_with(
            replication_user, configuration, bootstrap)

    @patch.object(mysql_service.BaseMySqlAppStatus, 'get',
                  new_callable=MagicMock)
    @patch.object(mariadb_service.MariaDBApp, 'reset_admin_password',
                  new_callable=MagicMock)
    def test_reset_admin_password(self, reset_admin_password, app_status_get):
        reset_admin_password.return_value = None
        app_status_get.return_value = MagicMock()

        admin_password = "password"
        self.manager.reset_admin_password(self.context, admin_password)
        app_status_get.assert_any_call()
        reset_admin_password.assert_called_with(admin_password)
