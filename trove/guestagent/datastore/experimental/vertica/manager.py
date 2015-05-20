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

from trove.common import cfg
from trove.common import exception
from trove.common.i18n import _
from trove.common import instance as rd_ins
from trove.guestagent.datastore.experimental.vertica.service import (
    VerticaAppStatus)
from trove.guestagent.datastore.experimental.vertica.service import VerticaApp
from trove.guestagent import dbaas
from trove.guestagent import volume
from trove.openstack.common import log as logging
from trove.openstack.common import periodic_task

LOG = logging.getLogger(__name__)
CONF = cfg.CONF
MANAGER = 'vertica' if not CONF.datastore_manager else CONF.datastore_manager


class Manager(periodic_task.PeriodicTasks):

    def __init__(self):
        self.appStatus = VerticaAppStatus()
        self.app = VerticaApp(self.appStatus)

    @periodic_task.periodic_task(ticks_between_runs=3)
    def update_status(self, context):
        """Update the status of the Vertica service."""
        self.appStatus.update()

    def rpc_ping(self, context):
        LOG.debug("Responding to RPC ping.")
        return True

    def prepare(self, context, packages, databases, memory_mb, users,
                device_path=None, mount_point=None, backup_info=None,
                config_contents=None, root_password=None, overrides=None,
                cluster_config=None,
                snapshot=None, path_exists_function=os.path.exists):
        """Makes ready DBAAS on a Guest container."""
        try:
            LOG.info(_("Setting instance status to BUILDING."))
            self.appStatus.begin_install()
            if device_path:
                device = volume.VolumeDevice(device_path)
                # unmount if device is already mounted
                device.unmount_device(device_path)
                device.format()
                if path_exists_function(mount_point):
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
                self.app.complete_install_or_restart()
            elif cluster_config['instance_type'] == "member":
                self.appStatus.set_status(rd_ins.ServiceStatuses.BUILD_PENDING)
            else:
                LOG.error(_("Bad cluster configuration; instance type "
                            "given as %s.") % cluster_config['instance_type'])
                raise RuntimeError("Bad cluster configuration.")
            LOG.info(_('Completed setup of Vertica database instance.'))
        except Exception:
            LOG.exception(_('Cannot prepare Vertica database instance.'))
            self.appStatus.set_status(rd_ins.ServiceStatuses.FAILED)

    def restart(self, context):
        LOG.debug("Restarting the database.")
        self.app.restart()
        LOG.debug("Restarted the database.")

    def get_filesystem_stats(self, context, fs_path):
        """Gets the filesystem stats for the path given."""
        LOG.debug("Finding the file-systems stats.")
        mount_point = CONF.get(MANAGER).mount_point
        return dbaas.get_filesystem_volume_stats(mount_point)

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

    def is_root_enabled(self, context):
        LOG.debug("Checking if root is enabled.")
        raise exception.DatastoreOperationNotSupported(
            operation='is_root_enabled', datastore=MANAGER)

    def create_backup(self, context, backup_info):
        LOG.debug("Creating backup.")
        raise exception.DatastoreOperationNotSupported(
            operation='create_backup', datastore=MANAGER)

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

    def cluster_complete(self, context):
        LOG.debug("Cluster creation complete, starting status checks.")
        status = self.appStatus._get_actual_db_status()
        self.appStatus.set_status(status)
