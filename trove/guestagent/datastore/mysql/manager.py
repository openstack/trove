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
from oslo_service import periodic_task

from trove.common import cfg
from trove.common import exception
from trove.common.i18n import _
from trove.common import instance as rd_instance
from trove.guestagent import backup
from trove.guestagent.common import operating_system
from trove.guestagent.datastore.mysql import service
from trove.guestagent.datastore.mysql.service import MySqlAdmin
from trove.guestagent.datastore.mysql.service import MySqlApp
from trove.guestagent.datastore.mysql.service import MySqlAppStatus
from trove.guestagent import dbaas
from trove.guestagent.strategies.replication import get_replication_strategy
from trove.guestagent import volume


LOG = logging.getLogger(__name__)
CONF = cfg.CONF
MANAGER = CONF.datastore_manager if CONF.datastore_manager else 'mysql'
REPLICATION_STRATEGY = CONF.get(MANAGER).replication_strategy
REPLICATION_NAMESPACE = CONF.get(MANAGER).replication_namespace
REPLICATION_STRATEGY_CLASS = get_replication_strategy(REPLICATION_STRATEGY,
                                                      REPLICATION_NAMESPACE)


class Manager(periodic_task.PeriodicTasks):

    def __init__(self):
        super(Manager, self).__init__(CONF)

    @periodic_task.periodic_task
    def update_status(self, context):
        """Update the status of the MySQL service."""
        MySqlAppStatus.get().update()

    def rpc_ping(self, context):
        LOG.debug("Responding to RPC ping.")
        return True

    def change_passwords(self, context, users):
        return MySqlAdmin().change_passwords(users)

    def update_attributes(self, context, username, hostname, user_attrs):
        return MySqlAdmin().update_attributes(username, hostname, user_attrs)

    def reset_configuration(self, context, configuration):
        app = MySqlApp(MySqlAppStatus.get())
        app.reset_configuration(configuration)

    def create_database(self, context, databases):
        return MySqlAdmin().create_database(databases)

    def create_user(self, context, users):
        MySqlAdmin().create_user(users)

    def delete_database(self, context, database):
        return MySqlAdmin().delete_database(database)

    def delete_user(self, context, user):
        MySqlAdmin().delete_user(user)

    def get_user(self, context, username, hostname):
        return MySqlAdmin().get_user(username, hostname)

    def grant_access(self, context, username, hostname, databases):
        return MySqlAdmin().grant_access(username, hostname, databases)

    def revoke_access(self, context, username, hostname, database):
        return MySqlAdmin().revoke_access(username, hostname, database)

    def list_access(self, context, username, hostname):
        return MySqlAdmin().list_access(username, hostname)

    def list_databases(self, context, limit=None, marker=None,
                       include_marker=False):
        return MySqlAdmin().list_databases(limit, marker,
                                           include_marker)

    def list_users(self, context, limit=None, marker=None,
                   include_marker=False):
        return MySqlAdmin().list_users(limit, marker,
                                       include_marker)

    def enable_root(self, context):
        return MySqlAdmin().enable_root()

    def is_root_enabled(self, context):
        return MySqlAdmin().is_root_enabled()

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

    def prepare(self, context, packages, databases, memory_mb, users,
                device_path=None, mount_point=None, backup_info=None,
                config_contents=None, root_password=None, overrides=None,
                cluster_config=None, snapshot=None):
        """Makes ready DBAAS on a Guest container."""
        MySqlAppStatus.get().begin_install()
        # status end_mysql_install set with secure()
        app = MySqlApp(MySqlAppStatus.get())
        app.install_if_needed(packages)
        if device_path:
            # stop and do not update database
            app.stop_db()
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
            operating_system.chown(
                mount_point, service.MYSQL_OWNER, service.MYSQL_OWNER,
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
        app.secure(config_contents, overrides)
        enable_root_on_restore = (backup_info and
                                  MySqlAdmin().is_root_enabled())
        if root_password and not backup_info:
            app.secure_root(secure_remote_root=True)
            MySqlAdmin().enable_root(root_password)
        elif enable_root_on_restore:
            app.secure_root(secure_remote_root=False)
            MySqlAppStatus.get().report_root(context, 'root')
        else:
            app.secure_root(secure_remote_root=True)

        app.complete_install_or_restart()

        if databases:
            self.create_database(context, databases)

        if users:
            self.create_user(context, users)

        if snapshot:
            self.attach_replica(context, snapshot, snapshot['config'])

        LOG.info(_('Completed setup of MySQL database instance.'))

    def restart(self, context):
        app = MySqlApp(MySqlAppStatus.get())
        app.restart()

    def start_db_with_conf_changes(self, context, config_contents):
        app = MySqlApp(MySqlAppStatus.get())
        app.start_db_with_conf_changes(config_contents)

    def stop_db(self, context, do_not_start_on_reboot=False):
        app = MySqlApp(MySqlAppStatus.get())
        app.stop_db(do_not_start_on_reboot=do_not_start_on_reboot)

    def get_filesystem_stats(self, context, fs_path):
        """Gets the filesystem stats for the path given."""
        mount_point = CONF.get(MANAGER).mount_point
        return dbaas.get_filesystem_volume_stats(mount_point)

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

    def mount_volume(self, context, device_path=None, mount_point=None):
        device = volume.VolumeDevice(device_path)
        device.mount(mount_point, write_to_fstab=False)
        LOG.debug("Mounted the device %s at the mount point %s." %
                  (device_path, mount_point))

    def unmount_volume(self, context, device_path=None, mount_point=None):
        device = volume.VolumeDevice(device_path)
        device.unmount(mount_point)
        LOG.debug("Unmounted the device %s from the mount point %s." %
                  (device_path, mount_point))

    def resize_fs(self, context, device_path=None, mount_point=None):
        device = volume.VolumeDevice(device_path)
        device.resize_fs(mount_point)
        LOG.debug("Resized the filesystem %s." % mount_point)

    def update_overrides(self, context, overrides, remove=False):
        app = MySqlApp(MySqlAppStatus.get())
        if remove:
            app.remove_overrides()
        app.update_overrides(overrides)

    def apply_overrides(self, context, overrides):
        LOG.debug("Applying overrides (%s)." % overrides)
        app = MySqlApp(MySqlAppStatus.get())
        app.apply_overrides(overrides)

    def get_replication_snapshot(self, context, snapshot_info,
                                 replica_source_config=None):
        LOG.debug("Getting replication snapshot.")
        app = MySqlApp(MySqlAppStatus.get())

        replication = REPLICATION_STRATEGY_CLASS(context)
        replication.enable_as_master(app, replica_source_config)

        snapshot_id, log_position = (
            replication.snapshot_for_replication(context, app, None,
                                                 snapshot_info))

        mount_point = CONF.get(MANAGER).mount_point
        volume_stats = dbaas.get_filesystem_volume_stats(mount_point)

        replication_snapshot = {
            'dataset': {
                'datastore_manager': MANAGER,
                'dataset_size': volume_stats.get('used', 0.0),
                'volume_size': volume_stats.get('total', 0.0),
                'snapshot_id': snapshot_id
            },
            'replication_strategy': REPLICATION_STRATEGY,
            'master': replication.get_master_ref(app, snapshot_info),
            'log_position': log_position
        }

        return replication_snapshot

    def enable_as_master(self, context, replica_source_config):
        LOG.debug("Calling enable_as_master.")
        app = MySqlApp(MySqlAppStatus.get())
        replication = REPLICATION_STRATEGY_CLASS(context)
        replication.enable_as_master(app, replica_source_config)

    # DEPRECATED: Maintain for API Compatibility
    def get_txn_count(self, context):
        LOG.debug("Calling get_txn_count")
        return MySqlApp(MySqlAppStatus.get()).get_txn_count()

    def get_last_txn(self, context):
        LOG.debug("Calling get_last_txn")
        return MySqlApp(MySqlAppStatus.get()).get_last_txn()

    def get_latest_txn_id(self, context):
        LOG.debug("Calling get_latest_txn_id.")
        return MySqlApp(MySqlAppStatus.get()).get_latest_txn_id()

    def wait_for_txn(self, context, txn):
        LOG.debug("Calling wait_for_txn.")
        MySqlApp(MySqlAppStatus.get()).wait_for_txn(txn)

    def detach_replica(self, context, for_failover=False):
        LOG.debug("Detaching replica.")
        app = MySqlApp(MySqlAppStatus.get())
        replication = REPLICATION_STRATEGY_CLASS(context)
        replica_info = replication.detach_slave(app, for_failover)
        return replica_info

    def get_replica_context(self, context):
        LOG.debug("Getting replica context.")
        app = MySqlApp(MySqlAppStatus.get())
        replication = REPLICATION_STRATEGY_CLASS(context)
        replica_info = replication.get_replica_context(app)
        return replica_info

    def _validate_slave_for_replication(self, context, replica_info):
        if (replica_info['replication_strategy'] != REPLICATION_STRATEGY):
            raise exception.IncompatibleReplicationStrategy(
                replica_info.update({
                    'guest_strategy': REPLICATION_STRATEGY
                }))

        mount_point = CONF.get(MANAGER).mount_point
        volume_stats = dbaas.get_filesystem_volume_stats(mount_point)
        if (volume_stats.get('total', 0.0) <
                replica_info['dataset']['dataset_size']):
            raise exception.InsufficientSpaceForReplica(
                replica_info.update({
                    'slave_volume_size': volume_stats.get('total', 0.0)
                }))

    def attach_replica(self, context, replica_info, slave_config):
        LOG.debug("Attaching replica.")
        app = MySqlApp(MySqlAppStatus.get())
        try:
            if 'replication_strategy' in replica_info:
                self._validate_slave_for_replication(context, replica_info)
            replication = REPLICATION_STRATEGY_CLASS(context)
            replication.enable_as_slave(app, replica_info, slave_config)
        except Exception:
            LOG.exception("Error enabling replication.")
            app.status.set_status(rd_instance.ServiceStatuses.FAILED)
            raise

    def make_read_only(self, context, read_only):
        LOG.debug("Executing make_read_only(%s)" % read_only)
        app = MySqlApp(MySqlAppStatus.get())
        app.make_read_only(read_only)

    def cleanup_source_on_replica_detach(self, context, replica_info):
        LOG.debug("Cleaning up the source on the detach of a replica.")
        replication = REPLICATION_STRATEGY_CLASS(context)
        replication.cleanup_source_on_replica_detach(MySqlAdmin(),
                                                     replica_info)

    def demote_replication_master(self, context):
        LOG.debug("Demoting replication master.")
        app = MySqlApp(MySqlAppStatus.get())
        replication = REPLICATION_STRATEGY_CLASS(context)
        replication.demote_master(app)
