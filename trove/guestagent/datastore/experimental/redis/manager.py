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

from trove.common import exception
from trove.common.i18n import _
from trove.common import instance as rd_instance
from trove.common.notification import EndNotification
from trove.common import utils
from trove.guestagent import backup
from trove.guestagent.common import operating_system
from trove.guestagent.datastore.experimental.redis import service
from trove.guestagent.datastore import manager
from trove.guestagent import volume


LOG = logging.getLogger(__name__)


class Manager(manager.Manager):
    """
    This is the Redis manager class. It is dynamically loaded
    based off of the service_type of the trove instance
    """

    def __init__(self):
        super(Manager, self).__init__('redis')
        self._app = service.RedisApp()

    @property
    def status(self):
        return self._app.status

    @property
    def configuration_manager(self):
        return self._app.configuration_manager

    def _perform_restore(self, backup_info, context, restore_location, app):
        """Perform a restore on this instance."""
        LOG.info(_("Restoring database from backup %s."), backup_info['id'])
        try:
            backup.restore(context, backup_info, restore_location)
        except Exception:
            LOG.exception(_("Error performing restore from backup %s."),
                          backup_info['id'])
            app.status.set_status(rd_instance.ServiceStatuses.FAILED)
            raise
        LOG.info(_("Restored database successfully."))

    def do_prepare(self, context, packages, databases, memory_mb, users,
                   device_path, mount_point, backup_info,
                   config_contents, root_password, overrides,
                   cluster_config, snapshot):
        """This is called from prepare in the base class."""
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
        else:
            # If we're not restoring, we have to force a restart of the
            # server manually so that the configuration stuff takes effect
            self._app.restart()
        if snapshot:
            self.attach_replica(context, snapshot, snapshot['config'])

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

    def create_backup(self, context, backup_info):
        """Create a backup of the database."""
        LOG.debug("Creating backup.")
        with EndNotification(context):
            backup.backup(context, backup_info)

    def update_overrides(self, context, overrides, remove=False):
        LOG.debug("Updating overrides.")
        if remove:
            self._app.remove_overrides()
        else:
            self._app.update_overrides(context, overrides, remove)

    def apply_overrides(self, context, overrides):
        LOG.debug("Applying overrides.")
        self._app.apply_overrides(self._app.admin, overrides)

    def backup_required_for_replication(self, context):
        return self.replication.backup_required_for_replication()

    def get_replication_snapshot(self, context, snapshot_info,
                                 replica_source_config=None):
        LOG.debug("Getting replication snapshot.")
        self.replication.enable_as_master(self._app, replica_source_config)

        snapshot_id, log_position = self.replication.snapshot_for_replication(
            context, self._app, None, snapshot_info)

        volume_stats = self.get_filesystem_stats(context, None)

        replication_snapshot = {
            'dataset': {
                'datastore_manager': self.manager,
                'dataset_size': volume_stats.get('used', 0.0),
                'volume_size': volume_stats.get('total', 0.0),
                'snapshot_id': snapshot_id
            },
            'replication_strategy': self.replication_strategy,
            'master': self.replication.get_master_ref(self._app,
                                                      snapshot_info),
            'log_position': log_position
        }

        return replication_snapshot

    def enable_as_master(self, context, replica_source_config):
        LOG.debug("Calling enable_as_master.")
        self.replication.enable_as_master(self._app, replica_source_config)

    def detach_replica(self, context, for_failover=False):
        LOG.debug("Detaching replica.")
        replica_info = self.replication.detach_slave(self._app, for_failover)
        return replica_info

    def get_replica_context(self, context):
        LOG.debug("Getting replica context.")
        replica_info = self.replication.get_replica_context(self._app)
        return replica_info

    def _validate_slave_for_replication(self, context, replica_info):
        if replica_info['replication_strategy'] != self.replication_strategy:
            raise exception.IncompatibleReplicationStrategy(
                replica_info.update({
                    'guest_strategy': self.replication_strategy
                }))

    def attach_replica(self, context, replica_info, slave_config):
        LOG.debug("Attaching replica.")
        try:
            if 'replication_strategy' in replica_info:
                self._validate_slave_for_replication(context, replica_info)
            self.replication.enable_as_slave(self._app, replica_info,
                                             slave_config)
        except Exception:
            LOG.exception(_("Error enabling replication."))
            raise

    def make_read_only(self, context, read_only):
        LOG.debug("Executing make_read_only(%s)", read_only)
        self._app.make_read_only(read_only)

    def _get_repl_info(self):
        return self._app.admin.get_info('replication')

    def _get_master_host(self):
        slave_info = self._get_repl_info()
        return slave_info and slave_info['master_host'] or None

    def _get_repl_offset(self):
        repl_info = self._get_repl_info()
        LOG.debug("Got repl info: %s", repl_info)
        offset_key = '%s_repl_offset' % repl_info['role']
        offset = repl_info[offset_key]
        LOG.debug("Found offset %(offset)s for key %(key)s.",
                  {'offset': offset, 'key': offset_key})
        return int(offset)

    def get_last_txn(self, context):
        master_host = self._get_master_host()
        repl_offset = self._get_repl_offset()
        return master_host, repl_offset

    def get_latest_txn_id(self, context):
        LOG.info(_("Retrieving latest repl offset."))
        return self._get_repl_offset()

    def wait_for_txn(self, context, txn):
        LOG.info(_("Waiting on repl offset '%s'."), txn)

        def _wait_for_txn():
            current_offset = self._get_repl_offset()
            LOG.debug("Current offset: %s.", current_offset)
            return current_offset >= txn

        try:
            utils.poll_until(_wait_for_txn, time_out=120)
        except exception.PollTimeOut:
            raise RuntimeError(_("Timeout occurred waiting for Redis repl "
                                 "offset to change to '%s'.") % txn)

    def cleanup_source_on_replica_detach(self, context, replica_info):
        LOG.debug("Cleaning up the source on the detach of a replica.")
        self.replication.cleanup_source_on_replica_detach(self._app,
                                                          replica_info)

    def demote_replication_master(self, context):
        LOG.debug("Demoting replica source.")
        self.replication.demote_master(self._app)

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
