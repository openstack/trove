# Copyright 2015 IBM Corp
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import os

from oslo_log import log as logging

from trove.common import instance as ds_instance
from trove.common.notification import EndNotification
from trove.guestagent import backup
from trove.guestagent.datastore.experimental.db2 import service
from trove.guestagent.datastore import manager
from trove.guestagent import volume


LOG = logging.getLogger(__name__)


class Manager(manager.Manager):
    """
    This is DB2 Manager class. It is dynamically loaded
    based off of the datastore of the Trove instance.
    """
    def __init__(self):
        self.appStatus = service.DB2AppStatus()
        self.app = service.DB2App(self.appStatus)
        self.admin = service.DB2Admin()
        super(Manager, self).__init__('db2')

    @property
    def status(self):
        return self.appStatus

    @property
    def configuration_manager(self):
        return self.app.configuration_manager

    def do_prepare(self, context, packages, databases, memory_mb, users,
                   device_path, mount_point, backup_info,
                   config_contents, root_password, overrides,
                   cluster_config, snapshot):
        """This is called from prepare in the base class."""
        if device_path:
            device = volume.VolumeDevice(device_path)
            device.unmount_device(device_path)
            device.format()
            if os.path.exists(mount_point):
                device.migrate_data(mount_point)
                device.mount(mount_point)
                LOG.debug("Mounted the volume.")
        self.app.update_hostname()
        self.app.change_ownership(mount_point)
        self.app.start_db()
        if backup_info:
            self._perform_restore(backup_info, context, mount_point)
        if config_contents:
            self.app.configuration_manager.save_configuration(
                config_contents)

    def restart(self, context):
        """
        Restart this DB2 instance.
        This method is called when the guest agent
        gets a restart message from the taskmanager.
        """
        LOG.debug("Restart a DB2 server instance.")
        self.app.restart()

    def stop_db(self, context, do_not_start_on_reboot=False):
        """
        Stop this DB2 instance.
        This method is called when the guest agent
        gets a stop message from the taskmanager.
        """
        LOG.debug("Stop a given DB2 server instance.")
        self.app.stop_db(do_not_start_on_reboot=do_not_start_on_reboot)

    def create_database(self, context, databases):
        LOG.debug("Creating database(s) %s.", databases)
        with EndNotification(context):
            self.admin.create_database(databases)

    def delete_database(self, context, database):
        LOG.debug("Deleting database %s.", database)
        with EndNotification(context):
            return self.admin.delete_database(database)

    def list_databases(self, context, limit=None, marker=None,
                       include_marker=False):
        LOG.debug("Listing all databases.")
        return self.admin.list_databases(limit, marker, include_marker)

    def create_user(self, context, users):
        LOG.debug("Create user(s).")
        with EndNotification(context):
            self.admin.create_user(users)

    def delete_user(self, context, user):
        LOG.debug("Delete a user %s.", user)
        with EndNotification(context):
            self.admin.delete_user(user)

    def get_user(self, context, username, hostname):
        LOG.debug("Show details of user %s.", username)
        return self.admin.get_user(username, hostname)

    def list_users(self, context, limit=None, marker=None,
                   include_marker=False):
        LOG.debug("List all users.")
        return self.admin.list_users(limit, marker, include_marker)

    def list_access(self, context, username, hostname):
        LOG.debug("List all the databases the user has access to.")
        return self.admin.list_access(username, hostname)

    def start_db_with_conf_changes(self, context, config_contents):
        LOG.debug("Starting DB2 with configuration changes.")
        self.app.start_db_with_conf_changes(config_contents)

    def _perform_restore(self, backup_info, context, restore_location):
        LOG.info("Restoring database from backup %s.", backup_info['id'])
        try:
            backup.restore(context, backup_info, restore_location)
        except Exception:
            LOG.exception("Error performing restore from backup %s.",
                          backup_info['id'])
            self.status.set_status(ds_instance.ServiceStatuses.FAILED)
            raise
        LOG.info("Restored database successfully.")

    def create_backup(self, context, backup_info):
        LOG.debug("Creating backup.")
        backup.backup(context, backup_info)

    def update_overrides(self, context, overrides, remove=False):
        LOG.debug("Updating overrides.")
        if remove:
            self.app.remove_overrides()
        else:
            self.app.update_overrides(context, overrides)

    def apply_overrides(self, context, overrides):
        if overrides:
            LOG.debug("Applying overrides: %s", str(overrides))
            self.app.apply_overrides(overrides)
