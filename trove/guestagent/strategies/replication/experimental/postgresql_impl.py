# Copyright 2014 Tesora, Inc.
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
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

import os

from oslo_log import log as logging
from oslo_utils import netutils
from trove.common import cfg
from trove.common import exception
from trove.common.i18n import _
from trove.common import stream_codecs
from trove.common import utils
from trove.guestagent.backup.backupagent import BackupAgent
from trove.guestagent.common import operating_system
from trove.guestagent.common.operating_system import FileMode
from trove.guestagent.datastore.experimental.postgresql import pgutil
from trove.guestagent.datastore.experimental.postgresql\
    .service.config import PgSqlConfig
from trove.guestagent.datastore.experimental.postgresql\
    .service.database import PgSqlDatabase
from trove.guestagent.datastore.experimental.postgresql\
    .service.install import PgSqlInstall
from trove.guestagent.datastore.experimental.postgresql \
    .service.process import PgSqlProcess
from trove.guestagent.datastore.experimental.postgresql\
    .service.root import PgSqlRoot
from trove.guestagent.db import models
from trove.guestagent.strategies import backup
from trove.guestagent.strategies.replication import base

AGENT = BackupAgent()
CONF = cfg.CONF

REPL_BACKUP_NAMESPACE = 'trove.guestagent.strategies.backup.experimental' \
                        '.postgresql_impl'
REPL_BACKUP_STRATEGY = 'PgBaseBackup'
REPL_BACKUP_INCREMENTAL_STRATEGY = 'PgBaseBackupIncremental'
REPL_BACKUP_RUNNER = backup.get_backup_strategy(
    REPL_BACKUP_STRATEGY, REPL_BACKUP_NAMESPACE)
REPL_BACKUP_INCREMENTAL_RUNNER = backup.get_backup_strategy(
    REPL_BACKUP_INCREMENTAL_STRATEGY, REPL_BACKUP_NAMESPACE)
REPL_EXTRA_OPTS = CONF.backup_runner_options.get(REPL_BACKUP_STRATEGY, '')

LOG = logging.getLogger(__name__)

TRIGGER_FILE = '/tmp/postgresql.trigger'
REPL_USER = 'replicator'
SLAVE_STANDBY_OVERRIDE = 'SlaveStandbyOverride'


class PostgresqlReplicationStreaming(
    base.Replication,
    PgSqlConfig,
    PgSqlDatabase,
    PgSqlRoot,
    PgSqlInstall,
):

    def __init__(self, *args, **kwargs):
        super(PostgresqlReplicationStreaming, self).__init__(*args, **kwargs)

    def get_master_ref(self, service, snapshot_info):
        master_ref = {
            'host': netutils.get_my_ipv4(),
            'port': CONF.postgresql.postgresql_port
        }
        return master_ref

    def backup_required_for_replication(self):
        return True

    def snapshot_for_replication(self, context, service,
                                 location, snapshot_info):

        snapshot_id = snapshot_info['id']
        replica_number = snapshot_info.get('replica_number', 1)

        LOG.debug("Acquiring backup for replica number %d." % replica_number)
        # Only create a backup if it's the first replica
        if replica_number == 1:
            AGENT.execute_backup(
                context, snapshot_info, runner=REPL_BACKUP_RUNNER,
                extra_opts=REPL_EXTRA_OPTS,
                incremental_runner=REPL_BACKUP_INCREMENTAL_RUNNER)
        else:
            LOG.info(_("Using existing backup created for previous replica."))

        repl_user_info = self._get_or_create_replication_user()

        log_position = {
            'replication_user': repl_user_info
        }

        return snapshot_id, log_position

    def _get_or_create_replication_user(self):
        # There are three scenarios we need to deal with here:
        # - This is a fresh master, with no replicator user created.
        #   Generate a new u/p
        # - We are attaching a new slave and need to give it the login creds
        #   Send the creds we have stored in PGDATA/.replpass
        # - This is a failed-over-to slave, who will have the replicator user
        #   but not the credentials file. Recreate the repl user in this case

        pwfile = os.path.join(self.pgsql_data_dir, ".replpass")
        if self.user_exists(REPL_USER):
            if operating_system.exists(pwfile, as_root=True):
                pw = operating_system.read_file(pwfile, as_root=True)
            else:
                u = models.PostgreSQLUser(REPL_USER)
                self._drop_user(context=None, user=u)
                pw = self._create_replication_user(pwfile)
        else:
            pw = self._create_replication_user(pwfile)

        repl_user_info = {
            'name': REPL_USER,
            'password': pw
        }

        return repl_user_info

    def _create_replication_user(self, pwfile):
        """Create the replication user. Unfortunately, to be able to
        run pg_rewind, we need SUPERUSER, not just REPLICATION privilege
        """

        pw = utils.generate_random_password()
        operating_system.write_file(pwfile, pw, as_root=True)
        operating_system.chown(pwfile, user=self.PGSQL_OWNER,
                               group=self.PGSQL_OWNER, as_root=True)
        operating_system.chmod(pwfile, FileMode.SET_USR_RWX(),
                               as_root=True)

        pgutil.psql("CREATE USER %s SUPERUSER ENCRYPTED "
                    "password '%s';" % (REPL_USER, pw))
        return pw

    def enable_as_master(self, service, master_config, for_failover=False):
        # For a server to be a master in postgres, we need to enable
        # replication user in pg_hba and ensure that WAL logging is
        # the appropriate level (use the same settings as backups)
        self._get_or_create_replication_user()
        hba_entry = "host   replication   replicator    0.0.0.0/0   md5 \n"

        tmp_hba = '/tmp/pg_hba'
        operating_system.copy(self.pgsql_hba_config, tmp_hba,
                              force=True, as_root=True)
        operating_system.chmod(tmp_hba, FileMode.SET_ALL_RWX(),
                               as_root=True)
        with open(tmp_hba, 'a+') as hba_file:
            hba_file.write(hba_entry)

        operating_system.copy(tmp_hba, self.pgsql_hba_config,
                              force=True, as_root=True)
        operating_system.chmod(self.pgsql_hba_config,
                               FileMode.SET_USR_RWX(),
                               as_root=True)
        operating_system.remove(tmp_hba, as_root=True)
        pgutil.psql("SELECT pg_reload_conf()")

    def enable_as_slave(self, service, snapshot, slave_config):
        """Adds appropriate config options to postgresql.conf, and writes out
        the recovery.conf file used to set up replication
        """
        self._write_standby_recovery_file(snapshot, sslmode='prefer')
        self.enable_hot_standby(service)
        # Ensure the WAL arch is empty before restoring
        PgSqlProcess.recreate_wal_archive_dir()

    def detach_slave(self, service, for_failover):
        """Touch trigger file in to disable recovery mode"""
        LOG.info(_("Detaching slave, use trigger to disable recovery mode"))
        operating_system.write_file(TRIGGER_FILE, '')
        operating_system.chown(TRIGGER_FILE, user=self.PGSQL_OWNER,
                               group=self.PGSQL_OWNER, as_root=True)

        def _wait_for_failover():
            # Wait until slave has switched out of recovery mode
            return not self.pg_is_in_recovery()

        try:
            utils.poll_until(_wait_for_failover, time_out=120)

        except exception.PollTimeOut:
            raise RuntimeError(_("Timeout occurred waiting for slave to exit"
                                 "recovery mode"))

    def cleanup_source_on_replica_detach(self, admin_service, replica_info):
        pass

    def _rewind_against_master(self, service):
        """Call pg_rewind to resync datadir against state of new master
        We should already have a recovery.conf file in PGDATA
        """
        rconf = operating_system.read_file(
            service.pgsql_recovery_config,
            codec=stream_codecs.KeyValueCodec(line_terminator='\n'),
            as_root=True)
        conninfo = rconf['primary_conninfo'].strip()

        # The recovery.conf file we want should already be there, but pg_rewind
        # will delete it, so copy it out first
        rec = self.pgsql_recovery_config
        tmprec = "/tmp/recovery.conf.bak"
        operating_system.move(rec, tmprec, as_root=True)

        cmd_full = " ".join(["pg_rewind", "-D", service.pgsql_data_dir,
                             '--source-pgdata=' + service.pgsql_data_dir,
                             '--source-server=' + conninfo])
        out, err = utils.execute("sudo", "su", "-", self.PGSQL_OWNER, "-c",
                                 "%s" % cmd_full, check_exit_code=0)
        LOG.debug("Got stdout %s and stderr %s from pg_rewind" %
                  (str(out), str(err)))

        operating_system.move(tmprec, rec, as_root=True)

    def demote_master(self, service):
        """In order to demote a master we need to shutdown the server and call
           pg_rewind against the new master to enable a proper timeline
           switch.
           """
        self.pg_checkpoint()
        self.stop_db(context=None)
        self._rewind_against_master(service)
        self.start_db(context=None)

    def connect_to_master(self, service, snapshot):
        # All that is required in postgresql to connect to a slave is to
        # restart with a recovery.conf file in the data dir, which contains
        # the connection information for the master.
        assert operating_system.exists(self.pgsql_recovery_config,
                                       as_root=True)
        self.restart(context=None)

    def _remove_recovery_file(self):
        operating_system.remove(self.pgsql_recovery_config, as_root=True)

    def _write_standby_recovery_file(self, snapshot, sslmode='prefer'):
        logging_config = snapshot['log_position']
        conninfo_params = \
            {'host': snapshot['master']['host'],
             'port': snapshot['master']['port'],
             'repl_user': logging_config['replication_user']['name'],
             'password': logging_config['replication_user']['password'],
             'sslmode': sslmode}

        conninfo = 'host=%(host)s ' \
                   'port=%(port)s ' \
                   'dbname=os_admin ' \
                   'user=%(repl_user)s ' \
                   'password=%(password)s ' \
                   'sslmode=%(sslmode)s ' % conninfo_params

        recovery_conf = "standby_mode = 'on'\n"
        recovery_conf += "primary_conninfo = '" + conninfo + "'\n"
        recovery_conf += "trigger_file = '/tmp/postgresql.trigger'\n"
        recovery_conf += "recovery_target_timeline='latest'\n"

        operating_system.write_file(self.pgsql_recovery_config, recovery_conf,
                                    codec=stream_codecs.IdentityCodec(),
                                    as_root=True)
        operating_system.chown(self.pgsql_recovery_config, user="postgres",
                               group="postgres", as_root=True)

    def enable_hot_standby(self, service):
        opts = {'hot_standby': 'on',
                'wal_level': 'hot_standby'}
        # wal_log_hints for pg_rewind is only supported in 9.4+
        if self.pg_version[1] in ('9.4', '9.5'):
            opts['wal_log_hints'] = 'on'

        service.configuration_manager.\
            apply_system_override(opts, SLAVE_STANDBY_OVERRIDE)

    def get_replica_context(self, service):
        repl_user_info = self._get_or_create_replication_user()

        log_position = {
            'replication_user': repl_user_info
        }

        return {
            'master': self.get_master_ref(None, None),
            'log_position': log_position
        }
