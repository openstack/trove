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
from trove.guestagent.datastore.galera_common import manager as galera_manager
from trove.guestagent.datastore.galera_common import service as galera_service
from trove.guestagent.datastore.mysql_common import service as mysql_service
from trove.tests.unittests import trove_testtools


class GaleraTestApp(galera_service.GaleraApp):

    def __init__(self, status):
        super(GaleraTestApp, self).__init__(
            status, mysql_service.BaseLocalSqlClient,
            mysql_service.BaseKeepAliveConnection)

    @property
    def cluster_configuration(self):
        return self.configuration_manager.get_value('mysqld')


class GaleraTestRootAccess(mysql_service.BaseMySqlRootAccess):

    def __init__(self):
        super(GaleraTestRootAccess, self).__init__(
            mysql_service.BaseLocalSqlClient,
            GaleraTestApp(mysql_service.BaseMySqlAppStatus.get()))


class GaleraTestAdmin(mysql_service.BaseMySqlAdmin):
    def __init__(self):
        super(GaleraTestAdmin, self).__init__(
            mysql_service.BaseLocalSqlClient, GaleraTestRootAccess(),
            GaleraTestApp)


class GuestAgentManagerTest(trove_testtools.TestCase):

    def setUp(self):
        super(GuestAgentManagerTest, self).setUp()
        self.manager = galera_manager.GaleraManager(
            GaleraTestApp, mysql_service.BaseMySqlAppStatus,
            GaleraTestAdmin)
        self.context = TroveContext()
        patcher_rs = patch(
            'trove.guestagent.strategies.replication.get_instance')
        patcher_rs.start()
        self.addCleanup(patcher_rs.stop)

    @patch.object(mysql_service.BaseMySqlAppStatus, 'get',
                  new_callable=MagicMock)
    @patch.object(galera_service.GaleraApp, 'install_cluster',
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
    @patch.object(galera_service.GaleraApp, 'reset_admin_password',
                  new_callable=MagicMock)
    def test_reset_admin_password(self, reset_admin_password, app_status_get):
        reset_admin_password.return_value = None
        app_status_get.return_value = MagicMock()

        admin_password = "password"
        self.manager.reset_admin_password(self.context, admin_password)
        app_status_get.assert_any_call()
        reset_admin_password.assert_called_with(admin_password)

    @patch.object(mysql_service.BaseMySqlAppStatus, 'get',
                  new_callable=MagicMock)
    @patch.object(galera_service.GaleraApp, 'get_cluster_context')
    def test_get_cluster_context(self, get_cluster_ctxt, app_status_get):
        get_cluster_ctxt.return_value = {'cluster': 'info'}
        self.manager.get_cluster_context(self.context)
        app_status_get.assert_any_call()
        get_cluster_ctxt.assert_any_call()

    @patch.object(mysql_service.BaseMySqlAppStatus, 'get',
                  new_callable=MagicMock)
    @patch.object(galera_service.GaleraApp,
                  'write_cluster_configuration_overrides')
    def test_write_cluster_configuration_overrides(self, conf_overries,
                                                   app_status_get):
        cluster_configuration = "cluster_configuration"
        self.manager.write_cluster_configuration_overrides(
            self.context, cluster_configuration)
        app_status_get.assert_any_call()
        conf_overries.assert_called_with(cluster_configuration)

    @patch.object(mysql_service.BaseMySqlAppStatus, 'get',
                  new_callable=MagicMock)
    @patch.object(mysql_service.BaseMySqlAdmin, 'enable_root')
    def test_enable_root_with_password(self, reset_admin_pwd,
                                       app_status_get):
        admin_password = "password"
        self.manager.enable_root_with_password(self.context, admin_password)
        reset_admin_pwd.assert_called_with(admin_password)
