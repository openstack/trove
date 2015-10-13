# Copyright 2015 Tesora, Inc.
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
#

import abc

from oslo_log import log as logging
from oslo_service import periodic_task

from trove.common import cfg
from trove.common import exception
from trove.common.i18n import _
from trove.guestagent import dbaas
from trove.guestagent.strategies import replication as repl_strategy
from trove.guestagent import volume


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class Manager(periodic_task.PeriodicTasks):
    """This is the base class for all datastore managers.  Over time, common
    functionality should be pulled back here from the existing managers.
    """

    def __init__(self, manager_name):

        super(Manager, self).__init__(CONF)

        # Manager properties
        self.__manager_name = manager_name
        self.__manager = None
        self.__prepare_error = False

    @property
    def manager_name(self):
        """This returns the passed-in name of the manager."""
        return self.__manager_name

    @property
    def manager(self):
        """This returns the name of the manager."""
        if not self.__manager:
            self.__manager = CONF.datastore_manager or self.__manager_name
        return self.__manager

    @property
    def prepare_error(self):
        return self.__prepare_error

    @prepare_error.setter
    def prepare_error(self, prepare_error):
        self.__prepare_error = prepare_error

    @property
    def replication(self):
        """If the datastore supports replication, return an instance of
        the strategy.
        """
        try:
            return repl_strategy.get_instance(self.manager)
        except Exception as ex:
            LOG.debug("Cannot get replication instance for '%s': %s" % (
                      self.manager, ex.message))

        return None

    @property
    def replication_strategy(self):
        """If the datastore supports replication, return the strategy."""
        try:
            return repl_strategy.get_strategy(self.manager)
        except Exception as ex:
            LOG.debug("Cannot get replication strategy for '%s': %s" % (
                      self.manager, ex.message))

        return None

    @abc.abstractproperty
    def status(self):
        """This should return an instance of a status class that has been
        inherited from datastore.service.BaseDbStatus.  Each datastore
        must implement this property.
        """
        return None

    @property
    def configuration_manager(self):
        """If the datastore supports the new-style configuration manager,
        it should override this to return it.
        """
        return None

    ################
    # Status related
    ################
    @periodic_task.periodic_task
    def update_status(self, context):
        """Update the status of the trove instance. It is decorated with
        perodic_task so it is called automatically.
        """
        LOG.debug("Update status called.")
        self.status.update()

    def rpc_ping(self, context):
        LOG.debug("Responding to RPC ping.")
        return True

    #################
    # Prepare related
    #################
    def prepare(self, context, packages, databases, memory_mb, users,
                device_path=None, mount_point=None, backup_info=None,
                config_contents=None, root_password=None, overrides=None,
                cluster_config=None, snapshot=None):
        """Set up datastore on a Guest Instance."""
        LOG.info(_("Starting datastore prepare for '%s'.") % self.manager)
        self.status.begin_install()
        post_processing = True if cluster_config else False
        try:
            self.do_prepare(context, packages, databases, memory_mb,
                            users, device_path, mount_point, backup_info,
                            config_contents, root_password, overrides,
                            cluster_config, snapshot)
        except Exception as ex:
            self.prepare_error = True
            LOG.exception(_("An error occurred preparing datastore: %s") %
                          ex.message)
            raise
        finally:
            LOG.info(_("Ending datastore prepare for '%s'.") % self.manager)
            self.status.end_install(error_occurred=self.prepare_error,
                                    post_processing=post_processing)
        # At this point critical 'prepare' work is done and the instance
        # is now in the correct 'ACTIVE' 'INSTANCE_READY' or 'ERROR' state.
        # Of cource if an error has occurred, none of the code that follows
        # will run.
        LOG.info(_("Completed setup of '%s' datastore successfully.") %
                 self.manager)

        # We only create databases and users automatically for non-cluster
        # instances.
        if not cluster_config:
            try:
                if databases:
                    LOG.info(_("Creating databases (called from 'prepare')."))
                    self.create_database(context, databases)
                    LOG.info(_('Databases created successfully.'))
                if users:
                    LOG.info(_("Creating users (called from 'prepare')"))
                    self.create_user(context, users)
                    LOG.info(_('Users created successfully.'))
            except Exception as ex:
                LOG.exception(_("An error occurred creating databases/users: "
                                "%s") % ex.message)
                raise

        try:
            LOG.info(_("Calling post_prepare for '%s' datastore.") %
                     self.manager)
            self.post_prepare(context, packages, databases, memory_mb,
                              users, device_path, mount_point, backup_info,
                              config_contents, root_password, overrides,
                              cluster_config, snapshot)
            LOG.info(_("Post prepare for '%s' datastore completed.") %
                     self.manager)
        except Exception as ex:
            LOG.exception(_("An error occurred in post prepare: %s") %
                          ex.message)
            raise

    @abc.abstractmethod
    def do_prepare(self, context, packages, databases, memory_mb, users,
                   device_path, mount_point, backup_info, config_contents,
                   root_password, overrides, cluster_config, snapshot):
        """This is called from prepare when the Trove instance first comes
        online.  'Prepare' is the first rpc message passed from the
        task manager.  do_prepare handles all the base configuration of
        the instance and is where the actual work is done.  Once this method
        completes, the datastore is considered either 'ready' for use (or
        for final connections to other datastores) or in an 'error' state,
        and the status is changed accordingly.  Each datastore must
        implement this method.
        """
        pass

    def post_prepare(self, context, packages, databases, memory_mb, users,
                     device_path, mount_point, backup_info, config_contents,
                     root_password, overrides, cluster_config, snapshot):
        """This is called after prepare has completed successfully.
        Processing done here should be limited to things that will not
        affect the actual 'running' status of the datastore (for example,
        creating databases and users, although these are now handled
        automatically).  Any exceptions are caught, logged and rethrown,
        however no status changes are made and the end-user will not be
        informed of the error.
        """
        LOG.info(_('No post_prepare work has been defined.'))
        pass

    #####################
    # File System related
    #####################
    def get_filesystem_stats(self, context, fs_path):
        """Gets the filesystem stats for the path given."""
        # TODO(peterstac) - note that fs_path is not used in this method.
        mount_point = CONF.get(self.manager).mount_point
        LOG.debug("Getting file system stats for '%s'" % mount_point)
        return dbaas.get_filesystem_volume_stats(mount_point)

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

    ###############
    # Configuration
    ###############
    def reset_configuration(self, context, configuration):
        """The default implementation should be sufficient if a
        configuration_manager is provided. Even if one is not, this
        method needs to be implemented to allow the rollback of
        flavor-resize on the guestagent side.
        """
        LOG.debug("Resetting configuration.")
        if self.configuration_manager:
            config_contents = configuration['config_contents']
            self.configuration_manager.save_configuration(config_contents)

    #################
    # Cluster related
    #################
    def cluster_complete(self, context):
        LOG.debug("Cluster creation complete, starting status checks.")
        self.status.end_install()

    ###############
    # Not Supported
    ###############
    def change_passwords(self, context, users):
        LOG.debug("Changing passwords.")
        raise exception.DatastoreOperationNotSupported(
            operation='change_passwords', datastore=self.manager)

    def enable_root(self, context):
        LOG.debug("Enabling root.")
        raise exception.DatastoreOperationNotSupported(
            operation='enable_root', datastore=self.manager)

    def enable_root_with_password(self, context, root_password=None):
        LOG.debug("Enabling root with password.")
        raise exception.DatastoreOperationNotSupported(
            operation='enable_root_with_password', datastore=self.manager)

    def is_root_enabled(self, context):
        LOG.debug("Checking if root was ever enabled.")
        raise exception.DatastoreOperationNotSupported(
            operation='is_root_enabled', datastore=self.manager)

    def create_backup(self, context, backup_info):
        LOG.debug("Creating backup.")
        raise exception.DatastoreOperationNotSupported(
            operation='create_backup', datastore=self.manager)

    def _perform_restore(self, backup_info, context, restore_location, app):
        LOG.debug("Performing restore.")
        raise exception.DatastoreOperationNotSupported(
            operation='_perform_restore', datastore=self.manager)

    def create_database(self, context, databases):
        LOG.debug("Creating databases.")
        raise exception.DatastoreOperationNotSupported(
            operation='create_database', datastore=self.manager)

    def list_databases(self, context, limit=None, marker=None,
                       include_marker=False):
        LOG.debug("Listing databases.")
        raise exception.DatastoreOperationNotSupported(
            operation='list_databases', datastore=self.manager)

    def delete_database(self, context, database):
        LOG.debug("Deleting database.")
        raise exception.DatastoreOperationNotSupported(
            operation='delete_database', datastore=self.manager)

    def create_user(self, context, users):
        LOG.debug("Creating users.")
        raise exception.DatastoreOperationNotSupported(
            operation='create_user', datastore=self.manager)

    def list_users(self, context, limit=None, marker=None,
                   include_marker=False):
        LOG.debug("Listing users.")
        raise exception.DatastoreOperationNotSupported(
            operation='list_users', datastore=self.manager)

    def delete_user(self, context, user):
        LOG.debug("Deleting user.")
        raise exception.DatastoreOperationNotSupported(
            operation='delete_user', datastore=self.manager)

    def get_user(self, context, username, hostname):
        LOG.debug("Getting user.")
        raise exception.DatastoreOperationNotSupported(
            operation='get_user', datastore=self.manager)

    def update_attributes(self, context, username, hostname, user_attrs):
        LOG.debug("Updating user attributes.")
        raise exception.DatastoreOperationNotSupported(
            operation='update_attributes', datastore=self.manager)

    def grant_access(self, context, username, hostname, databases):
        LOG.debug("Granting user access.")
        raise exception.DatastoreOperationNotSupported(
            operation='grant_access', datastore=self.manager)

    def revoke_access(self, context, username, hostname, database):
        LOG.debug("Revoking user access.")
        raise exception.DatastoreOperationNotSupported(
            operation='revoke_access', datastore=self.manager)

    def list_access(self, context, username, hostname):
        LOG.debug("Listing user access.")
        raise exception.DatastoreOperationNotSupported(
            operation='list_access', datastore=self.manager)

    def get_config_changes(self, cluster_config, mount_point=None):
        LOG.debug("Get configuration changes.")
        raise exception.DatastoreOperationNotSupported(
            operation='get_configuration_changes', datastore=self.manager)

    def update_overrides(self, context, overrides, remove=False):
        LOG.debug("Updating overrides.")
        raise exception.DatastoreOperationNotSupported(
            operation='update_overrides', datastore=self.manager)

    def apply_overrides(self, context, overrides):
        LOG.debug("Applying overrides.")
        raise exception.DatastoreOperationNotSupported(
            operation='apply_overrides', datastore=self.manager)

    def get_replication_snapshot(self, context, snapshot_info,
                                 replica_source_config=None):
        LOG.debug("Getting replication snapshot.")
        raise exception.DatastoreOperationNotSupported(
            operation='get_replication_snapshot', datastore=self.manager)

    def attach_replication_slave(self, context, snapshot, slave_config):
        LOG.debug("Attaching replication slave.")
        raise exception.DatastoreOperationNotSupported(
            operation='attach_replication_slave', datastore=self.manager)

    def detach_replica(self, context, for_failover=False):
        LOG.debug("Detaching replica.")
        raise exception.DatastoreOperationNotSupported(
            operation='detach_replica', datastore=self.manager)

    def get_replica_context(self, context):
        LOG.debug("Getting replica context.")
        raise exception.DatastoreOperationNotSupported(
            operation='get_replica_context', datastore=self.manager)

    def make_read_only(self, context, read_only):
        LOG.debug("Making datastore read-only.")
        raise exception.DatastoreOperationNotSupported(
            operation='make_read_only', datastore=self.manager)

    def enable_as_master(self, context, replica_source_config):
        LOG.debug("Enabling as master.")
        raise exception.DatastoreOperationNotSupported(
            operation='enable_as_master', datastore=self.manager)

    def get_txn_count(self, context):
        LOG.debug("Getting transaction count.")
        raise exception.DatastoreOperationNotSupported(
            operation='get_txn_count', datastore=self.manager)

    def get_latest_txn_id(self, context):
        LOG.debug("Getting latest transaction id.")
        raise exception.DatastoreOperationNotSupported(
            operation='get_latest_txn_id', datastore=self.manager)

    def wait_for_txn(self, context, txn):
        LOG.debug("Waiting for transaction.")
        raise exception.DatastoreOperationNotSupported(
            operation='wait_for_txn', datastore=self.manager)

    def demote_replication_master(self, context):
        LOG.debug("Demoting replication master.")
        raise exception.DatastoreOperationNotSupported(
            operation='demote_replication_master', datastore=self.manager)
