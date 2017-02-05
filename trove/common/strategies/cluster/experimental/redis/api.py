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

from oslo_log import log as logging

from trove.cluster import models
from trove.cluster.models import Cluster
from trove.cluster.tasks import ClusterTasks
from trove.cluster.views import ClusterView
from trove.common import cfg
from trove.common import exception
from trove.common import server_group as srv_grp
from trove.common.strategies.cluster import base
from trove.extensions.mgmt.clusters.views import MgmtClusterView
from trove.instance import models as inst_models
from trove.quota.quota import check_quotas
from trove.taskmanager import api as task_api
LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class RedisAPIStrategy(base.BaseAPIStrategy):

    @property
    def cluster_class(self):
        return RedisCluster

    @property
    def cluster_view_class(self):
        return RedisClusterView

    @property
    def mgmt_cluster_view_class(self):
        return RedisMgmtClusterView


class RedisCluster(models.Cluster):

    @staticmethod
    def _create_instances(context, db_info, datastore, datastore_version,
                          instances, extended_properties, locality):
        redis_conf = CONF.get(datastore_version.manager)
        ephemeral_enabled = redis_conf.device_path
        volume_enabled = redis_conf.volume_support

        num_instances = len(instances)

        models.validate_instance_flavors(
            context, instances, volume_enabled, ephemeral_enabled)

        total_volume_allocation = models.get_required_volume_size(
            instances, volume_enabled)

        name_index = 1
        for instance in instances:
            if not instance.get('name'):
                instance['name'] = "%s-member-%s" % (db_info.name, name_index)
                name_index += 1

        # Check quotas
        quota_request = {'instances': num_instances,
                         'volumes': total_volume_allocation}
        check_quotas(context.tenant, quota_request)

        # Creating member instances
        return [inst_models.Instance.create(context,
                                            instance['name'],
                                            instance['flavor_id'],
                                            datastore_version.image_id,
                                            [], [],
                                            datastore, datastore_version,
                                            instance.get('volume_size'),
                                            None,
                                            instance.get(
                                                'availability_zone', None),
                                            instance.get('nics', None),
                                            configuration_id=None,
                                            cluster_config={
                                                "id": db_info.id,
                                                "instance_type": "member"},
                                            modules=instance.get('modules'),
                                            locality=locality,
                                            region_name=instance.get(
                                                'region_name')
                                            )
                for instance in instances]

    @classmethod
    def create(cls, context, name, datastore, datastore_version,
               instances, extended_properties, locality, configuration):
        LOG.debug("Initiating cluster creation.")

        if configuration:
            raise exception.ConfigurationNotSupported()

        # Updating Cluster Task

        db_info = models.DBCluster.create(
            name=name, tenant_id=context.tenant,
            datastore_version_id=datastore_version.id,
            task_status=ClusterTasks.BUILDING_INITIAL)

        cls._create_instances(context, db_info, datastore, datastore_version,
                              instances, extended_properties, locality)

        # Calling taskmanager to further proceed for cluster-configuration
        task_api.load(context, datastore_version.manager).create_cluster(
            db_info.id)

        return RedisCluster(context, db_info, datastore, datastore_version)

    def grow(self, instances):
        LOG.debug("Growing cluster.")

        self.validate_cluster_available()

        context = self.context
        db_info = self.db_info
        datastore = self.ds
        datastore_version = self.ds_version

        db_info.update(task_status=ClusterTasks.GROWING_CLUSTER)

        locality = srv_grp.ServerGroup.convert_to_hint(self.server_group)
        new_instances = self._create_instances(context, db_info,
                                               datastore, datastore_version,
                                               instances, None, locality)

        task_api.load(context, datastore_version.manager).grow_cluster(
            db_info.id, [instance.id for instance in new_instances])

        return RedisCluster(context, db_info, datastore, datastore_version)

    def shrink(self, removal_ids):
        LOG.debug("Shrinking cluster %s.", self.id)

        self.validate_cluster_available()

        cluster_info = self.db_info
        cluster_info.update(task_status=ClusterTasks.SHRINKING_CLUSTER)
        try:
            removal_insts = [inst_models.Instance.load(self.context, inst_id)
                             for inst_id in removal_ids]
            node_ids = []
            error_ids = []
            for instance in removal_insts:
                node_id = Cluster.get_guest(instance).get_node_id_for_removal()
                if node_id:
                    node_ids.append(node_id)
                else:
                    error_ids.append(instance.id)
            if error_ids:
                raise exception.ClusterShrinkInstanceInUse(
                    id=error_ids,
                    reason="Nodes cannot be removed. Check slots."
                )

            all_instances = (
                inst_models.DBInstance.find_all(cluster_id=self.id,
                                                deleted=False).all())
            remain_insts = [inst_models.Instance.load(self.context, inst.id)
                            for inst in all_instances
                            if inst.id not in removal_ids]

            for inst in remain_insts:
                guest = Cluster.get_guest(inst)
                guest.remove_nodes(node_ids)
            for inst in removal_insts:
                inst.update_db(cluster_id=None)
            for inst in removal_insts:
                inst_models.Instance.delete(inst)

            return RedisCluster(self.context, cluster_info,
                                self.ds, self.ds_version)
        finally:
            cluster_info.update(task_status=ClusterTasks.NONE)


class RedisClusterView(ClusterView):

    def build_instances(self):
        return self._build_instances(['member'], ['member'])


class RedisMgmtClusterView(MgmtClusterView):

    def build_instances(self):
        return self._build_instances(['member'], ['member'])
