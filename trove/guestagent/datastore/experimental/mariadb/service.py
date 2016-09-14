# Copyright 2015 Tesora, Inc.
# All Rights Reserved.
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
#

from oslo_log import log as logging

from trove.common.i18n import _
from trove.guestagent.common import operating_system
from trove.guestagent.datastore.galera_common import service as galera_service
from trove.guestagent.datastore.mysql_common import service as mysql_service

LOG = logging.getLogger(__name__)


class MariaDBApp(galera_service.GaleraApp):

    OS = operating_system.get_os()

    def __init__(self, status):
        super(MariaDBApp, self).__init__(
            status, mysql_service.BaseLocalSqlClient,
            mysql_service.BaseKeepAliveConnection)

    @property
    def service_candidates(self):
        service_candidates = super(MariaDBApp, self).service_candidates
        return {
            operating_system.DEBIAN: service_candidates,
            operating_system.REDHAT: ["mariadb"],
            operating_system.SUSE: service_candidates
        }[self.OS]

    @property
    def mysql_service(self):
        result = super(MariaDBApp, self).mysql_service
        if result['type'] == 'sysvinit':
            result['cmd_bootstrap_galera_cluster'] = (
                "sudo service %s bootstrap"
                % result['service'])
        elif result['type'] == 'systemd':
            # TODO(mwj 2016/01/28): determine RHEL start for MariaDB Cluster
            result['cmd_bootstrap_galera_cluster'] = (
                "sudo systemctl start %s@bootstrap.service"
                % result['service'])
        return result

    @property
    def cluster_configuration(self):
        return self.configuration_manager.get_value('galera')

    def _get_slave_status(self):
        with self.local_sql_client(self.get_engine()) as client:
            return client.execute('SHOW SLAVE STATUS').first()

    def _get_master_UUID(self):
        slave_status = self._get_slave_status()
        return slave_status and slave_status['Master_Server_Id'] or None

    def _get_gtid_executed(self):
        with self.local_sql_client(self.get_engine()) as client:
            return client.execute('SELECT @@global.gtid_binlog_pos').first()[0]

    def get_last_txn(self):
        master_UUID = self._get_master_UUID()
        last_txn_id = '0'
        gtid_executed = self._get_gtid_executed()
        for gtid_set in gtid_executed.split(','):
            uuid_set = gtid_set.split('-')
            if uuid_set[1] == master_UUID:
                last_txn_id = uuid_set[-1]
                break
        return master_UUID, int(last_txn_id)

    def get_latest_txn_id(self):
        LOG.info(_("Retrieving latest txn id."))
        return self._get_gtid_executed()

    def wait_for_txn(self, txn):
        LOG.info(_("Waiting on txn '%s'.") % txn)
        with self.local_sql_client(self.get_engine()) as client:
            client.execute("SELECT MASTER_GTID_WAIT('%s')" % txn)


class MariaDBRootAccess(mysql_service.BaseMySqlRootAccess):
    def __init__(self):
        super(MariaDBRootAccess, self).__init__(
            mysql_service.BaseLocalSqlClient,
            MariaDBApp(mysql_service.BaseMySqlAppStatus.get()))


class MariaDBAdmin(mysql_service.BaseMySqlAdmin):
    def __init__(self):
        super(MariaDBAdmin, self).__init__(
            mysql_service.BaseLocalSqlClient, MariaDBRootAccess(),
            MariaDBApp)
