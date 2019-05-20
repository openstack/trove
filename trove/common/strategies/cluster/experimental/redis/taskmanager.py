# Copyright [2015] Hewlett-Packard Development Company, L.P.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from eventlet.timeout import Timeout
from oslo_log import log as logging

from trove.common import cfg
from trove.common.exception import TroveError
from trove.common.i18n import _
from trove.common.strategies.cluster import base
from trove.instance.models import DBInstance
from trove.instance.models import Instance
from trove.instance import tasks as inst_tasks
from trove.taskmanager import api as task_api
import trove.taskmanager.models as task_models


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class RedisTaskManagerStrategy(base.BaseTaskManagerStrategy):

    @property
    def task_manager_api_class(self):
        return RedisTaskManagerAPI

    @property
    def task_manager_cluster_tasks_class(self):
        return RedisClusterTasks


class RedisClusterTasks(task_models.ClusterTasks):

    def create_cluster(self, context, cluster_id):
        LOG.debug("Begin create_cluster for id: %s.", cluster_id)

        def _create_cluster():

            # Fetch instances by cluster_id against instances table.
            db_instances = DBInstance.find_all(cluster_id=cluster_id).all()
            instance_ids = [db_instance.id for db_instance in db_instances]

            # Wait for cluster members to get to cluster-ready status.
            if not self._all_instances_ready(instance_ids, cluster_id):
                return

            LOG.debug("All members ready, proceeding for cluster setup.")
            instances = [Instance.load(context, instance_id) for instance_id
                         in instance_ids]

            # Connect nodes to the first node
            guests = [self.get_guest(instance) for instance in instances]
            try:
                cluster_head = instances[0]
                cluster_head_port = '6379'
                cluster_head_ip = self.get_ip(cluster_head)
                for guest in guests[1:]:
                    guest.cluster_meet(cluster_head_ip, cluster_head_port)

                num_nodes = len(instances)
                total_slots = 16384
                slots_per_node = total_slots / num_nodes
                leftover_slots = total_slots % num_nodes
                first_slot = 0
                for guest in guests:
                    last_slot = first_slot + slots_per_node
                    if leftover_slots > 0:
                        leftover_slots -= 1
                    else:
                        last_slot -= 1
                    guest.cluster_addslots(first_slot, last_slot)
                    first_slot = last_slot + 1

                for guest in guests:
                    guest.cluster_complete()
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

    def grow_cluster(self, context, cluster_id, new_instance_ids):
        LOG.debug("Begin grow_cluster for id: %s.", cluster_id)

        def _grow_cluster():

            db_instances = DBInstance.find_all(cluster_id=cluster_id,
                                               deleted=False).all()
            cluster_head = next(Instance.load(context, db_inst.id)
                                for db_inst in db_instances
                                if db_inst.id not in new_instance_ids)
            if not cluster_head:
                raise TroveError(_("Unable to determine existing Redis cluster"
                                   " member"))

            (cluster_head_ip, cluster_head_port) = (
                self.get_guest(cluster_head).get_node_ip())

            # Wait for cluster members to get to cluster-ready status.
            if not self._all_instances_ready(new_instance_ids, cluster_id):
                return

            LOG.debug("All members ready, proceeding for cluster setup.")
            new_insts = [Instance.load(context, instance_id)
                         for instance_id in new_instance_ids]
            new_guests = map(self.get_guest, new_insts)

            # Connect nodes to the cluster head
            for guest in new_guests:
                guest.cluster_meet(cluster_head_ip, cluster_head_port)

            for guest in new_guests:
                guest.cluster_complete()

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
        except Exception:
            LOG.exception("Error growing cluster %s.", cluster_id)
            self.update_statuses_on_failure(
                cluster_id, status=inst_tasks.InstanceTasks.GROWING_ERROR)
        finally:
            timeout.cancel()

        LOG.debug("End grow_cluster for id: %s.", cluster_id)

    def upgrade_cluster(self, context, cluster_id, datastore_version):
        self.rolling_upgrade_cluster(context, cluster_id, datastore_version)


class RedisTaskManagerAPI(task_api.API):

    pass
