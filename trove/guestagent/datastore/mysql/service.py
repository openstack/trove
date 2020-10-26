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
import semantic_version

from trove.common import cfg
from trove.guestagent.datastore.mysql_common import service
from trove.guestagent.utils import mysql as mysql_util

CONF = cfg.CONF


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
            if uuid_set[0] == master_UUID:
                last_txn_id = uuid_set[-1].split('-')[-1]
                break
        return master_UUID, int(last_txn_id)

    def wait_for_txn(self, txn):
        with mysql_util.SqlClient(self.get_engine()) as client:
            client.execute("SELECT WAIT_UNTIL_SQL_THREAD_AFTER_GTIDS('%s')"
                           % txn)

    def get_backup_image(self):
        """Get the actual container image based on datastore version.

        For example, this method converts openstacktrove/db-backup-mysql:1.0.0
        to openstacktrove/db-backup-mysql5.7:1.0.0
        """
        image = cfg.get_configuration_property('backup_docker_image')
        name, tag = image.split(':', 1)

        # Get minor version
        cur_ver = semantic_version.Version.coerce(CONF.datastore_version)
        minor_ver = f"{cur_ver.major}.{cur_ver.minor}"

        return f"{name}{minor_ver}:{tag}"

    def get_backup_strategy(self):
        """Get backup strategy.

        innobackupex was removed in Percona XtraBackup 8.0, use xtrabackup
        instead.
        """
        strategy = cfg.get_configuration_property('backup_strategy')

        mysql_8 = semantic_version.Version('8.0.0')
        cur_ver = semantic_version.Version.coerce(CONF.datastore_version)
        if cur_ver >= mysql_8:
            strategy = 'xtrabackup'

        return strategy


class MySqlRootAccess(service.BaseMySqlRootAccess):
    def __init__(self, app):
        super(MySqlRootAccess, self).__init__(app)


class MySqlAdmin(service.BaseMySqlAdmin):
    def __init__(self, app):
        root_access = MySqlRootAccess(app)
        super(MySqlAdmin, self).__init__(root_access, app)
