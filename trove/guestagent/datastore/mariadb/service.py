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
from oslo_utils.excutils import save_and_reraise_exception

from trove.common import cfg
from trove.common import constants
from trove.common import exception
from trove.common import utils
from trove.guestagent.datastore.mysql_common import service as mysql_service
from trove.guestagent.utils import docker as docker_util
from trove.guestagent.utils import mysql as mysql_util


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class MariaDBApp(mysql_service.BaseMySqlApp):

    HEALTHCHECK = {
        "test": ["CMD", "healthcheck.sh", "--defaults-file",
                 "/var/lib/mysql/data/.my-healthcheck.cnf",
                 "--connect", "--innodb_initialized"],
        "start_period": 10 * 1000000000,  # 10 seconds in nanoseconds
        "interval": 10 * 1000000000,
        "timeout": 5 * 1000000000,
        "retries": 3
    }
    # # to regenerate the .my-healthcheck.cnf after restoring
    _extra_envs = {"MARIADB_AUTO_UPGRADE": 1}
    # Set to True for io_uring feature
    _previledged = True

    def __init__(self, status, docker_client):
        super(MariaDBApp, self).__init__(status, docker_client)

    def wait_for_slave_status(self, status, client, max_time):
        def verify_slave_status():
            actual_status = client.execute(
                'SHOW GLOBAL STATUS like "Slave_running";').first()[1]
            return actual_status.upper() == status.upper()

        LOG.debug("Waiting for slave status %s with timeout %s",
                  status, max_time)
        try:
            utils.poll_until(verify_slave_status, sleep_time=3,
                             time_out=max_time)
            LOG.info("Replication status: %s.", status)
        except exception.PollTimeOut:
            raise RuntimeError(
                "Replication is not %(status)s after %(max)d seconds." %
                {'status': status.lower(), 'max': max_time})

    def _get_slave_status(self):
        with mysql_util.SqlClient(self.get_engine()) as client:
            return client.execute('SHOW SLAVE STATUS').first()

    def _get_master_UUID(self):
        slave_status = self._get_slave_status()
        return slave_status and slave_status['Master_Server_Id'] or None

    def _get_gtid_executed(self):
        with mysql_util.SqlClient(self.get_engine()) as client:
            return client.execute('SELECT @@global.gtid_binlog_pos').first()[0]

    def _get_gtid_slave_executed(self):
        with mysql_util.SqlClient(self.get_engine()) as client:
            return client.execute('SELECT @@global.gtid_slave_pos').first()[0]

    def get_last_txn(self):
        master_UUID = self._get_master_UUID()
        last_txn_id = '0'
        gtid_executed = self._get_gtid_slave_executed()
        for gtid_set in gtid_executed.split(','):
            uuid_set = gtid_set.split('-')
            if str(uuid_set[1]) == str(master_UUID):
                last_txn_id = uuid_set[-1]
                break
        return master_UUID, int(last_txn_id)

    def get_latest_txn_id(self):
        return self._get_gtid_executed()

    def wait_for_txn(self, txn):
        cmd = "SELECT MASTER_GTID_WAIT('%s')" % txn
        with mysql_util.SqlClient(self.get_engine()) as client:
            client.execute(cmd)

    def wipe_ib_logfiles(self):
        # mariadb_backup doesn't need to delete this file
        pass

    def reset_data_for_restore_snapshot(self, data_dir):
        """This function try remove slave status in database"""
        command = "--skip-slave-start=ON --datadir=%s" % data_dir

        extra_volumes = {
            "/etc/mysql": {"bind": "/etc/mysql", "mode": "rw"},
            constants.MYSQL_HOST_SOCKET_PATH: {
                "bind": "/var/run/mysqld", "mode": "rw"},
            data_dir: {"bind": data_dir, "mode": "rw"},
        }

        try:
            self.start_db(ds_version=CONF.datastore_version, command=command,
                          extra_volumes=extra_volumes)
            self.stop_slave(for_failover=False)
        except Exception as err:
            with save_and_reraise_exception():
                LOG.error("Failed to remove slave status: %s", str(err))
        finally:
            try:
                LOG.debug(
                    'The init container log: %s',
                    docker_util.get_container_logs(self.docker_client))
                docker_util.remove_container(self.docker_client)
            except Exception as err:
                LOG.error('Failed to remove container. error: %s', str(err))


class MariaDBRootAccess(mysql_service.BaseMySqlRootAccess):
    def __init__(self, app):
        super(MariaDBRootAccess, self).__init__(app)


class MariaDBAdmin(mysql_service.BaseMySqlAdmin):
    def __init__(self, app):
        root_access = MariaDBRootAccess(app)
        super(MariaDBAdmin, self).__init__(root_access, app)
