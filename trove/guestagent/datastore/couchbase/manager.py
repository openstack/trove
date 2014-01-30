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

from trove.common import cfg
from trove.common import exception
from trove.guestagent import dbaas
from trove.guestagent import volume
from trove.guestagent.datastore.couchbase import system
from trove.guestagent.datastore.couchbase import service
from trove.openstack.common import log as logging
from trove.openstack.common import periodic_task
from trove.openstack.common.gettextutils import _


LOG = logging.getLogger(__name__)
CONF = cfg.CONF
ERROR_MSG = _("Not supported")


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
        raise exception.TroveError(ERROR_MSG)

    def reset_configuration(self, context, configuration):
        raise exception.TroveError(ERROR_MSG)

    def prepare(self, context, packages, databases, memory_mb, users,
                device_path=None, mount_point=None, backup_info=None,
                config_contents=None, root_password=None, overrides=None):
        """
        This is called when the trove instance first comes online.
        It is the first rpc message passed from the task manager.
        prepare handles all the base configuration of the Couchbase instance.
        """
        self.appStatus.begin_install()
        if device_path:
            device = volume.VolumeDevice(device_path)
            device.format()
            device.mount(system.COUCHBASE_MOUNT_POINT)
            LOG.debug(_('Mounted the volume.'))
        self.app.install_if_needed(packages)
        LOG.info(_('Securing couchbase now.'))
        self.app.complete_install_or_restart()
        LOG.info(_('"prepare" couchbase call has finished.'))

    def restart(self, context):
        """
        Restart this couchbase instance.
        This method is called when the guest agent
        gets a restart message from the taskmanager.
        """
        self.app.restart()

    def start_db_with_conf_changes(self, context, config_contents):
        raise exception.TroveError(ERROR_MSG)

    def stop_db(self, context, do_not_start_on_reboot=False):
        """
        Stop this couchbase instance.
        This method is called when the guest agent
        gets a stop message from the taskmanager.
        """
        self.app.stop_db(do_not_start_on_reboot=do_not_start_on_reboot)

    def get_filesystem_stats(self, context, fs_path):
        """
        Gets file system stats from the provided fs_path.
        """
        return dbaas.get_filesystem_volume_stats(system.COUCHBASE_MOUNT_POINT)

    def update_attributes(self, context, username, hostname, user_attrs):
        raise exception.TroveError(ERROR_MSG)

    def create_database(self, context, databases):
        raise exception.TroveError(ERROR_MSG)

    def create_user(self, context, users):
        raise exception.TroveError(ERROR_MSG)

    def delete_database(self, context, database):
        raise exception.TroveError(ERROR_MSG)

    def delete_user(self, context, user):
        raise exception.TroveError(ERROR_MSG)

    def get_user(self, context, username, hostname):
        raise exception.TroveError(ERROR_MSG)

    def grant_access(self, context, username, hostname, databases):
        raise exception.TroveError(ERROR_MSG)

    def revoke_access(self, context, username, hostname, database):
        raise exception.TroveError(ERROR_MSG)

    def list_access(self, context, username, hostname):
        raise exception.TroveError(ERROR_MSG)

    def list_databases(self, context, limit=None, marker=None,
                       include_marker=False):
        raise exception.TroveError(ERROR_MSG)

    def list_users(self, context, limit=None, marker=None,
                   include_marker=False):
        raise exception.TroveError(ERROR_MSG)

    def enable_root(self, context):
        raise exception.TroveError(ERROR_MSG)

    def is_root_enabled(self, context):
        raise exception.TroveError(ERROR_MSG)

    def _perform_restore(self, backup_info, context, restore_location, app):
        raise exception.TroveError(ERROR_MSG)

    def create_backup(self, context, backup_info):
        raise exception.TroveError(ERROR_MSG)

    def mount_volume(self, context, device_path=None, mount_point=None):
        device = volume.VolumeDevice(device_path)
        device.mount(mount_point, write_to_fstab=False)
        LOG.debug(_("Mounted the volume."))

    def unmount_volume(self, context, device_path=None, mount_point=None):
        device = volume.VolumeDevice(device_path)
        device.unmount(mount_point)
        LOG.debug(_("Unmounted the volume."))

    def resize_fs(self, context, device_path=None, mount_point=None):
        device = volume.VolumeDevice(device_path)
        device.resize_fs(mount_point)
        LOG.debug(_("Resized the filesystem."))

    def update_overrides(self, context, overrides, remove=False):
        raise exception.TroveError(ERROR_MSG)

    def apply_overrides(self, context, overrides):
        raise exception.TroveError(ERROR_MSG)
