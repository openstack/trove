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
import os

from oslo_log import log as logging
from oslo_utils import netutils

from trove.common import cfg
from trove.common import exception
from trove.common import utils
from trove.common.db.postgresql import models
from trove.guestagent.common import operating_system
from trove.guestagent.common.operating_system import FileMode
from trove.guestagent.datastore.postgres import service as pg_service
from trove.guestagent.strategies.replication import base

LOG = logging.getLogger(__name__)
CONF = cfg.CONF
REPL_USER = 'replicator'


class PostgresqlReplicationStreaming(base.Replication):
    def _create_replication_user(self, service, adm_mgr, pwfile):
        """Create the replication user and password file.

        Unfortunately, to be able to run pg_rewind, we need SUPERUSER, not just
        REPLICATION privilege
        """
        pw = utils.generate_random_password()
        operating_system.write_file(pwfile, pw, as_root=True)
        operating_system.chown(pwfile, user=CONF.database_service_uid,
                               group=CONF.database_service_uid, as_root=True)
        operating_system.chmod(pwfile, FileMode.SET_USR_RWX(),
                               as_root=True)
        LOG.debug(f"File {pwfile} created")

        LOG.debug(f"Creating replication user {REPL_USER}")
        repl_user = models.PostgreSQLUser(name=REPL_USER, password=pw)
        adm_mgr.create_user(repl_user, None,
                            *('REPLICATION', 'SUPERUSER', 'LOGIN'))

        return pw

    def _get_or_create_replication_user(self, service):
        """There are three scenarios we need to deal with here:

        - This is a fresh master, with no replicator user created.
           Generate a new u/p
        - We are attaching a new slave and need to give it the login creds
           Send the creds we have stored in PGDATA/.replpass
        - This is a failed-over-to slave, who will have the replicator user
           but not the credentials file. Recreate the repl user in this case
        """
        LOG.debug("Checking for replication user")

        pwfile = os.path.join(service.datadir, ".replpass")
        adm_mgr = service.adm

        if adm_mgr.user_exists(REPL_USER):
            if operating_system.exists(pwfile, as_root=True):
                LOG.debug("Found existing .replpass")
                pw = operating_system.read_file(pwfile, as_root=True)
            else:
                LOG.debug("Found user but not .replpass, recreate")
                adm_mgr.delete_user(models.PostgreSQLUser(REPL_USER))
                pw = self._create_replication_user(service, adm_mgr, pwfile)
        else:
            LOG.debug("Found no replicator user, create one")
            pw = self._create_replication_user(service, adm_mgr, pwfile)

        repl_user_info = {
            'name': REPL_USER,
            'password': pw
        }

        return repl_user_info

    def enable_as_master(self, service, master_config):
        """Primary postgredql settings.

        For a server to be a master in postgres, we need to enable
        the replication user in pg_hba.conf
        """
        self._get_or_create_replication_user(service)

        hba_entry = f"host replication {REPL_USER} 0.0.0.0/0 md5\n"
        tmp_hba = '/tmp/pg_hba'
        operating_system.copy(pg_service.HBA_CONFIG_FILE, tmp_hba,
                              force=True, as_root=True)
        operating_system.chmod(tmp_hba, FileMode.SET_ALL_RWX(),
                               as_root=True)
        with open(tmp_hba, 'a+') as hba_file:
            hba_file.write(hba_entry)

        operating_system.copy(tmp_hba, pg_service.HBA_CONFIG_FILE,
                              force=True, as_root=True)
        operating_system.chown(pg_service.HBA_CONFIG_FILE,
                               user=CONF.database_service_uid,
                               group=CONF.database_service_uid, as_root=True)
        operating_system.chmod(pg_service.HBA_CONFIG_FILE,
                               FileMode.SET_USR_RWX(),
                               as_root=True)
        operating_system.remove(tmp_hba, as_root=True)
        LOG.debug(f"{pg_service.HBA_CONFIG_FILE} changed")

        service.restart()

    def snapshot_for_replication(self, context, service, adm, location,
                                 snapshot_info):
        LOG.info("Creating backup for replication")

        volumes_mapping = {
            '/var/lib/postgresql/data': {
                'bind': '/var/lib/postgresql/data', 'mode': 'rw'
            },
            "/var/run/postgresql": {"bind": "/var/run/postgresql",
                                    "mode": "ro"},
        }
        extra_params = f"--pg-wal-archive-dir {pg_service.WAL_ARCHIVE_DIR}"
        service.create_backup(context, snapshot_info,
                              volumes_mapping=volumes_mapping,
                              need_dbuser=False,
                              extra_params=extra_params)

        LOG.info('Getting or creating replication user')
        replication_user = self._get_or_create_replication_user(service)

        log_position = {
            'replication_user': replication_user
        }
        return snapshot_info['id'], log_position

    def get_master_ref(self, service, snapshot_info):
        master_ref = {
            'host': netutils.get_my_ipv4(),
            'port': cfg.get_configuration_property('postgresql_port')
        }
        return master_ref

    def enable_as_slave(self, service, snapshot, slave_config):
        """Set up the replica server."""
        signal_file = f"{service.datadir}/standby.signal"
        operating_system.execute_shell_cmd(
            f"touch {signal_file}", [], shell=True, as_root=True)
        operating_system.chown(signal_file, CONF.database_service_uid,
                               CONF.database_service_uid, force=True,
                               as_root=True)
        LOG.debug("Standby signal file created")

        user = snapshot['log_position']['replication_user']
        conninfo = (f"host={snapshot['master']['host']} "
                    f"port={snapshot['master']['port']} "
                    f"dbname=postgres "
                    f"user={user['name']} password={user['password']}")
        service.configuration_manager.apply_system_override(
            {'primary_conninfo': conninfo})
        LOG.debug("primary_conninfo is set in the config file.")

    def detach_slave(self, service, for_failover):
        """Promote replica and wait for its running.

        Running on replica, detach from the primary.
        """
        service.adm.query("select pg_promote()")

        def _wait_for_failover():
            """Wait until slave has switched out of recovery mode"""
            return not service.is_replica()

        try:
            utils.poll_until(_wait_for_failover, time_out=60)
        except exception.PollTimeOut:
            raise exception.TroveError(
                "Timeout occurred waiting for replica to exit standby mode")

    def get_replica_context(self, service, adm):
        """Running on primary."""
        repl_user_info = self._get_or_create_replication_user(service)

        return {
            'master': self.get_master_ref(None, None),
            'log_position': {'replication_user': repl_user_info}
        }

    def cleanup_source_on_replica_detach(self, admin_service, replica_info):
        pass

    def _pg_rewind(self, service):
        conn_info = service.configuration_manager.get_value('primary_conninfo')
        service.pg_rewind(conn_info)

        signal_file = f"{service.datadir}/standby.signal"
        operating_system.execute_shell_cmd(
            f"touch {signal_file}", [], shell=True, as_root=True)
        operating_system.chown(signal_file, CONF.database_service_uid,
                               CONF.database_service_uid, force=True,
                               as_root=True)
        LOG.debug("Standby signal file created")

    def demote_master(self, service):
        """Running on the old primary.

        In order to demote a master we need to shutdown the server and call
        pg_rewind against the new master to enable a proper timeline
        switch.
        """
        service.stop_db()
        self._pg_rewind(service)
        service.restart()
