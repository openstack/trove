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

from sqlalchemy.sql.expression import text

from oslo_log import log as logging
from oslo_utils.excutils import save_and_reraise_exception
from trove.common import cfg
from trove.common import constants
from trove.guestagent.datastore.mysql_common import service
from trove.guestagent.utils import docker as docker_util
from trove.guestagent.utils import mysql as mysql_util


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class MySqlApp(service.BaseMySqlApp):

    HEALTHCHECK = {
        "test": ["CMD", "mysqladmin", "ping", "-h",
                 "127.0.0.1", "-u", "root",
                 "--password=$MYSQL_ROOT_PASSWORD"],
        "start_period": 10 * 1000000000,  # 10 seconds in nanoseconds
        "interval": 10 * 1000000000,
        "timeout": 5 * 1000000000,
        "retries": 3
    }

    def _is_mysql84(self):
        mysql_84 = semantic_version.Version('8.4.0')
        cur_ver = semantic_version.Version.coerce(CONF.datastore_version)
        if cur_ver >= mysql_84:
            return True
        else:
            return False

    def __init__(self, status, docker_client):
        super(MySqlApp, self).__init__(status, docker_client)

    def _get_gtid_executed(self):
        with mysql_util.SqlClient(self.get_engine()) as client:
            return client.execute(
                text('SELECT @@global.gtid_executed')).first()[0]

    def _get_slave_status(self):
        with mysql_util.SqlClient(self.get_engine()) as client:
            if self._is_mysql84():
                return client.execute(text('SHOW REPLICA STATUS')).first()
            else:
                return client.execute(text('SHOW SLAVE STATUS')).first()

    def _get_master_UUID(self):
        slave_status = self._get_slave_status()
        if self._is_mysql84():
            return slave_status and slave_status._mapping['Source_UUID'] \
                or None
        else:
            return slave_status and slave_status._mapping['Master_UUID'] \
                or None

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
        if self._is_mysql84():
            _sql = "SELECT WAIT_FOR_EXECUTED_GTID_SET('%s')" % txn
        else:
            _sql = "SELECT WAIT_UNTIL_SQL_THREAD_AFTER_GTIDS('%s')" % txn
        with mysql_util.SqlClient(self.get_engine()) as client:
            client.execute(text(_sql))

    def stop_master(self):
        LOG.info("Stopping replication master.")
        if not self._is_mysql84():
            return super().stop_master()
        with mysql_util.SqlClient(self.get_engine()) as client:
            client.execute(text("RESET BINARY LOGS AND GTIDS"))

    def get_backup_image(self):
        """Get the actual container image based on datastore version.

        For example, this method converts openstacktrove/db-backup-mysql:1.0.0
        to openstacktrove/db-backup-mysql5.7:1.0.0

        **deprecated**: this function is for backward compatibility.
        """
        image = cfg.get_configuration_property('backup_docker_image')
        if not self._image_has_tag(image):
            return super().get_backup_image()
        else:
            name, tag = image.rsplit(':', 1)
            # Get minor version
            cur_ver = semantic_version.Version.coerce(CONF.datastore_version)
            minor_ver = f"{cur_ver.major}.{cur_ver.minor}"
            return f"{name}{minor_ver}:{tag}"

    def get_backup_strategy(self):
        """Get backup strategy.

        innobackupex was removed in Percona XtraBackup 8.0, use xtrabackup
        instead.
        """
        return 'xtrabackup'

    def reset_data_for_restore_snapshot(self, data_dir):
        """This function try remove replica status in database"""
        # '--skip-replica-start' was introduced in mysql 8.0.26 and the
        # '--skip-slave-start' not be removed yet for mysql 8.0.x
        if self._is_mysql84:
            command = "mysqld --skip-replica-start=ON --datadir=%s" % data_dir
        else:
            command = "mysqld --skip-slave-start=ON --datadir=%s" % data_dir

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

    def start_slave(self):
        LOG.info("Starting slave replication.")
        if not self._is_mysql84():
            return super().start_slave()
        with mysql_util.SqlClient(self.get_engine()) as client:
            client.execute(text('START REPLICA'))
            self.wait_for_slave_status("ON", client, 180)

    def stop_slave(self, for_failover):
        LOG.info("Stopping slave replication.")
        if not self._is_mysql84():
            return super().stop_slave(for_failover)
        replication_user = None
        with mysql_util.SqlClient(self.get_engine()) as client:
            result = client.execute(
                text('SHOW REPLICA STATUS')).mappings().first()
            if result:
                replication_user = result['Source_User']
                client.execute(text('STOP REPLICA'))
                client.execute(text('RESET REPLICA ALL'))
            self.wait_for_slave_status('OFF', client, 180)
            if not for_failover and replication_user:
                client.execute(
                    text('DROP USER IF EXISTS ' + replication_user))
        return {
            'replication_user': replication_user
        }


class MySqlRootAccess(service.BaseMySqlRootAccess):
    def __init__(self, app):
        super(MySqlRootAccess, self).__init__(app)


class MySqlAdmin(service.BaseMySqlAdmin):
    def __init__(self, app):
        root_access = MySqlRootAccess(app)
        super(MySqlAdmin, self).__init__(root_access, app)
