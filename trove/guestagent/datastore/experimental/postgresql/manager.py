# Copyright (c) 2013 OpenStack Foundation
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


import os

from oslo_log import log as logging

from .service.config import PgSqlConfig
from .service.database import PgSqlDatabase
from .service.install import PgSqlInstall
from .service.root import PgSqlRoot
from .service.status import PgSqlAppStatus

from trove.common import cfg
from trove.common import exception
from trove.common.i18n import _
from trove.common.notification import EndNotification
from trove.common import utils
from trove.guestagent import backup
from trove.guestagent.datastore.experimental.postgresql import pgutil
from trove.guestagent.datastore import manager
from trove.guestagent.db import models
from trove.guestagent import dbaas
from trove.guestagent import guest_log
from trove.guestagent import volume


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class Manager(
        PgSqlDatabase,
        PgSqlRoot,
        PgSqlConfig,
        PgSqlInstall,
        manager.Manager
):

    PG_BUILTIN_ADMIN = 'postgres'

    def __init__(self):
        super(Manager, self).__init__('postgresql')

    @property
    def status(self):
        return PgSqlAppStatus.get()

    @property
    def configuration_manager(self):
        return self._configuration_manager

    @property
    def datastore_log_defs(self):
        datastore_dir = '/var/log/postgresql/'
        long_query_time = CONF.get(self.manager).get(
            'guest_log_long_query_time')
        general_log_file = self.build_log_file_name(
            self.GUEST_LOG_DEFS_GENERAL_LABEL, self.PGSQL_OWNER,
            datastore_dir=datastore_dir)
        general_log_dir, general_log_filename = os.path.split(general_log_file)
        return {
            self.GUEST_LOG_DEFS_GENERAL_LABEL: {
                self.GUEST_LOG_TYPE_LABEL: guest_log.LogType.USER,
                self.GUEST_LOG_USER_LABEL: self.PGSQL_OWNER,
                self.GUEST_LOG_FILE_LABEL: general_log_file,
                self.GUEST_LOG_ENABLE_LABEL: {
                    'logging_collector': 'on',
                    'log_destination': self._quote('stderr'),
                    'log_directory': self._quote(general_log_dir),
                    'log_filename': self._quote(general_log_filename),
                    'log_statement': self._quote('all'),
                    'debug_print_plan': 'on',
                    'log_min_duration_statement': long_query_time,
                },
                self.GUEST_LOG_DISABLE_LABEL: {
                    'logging_collector': 'off',
                },
                self.GUEST_LOG_RESTART_LABEL: True,
            },
        }

    def do_prepare(self, context, packages, databases, memory_mb, users,
                   device_path, mount_point, backup_info, config_contents,
                   root_password, overrides, cluster_config, snapshot):
        pgutil.PG_ADMIN = self.PG_BUILTIN_ADMIN
        self.install(context, packages)
        self.stop_db(context)
        if device_path:
            device = volume.VolumeDevice(device_path)
            device.format()
            if os.path.exists(mount_point):
                device.migrate_data(mount_point)
            device.mount(mount_point)
        self.configuration_manager.save_configuration(config_contents)
        self.apply_initial_guestagent_configuration()

        if backup_info:
            pgutil.PG_ADMIN = self.ADMIN_USER
            backup.restore(context, backup_info, '/tmp')

        if snapshot:
            self.attach_replica(context, snapshot, snapshot['config'])

        self.start_db(context)

        if not backup_info:
            self._secure(context)

        if not cluster_config and self.is_root_enabled(context):
            self.status.report_root(context, 'postgres')

    def _secure(self, context):
        # Create a new administrative user for Trove and also
        # disable the built-in superuser.
        os_admin_db = models.PostgreSQLSchema(self.ADMIN_USER)
        self._create_database(context, os_admin_db)
        self._create_admin_user(context, databases=[os_admin_db])
        pgutil.PG_ADMIN = self.ADMIN_USER
        postgres = models.PostgreSQLRootUser()
        self.alter_user(context, postgres, 'NOSUPERUSER', 'NOLOGIN')

    def create_backup(self, context, backup_info):
        with EndNotification(context):
            self.enable_backups()
            backup.backup(context, backup_info)

    def backup_required_for_replication(self, context):
        return self.replication.backup_required_for_replication()

    def attach_replica(self, context, replica_info, slave_config):
        self.replication.enable_as_slave(self, replica_info, None)

    def detach_replica(self, context, for_failover=False):
        replica_info = self.replication.detach_slave(self, for_failover)
        return replica_info

    def enable_as_master(self, context, replica_source_config):
        self.enable_backups()
        self.replication.enable_as_master(self, None)

    def make_read_only(self, context, read_only):
        """There seems to be no way to flag this at the database level in
        PostgreSQL at the moment -- see discussion here:
        http://www.postgresql.org/message-id/flat/CA+TgmobWQJ-GCa_tWUc4=80A
        1RJ2_+Rq3w_MqaVguk_q018dqw@mail.gmail.com#CA+TgmobWQJ-GCa_tWUc4=80A1RJ
        2_+Rq3w_MqaVguk_q018dqw@mail.gmail.com
        """
        pass

    def get_replica_context(self, context):
        return self.replication.get_replica_context(None)

    def get_latest_txn_id(self, context):
        if self.pg_is_in_recovery():
            lsn = self.pg_last_xlog_replay_location()
        else:
            lsn = self.pg_current_xlog_location()
        LOG.info(_("Last xlog location found: %s") % lsn)
        return lsn

    def get_last_txn(self, context):
        master_host = self.pg_primary_host()
        repl_offset = self.get_latest_txn_id(context)
        return master_host, repl_offset

    def wait_for_txn(self, context, txn):
        if not self.pg_is_in_recovery():
            raise RuntimeError(_("Attempting to wait for a txn on a server "
                                 "not in recovery mode!"))

        def _wait_for_txn():
            lsn = self.pg_last_xlog_replay_location()
            LOG.info(_("Last xlog location found: %s") % lsn)
            return lsn >= txn
        try:
            utils.poll_until(_wait_for_txn, time_out=120)
        except exception.PollTimeOut:
            raise RuntimeError(_("Timeout occurred waiting for xlog "
                                 "offset to change to '%s'.") % txn)

    def cleanup_source_on_replica_detach(self, context, replica_info):
        self.replication.cleanup_source_on_replica_detach()

    def demote_replication_master(self, context):
        self.replication.demote_master(self)

    def get_replication_snapshot(self, context, snapshot_info,
                                 replica_source_config=None):

        self.enable_backups()
        self.replication.enable_as_master(None, None)

        snapshot_id, log_position = (
            self.replication.snapshot_for_replication(context, None, None,
                                                      snapshot_info))

        mount_point = CONF.get(self.manager).mount_point
        volume_stats = dbaas.get_filesystem_volume_stats(mount_point)

        replication_snapshot = {
            'dataset': {
                'datastore_manager': self.manager,
                'dataset_size': volume_stats.get('used', 0.0),
                'snapshot_id': snapshot_id
            },
            'replication_strategy': self.replication_strategy,
            'master': self.replication.get_master_ref(None, snapshot_info),
            'log_position': log_position
        }

        return replication_snapshot
