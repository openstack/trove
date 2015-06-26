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
from oslo_service import periodic_task

from trove.common import cfg
from trove.common import exception
from trove.common.i18n import _
from trove.common import instance as ds_instance
from trove.guestagent import backup
from trove.guestagent.common import operating_system
from trove.guestagent.datastore.experimental.mongodb import service
from trove.guestagent.datastore.experimental.mongodb import system
from trove.guestagent import dbaas
from trove.guestagent import volume


LOG = logging.getLogger(__name__)
CONF = cfg.CONF
MANAGER = CONF.datastore_manager


class Manager(periodic_task.PeriodicTasks):

    def __init__(self):
        self.app = service.MongoDBApp()
        super(Manager, self).__init__(CONF)

    @periodic_task.periodic_task
    def update_status(self, context):
        """Update the status of the MongoDB service."""
        self.app.status.update()

    def rpc_ping(self, context):
        LOG.debug("Responding to RPC ping.")
        return True

    def prepare(self, context, packages, databases, memory_mb, users,
                device_path=None, mount_point=None, backup_info=None,
                config_contents=None, root_password=None, overrides=None,
                cluster_config=None, snapshot=None):
        """Makes ready DBAAS on a Guest container."""

        LOG.debug("Preparing MongoDB instance.")

        self.app.status.begin_install()
        self.app.install_if_needed(packages)
        self.app.wait_for_start()
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
                self.app.status.report_root('root')

        if not cluster_config and root_password:
            LOG.debug('Root password provided. Enabling root.')
            service.MongoDBAdmin().enable_root(root_password)

        if not cluster_config:
            if databases:
                self.create_database(context, databases)
            if users:
                self.create_user(context, users)

        if cluster_config:
            self.app.status.set_status(
                ds_instance.ServiceStatuses.BUILD_PENDING)
        else:
            self.app.complete_install_or_restart()

        LOG.info(_('Completed setup of MongoDB database instance.'))

    def restart(self, context):
        LOG.debug("Restarting MongoDB.")
        self.app.restart()

    def start_db_with_conf_changes(self, context, config_contents):
        LOG.debug("Starting MongoDB with configuration changes.")
        self.app.start_db_with_conf_changes(config_contents)

    def stop_db(self, context, do_not_start_on_reboot=False):
        LOG.debug("Stopping MongoDB.")
        self.app.stop_db(do_not_start_on_reboot=do_not_start_on_reboot)

    def reset_configuration(self, context, configuration):
        LOG.debug("Resetting MongoDB configuration.")
        self.app.reset_configuration(configuration)

    def get_filesystem_stats(self, context, fs_path):
        """Gets the filesystem stats for the path given."""
        LOG.debug("Getting file system status.")
        return dbaas.get_filesystem_volume_stats(system.MONGODB_MOUNT_POINT)

    def change_passwords(self, context, users):
        LOG.debug("Changing password.")
        raise exception.DatastoreOperationNotSupported(
            operation='change_passwords', datastore=MANAGER)

    def update_attributes(self, context, username, hostname, user_attrs):
        LOG.debug("Updating database attributes.")
        raise exception.DatastoreOperationNotSupported(
            operation='update_attributes', datastore=MANAGER)

    def create_database(self, context, databases):
        LOG.debug("Creating database(s).")
        return service.MongoDBAdmin().create_database(databases)

    def create_user(self, context, users):
        LOG.debug("Creating user(s).")
        return service.MongoDBAdmin().create_users(users)

    def delete_database(self, context, database):
        LOG.debug("Deleting database.")
        return service.MongoDBAdmin().delete_database(database)

    def delete_user(self, context, user):
        LOG.debug("Deleting user.")
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
        LOG.debug("Enabling root with password.")
        raise exception.DatastoreOperationNotSupported(
            operation='enable_root_with_password', datastore=MANAGER)

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
        backup.backup(context, backup_info)

    def mount_volume(self, context, device_path=None, mount_point=None):
        LOG.debug("Mounting the device %s at the mount point %s." %
                  (device_path, mount_point))
        device = volume.VolumeDevice(device_path)
        device.mount(mount_point, write_to_fstab=False)

    def unmount_volume(self, context, device_path=None, mount_point=None):
        LOG.debug("Unmounting the device %s from the mount point %s." %
                  (device_path, mount_point))
        device = volume.VolumeDevice(device_path)
        device.unmount(mount_point)

    def resize_fs(self, context, device_path=None, mount_point=None):
        LOG.debug("Resizing the filesystem at %s." % mount_point)
        device = volume.VolumeDevice(device_path)
        device.resize_fs(mount_point)

    def update_overrides(self, context, overrides, remove=False):
        LOG.debug("Updating overrides.")
        if remove:
            self.app.remove_overrides()
        else:
            self.app.update_overrides(context, overrides, remove)

    def apply_overrides(self, context, overrides):
        LOG.debug("Overrides will be applied after restart.")
        pass

    def get_replication_snapshot(self, context, snapshot_info,
                                 replica_source_config=None):
        LOG.debug("Getting replication snapshot.")
        raise exception.DatastoreOperationNotSupported(
            operation='get_replication_snapshot', datastore=MANAGER)

    def attach_replication_slave(self, context, snapshot, slave_config):
        LOG.debug("Attaching replica.")
        raise exception.DatastoreOperationNotSupported(
            operation='attach_replication_slave', datastore=MANAGER)

    def detach_replica(self, context, for_failover=False):
        LOG.debug("Detaching replica.")
        raise exception.DatastoreOperationNotSupported(
            operation='detach_replica', datastore=MANAGER)

    def get_replica_context(self, context):
        raise exception.DatastoreOperationNotSupported(
            operation='get_replica_context', datastore=MANAGER)

    def make_read_only(self, context, read_only):
        raise exception.DatastoreOperationNotSupported(
            operation='make_read_only', datastore=MANAGER)

    def enable_as_master(self, context, replica_source_config):
        raise exception.DatastoreOperationNotSupported(
            operation='enable_as_master', datastore=MANAGER)

    def get_txn_count(self):
        raise exception.DatastoreOperationNotSupported(
            operation='get_txn_count', datastore=MANAGER)

    def get_latest_txn_id(self):
        raise exception.DatastoreOperationNotSupported(
            operation='get_latest_txn_id', datastore=MANAGER)

    def wait_for_txn(self, txn):
        raise exception.DatastoreOperationNotSupported(
            operation='wait_for_txn', datastore=MANAGER)

    def demote_replication_master(self, context):
        LOG.debug("Demoting replica source.")
        raise exception.DatastoreOperationNotSupported(
            operation='demote_replication_master', datastore=MANAGER)

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

    def cluster_complete(self, context):
        # Now that cluster creation is complete, start status checks
        LOG.debug("Cluster creation complete, starting status checks.")
        status = self.app.status._get_actual_db_status()
        self.app.status.set_status(status)

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
