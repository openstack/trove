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
from trove.common.db.postgresql import models
from trove.common import exception
from trove.common.i18n import _
from trove.common import stream_codecs
from trove.common import utils
from trove.guestagent.backup.backupagent import BackupAgent
from trove.guestagent.common import operating_system
from trove.guestagent.common.operating_system import FileMode
from trove.guestagent.strategies import backup
from trove.guestagent.strategies.replication import base

AGENT = BackupAgent()
CONF = cfg.CONF

REPL_BACKUP_NAMESPACE = 'trove.guestagent.strategies.backup.experimental' \
                        '.postgresql_impl'

LOG = logging.getLogger(__name__)

TRIGGER_FILE = '/tmp/postgresql.trigger'
REPL_USER = 'replicator'
SLAVE_STANDBY_OVERRIDE = 'SlaveStandbyOverride'


class PostgresqlReplicationStreaming(base.Replication):

    def __init__(self, *args, **kwargs):
        super(PostgresqlReplicationStreaming, self).__init__(*args, **kwargs)

    @property
    def repl_backup_runner(self):
        return backup.get_backup_strategy('PgBaseBackup',
                                          REPL_BACKUP_NAMESPACE)

    @property
    def repl_incr_backup_runner(self):
        return backup.get_backup_strategy('PgBaseBackupIncremental',
                                          REPL_BACKUP_NAMESPACE)

    @property
    def repl_backup_extra_opts(self):
        return CONF.backup_runner_options.get('PgBaseBackup', '')

    def get_master_ref(self, service, snapshot_info):
        master_ref = {
            'host': netutils.get_my_ipv4(),
            'port': cfg.get_configuration_property('postgresql_port')
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
                context, snapshot_info, runner=self.repl_backup_runner,
                extra_opts=self.repl_backup_extra_opts,
                incremental_runner=self.repl_incr_backup_runner)
        else:
            LOG.info(_("Using existing backup created for previous replica."))

        repl_user_info = self._get_or_create_replication_user(service)

        log_position = {
            'replication_user': repl_user_info
        }

        return snapshot_id, log_position

    def _get_or_create_replication_user(self, service):
        """There are three scenarios we need to deal with here:
        - This is a fresh master, with no replicator user created.
           Generate a new u/p
        - We are attaching a new slave and need to give it the login creds
           Send the creds we have stored in PGDATA/.replpass
        - This is a failed-over-to slave, who will have the replicator user
           but not the credentials file. Recreate the repl user in this case
        """

        LOG.debug("Checking for replicator user")
        pwfile = os.path.join(service.pgsql_data_dir, ".replpass")
        admin = service.build_admin()
        if admin.user_exists(REPL_USER):
            if operating_system.exists(pwfile, as_root=True):
                LOG.debug("Found existing .replpass, returning pw")
                pw = operating_system.read_file(pwfile, as_root=True)
            else:
                LOG.debug("Found user but not .replpass, recreate")
                u = models.PostgreSQLUser(REPL_USER)
                admin._drop_user(context=None, user=u)
                pw = self._create_replication_user(service, admin, pwfile)
        else:
            LOG.debug("Found no replicator user, create one")
            pw = self._create_replication_user(service, admin, pwfile)

        repl_user_info = {
            'name': REPL_USER,
            'password': pw
        }

        return repl_user_info

    def _create_replication_user(self, service, admin, pwfile):
        """Create the replication user. Unfortunately, to be able to
        run pg_rewind, we need SUPERUSER, not just REPLICATION privilege
        """

        pw = utils.generate_random_password()
        operating_system.write_file(pwfile, pw, as_root=True)
        operating_system.chown(pwfile, user=service.pgsql_owner,
                               group=service.pgsql_owner, as_root=True)
        operating_system.chmod(pwfile, FileMode.SET_USR_RWX(),
                               as_root=True)

        repl_user = models.PostgreSQLUser(name=REPL_USER, password=pw)
        admin._create_user(context=None, user=repl_user)
        admin.alter_user(None, repl_user, True, 'REPLICATION', 'LOGIN')

        return pw

    def enable_as_master(self, service, master_config, for_failover=False):
        """For a server to be a master in postgres, we need to enable
        the replication user in pg_hba and ensure that WAL logging is
        at the appropriate level (use the same settings as backups)
        """
        LOG.debug("Enabling as master, with cfg: %s " % master_config)
        self._get_or_create_replication_user(service)
        hba_entry = "host   replication   replicator    0.0.0.0/0   md5 \n"

        tmp_hba = '/tmp/pg_hba'
        operating_system.copy(service.pgsql_hba_config, tmp_hba,
                              force=True, as_root=True)
        operating_system.chmod(tmp_hba, FileMode.SET_ALL_RWX(),
                               as_root=True)
        with open(tmp_hba, 'a+') as hba_file:
            hba_file.write(hba_entry)

        operating_system.copy(tmp_hba, service.pgsql_hba_config,
                              force=True, as_root=True)
        operating_system.chmod(service.pgsql_hba_config,
                               FileMode.SET_USR_RWX(),
                               as_root=True)
        operating_system.remove(tmp_hba, as_root=True)
        service.reload_configuration()

    def enable_as_slave(self, service, snapshot, slave_config):
        """Adds appropriate config options to postgresql.conf, and writes out
        the recovery.conf file used to set up replication
        """
        LOG.debug("Got slave_config: %s" % str(slave_config))
        self._write_standby_recovery_file(service, snapshot, sslmode='prefer')
        self.enable_hot_standby(service)
        # Ensure the WAL arch is empty before restoring
        service.recreate_wal_archive_dir()

    def detach_slave(self, service, for_failover):
        """Touch trigger file in to disable recovery mode"""
        LOG.info(_("Detaching slave, use trigger to disable recovery mode"))
        operating_system.write_file(TRIGGER_FILE, '')
        operating_system.chown(TRIGGER_FILE, user=service.pgsql_owner,
                               group=service.pgsql_owner, as_root=True)

        def _wait_for_failover():
            """Wait until slave has switched out of recovery mode"""
            return not service.pg_is_in_recovery()

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
        rec = service.pgsql_recovery_config
        tmprec = "/tmp/recovery.conf.bak"
        operating_system.move(rec, tmprec, as_root=True)

        cmd_full = " ".join(["pg_rewind", "-D", service.pgsql_data_dir,
                             '--source-pgdata=' + service.pgsql_data_dir,
                             '--source-server=' + conninfo])
        out, err = utils.execute("sudo", "su", "-", service.pgsql_owner,
                                 "-c", "%s" % cmd_full, check_exit_code=0)
        LOG.debug("Got stdout %s and stderr %s from pg_rewind" %
                  (str(out), str(err)))

        operating_system.move(tmprec, rec, as_root=True)

    def demote_master(self, service):
        """In order to demote a master we need to shutdown the server and call
           pg_rewind against the new master to enable a proper timeline
           switch.
           """
        service.stop_db()
        self._rewind_against_master(service)
        service.start_db()

    def connect_to_master(self, service, snapshot):
        """All that is required in postgresql to connect to a slave is to
        restart with a recovery.conf file in the data dir, which contains
        the connection information for the master.
        """
        assert operating_system.exists(service.pgsql_recovery_config,
                                       as_root=True)
        service.restart()

    def _remove_recovery_file(self, service):
        operating_system.remove(service.pgsql_recovery_config, as_root=True)

    def _write_standby_recovery_file(self, service, snapshot,
                                     sslmode='prefer'):
        LOG.info("Snapshot data received:" + str(snapshot))

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

        operating_system.write_file(service.pgsql_recovery_config,
                                    recovery_conf,
                                    codec=stream_codecs.IdentityCodec(),
                                    as_root=True)
        operating_system.chown(service.pgsql_recovery_config,
                               user=service.pgsql_owner,
                               group=service.pgsql_owner, as_root=True)

    def enable_hot_standby(self, service):
        opts = {'hot_standby': 'on',
                'wal_level': 'hot_standby'}
        # wal_log_hints for pg_rewind is only supported in 9.4+
        if service.pg_version[1] in ('9.4', '9.5'):
            opts['wal_log_hints'] = 'on'

        service.configuration_manager.\
            apply_system_override(opts, SLAVE_STANDBY_OVERRIDE)

    def get_replica_context(self, service):
        LOG.debug("Calling get_replica_context")
        repl_user_info = self._get_or_create_replication_user(service)

        log_position = {
            'replication_user': repl_user_info
        }

        return {
            'master': self.get_master_ref(None, None),
            'log_position': log_position
        }
