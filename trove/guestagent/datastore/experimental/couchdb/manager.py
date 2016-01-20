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
