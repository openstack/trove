# Copyright [2015] Hewlett-Packard Development Company, L.P.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os

from oslo_log import log as logging

from trove.common import exception
from trove.common.i18n import _
from trove.common import instance as rd_ins
from trove.guestagent.datastore.experimental.vertica.service import (
    VerticaAppStatus)
from trove.guestagent.datastore.experimental.vertica.service import VerticaApp
from trove.guestagent.datastore import manager
from trove.guestagent import volume


LOG = logging.getLogger(__name__)


class Manager(manager.Manager):

    def __init__(self):
        self.appStatus = VerticaAppStatus()
        self.app = VerticaApp(self.appStatus)
        super(Manager, self).__init__('vertica')

    @property
    def status(self):
        return self.appStatus

    def do_prepare(self, context, packages, databases, memory_mb, users,
                   device_path, mount_point, backup_info,
                   config_contents, root_password, overrides,
                   cluster_config, snapshot):
        """This is called from prepare in the base class."""
        if device_path:
            device = volume.VolumeDevice(device_path)
            # unmount if device is already mounted
            device.unmount_device(device_path)
            device.format()
            if os.path.exists(mount_point):
                # rsync any existing data
                device.migrate_data(mount_point)
                # mount the volume
                device.mount(mount_point)
                LOG.debug("Mounted the volume.")
        self.app.install_if_needed(packages)
        self.app.prepare_for_install_vertica()
        if cluster_config is None:
            self.app.install_vertica()
            self.app.create_db()
        elif cluster_config['instance_type'] != "member":
            raise RuntimeError(_("Bad cluster configuration: instance type "
                               "given as %s.") %
                               cluster_config['instance_type'])

    def restart(self, context):
        LOG.debug("Restarting the database.")
        self.app.restart()
        LOG.debug("Restarted the database.")

    def stop_db(self, context, do_not_start_on_reboot=False):
        LOG.debug("Stopping the database.")
        self.app.stop_db(do_not_start_on_reboot=do_not_start_on_reboot)
        LOG.debug("Stopped the database.")

    def mount_volume(self, context, device_path=None, mount_point=None):
        LOG.debug("Mounting the volume.")
        device = volume.VolumeDevice(device_path)
        device.mount(mount_point, write_to_fstab=False)
        LOG.debug("Mounted the volume.")

    def unmount_volume(self, context, device_path=None, mount_point=None):
        LOG.debug("Unmounting the volume.")
        device = volume.VolumeDevice(device_path)
        device.unmount(mount_point)
        LOG.debug("Unmounted the volume.")

    def resize_fs(self, context, device_path=None, mount_point=None):
        LOG.debug("Resizing the filesystem.")
        device = volume.VolumeDevice(device_path)
        device.resize_fs(mount_point)
        LOG.debug("Resized the filesystem.")

    def reset_configuration(self, context, configuration):
        """
         Currently this method does nothing. This method needs to be
         implemented to enable rollback of flavor-resize on guestagent side.
        """
        LOG.debug("Resetting Vertica configuration.")
        pass

    def change_passwords(self, context, users):
        LOG.debug("Changing password.")
        raise exception.DatastoreOperationNotSupported(
            operation='change_passwords', datastore=self.manager)

    def update_attributes(self, context, username, hostname, user_attrs):
        LOG.debug("Updating database attributes.")
        raise exception.DatastoreOperationNotSupported(
            operation='update_attributes', datastore=self.manager)

    def create_database(self, context, databases):
        LOG.debug("Creating database.")
        raise exception.DatastoreOperationNotSupported(
            operation='create_database', datastore=self.manager)

    def create_user(self, context, users):
        LOG.debug("Creating user.")
        raise exception.DatastoreOperationNotSupported(
            operation='create_user', datastore=self.manager)

    def delete_database(self, context, database):
        LOG.debug("Deleting database.")
        raise exception.DatastoreOperationNotSupported(
            operation='delete_database', datastore=self.manager)

    def delete_user(self, context, user):
        LOG.debug("Deleting user.")
        raise exception.DatastoreOperationNotSupported(
            operation='delete_user', datastore=self.manager)

    def get_user(self, context, username, hostname):
        LOG.debug("Getting user.")
        raise exception.DatastoreOperationNotSupported(
            operation='get_user', datastore=self.manager)

    def grant_access(self, context, username, hostname, databases):
        LOG.debug("Granting acccess.")
        raise exception.DatastoreOperationNotSupported(
            operation='grant_access', datastore=self.manager)

    def revoke_access(self, context, username, hostname, database):
        LOG.debug("Revoking access.")
        raise exception.DatastoreOperationNotSupported(
            operation='revoke_access', datastore=self.manager)

    def list_access(self, context, username, hostname):
        LOG.debug("Listing access.")
        raise exception.DatastoreOperationNotSupported(
            operation='list_access', datastore=self.manager)

    def list_databases(self, context, limit=None, marker=None,
                       include_marker=False):
        LOG.debug("Listing databases.")
        raise exception.DatastoreOperationNotSupported(
            operation='list_databases', datastore=self.manager)

    def list_users(self, context, limit=None, marker=None,
                   include_marker=False):
        LOG.debug("Listing users.")
        raise exception.DatastoreOperationNotSupported(
            operation='list_users', datastore=self.manager)

    def enable_root(self, context):
        LOG.debug("Enabling root.")
        return self.app.enable_root()

    def enable_root_with_password(self, context, root_password=None):
        LOG.debug("Enabling root.")
        return self.app.enable_root(root_password)

    def is_root_enabled(self, context):
        LOG.debug("Checking if root is enabled.")
        return self.app.is_root_enabled()

    def create_backup(self, context, backup_info):
        LOG.debug("Creating backup.")
        raise exception.DatastoreOperationNotSupported(
            operation='create_backup', datastore=self.manager)

    def start_db_with_conf_changes(self, context, config_contents):
        LOG.debug("Starting with configuration changes.")
        self.app.start_db_with_conf_changes(config_contents)

    def get_public_keys(self, context, user):
        LOG.debug("Retrieving public keys for %s." % user)
        return self.app.get_public_keys(user)

    def authorize_public_keys(self, context, user, public_keys):
        LOG.debug("Authorizing public keys for %s." % user)
        return self.app.authorize_public_keys(user, public_keys)

    def install_cluster(self, context, members):
        try:
            LOG.debug("Installing cluster on members: %s." % members)
            self.app.install_cluster(members)
            LOG.debug("install_cluster call has finished.")
        except Exception:
            LOG.exception(_('Cluster installation failed.'))
            self.appStatus.set_status(rd_ins.ServiceStatuses.FAILED)
            raise
