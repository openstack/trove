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

from oslo_log import log as logging

from trove.common.i18n import _
from trove.common import instance as rd_instance
from trove.common.notification import EndNotification
from trove.guestagent import backup
from trove.guestagent.datastore.experimental.couchbase import service
from trove.guestagent.datastore.experimental.couchbase import system
from trove.guestagent.datastore import manager
from trove.guestagent import volume


LOG = logging.getLogger(__name__)


class Manager(manager.Manager):
    """
    This is Couchbase Manager class. It is dynamically loaded
    based off of the datastore of the trove instance
    """
    def __init__(self):
        self.appStatus = service.CouchbaseAppStatus()
        self.app = service.CouchbaseApp(self.appStatus)
        super(Manager, self).__init__('couchbase')

    @property
    def status(self):
        return self.appStatus

    def reset_configuration(self, context, configuration):
        self.app.reset_configuration(configuration)

    def do_prepare(self, context, packages, databases, memory_mb, users,
                   device_path, mount_point, backup_info,
                   config_contents, root_password, overrides,
                   cluster_config, snapshot):
        """This is called from prepare in the base class."""
        self.app.install_if_needed(packages)
        if device_path:
            device = volume.VolumeDevice(device_path)
            # unmount if device is already mounted
            device.unmount_device(device_path)
            device.format()
            device.mount(mount_point)
            LOG.debug('Mounted the volume (%s).', device_path)
        self.app.start_db_with_conf_changes(config_contents)
        LOG.debug('Securing couchbase now.')
        self.app.initial_setup()
        if backup_info:
            LOG.debug('Now going to perform restore.')
            self._perform_restore(backup_info,
                                  context,
                                  mount_point)

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

    def enable_root(self, context):
        LOG.debug("Enabling root.")
        return self.app.enable_root()

    def enable_root_with_password(self, context, root_password=None):
        return self.app.enable_root(root_password)

    def is_root_enabled(self, context):
        LOG.debug("Checking if root is enabled.")
        return os.path.exists(system.pwd_file)

    def _perform_restore(self, backup_info, context, restore_location):
        """
        Restores all couchbase buckets and their documents from the
        backup.
        """
        LOG.info(_("Restoring database from backup %s"), backup_info['id'])
        try:
            backup.restore(context, backup_info, restore_location)
        except Exception as e:
            LOG.error(_("Error performing restore from backup %s"),
                      backup_info['id'])
            LOG.error(e)
            self.status.set_status(rd_instance.ServiceStatuses.FAILED)
            raise
        LOG.info(_("Restored database successfully"))

    def create_backup(self, context, backup_info):
        """
        Backup all couchbase buckets and their documents.
        """
        with EndNotification(context):
            backup.backup(context, backup_info)
