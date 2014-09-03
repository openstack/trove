# Copyright (c) 2013 eBay Software Foundation
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

from trove.common import cfg
from trove.common import exception
from trove.common import instance as rd_instance
from trove.guestagent import backup
from trove.guestagent import dbaas
from trove.guestagent import volume
from trove.guestagent.datastore.couchbase import service
from trove.guestagent.datastore.couchbase import system
from trove.openstack.common import log as logging
from trove.openstack.common import periodic_task
from trove.openstack.common.gettextutils import _


LOG = logging.getLogger(__name__)
CONF = cfg.CONF
MANAGER = CONF.datastore_manager


class Manager(periodic_task.PeriodicTasks):
    """
    This is Couchbase Manager class. It is dynamically loaded
    based off of the datastore of the trove instance
    """
    def __init__(self):
        self.appStatus = service.CouchbaseAppStatus()
        self.app = service.CouchbaseApp(self.appStatus)

    @periodic_task.periodic_task(ticks_between_runs=3)
    def update_status(self, context):
        """
        Updates the couchbase trove instance. It is decorated with
        perodic task so it is automatically called every 3 ticks.
        """
        self.appStatus.update()

    def change_passwords(self, context, users):
        raise exception.DatastoreOperationNotSupported(
            operation='change_passwords', datastore=MANAGER)

    def reset_configuration(self, context, configuration):
        self.app.reset_configuration(configuration)

    def prepare(self, context, packages, databases, memory_mb, users,
                device_path=None, mount_point=None, backup_info=None,
                config_contents=None, root_password=None, overrides=None):
        """
        This is called when the trove instance first comes online.
        It is the first rpc message passed from the task manager.
        prepare handles all the base configuration of the Couchbase instance.
        """
        self.appStatus.begin_install()
        self.app.install_if_needed(packages)
        if device_path:
            device = volume.VolumeDevice(device_path)
            # unmount if device is already mounted
            device.unmount_device(device_path)
            device.format()
            device.mount(mount_point)
            LOG.debug('Mounted the volume (%s).' % device_path)
        self.app.start_db_with_conf_changes(config_contents)
        LOG.debug('Securing couchbase now.')
        if root_password:
            self.app.enable_root(root_password)
        self.app.initial_setup()
        if backup_info:
            LOG.debug('Now going to perform restore.')
            self._perform_restore(backup_info,
                                  context,
                                  mount_point)
        self.app.complete_install_or_restart()
        LOG.info(_('Completed setup of Couchbase database instance.'))

    def restart(self, context):
        """
        Restart this couchbase instance.
        This method is called when the guest agent
        gets a restart message from the taskmanager.
        """
        self.app.restart()

    def start_db_with_conf_changes(self, context, config_contents):
        self.app.start_db_with_conf_changes(config_contents)

    def stop_db(self, context, do_not_start_on_reboot=False):
        """
        Stop this couchbase instance.
        This method is called when the guest agent
        gets a stop message from the taskmanager.
        """
        self.app.stop_db(do_not_start_on_reboot=do_not_start_on_reboot)

    def get_filesystem_stats(self, context, fs_path):
        """Gets the filesystem stats for the path given."""
        mount_point = CONF.get(
            'mysql' if not MANAGER else MANAGER).mount_point
        return dbaas.get_filesystem_volume_stats(mount_point)

    def update_attributes(self, context, username, hostname, user_attrs):
        raise exception.DatastoreOperationNotSupported(
            operation='update_attributes', datastore=MANAGER)

    def create_database(self, context, databases):
        raise exception.DatastoreOperationNotSupported(
            operation='create_database', datastore=MANAGER)

    def create_user(self, context, users):
        raise exception.DatastoreOperationNotSupported(
            operation='create_user', datastore=MANAGER)

    def delete_database(self, context, database):
        raise exception.DatastoreOperationNotSupported(
            operation='delete_database', datastore=MANAGER)

    def delete_user(self, context, user):
        raise exception.DatastoreOperationNotSupported(
            operation='delete_user', datastore=MANAGER)

    def get_user(self, context, username, hostname):
        raise exception.DatastoreOperationNotSupported(
            operation='get_user', datastore=MANAGER)

    def grant_access(self, context, username, hostname, databases):
        raise exception.DatastoreOperationNotSupported(
            operation='grant_access', datastore=MANAGER)

    def revoke_access(self, context, username, hostname, database):
        raise exception.DatastoreOperationNotSupported(
            operation='revoke_access', datastore=MANAGER)

    def list_access(self, context, username, hostname):
        raise exception.DatastoreOperationNotSupported(
            operation='list_access', datastore=MANAGER)

    def list_databases(self, context, limit=None, marker=None,
                       include_marker=False):
        raise exception.DatastoreOperationNotSupported(
            operation='list_databases', datastore=MANAGER)

    def list_users(self, context, limit=None, marker=None,
                   include_marker=False):
        raise exception.DatastoreOperationNotSupported(
            operation='list_users', datastore=MANAGER)

    def enable_root(self, context):
        return self.app.enable_root()

    def is_root_enabled(self, context):
        return os.path.exists(system.pwd_file)

    def _perform_restore(self, backup_info, context, restore_location):
        """
        Restores all couchbase buckets and their documents from the
        backup.
        """
        LOG.info(_("Restoring database from backup %s") %
                 backup_info['id'])
        try:
            backup.restore(context, backup_info, restore_location)
        except Exception as e:
            LOG.error(_("Error performing restore from backup %s") %
                      backup_info['id'])
            LOG.error(e)
            self.status.set_status(rd_instance.ServiceStatuses.FAILED)
            raise
        LOG.info(_("Restored database successfully"))

    def create_backup(self, context, backup_info):
        """
        Backup all couchbase buckets and their documents.
        """
        backup.backup(context, backup_info)

    def mount_volume(self, context, device_path=None, mount_point=None):
        device = volume.VolumeDevice(device_path)
        device.mount(mount_point, write_to_fstab=False)
        LOG.debug("Mounted the device %s at the mount_point %s." %
                  (device_path, mount_point))

    def unmount_volume(self, context, device_path=None, mount_point=None):
        device = volume.VolumeDevice(device_path)
        device.unmount(mount_point)
        LOG.debug("Unmounted the device %s from the mount point %s." %
                  (device_path, mount_point))

    def resize_fs(self, context, device_path=None, mount_point=None):
        device = volume.VolumeDevice(device_path)
        device.resize_fs(mount_point)
        LOG.debug("Resized the filesystem at %s." % mount_point)

    def update_overrides(self, context, overrides, remove=False):
        LOG.debug("Updating overrides.")
        raise exception.DatastoreOperationNotSupported(
            operation='update_overrides', datastore=MANAGER)

    def apply_overrides(self, context, overrides):
        LOG.debug("Applying overrides.")
        raise exception.DatastoreOperationNotSupported(
            operation='apply_overrides', datastore=MANAGER)

    def get_replication_snapshot(self, context, snapshot_info):
        raise exception.DatastoreOperationNotSupported(
            operation='get_replication_snapshot', datastore=MANAGER)

    def attach_replication_slave(self, context, snapshot, slave_config):
        LOG.debug("Attaching replication slave.")
        raise exception.DatastoreOperationNotSupported(
            operation='attach_replication_slave', datastore=MANAGER)

    def detach_replica(self, context):
        raise exception.DatastoreOperationNotSupported(
            operation='detach_replica', datastore=MANAGER)

    def demote_replication_master(self, context):
        LOG.debug("Demoting replication slave.")
        raise exception.DatastoreOperationNotSupported(
            operation='demote_replication_master', datastore=MANAGER)
