# Copyright (c) 2013 Rackspace
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

from oslo_log import log as logging
from oslo_service import periodic_task

from trove.common import cfg
from trove.common import exception
from trove.common.i18n import _
from trove.common import instance as rd_instance
from trove.common import utils
from trove.guestagent import backup
from trove.guestagent.common import operating_system
from trove.guestagent.datastore.experimental.redis import service
from trove.guestagent import dbaas
from trove.guestagent.strategies.replication import get_replication_strategy
from trove.guestagent import volume


LOG = logging.getLogger(__name__)
CONF = cfg.CONF
MANAGER = CONF.datastore_manager or 'redis'
REPLICATION_STRATEGY = CONF.get(MANAGER).replication_strategy
REPLICATION_NAMESPACE = CONF.get(MANAGER).replication_namespace
REPLICATION_STRATEGY_CLASS = get_replication_strategy(REPLICATION_STRATEGY,
                                                      REPLICATION_NAMESPACE)


class Manager(periodic_task.PeriodicTasks):
    """
    This is the Redis manager class. It is dynamically loaded
    based off of the service_type of the trove instance
    """

    def __init__(self):
        super(Manager, self).__init__(CONF)
        self._app = service.RedisApp()

    @periodic_task.periodic_task
    def update_status(self, context):
        """
        Updates the redis trove instance. It is decorated with
        perodic task so it is automatically called every 3 ticks.
        """
        LOG.debug("Update status called.")
        self._app.status.update()

    def rpc_ping(self, context):
        LOG.debug("Responding to RPC ping.")
        return True

    def change_passwords(self, context, users):
        """
        Changes the redis instance password,
        it is currently not not implemented.
        """
        LOG.debug("Change passwords called.")
        raise exception.DatastoreOperationNotSupported(
            operation='change_passwords', datastore=MANAGER)

    def reset_configuration(self, context, configuration):
        """
        Resets to the default configuration,
        currently this does nothing.
        """
        LOG.debug("Reset configuration called.")
        self._app.reset_configuration(configuration)

    def _perform_restore(self, backup_info, context, restore_location, app):
        """Perform a restore on this instance."""
        LOG.info(_("Restoring database from backup %s.") % backup_info['id'])
        try:
            backup.restore(context, backup_info, restore_location)
        except Exception:
            LOG.exception(_("Error performing restore from backup %s.") %
                          backup_info['id'])
            app.status.set_status(rd_instance.ServiceStatuses.FAILED)
            raise
        LOG.info(_("Restored database successfully."))

    def prepare(self, context, packages, databases, memory_mb, users,
                device_path=None, mount_point=None, backup_info=None,
                config_contents=None, root_password=None, overrides=None,
                cluster_config=None, snapshot=None):
        """
        This is called when the trove instance first comes online.
        It is the first rpc message passed from the task manager.
        prepare handles all the base configuration of the redis instance.
        """
        try:
            self._app.status.begin_install()
            if device_path:
                device = volume.VolumeDevice(device_path)
                # unmount if device is already mounted
                device.unmount_device(device_path)
                device.format()
                device.mount(mount_point)
                operating_system.chown(mount_point, 'redis', 'redis',
                                       as_root=True)
                LOG.debug('Mounted the volume.')
            self._app.install_if_needed(packages)
            LOG.info(_('Writing redis configuration.'))
            if cluster_config:
                config_contents = (config_contents + "\n"
                                   + "cluster-enabled yes\n"
                                   + "cluster-config-file cluster.conf\n")
            self._app.configuration_manager.save_configuration(config_contents)
            self._app.apply_initial_guestagent_configuration()
            if backup_info:
                persistence_dir = self._app.get_working_dir()
                self._perform_restore(backup_info, context, persistence_dir,
                                      self._app)
            if snapshot:
                self.attach_replica(context, snapshot, snapshot['config'])
            self._app.restart()
            if cluster_config:
                self._app.status.set_status(
                    rd_instance.ServiceStatuses.BUILD_PENDING)
            else:
                self._app.complete_install_or_restart()
            LOG.info(_('Redis instance has been setup and configured.'))
        except Exception:
            LOG.exception(_("Error setting up Redis instance."))
            self._app.status.set_status(rd_instance.ServiceStatuses.FAILED)
            raise

    def restart(self, context):
        """
        Restart this redis instance.
        This method is called when the guest agent
        gets a restart message from the taskmanager.
        """
        LOG.debug("Restart called.")
        self._app.restart()

    def start_db_with_conf_changes(self, context, config_contents):
        """
        Start this redis instance with new conf changes.
        """
        LOG.debug("Start DB with conf changes called.")
        self._app.start_db_with_conf_changes(config_contents)

    def stop_db(self, context, do_not_start_on_reboot=False):
        """
        Stop this redis instance.
        This method is called when the guest agent
        gets a stop message from the taskmanager.
        """
        LOG.debug("Stop DB called.")
        self._app.stop_db(do_not_start_on_reboot=do_not_start_on_reboot)

    def get_filesystem_stats(self, context, fs_path):
        """Gets the filesystem stats for the path given."""
        LOG.debug("Get Filesystem Stats.")
        mount_point = CONF.get(
            'mysql' if not MANAGER else MANAGER).mount_point
        return dbaas.get_filesystem_volume_stats(mount_point)

    def create_backup(self, context, backup_info):
        """Create a backup of the database."""
        LOG.debug("Creating backup.")
        backup.backup(context, backup_info)

    def mount_volume(self, context, device_path=None, mount_point=None):
        device = volume.VolumeDevice(device_path)
        device.mount(mount_point, write_to_fstab=False)
        LOG.debug("Mounted the device %s at the mount point %s." %
                  (device_path, mount_point))

    def unmount_volume(self, context, device_path=None, mount_point=None):
        device = volume.VolumeDevice(device_path)
        device.unmount(mount_point)
        LOG.debug("Unmounted the device %s from the mount point %s." %
                  (device_path, mount_point))

    def resize_fs(self, context, device_path=None, mount_point=None):
        device = volume.VolumeDevice(device_path)
        device.resize_fs(mount_point)
        LOG.debug("Resized the filesystem at %s." % mount_point)

    def update_overrides(self, context, overrides, remove=False):
        LOG.debug("Updating overrides.")
        if remove:
            self._app.remove_overrides()
        else:
            self._app.update_overrides(context, overrides, remove)

    def apply_overrides(self, context, overrides):
        LOG.debug("Applying overrides.")
        self._app.apply_overrides(self._app.admin, overrides)

    def update_attributes(self, context, username, hostname, user_attrs):
        LOG.debug("Updating attributes.")
        raise exception.DatastoreOperationNotSupported(
            operation='update_attributes', datastore=MANAGER)

    def create_database(self, context, databases):
        LOG.debug("Creating database.")
        raise exception.DatastoreOperationNotSupported(
            operation='create_database', datastore=MANAGER)

    def create_user(self, context, users):
        LOG.debug("Creating user.")
        raise exception.DatastoreOperationNotSupported(
            operation='create_user', datastore=MANAGER)

    def delete_database(self, context, database):
        LOG.debug("Deleting database.")
        raise exception.DatastoreOperationNotSupported(
            operation='delete_database', datastore=MANAGER)

    def delete_user(self, context, user):
        LOG.debug("Deleting user.")
        raise exception.DatastoreOperationNotSupported(
            operation='delete_user', datastore=MANAGER)

    def get_user(self, context, username, hostname):
        LOG.debug("Getting user.")
        raise exception.DatastoreOperationNotSupported(
            operation='get_user', datastore=MANAGER)

    def grant_access(self, context, username, hostname, databases):
        LOG.debug("Granting access.")
        raise exception.DatastoreOperationNotSupported(
            operation='grant_access', datastore=MANAGER)

    def revoke_access(self, context, username, hostname, database):
        LOG.debug("Revoking access.")
        raise exception.DatastoreOperationNotSupported(
            operation='revoke_access', datastore=MANAGER)

    def list_access(self, context, username, hostname):
        LOG.debug("Listing access.")
        raise exception.DatastoreOperationNotSupported(
            operation='list_access', datastore=MANAGER)

    def list_databases(self, context, limit=None, marker=None,
                       include_marker=False):
        LOG.debug("Listing databases.")
        raise exception.DatastoreOperationNotSupported(
            operation='list_databases', datastore=MANAGER)

    def list_users(self, context, limit=None, marker=None,
                   include_marker=False):
        LOG.debug("Listing users.")
        raise exception.DatastoreOperationNotSupported(
            operation='list_users', datastore=MANAGER)

    def enable_root(self, context):
        LOG.debug("Enabling root.")
        raise exception.DatastoreOperationNotSupported(
            operation='enable_root', datastore=MANAGER)

    def is_root_enabled(self, context):
        LOG.debug("Checking if root is enabled.")
        raise exception.DatastoreOperationNotSupported(
            operation='is_root_enabled', datastore=MANAGER)

    def backup_required_for_replication(self, context):
        replication = REPLICATION_STRATEGY_CLASS(context)
        return replication.backup_required_for_replication()

    def get_replication_snapshot(self, context, snapshot_info,
                                 replica_source_config=None):
        LOG.debug("Getting replication snapshot.")
        replication = REPLICATION_STRATEGY_CLASS(context)
        replication.enable_as_master(self._app, replica_source_config)

        snapshot_id, log_position = (
            replication.snapshot_for_replication(context, self._app, None,
                                                 snapshot_info))

        mount_point = CONF.get(MANAGER).mount_point
        volume_stats = dbaas.get_filesystem_volume_stats(mount_point)

        replication_snapshot = {
            'dataset': {
                'datastore_manager': MANAGER,
                'dataset_size': volume_stats.get('used', 0.0),
                'volume_size': volume_stats.get('total', 0.0),
                'snapshot_id': snapshot_id
            },
            'replication_strategy': REPLICATION_STRATEGY,
            'master': replication.get_master_ref(self._app, snapshot_info),
            'log_position': log_position
        }

        return replication_snapshot

    def enable_as_master(self, context, replica_source_config):
        LOG.debug("Calling enable_as_master.")
        replication = REPLICATION_STRATEGY_CLASS(context)
        replication.enable_as_master(self._app, replica_source_config)

    def detach_replica(self, context, for_failover=False):
        LOG.debug("Detaching replica.")
        replication = REPLICATION_STRATEGY_CLASS(context)
        replica_info = replication.detach_slave(self._app, for_failover)
        return replica_info

    def get_replica_context(self, context):
        LOG.debug("Getting replica context.")
        replication = REPLICATION_STRATEGY_CLASS(context)
        replica_info = replication.get_replica_context(self._app)
        return replica_info

    def _validate_slave_for_replication(self, context, replica_info):
        if (replica_info['replication_strategy'] != REPLICATION_STRATEGY):
            raise exception.IncompatibleReplicationStrategy(
                replica_info.update({
                    'guest_strategy': REPLICATION_STRATEGY
                }))

    def attach_replica(self, context, replica_info, slave_config):
        LOG.debug("Attaching replica.")
        try:
            if 'replication_strategy' in replica_info:
                self._validate_slave_for_replication(context, replica_info)
            replication = REPLICATION_STRATEGY_CLASS(context)
            replication.enable_as_slave(self._app, replica_info,
                                        slave_config)
        except Exception:
            LOG.exception("Error enabling replication.")
            self._app.status.set_status(rd_instance.ServiceStatuses.FAILED)
            raise

    def make_read_only(self, context, read_only):
        LOG.debug("Executing make_read_only(%s)" % read_only)
        self._app.make_read_only(read_only)

    def _get_repl_info(self):
        return self._app.admin.get_info('replication')

    def _get_master_host(self):
        slave_info = self._get_repl_info()
        return slave_info and slave_info['master_host'] or None

    def _get_repl_offset(self):
        repl_info = self._get_repl_info()
        LOG.debug("Got repl info: %s" % repl_info)
        offset_key = '%s_repl_offset' % repl_info['role']
        offset = repl_info[offset_key]
        LOG.debug("Found offset %s for key %s." % (offset, offset_key))
        return int(offset)

    def get_last_txn(self, context):
        master_host = self._get_master_host()
        repl_offset = self._get_repl_offset()
        return master_host, repl_offset

    def get_latest_txn_id(self, context):
        LOG.info(_("Retrieving latest repl offset."))
        return self._get_repl_offset()

    def wait_for_txn(self, context, txn):
        LOG.info(_("Waiting on repl offset '%s'.") % txn)

        def _wait_for_txn():
            current_offset = self._get_repl_offset()
            LOG.debug("Current offset: %s." % current_offset)
            return current_offset >= txn

        try:
            utils.poll_until(_wait_for_txn, time_out=120)
        except exception.PollTimeOut:
            raise RuntimeError(_("Timeout occurred waiting for Redis repl "
                                 "offset to change to '%s'.") % txn)

    def cleanup_source_on_replica_detach(self, context, replica_info):
        LOG.debug("Cleaning up the source on the detach of a replica.")
        replication = REPLICATION_STRATEGY_CLASS(context)
        replication.cleanup_source_on_replica_detach(self._app, replica_info)

    def demote_replication_master(self, context):
        LOG.debug("Demoting replica source.")
        replication = REPLICATION_STRATEGY_CLASS(context)
        replication.demote_master(self._app)

    def cluster_meet(self, context, ip, port):
        LOG.debug("Executing cluster_meet to join node to cluster.")
        self._app.cluster_meet(ip, port)

    def get_node_ip(self, context):
        LOG.debug("Retrieving cluster node ip address.")
        return self._app.get_node_ip()

    def get_node_id_for_removal(self, context):
        LOG.debug("Validating removal of node from cluster.")
        return self._app.get_node_id_for_removal()

    def remove_nodes(self, context, node_ids):
        LOG.debug("Removing nodes from cluster.")
        self._app.remove_nodes(node_ids)

    def cluster_addslots(self, context, first_slot, last_slot):
        LOG.debug("Executing cluster_addslots to assign hash slots %s-%s.",
                  first_slot, last_slot)
        self._app.cluster_addslots(first_slot, last_slot)

    def cluster_complete(self, context):
        LOG.debug("Cluster creation complete, starting status checks.")
        self._app.complete_install_or_restart()
