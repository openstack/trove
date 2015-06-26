# Copyright 2015 IBM Corp.
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
from oslo_service import periodic_task

from trove.common import cfg
from trove.common import exception
from trove.common.i18n import _
from trove.guestagent.datastore.experimental.couchdb import service
from trove.guestagent import dbaas
from trove.guestagent import volume

LOG = logging.getLogger(__name__)
CONF = cfg.CONF
MANAGER = CONF.datastore_manager


class Manager(periodic_task.PeriodicTasks):
    """
    This is CouchDB Manager class. It is dynamically loaded
    based off of the datastore of the Trove instance.
    """

    def __init__(self):
        self.appStatus = service.CouchDBAppStatus()
        self.app = service.CouchDBApp(self.appStatus)
        super(Manager, self).__init__(CONF)

    def rpc_ping(self, context):
        LOG.debug("Responding to RPC ping.")
        return True

    def prepare(self, context, packages, databases, memory_mb, users,
                device_path=None, mount_point=None, backup_info=None,
                config_contents=None, root_password=None, overrides=None,
                cluster_config=None, snapshot=None):
        """
        This is called when the Trove instance first comes online.
        It is the first RPC  message passed from the task manager.
        prepare handles all the base configuration of the CouchDB instance.
        """
        self.appStatus.begin_install()
        self.app.install_if_needed(packages)
        if device_path:
            self.app.stop_db()
            device = volume.VolumeDevice(device_path)
            # unmount if device is already mounted
            device.unmount_device(device_path)
            device.format()
            if os.path.exists(mount_point):
                device.migrate_data(mount_point)
            device.mount(mount_point)
            LOG.debug('Mounted the volume (%s).' % device_path)
            self.app.start_db()
        self.app.change_permissions()
        self.app.make_host_reachable()
        self.app.complete_install_or_restart()
        LOG.info(_('Completed setup of CouchDB database instance.'))

    @periodic_task.periodic_task
    def update_status(self, context):
        """Update the status of the CouchDB service."""
        self.appStatus.update()

    def get_filesystem_stats(self, context, fs_path):
        """Gets the filesystem stats for the path given."""
        LOG.debug("In get_filesystem_stats: fs_path= %s" % fs_path)
        mount_point = CONF.get(
            'mysql' if not MANAGER else MANAGER).mount_point
        return dbaas.get_filesystem_volume_stats(mount_point)

    def stop_db(self, context, do_not_start_on_reboot=False):
        """
        Stop this CouchDB instance.
        This method is called when the guest agent
        gets a stop message from the taskmanager.
        """
        LOG.debug("Stopping the CouchDB instance.")
        self.app.stop_db(do_not_start_on_reboot=do_not_start_on_reboot)

    def restart(self, context):
        """
        Restart this CouchDB instance.
        This method is called when the guest agent
        gets a restart message from the taskmanager.
        """
        LOG.debug("Restarting the CouchDB instance.")
        self.app.restart()

    def reset_configuration(self, context, configuration):
        """
         Currently this method does nothing. This method needs to be
         implemented to enable rollback of flavor-resize on guestagent side.
        """
        LOG.debug("Resetting CouchDB configuration.")
        pass

    def change_passwords(self, context, users):
        LOG.debug("Changing password.")
        raise exception.DatastoreOperationNotSupported(
            operation='change_passwords', datastore=MANAGER)

    def update_attributes(self, context, username, hostname, user_attrs):
        LOG.debug("Updating database attributes.")
        raise exception.DatastoreOperationNotSupported(
            operation='update_attributes', datastore=MANAGER)

    def create_database(self, context, databases):
        LOG.debug("Creating database.")
        raise exception.DatastoreOperationNotSupported(
            operation='create_database', datastore=MANAGER)

    def create_user(self, context, users):
        LOG.debug("Creating user.")
        raise exception.DatastoreOperationNotSupported(
            operation='create_user', datastore=MANAGER)

    def delete_database(self, context, database):
        LOG.debug("Deleting database.")
        raise exception.DatastoreOperationNotSupported(
            operation='delete_database', datastore=MANAGER)

    def delete_user(self, context, user):
        LOG.debug("Deleting user.")
        raise exception.DatastoreOperationNotSupported(
            operation='delete_user', datastore=MANAGER)

    def get_user(self, context, username, hostname):
        LOG.debug("Getting user.")
        raise exception.DatastoreOperationNotSupported(
            operation='get_user', datastore=MANAGER)

    def grant_access(self, context, username, hostname, databases):
        LOG.debug("Granting acccess.")
        raise exception.DatastoreOperationNotSupported(
            operation='grant_access', datastore=MANAGER)

    def revoke_access(self, context, username, hostname, database):
        LOG.debug("Revoking access.")
        raise exception.DatastoreOperationNotSupported(
            operation='revoke_access', datastore=MANAGER)

    def list_access(self, context, username, hostname):
        LOG.debug("Listing access.")
        raise exception.DatastoreOperationNotSupported(
            operation='list_access', datastore=MANAGER)

    def list_databases(self, context, limit=None, marker=None,
                       include_marker=False):
        LOG.debug("Listing databases.")
        raise exception.DatastoreOperationNotSupported(
            operation='list_databases', datastore=MANAGER)

    def list_users(self, context, limit=None, marker=None,
                   include_marker=False):
        LOG.debug("Listing users.")
        raise exception.DatastoreOperationNotSupported(
            operation='list_users', datastore=MANAGER)

    def enable_root(self, context):
        LOG.debug("Enabling root.")
        raise exception.DatastoreOperationNotSupported(
            operation='enable_root', datastore=MANAGER)

    def enable_root_with_password(self, context, root_password=None):
        LOG.debug("Enabling root with password.")
        raise exception.DatastoreOperationNotSupported(
            operation='enable_root_with_password', datastore=MANAGER)

    def is_root_enabled(self, context):
        LOG.debug("Checking if root is enabled.")
        raise exception.DatastoreOperationNotSupported(
            operation='is_root_enabled', datastore=MANAGER)

    def create_backup(self, context, backup_info):
        LOG.debug("Creating backup.")
        raise exception.DatastoreOperationNotSupported(
            operation='create_backup', datastore=MANAGER)

    def start_db_with_conf_changes(self, context, config_contents):
        LOG.debug("Starting CouchDB with configuration changes.")
        self.app.start_db_with_conf_changes(config_contents)

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
