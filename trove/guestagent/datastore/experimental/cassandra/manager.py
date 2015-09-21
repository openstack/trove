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

from oslo_log import log as logging

from trove.common import cfg
from trove.common.i18n import _
from trove.common import instance as trove_instance
from trove.common.notification import EndNotification
from trove.guestagent import backup
from trove.guestagent.datastore.experimental.cassandra import service
from trove.guestagent.datastore.experimental.cassandra.service import (
    CassandraAdmin
)
from trove.guestagent.datastore import manager
from trove.guestagent import volume


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class Manager(manager.Manager):

    def __init__(self):
        self._app = service.CassandraApp()
        self.__admin = CassandraAdmin(self.app.get_current_superuser())
        super(Manager, self).__init__('cassandra')

    @property
    def status(self):
        return self.app.status

    @property
    def app(self):
        return self._app

    @property
    def admin(self):
        return self.__admin

    @property
    def configuration_manager(self):
        return self.app.configuration_manager

    def restart(self, context):
        self.app.restart()

    def start_db_with_conf_changes(self, context, config_contents):
        self.app.start_db_with_conf_changes(config_contents)

    def stop_db(self, context, do_not_start_on_reboot=False):
        self.app.stop_db(do_not_start_on_reboot=do_not_start_on_reboot)

    def reset_configuration(self, context, configuration):
        self.app.reset_configuration(configuration)

    def do_prepare(self, context, packages, databases, memory_mb, users,
                   device_path, mount_point, backup_info,
                   config_contents, root_password, overrides,
                   cluster_config, snapshot):
        """This is called from prepare in the base class."""
        self.app.install_if_needed(packages)
        self.app.init_storage_structure(mount_point)

        if config_contents or device_path or backup_info:

            # FIXME(pmalik) Once the cassandra bug
            # https://issues.apache.org/jira/browse/CASSANDRA-2356
            # is fixed, this code may have to be revisited.
            #
            # Cassandra generates system keyspaces on the first start.
            # The stored properties include the 'cluster_name', which once
            # saved cannot be easily changed without removing the system
            # tables. It is crucial that the service does not boot up in
            # the middle of the configuration procedure.
            # We wait here for the service to come up, stop it properly and
            # remove the generated keyspaces before proceeding with
            # configuration. If it does not start up within the time limit
            # we assume it is not going to and proceed with configuration
            # right away.
            LOG.debug("Waiting for database first boot.")
            if (self.app.status.wait_for_real_status_to_change_to(
                    trove_instance.ServiceStatuses.RUNNING,
                    CONF.state_change_wait_time,
                    False)):
                LOG.debug("Stopping database prior to initial configuration.")
                self.app.stop_db()
                self.app._remove_system_tables()

            LOG.debug("Starting initial configuration.")
            if config_contents:
                LOG.debug("Applying configuration.")
                self.app.configuration_manager.save_configuration(
                    config_contents)
                self.app.apply_initial_guestagent_configuration()

            if device_path:
                LOG.debug("Preparing data volume.")
                device = volume.VolumeDevice(device_path)
                # unmount if device is already mounted
                device.unmount_device(device_path)
                device.format()
                if os.path.exists(mount_point):
                    # rsync exiting data
                    LOG.debug("Migrating existing data.")
                    device.migrate_data(mount_point)
                # mount the volume
                LOG.debug("Mounting new volume.")
                device.mount(mount_point)

            if backup_info:
                self._perform_restore(backup_info, context, mount_point)

            LOG.debug("Starting database with configuration changes.")
            self.app.start_db(update_db=False)

            if not self.app.has_user_config():
                LOG.debug("Securing superuser access.")
                self.app.secure()
                self.app.restart()

            self.__admin = CassandraAdmin(self.app.get_current_superuser())

    def change_passwords(self, context, users):
        with EndNotification(context):
            self.admin.change_passwords(context, users)

    def update_attributes(self, context, username, hostname, user_attrs):
        with EndNotification(context):
            self.admin.update_attributes(context, username, hostname,
                                         user_attrs)

    def create_database(self, context, databases):
        with EndNotification(context):
            self.admin.create_database(context, databases)

    def create_user(self, context, users):
        with EndNotification(context):
            self.admin.create_user(context, users)

    def delete_database(self, context, database):
        with EndNotification(context):
            self.admin.delete_database(context, database)

    def delete_user(self, context, user):
        with EndNotification(context):
            self.admin.delete_user(context, user)

    def get_user(self, context, username, hostname):
        return self.admin.get_user(context, username, hostname)

    def grant_access(self, context, username, hostname, databases):
        self.admin.grant_access(context, username, hostname, databases)

    def revoke_access(self, context, username, hostname, database):
        self.admin.revoke_access(context, username, hostname, database)

    def list_access(self, context, username, hostname):
        return self.admin.list_access(context, username, hostname)

    def list_databases(self, context, limit=None, marker=None,
                       include_marker=False):
        return self.admin.list_databases(context, limit, marker,
                                         include_marker)

    def list_users(self, context, limit=None, marker=None,
                   include_marker=False):
        return self.admin.list_users(context, limit, marker, include_marker)

    def _perform_restore(self, backup_info, context, restore_location):
        LOG.info(_("Restoring database from backup %s.") % backup_info['id'])
        try:
            backup.restore(context, backup_info, restore_location)
            self.app._apply_post_restore_updates(backup_info)
        except Exception as e:
            LOG.error(e)
            LOG.error(_("Error performing restore from backup %s.") %
                      backup_info['id'])
            self.app.status.set_status(trove_instance.ServiceStatuses.FAILED)
            raise
        LOG.info(_("Restored database successfully."))

    def create_backup(self, context, backup_info):
        """
        Entry point for initiating a backup for this instance.
        The call currently blocks guestagent until the backup is finished.

        :param backup_info: a dictionary containing the db instance id of the
                            backup task, location, type, and other data.
        """

        with EndNotification(context):
            backup.backup(context, backup_info)

    def update_overrides(self, context, overrides, remove=False):
        LOG.debug("Updating overrides.")
        if remove:
            self.app.remove_overrides()
        else:
            self.app.update_overrides(context, overrides, remove)

    def apply_overrides(self, context, overrides):
        """Configuration changes are made in the config YAML file and
        require restart, so this is a no-op.
        """
        pass
