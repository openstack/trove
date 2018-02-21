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

from trove.common import cfg
from trove.common.db.postgresql import models
from trove.common import exception
from trove.common.i18n import _
from trove.common import instance as trove_instance
from trove.common.notification import EndNotification
from trove.common import utils
from trove.guestagent import backup
from trove.guestagent.datastore.experimental.postgresql.service import (
    PgSqlAdmin)
from trove.guestagent.datastore.experimental.postgresql.service import PgSqlApp
from trove.guestagent.datastore import manager
from trove.guestagent import guest_log
from trove.guestagent import volume


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class Manager(manager.Manager):

    def __init__(self, manager_name='postgresql'):
        super(Manager, self).__init__(manager_name)
        self._app = None
        self._admin = None

    @property
    def status(self):
        return self.app.status

    @property
    def app(self):
        if self._app is None:
            self._app = self.build_app()
        return self._app

    def build_app(self):
        return PgSqlApp()

    @property
    def admin(self):
        if self._admin is None:
            self._admin = self.app.build_admin()
        return self._admin

    @property
    def configuration_manager(self):
        return self.app.configuration_manager

    @property
    def datastore_log_defs(self):
        owner = self.app.pgsql_owner
        long_query_time = CONF.get(self.manager).get(
            'guest_log_long_query_time')
        general_log_file = self.build_log_file_name(
            self.GUEST_LOG_DEFS_GENERAL_LABEL, owner,
            datastore_dir=self.app.pgsql_log_dir)
        general_log_dir, general_log_filename = os.path.split(general_log_file)
        return {
            self.GUEST_LOG_DEFS_GENERAL_LABEL: {
                self.GUEST_LOG_TYPE_LABEL: guest_log.LogType.USER,
                self.GUEST_LOG_USER_LABEL: owner,
                self.GUEST_LOG_FILE_LABEL: general_log_file,
                self.GUEST_LOG_ENABLE_LABEL: {
                    'logging_collector': 'on',
                    'log_destination': self._quote_str('stderr'),
                    'log_directory': self._quote_str(general_log_dir),
                    'log_filename': self._quote_str(general_log_filename),
                    'log_statement': self._quote_str('all'),
                    'debug_print_plan': 'on',
                    'log_min_duration_statement': long_query_time,
                },
                self.GUEST_LOG_DISABLE_LABEL: {
                    'logging_collector': 'off',
                },
                self.GUEST_LOG_RESTART_LABEL: True,
            },
        }

    def _quote_str(self, value):
        return "'%s'" % value

    def grant_access(self, context, username, hostname, databases):
        self.admin.grant_access(context, username, hostname, databases)

    def revoke_access(self, context, username, hostname, database):
        self.admin.revoke_access(context, username, hostname, database)

    def list_access(self, context, username, hostname):
        return self.admin.list_access(context, username, hostname)

    def update_overrides(self, context, overrides, remove=False):
        self.app.update_overrides(context, overrides, remove)

    def apply_overrides(self, context, overrides):
        self.app.apply_overrides(context, overrides)

    def reset_configuration(self, context, configuration):
        self.app.reset_configuration(context, configuration)

    def start_db_with_conf_changes(self, context, config_contents):
        self.app.start_db_with_conf_changes(context, config_contents)

    def create_database(self, context, databases):
        with EndNotification(context):
            self.admin.create_database(context, databases)

    def delete_database(self, context, database):
        with EndNotification(context):
            self.admin.delete_database(context, database)

    def list_databases(
            self, context, limit=None, marker=None, include_marker=False):
        return self.admin.list_databases(
            context, limit=limit, marker=marker, include_marker=include_marker)

    def install(self, context, packages):
        self.app.install(context, packages)

    def stop_db(self, context, do_not_start_on_reboot=False):
        self.app.stop_db(do_not_start_on_reboot=do_not_start_on_reboot)

    def restart(self, context):
        self.app.restart()
        self.set_guest_log_status(guest_log.LogStatus.Restart_Completed)

    def pre_upgrade(self, context):
        LOG.debug('Preparing Postgresql for upgrade.')
        self.app.status.begin_restart()
        self.app.stop_db()
        mount_point = self.app.pgsql_base_data_dir
        upgrade_info = self.app.save_files_pre_upgrade(mount_point)
        upgrade_info['mount_point'] = mount_point
        return upgrade_info

    def post_upgrade(self, context, upgrade_info):
        LOG.debug('Finalizing Postgresql upgrade.')
        self.app.stop_db()
        if 'device' in upgrade_info:
            self.mount_volume(context, mount_point=upgrade_info['mount_point'],
                              device_path=upgrade_info['device'],
                              write_to_fstab=True)
        self.app.restore_files_post_upgrade(upgrade_info)
        self.app.start_db()

    def is_root_enabled(self, context):
        return self.app.is_root_enabled(context)

    def enable_root(self, context, root_password=None):
        return self.app.enable_root(context, root_password=root_password)

    def disable_root(self, context):
        self.app.disable_root(context)

    def enable_root_with_password(self, context, root_password=None):
        return self.app.enable_root_with_password(
            context,
            root_password=root_password)

    def create_user(self, context, users):
        with EndNotification(context):
            self.admin.create_user(context, users)

    def list_users(
            self, context, limit=None, marker=None, include_marker=False):
        return self.admin.list_users(
            context, limit=limit, marker=marker, include_marker=include_marker)

    def delete_user(self, context, user):
        with EndNotification(context):
            self.admin.delete_user(context, user)

    def get_user(self, context, username, hostname):
        return self.admin.get_user(context, username, hostname)

    def change_passwords(self, context, users):
        with EndNotification(context):
            self.admin.change_passwords(context, users)

    def update_attributes(self, context, username, hostname, user_attrs):
        with EndNotification(context):
            self.admin.update_attributes(
                context,
                username,
                hostname,
                user_attrs)

    def do_prepare(self, context, packages, databases, memory_mb, users,
                   device_path, mount_point, backup_info, config_contents,
                   root_password, overrides, cluster_config, snapshot):
        self.app.install(context, packages)
        LOG.debug("Waiting for database first boot.")
        if (self.app.status.wait_for_real_status_to_change_to(
                trove_instance.ServiceStatuses.RUNNING,
                CONF.state_change_wait_time,
                False)):
            LOG.debug("Stopping database prior to initial configuration.")
            self.app.stop_db()

        if device_path:
            device = volume.VolumeDevice(device_path)
            device.format()
            if os.path.exists(mount_point):
                device.migrate_data(mount_point)
            device.mount(mount_point)
        self.configuration_manager.save_configuration(config_contents)
        self.app.apply_initial_guestagent_configuration()

        os_admin = models.PostgreSQLUser(self.app.ADMIN_USER)

        if backup_info:
            backup.restore(context, backup_info, '/tmp')
            self.app.set_current_admin_user(os_admin)

        if snapshot:
            LOG.info("Found snapshot info: %s", str(snapshot))
            self.attach_replica(context, snapshot, snapshot['config'])

        self.app.start_db()

        if not backup_info:
            self.app.secure(context)

        self._admin = PgSqlAdmin(os_admin)

        if not cluster_config and self.is_root_enabled(context):
            self.status.report_root(context)

    def create_backup(self, context, backup_info):
        with EndNotification(context):
            self.app.enable_backups()
            backup.backup(context, backup_info)

    def backup_required_for_replication(self, context):
        return self.replication.backup_required_for_replication()

    def attach_replica(self, context, replica_info, slave_config):
        self.replication.enable_as_slave(self.app, replica_info, None)

    def detach_replica(self, context, for_failover=False):
        replica_info = self.replication.detach_slave(self.app, for_failover)
        return replica_info

    def enable_as_master(self, context, replica_source_config):
        self.app.enable_backups()
        self.replication.enable_as_master(self.app, None)

    def make_read_only(self, context, read_only):
        """There seems to be no way to flag this at the database level in
        PostgreSQL at the moment -- see discussion here:
        http://www.postgresql.org/message-id/flat/CA+TgmobWQJ-GCa_tWUc4=80A
        1RJ2_+Rq3w_MqaVguk_q018dqw@mail.gmail.com#CA+TgmobWQJ-GCa_tWUc4=80A1RJ
        2_+Rq3w_MqaVguk_q018dqw@mail.gmail.com
        """
        pass

    def get_replica_context(self, context):
        LOG.debug("Getting replica context.")
        return self.replication.get_replica_context(self.app)

    def get_latest_txn_id(self, context):
        if self.app.pg_is_in_recovery():
            lsn = self.app.pg_last_xlog_replay_location()
        else:
            lsn = self.app.pg_current_xlog_location()
        LOG.info("Last xlog location found: %s", lsn)
        return lsn

    def get_last_txn(self, context):
        master_host = self.app.pg_primary_host()
        repl_offset = self.get_latest_txn_id(context)
        return master_host, repl_offset

    def wait_for_txn(self, context, txn):
        if not self.app.pg_is_in_recovery():
            raise RuntimeError(_("Attempting to wait for a txn on a server "
                                 "not in recovery mode!"))

        def _wait_for_txn():
            lsn = self.app.pg_last_xlog_replay_location()
            LOG.info("Last xlog location found: %s", lsn)
            return lsn >= txn
        try:
            utils.poll_until(_wait_for_txn, time_out=120)
        except exception.PollTimeOut:
            raise RuntimeError(_("Timeout occurred waiting for xlog "
                                 "offset to change to '%s'.") % txn)

    def cleanup_source_on_replica_detach(self, context, replica_info):
        LOG.debug("Calling cleanup_source_on_replica_detach")
        self.replication.cleanup_source_on_replica_detach(self.app,
                                                          replica_info)

    def demote_replication_master(self, context):
        LOG.debug("Calling demote_replication_master")
        self.replication.demote_master(self.app)

    def get_replication_snapshot(self, context, snapshot_info,
                                 replica_source_config=None):
        LOG.debug("Getting replication snapshot.")

        self.app.enable_backups()
        self.replication.enable_as_master(self.app, None)

        snapshot_id, log_position = (
            self.replication.snapshot_for_replication(context, self.app, None,
                                                      snapshot_info))

        mount_point = CONF.get(self.manager).mount_point
        volume_stats = self.get_filesystem_stats(context, mount_point)

        replication_snapshot = {
            'dataset': {
                'datastore_manager': self.manager,
                'dataset_size': volume_stats.get('used', 0.0),
                'volume_size': volume_stats.get('total', 0.0),
                'snapshot_id': snapshot_id
            },
            'replication_strategy': self.replication_strategy,
            'master': self.replication.get_master_ref(self.app, snapshot_info),
            'log_position': log_position
        }

        return replication_snapshot
