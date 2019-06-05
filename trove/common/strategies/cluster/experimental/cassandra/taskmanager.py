# Copyright 2015 Tesora Inc.
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

from eventlet.timeout import Timeout
from oslo_log import log as logging

from trove.common import cfg
from trove.common.strategies.cluster import base
from trove.common import utils
from trove.instance.models import DBInstance
from trove.instance.models import Instance
from trove.instance import tasks as inst_tasks
from trove.taskmanager import api as task_api
import trove.taskmanager.models as task_models


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class CassandraTaskManagerStrategy(base.BaseTaskManagerStrategy):

    @property
    def task_manager_api_class(self):
        return CassandraTaskManagerAPI

    @property
    def task_manager_cluster_tasks_class(self):
        return CassandraClusterTasks


class CassandraClusterTasks(task_models.ClusterTasks):

    def create_cluster(self, context, cluster_id):
        LOG.debug("Begin create_cluster for id: %s.", cluster_id)

        def _create_cluster():
            cluster_node_ids = self.find_cluster_node_ids(cluster_id)

            # Wait for cluster nodes to get to cluster-ready status.
            LOG.debug("Waiting for all nodes to become ready.")
            if not self._all_instances_ready(cluster_node_ids, cluster_id):
                return

            cluster_nodes = self.load_cluster_nodes(context, cluster_node_ids)

            LOG.debug("All nodes ready, proceeding with cluster setup.")
            seeds = self.choose_seed_nodes(cluster_nodes)

            # Configure each cluster node with the list of seeds.
            # Once all nodes are configured, start the seed nodes one at a time
            # followed by the rest of the nodes.
            try:
                LOG.debug("Selected seed nodes: %s", seeds)

                for node in cluster_nodes:
                    LOG.debug("Configuring node: %s.", node['id'])
                    node['guest'].set_seeds(seeds)
                    node['guest'].set_auto_bootstrap(False)

                LOG.debug("Starting seed nodes.")
                for node in cluster_nodes:
                    if node['ip'] in seeds:
                        node['guest'].restart()
                        node['guest'].set_auto_bootstrap(True)

                LOG.debug("All seeds running, starting remaining nodes.")
                for node in cluster_nodes:
                    if node['ip'] not in seeds:
                        node['guest'].restart()
                        node['guest'].set_auto_bootstrap(True)

                # Create the in-database user via the first node. The remaining
                # nodes will replicate in-database changes automatically.
                # Only update the local authentication file on the other nodes.
                LOG.debug("Securing the cluster.")
                key = utils.generate_random_password()
                admin_creds = None
                for node in cluster_nodes:
                    if admin_creds is None:
                        admin_creds = node['guest'].cluster_secure(key)
                    else:
                        node['guest'].store_admin_credentials(admin_creds)
                    node['guest'].cluster_complete()

                LOG.debug("Cluster configuration finished successfully.")
            except Exception:
                LOG.exception("Error creating cluster.")
                self.update_statuses_on_failure(cluster_id)

        timeout = Timeout(CONF.cluster_usage_timeout)
        try:
            _create_cluster()
            self.reset_task()
        except Timeout as t:
            if t is not timeout:
                raise  # not my timeout
            LOG.exception("Timeout for building cluster.")
            self.update_statuses_on_failure(cluster_id)
        finally:
            timeout.cancel()

        LOG.debug("End create_cluster for id: %s.", cluster_id)

    @classmethod
    def find_cluster_node_ids(cls, cluster_id):
        db_instances = DBInstance.find_all(cluster_id=cluster_id,
                                           deleted=False).all()
        return [db_instance.id for db_instance in db_instances]

    @classmethod
    def load_cluster_nodes(cls, context, node_ids):
        return [cls.build_node_info(Instance.load(context, node_id))
                for node_id in node_ids]

    @classmethod
    def build_node_info(cls, instance):
        guest = cls.get_guest(instance)
        return {'instance': instance,
                'guest': guest,
                'id': instance.id,
                'ip': cls.get_ip(instance),
                'dc': guest.get_data_center(),
                'rack': guest.get_rack()}

    @classmethod
    def choose_seed_nodes(cls, node_info):
        """Select gossip seeds. The seeds are cluster nodes from which any
        new/other cluster nodes request information on the
        cluster geometry.
        They should include at least one node from each data center and
        rack. Gossip optimization is not critical, but it is recommended
        to use a small seed list.

        Select one (random) node from each dc and rack.

        :param node_info:        List of cluster nodes.
        :type node_info:         list of dicts
        """
        ips_by_affinity = cls._group_by_affinity(node_info)
        return {ips_by_affinity[dc][rack][0]
                for dc in ips_by_affinity
                for rack in ips_by_affinity[dc]}

    @classmethod
    def _group_by_affinity(cls, node_info):
        """Group node IPs by affinity to data center and rack."""
        ips_by_affinity = dict()
        for node in node_info:
            ip = node['ip']
            dc = node['dc']
            rack = node['rack']
            if dc in ips_by_affinity:
                dc_nodes = ips_by_affinity[dc]
                if rack in dc_nodes:
                    rack_nodes = dc_nodes[rack]
                    rack_nodes.append(ip)
                else:
                    dc_nodes.update({rack: [ip]})
            else:
                ips_by_affinity.update({dc: {rack: [ip]}})

        return ips_by_affinity

    def grow_cluster(self, context, cluster_id, new_instance_ids):
        LOG.debug("Begin grow_cluster for id: %s.", cluster_id)

        def _grow_cluster():
            # Wait for new nodes to get to cluster-ready status.
            LOG.debug("Waiting for new nodes to become ready.")
            if not self._all_instances_ready(new_instance_ids, cluster_id):
                return

            new_instances = [Instance.load(context, instance_id)
                             for instance_id in new_instance_ids]
            added_nodes = [self.build_node_info(instance)
                           for instance in new_instances]

            LOG.debug("All nodes ready, proceeding with cluster setup.")

            cluster_node_ids = self.find_cluster_node_ids(cluster_id)
            cluster_nodes = self.load_cluster_nodes(context, cluster_node_ids)

            old_nodes = [node for node in cluster_nodes
                         if node['id'] not in new_instance_ids]

            try:

                # All nodes should have the same seeds and credentials.
                # Retrieve the information from the first node.
                test_node = old_nodes[0]
                current_seeds = test_node['guest'].get_seeds()
                admin_creds = test_node['guest'].get_admin_credentials()

                # Bootstrap new nodes.
                # Seed nodes do not bootstrap. Current running nodes
                # must be used as seeds during the process.
                # Since we are adding to an existing cluster, ensure that the
                # new nodes have auto-bootstrapping enabled.
                # Start the added nodes.
                LOG.debug("Starting new nodes.")
                for node in added_nodes:
                    node['guest'].set_auto_bootstrap(True)
                    node['guest'].set_seeds(current_seeds)
                    node['guest'].store_admin_credentials(admin_creds)
                    node['guest'].restart()
                    node['guest'].cluster_complete()

                # Recompute the seed nodes based on the updated cluster
                # geometry.
                seeds = self.choose_seed_nodes(cluster_nodes)

                # Configure each cluster node with the updated list of seeds.
                LOG.debug("Updating all nodes with new seeds: %s", seeds)
                for node in cluster_nodes:
                    node['guest'].set_seeds(seeds)

                # Run nodetool cleanup on each of the previously existing nodes
                # to remove the keys that no longer belong to those nodes.
                # Wait for cleanup to complete on one node before running
                # it on the next node.
                LOG.debug("Cleaning up orphan data on old cluster nodes.")
                for node in old_nodes:
                    nid = node['id']
                    node['guest'].node_cleanup_begin()
                    node['guest'].node_cleanup()
                    LOG.debug("Waiting for node to finish its "
                              "cleanup: %s", nid)
                    if not self._all_instances_running([nid], cluster_id):
                        LOG.warning("Node did not complete cleanup "
                                    "successfully: %s", nid)

                LOG.debug("Cluster configuration finished successfully.")
            except Exception:
                LOG.exception("Error growing cluster.")
                self.update_statuses_on_failure(
                    cluster_id, status=inst_tasks.InstanceTasks.GROWING_ERROR)

        timeout = Timeout(CONF.cluster_usage_timeout)
        try:
            _grow_cluster()
            self.reset_task()
        except Timeout as t:
            if t is not timeout:
                raise  # not my timeout
            LOG.exception("Timeout for growing cluster.")
            self.update_statuses_on_failure(
                cluster_id, status=inst_tasks.InstanceTasks.GROWING_ERROR)
        finally:
            timeout.cancel()

        LOG.debug("End grow_cluster for id: %s.", cluster_id)

    def shrink_cluster(self, context, cluster_id, removal_ids):
        LOG.debug("Begin shrink_cluster for id: %s.", cluster_id)

        def _shrink_cluster():
            cluster_node_ids = self.find_cluster_node_ids(cluster_id)
            cluster_nodes = self.load_cluster_nodes(context, cluster_node_ids)

            removed_nodes = CassandraClusterTasks.load_cluster_nodes(
                context, removal_ids)

            LOG.debug("All nodes ready, proceeding with cluster setup.")

            # Update the list of seeds on remaining nodes if necessary.
            # Once all nodes are configured, decommission the removed nodes.
            # Cassandra will stream data from decommissioned nodes to the
            # remaining ones.
            try:

                current_seeds = self._get_current_seeds(context, cluster_id)
                # The seeds will have to be updated on all remaining instances
                # if any of the seed nodes is going to be removed.
                update_seeds = any(node['ip'] in current_seeds
                                   for node in removed_nodes)

                LOG.debug("Decommissioning removed nodes.")
                for node in removed_nodes:
                    node['guest'].node_decommission()
                    node['instance'].update_db(cluster_id=None)

                # Recompute the seed nodes based on the updated cluster
                # geometry if any of the existing seed nodes was removed.
                if update_seeds:
                    LOG.debug("Updating seeds on the remaining nodes.")
                    cluster_nodes = self.load_cluster_nodes(
                        context, cluster_node_ids)

                    remaining_nodes = [node for node in cluster_nodes
                                       if node['id'] not in removal_ids]
                    seeds = self.choose_seed_nodes(remaining_nodes)
                    LOG.debug("Selected seed nodes: %s", seeds)
                    for node in remaining_nodes:
                        LOG.debug("Configuring node: %s.", node['id'])
                        node['guest'].set_seeds(seeds)

                # Wait for the removed nodes to go SHUTDOWN.
                LOG.debug("Waiting for all decommissioned nodes to shutdown.")
                if not self._all_instances_shutdown(removal_ids, cluster_id):
                    # Now detached, failed nodes will stay available
                    # in the list of standalone instances.
                    return

                # Delete decommissioned instances only when the cluster is in a
                # consistent state.
                LOG.debug("Deleting decommissioned instances.")
                for node in removed_nodes:
                    Instance.delete(node['instance'])

                LOG.debug("Cluster configuration finished successfully.")
            except Exception:
                LOG.exception("Error shrinking cluster.")
                self.update_statuses_on_failure(
                    cluster_id,
                    status=inst_tasks.InstanceTasks.SHRINKING_ERROR)

        timeout = Timeout(CONF.cluster_usage_timeout)
        try:
            _shrink_cluster()
            self.reset_task()
        except Timeout as t:
            if t is not timeout:
                raise  # not my timeout
            LOG.exception("Timeout for shrinking cluster.")
            self.update_statuses_on_failure(
                cluster_id, status=inst_tasks.InstanceTasks.SHRINKING_ERROR)
        finally:
            timeout.cancel()

        LOG.debug("End shrink_cluster for id: %s.", cluster_id)

    def restart_cluster(self, context, cluster_id):
        self.rolling_restart_cluster(
            context, cluster_id, delay_sec=CONF.cassandra.node_sync_time)

    def upgrade_cluster(self, context, cluster_id, datastore_version):
        current_seeds = self._get_current_seeds(context, cluster_id)

        def ordering_function(instance):

            if self.get_ip(instance) in current_seeds:
                return -1
            return 0

        self.rolling_upgrade_cluster(context, cluster_id,
                                     datastore_version, ordering_function)

    def _get_current_seeds(self, context, cluster_id):
        # All nodes should have the same seeds.
        # We retrieve current seeds from the first node.
        cluster_node_ids = self.find_cluster_node_ids(cluster_id)
        test_node = self.load_cluster_nodes(context,
                                            cluster_node_ids[:1])[0]
        return test_node['guest'].get_seeds()


class CassandraTaskManagerAPI(task_api.API):
    pass
