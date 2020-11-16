# Copyright 2020 Catalyst Cloud
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.
from trove.guestagent.datastore.mysql_common import service
from trove.guestagent.utils import mysql as mysql_util


class MySqlAppStatus(service.BaseMySqlAppStatus):
    def __init__(self, docker_client):
        super(MySqlAppStatus, self).__init__(docker_client)


class MySqlApp(service.BaseMySqlApp):
    def __init__(self, status, docker_client):
        super(MySqlApp, self).__init__(status, docker_client)

    def _get_gtid_executed(self):
        with mysql_util.SqlClient(self.get_engine()) as client:
            return client.execute('SELECT @@global.gtid_executed').first()[0]

    def _get_slave_status(self):
        with mysql_util.SqlClient(self.get_engine()) as client:
            return client.execute('SHOW SLAVE STATUS').first()

    def _get_master_UUID(self):
        slave_status = self._get_slave_status()
        return slave_status and slave_status['Master_UUID'] or None

    def get_latest_txn_id(self):
        return self._get_gtid_executed()

    def get_last_txn(self):
        master_UUID = self._get_master_UUID()
        last_txn_id = '0'
        gtid_executed = self._get_gtid_executed()
        for gtid_set in gtid_executed.split(','):
            uuid_set = gtid_set.split(':')
            if str(uuid_set[0]) == str(master_UUID):
                last_txn_id = uuid_set[-1].split('-')[-1]
                break
        return master_UUID, int(last_txn_id)

    def wait_for_txn(self, txn):
        with mysql_util.SqlClient(self.get_engine()) as client:
            client.execute("SELECT WAIT_UNTIL_SQL_THREAD_AFTER_GTIDS('%s')"
                           % txn)


class MySqlRootAccess(service.BaseMySqlRootAccess):
    def __init__(self, app):
        super(MySqlRootAccess, self).__init__(app)


class MySqlAdmin(service.BaseMySqlAdmin):
    def __init__(self, app):
        root_access = MySqlRootAccess(app)
        super(MySqlAdmin, self).__init__(root_access, app)
