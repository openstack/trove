#  Copyright 2013 Mirantis Inc.
#  All Rights Reserved.
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
from trove.guestagent import volume
from trove.guestagent.datastore.cassandra import service
from trove.guestagent.datastore.cassandra import system
from trove.openstack.common import periodic_task
from trove.openstack.common import log as logging
from trove.openstack.common.gettextutils import _
from trove.guestagent import dbaas

CONF = cfg.CONF
LOG = logging.getLogger(__name__)
USAGE_SLEEP_TIME = CONF.usage_sleep_time  # seconds.
USAGE_TIMEOUT = CONF.usage_timeout  # seconds.
ERROR_MSG = _("Not supported")


class Manager(periodic_task.PeriodicTasks):

    def __init__(self):
        self.appStatus = service.CassandraAppStatus()
        self.app = service.CassandraApp(self.appStatus)

    @periodic_task.periodic_task(ticks_between_runs=3)
    def update_status(self, context):
        """Update the status of the Cassandra service"""
        self.appStatus.update()

    def restart(self, context):
        self.app.restart()

    def get_filesystem_stats(self, context, fs_path):
        """Gets the filesystem stats for the path given. """
        return dbaas.get_filesystem_volume_stats(
            system.CASSANDRA_MOUNT_POINT)

    def start_db_with_conf_changes(self, context, config_contents):
        self.app.start_db_with_conf_changes(config_contents)

    def stop_db(self, context, do_not_start_on_reboot=False):
        self.app.stop_db(do_not_start_on_reboot=do_not_start_on_reboot)

    def reset_configuration(self, context, configuration):
        self.app.reset_configuration(configuration)

    def prepare(self, context, packages, databases, memory_mb, users,
                device_path=None, mount_point=None, backup_info=None,
                config_contents=None, root_password=None, overrides=None):
        LOG.info(_("Setting status BUILDING"))
        self.appStatus.begin_install()
        LOG.info("Installing cassandra")
        self.app.install_if_needed(packages)
        self.app.init_storage_structure()
        if config_contents:
            LOG.info(_("Config processing"))
            self.app.write_config(config_contents)
            self.app.make_host_reachable()
        if device_path:
            device = volume.VolumeDevice(device_path)
            device.format()
            if os.path.exists(system.CASSANDRA_MOUNT_POINT):
                #rsync exiting data
                device.migrate_data(system.CASSANDRA_MOUNT_POINT)
            #mount the volume
            device.mount(system.CASSANDRA_MOUNT_POINT)
            LOG.debug(_("Mounting new volume."))
            self.app.restart()

        self.appStatus.end_install_or_restart()
        LOG.info(_('"prepare" call has finished.'))

    def change_passwords(self, context, users):
        raise exception.TroveError(ERROR_MSG)

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
        LOG.debug(_("Resized the filesystem"))

    def update_overrides(self, context, overrides, remove=False):
        raise exception.TroveError(ERROR_MSG)

    def apply_overrides(self, context, overrides):
        raise exception.TroveError(ERROR_MSG)
