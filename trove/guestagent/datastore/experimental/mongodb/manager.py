#   Copyright (c) 2014 Mirantis, Inc.
#   All Rights Reserved.
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
from trove.common import instance as ds_instance
from trove.common.notification import EndNotification
from trove.guestagent import backup
from trove.guestagent.common import operating_system
from trove.guestagent.datastore.experimental.mongodb import service
from trove.guestagent.datastore.experimental.mongodb import system
from trove.guestagent.datastore import manager
from trove.guestagent import dbaas
from trove.guestagent import volume


LOG = logging.getLogger(__name__)


class Manager(manager.Manager):

    def __init__(self):
        self.app = service.MongoDBApp()
        super(Manager, self).__init__('mongodb')

    @property
    def status(self):
        return self.app.status

    @property
    def configuration_manager(self):
        return self.app.configuration_manager

    def do_prepare(self, context, packages, databases, memory_mb, users,
                   device_path, mount_point, backup_info,
                   config_contents, root_password, overrides,
                   cluster_config, snapshot):
        """This is called from prepare in the base class."""
        self.app.install_if_needed(packages)
        self.status.wait_for_database_service_start(
            self.app.state_change_wait_time)
        self.app.stop_db()
        self.app.clear_storage()
        mount_point = system.MONGODB_MOUNT_POINT
        if device_path:
            device = volume.VolumeDevice(device_path)
            # unmount if device is already mounted
            device.unmount_device(device_path)
            device.format()
            if os.path.exists(system.MONGODB_MOUNT_POINT):
                device.migrate_data(mount_point)
            device.mount(mount_point)
            operating_system.chown(mount_point,
                                   system.MONGO_USER, system.MONGO_USER,
                                   as_root=True)

            LOG.debug("Mounted the volume %(path)s as %(mount)s." %
                      {'path': device_path, "mount": mount_point})

        if config_contents:
            # Save resolved configuration template first.
            self.app.configuration_manager.save_configuration(config_contents)

        # Apply guestagent specific configuration changes.
        self.app.apply_initial_guestagent_configuration(
            cluster_config, mount_point)

        if not cluster_config:
            # Create the Trove admin user.
            self.app.secure()

        # Don't start mongos until add_config_servers is invoked,
        # don't start members as they should already be running.
        if not (self.app.is_query_router or self.app.is_cluster_member):
            self.app.start_db(update_db=True)

        if not cluster_config and backup_info:
            self._perform_restore(backup_info, context, mount_point, self.app)
            if service.MongoDBAdmin().is_root_enabled():
                self.app.status.report_root(context, 'root')

    def restart(self, context):
        LOG.debug("Restarting MongoDB.")
        self.app.restart()

    def start_db_with_conf_changes(self, context, config_contents):
        LOG.debug("Starting MongoDB with configuration changes.")
        self.app.start_db_with_conf_changes(config_contents)

    def stop_db(self, context, do_not_start_on_reboot=False):
        LOG.debug("Stopping MongoDB.")
        self.app.stop_db(do_not_start_on_reboot=do_not_start_on_reboot)

    def get_filesystem_stats(self, context, fs_path):
        """Gets the filesystem stats for the path given."""
        LOG.debug("Getting file system status.")
        # TODO(peterstac) - why is this hard-coded?
        return dbaas.get_filesystem_volume_stats(system.MONGODB_MOUNT_POINT)

    def change_passwords(self, context, users):
        LOG.debug("Changing password.")
        with EndNotification(context):
            return service.MongoDBAdmin().change_passwords(users)

    def update_attributes(self, context, username, hostname, user_attrs):
        LOG.debug("Updating database attributes.")
        with EndNotification(context):
            return service.MongoDBAdmin().update_attributes(username,
                                                            user_attrs)

    def create_database(self, context, databases):
        LOG.debug("Creating database(s).")
        with EndNotification(context):
            return service.MongoDBAdmin().create_database(databases)

    def create_user(self, context, users):
        LOG.debug("Creating user(s).")
        with EndNotification(context):
            return service.MongoDBAdmin().create_users(users)

    def delete_database(self, context, database):
        LOG.debug("Deleting database.")
        with EndNotification(context):
            return service.MongoDBAdmin().delete_database(database)

    def delete_user(self, context, user):
        LOG.debug("Deleting user.")
        with EndNotification(context):
            return service.MongoDBAdmin().delete_user(user)

    def get_user(self, context, username, hostname):
        LOG.debug("Getting user.")
        return service.MongoDBAdmin().get_user(username)

    def grant_access(self, context, username, hostname, databases):
        LOG.debug("Granting acccess.")
        return service.MongoDBAdmin().grant_access(username, databases)

    def revoke_access(self, context, username, hostname, database):
        LOG.debug("Revoking access.")
        return service.MongoDBAdmin().revoke_access(username, database)

    def list_access(self, context, username, hostname):
        LOG.debug("Listing access.")
        return service.MongoDBAdmin().list_access(username)

    def list_databases(self, context, limit=None, marker=None,
                       include_marker=False):
        LOG.debug("Listing databases.")
        return service.MongoDBAdmin().list_databases(limit, marker,
                                                     include_marker)

    def list_users(self, context, limit=None, marker=None,
                   include_marker=False):
        LOG.debug("Listing users.")
        return service.MongoDBAdmin().list_users(limit, marker, include_marker)

    def enable_root(self, context):
        LOG.debug("Enabling root.")
        return service.MongoDBAdmin().enable_root()

    def enable_root_with_password(self, context, root_password=None):
        return service.MongoDBAdmin().enable_root(root_password)

    def is_root_enabled(self, context):
        LOG.debug("Checking if root is enabled.")
        return service.MongoDBAdmin().is_root_enabled()

    def _perform_restore(self, backup_info, context, restore_location, app):
        LOG.info(_("Restoring database from backup %s.") % backup_info['id'])
        try:
            backup.restore(context, backup_info, restore_location)
        except Exception:
            LOG.exception(_("Error performing restore from backup %s.") %
                          backup_info['id'])
            self.status.set_status(ds_instance.ServiceStatuses.FAILED)
            raise
        LOG.info(_("Restored database successfully."))

    def create_backup(self, context, backup_info):
        LOG.debug("Creating backup.")
        with EndNotification(context):
            backup.backup(context, backup_info)

    def update_overrides(self, context, overrides, remove=False):
        LOG.debug("Updating overrides.")
        if remove:
            self.app.remove_overrides()
        else:
            self.app.update_overrides(context, overrides, remove)

    def apply_overrides(self, context, overrides):
        LOG.debug("Overrides will be applied after restart.")
        pass

    def add_members(self, context, members):
        try:
            LOG.debug("add_members called.")
            LOG.debug("args: members=%s." % members)
            self.app.add_members(members)
            LOG.debug("add_members call has finished.")
        except Exception:
            self.app.status.set_status(ds_instance.ServiceStatuses.FAILED)
            raise

    def add_config_servers(self, context, config_servers):
        try:
            LOG.debug("add_config_servers called.")
            LOG.debug("args: config_servers=%s." % config_servers)
            self.app.add_config_servers(config_servers)
            LOG.debug("add_config_servers call has finished.")
        except Exception:
            self.app.status.set_status(ds_instance.ServiceStatuses.FAILED)
            raise

    def add_shard(self, context, replica_set_name, replica_set_member):
        try:
            LOG.debug("add_shard called.")
            LOG.debug("args: replica_set_name=%s, replica_set_member=%s." %
                      (replica_set_name, replica_set_member))
            self.app.add_shard(replica_set_name, replica_set_member)
            LOG.debug("add_shard call has finished.")
        except Exception:
            self.app.status.set_status(ds_instance.ServiceStatuses.FAILED)
            raise

    def get_key(self, context):
        # Return the cluster key
        LOG.debug("Getting the cluster key.")
        return self.app.get_key()

    def prep_primary(self, context):
        LOG.debug("Preparing to be primary member.")
        self.app.prep_primary()

    def create_admin_user(self, context, password):
        self.app.create_admin_user(password)

    def store_admin_password(self, context, password):
        self.app.store_admin_password(password)

    def get_replica_set_name(self, context):
        # Return this nodes replica set name
        LOG.debug("Getting the replica set name.")
        return self.app.replica_set_name

    def get_admin_password(self, context):
        # Return the admin password from this instance
        LOG.debug("Getting the admin password.")
        return self.app.admin_password

    def is_shard_active(self, context, replica_set_name):
        return self.app.is_shard_active(replica_set_name)
