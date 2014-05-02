# Copyright 2013 OpenStack Foundation
# Copyright 2013 Rackspace Hosting
# Copyright 2013 Hewlett-Packard Development Company, L.P.
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

import os
from trove.common import cfg
from trove.common import exception
from trove.common import instance as rd_instance
from trove.guestagent import dbaas
from trove.guestagent import backup
from trove.guestagent import volume
from trove.guestagent.datastore.mysql.service import MySqlAppStatus
from trove.guestagent.datastore.mysql.service import MySqlAdmin
from trove.guestagent.datastore.mysql.service import MySqlApp
from trove.openstack.common import log as logging
from trove.openstack.common.gettextutils import _
from trove.openstack.common import periodic_task


LOG = logging.getLogger(__name__)
CONF = cfg.CONF
MANAGER = CONF.datastore_manager


class Manager(periodic_task.PeriodicTasks):

    @periodic_task.periodic_task(ticks_between_runs=3)
    def update_status(self, context):
        """Update the status of the MySQL service."""
        MySqlAppStatus.get().update()

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
        LOG.info(_("Restoring database from backup %s") % backup_info['id'])
        try:
            backup.restore(context, backup_info, restore_location)
        except Exception as e:
            LOG.error(e)
            LOG.error("Error performing restore from backup %s",
                      backup_info['id'])
            app.status.set_status(rd_instance.ServiceStatuses.FAILED)
            raise
        LOG.info(_("Restored database successfully"))

    def prepare(self, context, packages, databases, memory_mb, users,
                device_path=None, mount_point=None, backup_info=None,
                config_contents=None, root_password=None, overrides=None):
        """Makes ready DBAAS on a Guest container."""
        MySqlAppStatus.get().begin_install()
        # status end_mysql_install set with secure()
        app = MySqlApp(MySqlAppStatus.get())
        app.install_if_needed(packages)
        if device_path:
            #stop and do not update database
            app.stop_db()
            device = volume.VolumeDevice(device_path)
            # unmount if device is already mounted
            device.unmount_device(device_path)
            device.format()
            if os.path.exists(mount_point):
                #rsync exiting data
                device.migrate_data(mount_point)
            #mount the volume
            device.mount(mount_point)
            LOG.debug("Mounted the volume.")
            app.start_mysql()
        if backup_info:
            self._perform_restore(backup_info, context,
                                  mount_point, app)
        LOG.info(_("Securing mysql now."))
        app.secure(config_contents, overrides)
        enable_root_on_restore = (backup_info and
                                  MySqlAdmin().is_root_enabled())
        if root_password and not backup_info:
            app.secure_root(secure_remote_root=True)
            MySqlAdmin().enable_root(root_password)
        elif enable_root_on_restore:
            app.secure_root(secure_remote_root=False)
        else:
            app.secure_root(secure_remote_root=True)

        app.complete_install_or_restart()

        if databases:
            self.create_database(context, databases)

        if users:
            self.create_user(context, users)

        LOG.info('"prepare" call has finished.')

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
        mount_point = CONF.get(
            'mysql' if not MANAGER else MANAGER).mount_point
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
        LOG.debug("Mounted the volume.")

    def unmount_volume(self, context, device_path=None, mount_point=None):
        device = volume.VolumeDevice(device_path)
        device.unmount(mount_point)
        LOG.debug("Unmounted the volume.")

    def resize_fs(self, context, device_path=None, mount_point=None):
        device = volume.VolumeDevice(device_path)
        device.resize_fs(mount_point)
        LOG.debug("Resized the filesystem")

    def update_overrides(self, context, overrides, remove=False):
        app = MySqlApp(MySqlAppStatus.get())
        app.update_overrides(overrides, remove=remove)

    def apply_overrides(self, context, overrides):
        app = MySqlApp(MySqlAppStatus.get())
        app.apply_overrides(overrides)

    def get_replication_snapshot(self, master_config):
        raise exception.DatastoreOperationNotSupported(
            operation='get_replication_snapshot', datastore=MANAGER)

    def attach_replication_slave(self, snapshot, slave_config):
        raise exception.DatastoreOperationNotSupported(
            operation='attach_replication_slave', datastore=MANAGER)

    def detach_replication_slave(self):
        raise exception.DatastoreOperationNotSupported(
            operation='detach_replication_slave', datastore=MANAGER)

    def demote_replication_master(self):
        raise exception.DatastoreOperationNotSupported(
            operation='demote_replication_master', datastore=MANAGER)
