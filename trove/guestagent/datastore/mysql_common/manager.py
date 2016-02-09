# Copyright 2013 OpenStack Foundation
# Copyright 2013 Rackspace Hosting
# Copyright 2013 Hewlett-Packard Development Company, L.P.
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

from trove.common import cfg
from trove.common import configurations
from trove.common import exception
from trove.common.i18n import _
from trove.common import instance as rd_instance
from trove.guestagent import backup
from trove.guestagent.common import operating_system
from trove.guestagent.datastore import manager
from trove.guestagent.datastore.mysql_common import service
from trove.guestagent import guest_log
from trove.guestagent import volume


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class MySqlManager(manager.Manager):

    def __init__(self, mysql_app, mysql_app_status, mysql_admin,
                 manager_name='mysql'):

        super(MySqlManager, self).__init__(manager_name)
        self._mysql_app = mysql_app
        self._mysql_app_status = mysql_app_status
        self._mysql_admin = mysql_admin

        self.volume_do_not_start_on_reboot = False

    @property
    def mysql_app(self):
        return self._mysql_app

    @property
    def mysql_app_status(self):
        return self._mysql_app_status

    @property
    def mysql_admin(self):
        return self._mysql_admin

    @property
    def status(self):
        return self.mysql_app_status.get()

    @property
    def configuration_manager(self):
        return self.mysql_app(
            self.mysql_app_status.get()).configuration_manager

    @property
    def datastore_log_defs(self):
        owner = 'mysql'
        datastore_dir = self.mysql_app.get_data_dir()
        server_section = configurations.MySQLConfParser.SERVER_CONF_SECTION
        long_query_time = CONF.get(self.manager).get(
            'guest_log_long_query_time') / 1000
        general_log_file = self.build_log_file_name(
            self.GUEST_LOG_DEFS_GENERAL_LABEL, owner,
            datastore_dir=datastore_dir)
        error_log_file = self.validate_log_file('/var/log/mysqld.log', owner)
        slow_query_log_file = self.build_log_file_name(
            self.GUEST_LOG_DEFS_SLOW_QUERY_LABEL, owner,
            datastore_dir=datastore_dir)
        return {
            self.GUEST_LOG_DEFS_GENERAL_LABEL: {
                self.GUEST_LOG_TYPE_LABEL: guest_log.LogType.USER,
                self.GUEST_LOG_USER_LABEL: owner,
                self.GUEST_LOG_FILE_LABEL: general_log_file,
                self.GUEST_LOG_SECTION_LABEL: server_section,
                self.GUEST_LOG_ENABLE_LABEL: {
                    'general_log': 'on',
                    'general_log_file': general_log_file,
                    'log_output': 'file',
                },
                self.GUEST_LOG_DISABLE_LABEL: {
                    'general_log': 'off',
                },
            },
            self.GUEST_LOG_DEFS_SLOW_QUERY_LABEL: {
                self.GUEST_LOG_TYPE_LABEL: guest_log.LogType.USER,
                self.GUEST_LOG_USER_LABEL: owner,
                self.GUEST_LOG_FILE_LABEL: slow_query_log_file,
                self.GUEST_LOG_SECTION_LABEL: server_section,
                self.GUEST_LOG_ENABLE_LABEL: {
                    'slow_query_log': 'on',
                    'slow_query_log_file': slow_query_log_file,
                    'long_query_time': long_query_time,
                },
                self.GUEST_LOG_DISABLE_LABEL: {
                    'slow_query_log': 'off',
                },
            },
            self.GUEST_LOG_DEFS_ERROR_LABEL: {
                self.GUEST_LOG_TYPE_LABEL: guest_log.LogType.SYS,
                self.GUEST_LOG_USER_LABEL: owner,
                self.GUEST_LOG_FILE_LABEL: error_log_file,
            },
        }

    def change_passwords(self, context, users):
        return self.mysql_admin().change_passwords(users)

    def update_attributes(self, context, username, hostname, user_attrs):
        return self.mysql_admin().update_attributes(
            username, hostname, user_attrs)

    def reset_configuration(self, context, configuration):
        app = self.mysql_app(self.mysql_app_status.get())
        app.reset_configuration(configuration)

    def create_database(self, context, databases):
        return self.mysql_admin().create_database(databases)

    def create_user(self, context, users):
        self.mysql_admin().create_user(users)

    def delete_database(self, context, database):
        return self.mysql_admin().delete_database(database)

    def delete_user(self, context, user):
        self.mysql_admin().delete_user(user)

    def get_user(self, context, username, hostname):
        return self.mysql_admin().get_user(username, hostname)

    def grant_access(self, context, username, hostname, databases):
        return self.mysql_admin().grant_access(username, hostname, databases)

    def revoke_access(self, context, username, hostname, database):
        return self.mysql_admin().revoke_access(username, hostname, database)

    def list_access(self, context, username, hostname):
        return self.mysql_admin().list_access(username, hostname)

    def list_databases(self, context, limit=None, marker=None,
                       include_marker=False):
        return self.mysql_admin().list_databases(limit, marker,
                                                 include_marker)

    def list_users(self, context, limit=None, marker=None,
                   include_marker=False):
        return self.mysql_admin().list_users(limit, marker,
                                             include_marker)

    def enable_root(self, context):
        return self.mysql_admin().enable_root()

    def enable_root_with_password(self, context, root_password=None):
        raise exception.DatastoreOperationNotSupported(
            operation='enable_root_with_password', datastore=self.manager)

    def is_root_enabled(self, context):
        return self.mysql_admin().is_root_enabled()

    def disable_root(self, context):
        return self.mysql_admin().disable_root()

    def _perform_restore(self, backup_info, context, restore_location, app):
        LOG.info(_("Restoring database from backup %s.") % backup_info['id'])
        try:
            backup.restore(context, backup_info, restore_location)
        except Exception:
            LOG.exception(_("Error performing restore from backup %s.") %
                          backup_info['id'])
            app.status.set_status(rd_instance.ServiceStatuses.FAILED)
            raise
        LOG.info(_("Restored database successfully."))

    def do_prepare(self, context, packages, databases, memory_mb, users,
                   device_path, mount_point, backup_info,
                   config_contents, root_password, overrides,
                   cluster_config, snapshot):
        """This is called from prepare in the base class."""
        app = self.mysql_app(self.mysql_app_status.get())
        app.install_if_needed(packages)
        if device_path:
            # stop and do not update database
            app.stop_db(
                do_not_start_on_reboot=self.volume_do_not_start_on_reboot)
            device = volume.VolumeDevice(device_path)
            # unmount if device is already mounted
            device.unmount_device(device_path)
            device.format()
            if os.path.exists(mount_point):
                # rsync existing data to a "data" sub-directory
                # on the new volume
                device.migrate_data(mount_point, target_subdir="data")
            # mount the volume
            device.mount(mount_point)
            operating_system.chown(mount_point, service.MYSQL_OWNER,
                                   service.MYSQL_OWNER,
                                   recursive=False, as_root=True)

            LOG.debug("Mounted the volume at %s." % mount_point)
            # We need to temporarily update the default my.cnf so that
            # mysql will start after the volume is mounted. Later on it
            # will be changed based on the config template
            # (see MySqlApp.secure()) and restart.
            app.set_data_dir(mount_point + '/data')
            app.start_mysql()
        if backup_info:
            self._perform_restore(backup_info, context,
                                  mount_point + "/data", app)
        LOG.debug("Securing MySQL now.")
        app.secure(config_contents)
        enable_root_on_restore = (backup_info and
                                  self.mysql_admin().is_root_enabled())
        if root_password and not backup_info:
            app.secure_root(secure_remote_root=True)
            self.mysql_admin().enable_root(root_password)
        elif enable_root_on_restore:
            app.secure_root(secure_remote_root=False)
            self.mysql_app_status.get().report_root(context, 'root')
        else:
            app.secure_root(secure_remote_root=True)

        if snapshot:
            self.attach_replica(context, snapshot, snapshot['config'])

    def restart(self, context):
        app = self.mysql_app(self.mysql_app_status.get())
        app.restart()

    def start_db_with_conf_changes(self, context, config_contents):
        app = self.mysql_app(self.mysql_app_status.get())
        app.start_db_with_conf_changes(config_contents)

    def stop_db(self, context, do_not_start_on_reboot=False):
        app = self.mysql_app(self.mysql_app_status.get())
        app.stop_db(do_not_start_on_reboot=do_not_start_on_reboot)

    def create_backup(self, context, backup_info):
        """
        Entry point for initiating a backup for this guest agents db instance.
        The call currently blocks until the backup is complete or errors. If
        device_path is specified, it will be mounted based to a point specified
        in configuration.

        :param backup_info: a dictionary containing the db instance id of the
                            backup task, location, type, and other data.
        """
        backup.backup(context, backup_info)

    def update_overrides(self, context, overrides, remove=False):
        app = self.mysql_app(self.mysql_app_status.get())
        if remove:
            app.remove_overrides()
        app.update_overrides(overrides)

    def apply_overrides(self, context, overrides):
        LOG.debug("Applying overrides (%s)." % overrides)
        app = self.mysql_app(self.mysql_app_status.get())
        app.apply_overrides(overrides)

    def backup_required_for_replication(self, context):
        return self.replication.backup_required_for_replication()

    def get_replication_snapshot(self, context, snapshot_info,
                                 replica_source_config=None):
        LOG.debug("Getting replication snapshot.")
        app = self.mysql_app(self.mysql_app_status.get())

        self.replication.enable_as_master(app, replica_source_config)

        snapshot_id, log_position = self.replication.snapshot_for_replication(
            context, app, None, snapshot_info)

        volume_stats = self.get_filesystem_stats(context, None)

        replication_snapshot = {
            'dataset': {
                'datastore_manager': self.manager,
                'dataset_size': volume_stats.get('used', 0.0),
                'volume_size': volume_stats.get('total', 0.0),
                'snapshot_id': snapshot_id
            },
            'replication_strategy': self.replication_strategy,
            'master': self.replication.get_master_ref(app, snapshot_info),
            'log_position': log_position
        }

        return replication_snapshot

    def enable_as_master(self, context, replica_source_config):
        LOG.debug("Calling enable_as_master.")
        app = self.mysql_app(self.mysql_app_status.get())
        self.replication.enable_as_master(app, replica_source_config)

    # DEPRECATED: Maintain for API Compatibility
    def get_txn_count(self, context):
        LOG.debug("Calling get_txn_count")
        return self.mysql_app(self.mysql_app_status.get()).get_txn_count()

    def get_last_txn(self, context):
        LOG.debug("Calling get_last_txn")
        return self.mysql_app(self.mysql_app_status.get()).get_last_txn()

    def get_latest_txn_id(self, context):
        LOG.debug("Calling get_latest_txn_id.")
        return self.mysql_app(self.mysql_app_status.get()).get_latest_txn_id()

    def wait_for_txn(self, context, txn):
        LOG.debug("Calling wait_for_txn.")
        self.mysql_app(self.mysql_app_status.get()).wait_for_txn(txn)

    def detach_replica(self, context, for_failover=False):
        LOG.debug("Detaching replica.")
        app = self.mysql_app(self.mysql_app_status.get())
        replica_info = self.replication.detach_slave(app, for_failover)
        return replica_info

    def get_replica_context(self, context):
        LOG.debug("Getting replica context.")
        app = self.mysql_app(self.mysql_app_status.get())
        replica_info = self.replication.get_replica_context(app)
        return replica_info

    def _validate_slave_for_replication(self, context, replica_info):
        if replica_info['replication_strategy'] != self.replication_strategy:
            raise exception.IncompatibleReplicationStrategy(
                replica_info.update({
                    'guest_strategy': self.replication_strategy
                }))

        volume_stats = self.get_filesystem_stats(context, None)
        if (volume_stats.get('total', 0.0) <
                replica_info['dataset']['dataset_size']):
            raise exception.InsufficientSpaceForReplica(
                replica_info.update({
                    'slave_volume_size': volume_stats.get('total', 0.0)
                }))

    def attach_replica(self, context, replica_info, slave_config):
        LOG.debug("Attaching replica.")
        app = self.mysql_app(self.mysql_app_status.get())
        try:
            if 'replication_strategy' in replica_info:
                self._validate_slave_for_replication(context, replica_info)
            self.replication.enable_as_slave(app, replica_info, slave_config)
        except Exception:
            LOG.exception("Error enabling replication.")
            app.status.set_status(rd_instance.ServiceStatuses.FAILED)
            raise

    def make_read_only(self, context, read_only):
        LOG.debug("Executing make_read_only(%s)" % read_only)
        app = self.mysql_app(self.mysql_app_status.get())
        app.make_read_only(read_only)

    def cleanup_source_on_replica_detach(self, context, replica_info):
        LOG.debug("Cleaning up the source on the detach of a replica.")
        self.replication.cleanup_source_on_replica_detach(self.mysql_admin(),
                                                          replica_info)

    def demote_replication_master(self, context):
        LOG.debug("Demoting replication master.")
        app = self.mysql_app(self.mysql_app_status.get())
        self.replication.demote_master(app)
