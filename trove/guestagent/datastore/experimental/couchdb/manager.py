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

from trove.common.i18n import _
from trove.common import instance as rd_instance
from trove.guestagent import backup
from trove.guestagent.datastore.experimental.couchdb import service
from trove.guestagent.datastore import manager
from trove.guestagent import volume

LOG = logging.getLogger(__name__)


class Manager(manager.Manager):
    """
    This is CouchDB Manager class. It is dynamically loaded
    based off of the datastore of the Trove instance.
    """

    def __init__(self):
        self.appStatus = service.CouchDBAppStatus()
        self.app = service.CouchDBApp(self.appStatus)
        super(Manager, self).__init__('couchdb')

    @property
    def status(self):
        return self.appStatus

    def do_prepare(self, context, packages, databases, memory_mb, users,
                   device_path, mount_point, backup_info,
                   config_contents, root_password, overrides,
                   cluster_config, snapshot):
        """This is called from prepare in the base class."""
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
        if backup_info:
            self._perform_restore(backup_info, context, mount_point)
        self.app.secure()

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

    def start_db_with_conf_changes(self, context, config_contents):
        LOG.debug("Starting CouchDB with configuration changes.")
        self.app.start_db_with_conf_changes(config_contents)

    def _perform_restore(self, backup_info, context, restore_location):
        """
        Restores all CouchDB databases and their documents from the
        backup.
        """
        LOG.info(_("Restoring database from backup %s") %
                 backup_info['id'])
        try:
            backup.restore(context, backup_info, restore_location)
        except Exception:
            LOG.exception(_("Error performing restore from backup %s") %
                          backup_info['id'])
            self.status.set_status(rd_instance.ServiceStatuses.FAILED)
            raise
        LOG.info(_("Restored database successfully"))

    def create_backup(self, context, backup_info):
        LOG.debug("Creating backup for CouchDB.")
        backup.backup(context, backup_info)

    def create_admin_user(self, context, password):
        self.app.create_admin_user(password)

    def store_admin_password(self, context, password):
        self.app.store_admin_password(password)

    def create_user(self, context, users):
        LOG.debug("Creating user(s).")
        return service.CouchDBAdmin().create_user(users)

    def delete_user(self, context, user):
        LOG.debug("Deleting user.")
        return service.CouchDBAdmin().delete_user(user)

    def list_users(self, context, limit=None, marker=None,
                   include_marker=False):
        LOG.debug("Listing users.")
        return service.CouchDBAdmin().list_users(limit, marker, include_marker)

    def get_user(self, context, username, hostname):
        LOG.debug("Show details of user %s." % username)
        return service.CouchDBAdmin().get_user(username, hostname)

    def grant_access(self, context, username, hostname, databases):
        LOG.debug("Granting acccess.")
        return service.CouchDBAdmin().grant_access(username, databases)

    def revoke_access(self, context, username, hostname, database):
        LOG.debug("Revoking access.")
        return service.CouchDBAdmin().revoke_access(username, database)

    def list_access(self, context, username, hostname):
        LOG.debug("Listing access.")
        return service.CouchDBAdmin().list_access(username, hostname)

    def enable_root(self, context):
        LOG.debug("Enabling root.")
        return service.CouchDBAdmin().enable_root()

    def enable_root_with_password(self, context, root_password=None):
        return service.CouchDBAdmin().enable_root(root_pwd=root_password)

    def is_root_enabled(self, context):
        LOG.debug("Checking if root is enabled.")
        return service.CouchDBAdmin().is_root_enabled()

    def create_database(self, context, databases):
        LOG.debug("Creating database(s).")
        return service.CouchDBAdmin().create_database(databases)

    def list_databases(self, context, limit=None, marker=None,
                       include_marker=False):
        LOG.debug("Listing databases.")
        return service.CouchDBAdmin().list_databases(limit, marker,
                                                     include_marker)

    def delete_database(self, context, database):
        LOG.debug("Deleting database.")
        return service.CouchDBAdmin().delete_database(database)
