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
from trove.cluster.tasks import ClusterTasks
from trove.cluster.views import ClusterView
from trove.common import cfg
from trove.common import exception
from trove.common import server_group as srv_grp
from trove.common.strategies.cluster import base
from trove.common import utils
from trove.extensions.mgmt.clusters.views import MgmtClusterView
from trove.instance import models as inst_models
from trove.quota.quota import check_quotas
from trove.taskmanager import api as task_api


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class VerticaAPIStrategy(base.BaseAPIStrategy):

    @property
    def cluster_class(self):
        return VerticaCluster

    def _action_grow(self, cluster, body):
        nodes = body['grow']
        instances = []
        for node in nodes:
            instance = {
                'flavor_id': utils.get_id_from_href(node['flavorRef'])
            }
            if 'name' in node:
                instance['name'] = node['name']
            if 'volume' in node:
                instance['volume_size'] = int(node['volume']['size'])
            instances.append(instance)
        return cluster.grow(instances)

    def _action_shrink(self, cluster, body):
        nodes = body['shrink']
        instance_ids = [node['id'] for node in nodes]
        return cluster.shrink(instance_ids)

    @property
    def cluster_view_class(self):
        return VerticaClusterView

    @property
    def mgmt_cluster_view_class(self):
        return VerticaMgmtClusterView


class VerticaCluster(models.Cluster):

    @staticmethod
    def _create_instances(context, db_info, datastore, datastore_version,
                          instances, extended_properties, locality,
                          new_cluster=True):
        vertica_conf = CONF.get(datastore_version.manager)
        num_instances = len(instances)

        existing = inst_models.DBInstance.find_all(cluster_id=db_info.id).all()
        num_existing = len(existing)

        # Matching number of instances with configured cluster_member_count
        if (new_cluster and
                num_instances != vertica_conf.cluster_member_count):
            raise exception.ClusterNumInstancesNotSupported(
                num_instances=vertica_conf.cluster_member_count)

        models.validate_instance_flavors(
            context, instances, vertica_conf.volume_support,
            vertica_conf.device_path)

        req_volume_size = models.get_required_volume_size(
            instances, vertica_conf.volume_support)
        models.assert_homogeneous_cluster(instances)

        deltas = {'instances': num_instances, 'volumes': req_volume_size}

        check_quotas(context.tenant, deltas)

        flavor_id = instances[0]['flavor_id']
        volume_size = instances[0].get('volume_size', None)

        nics = [instance.get('nics', None) for instance in instances]

        azs = [instance.get('availability_zone', None)
               for instance in instances]

        regions = [instance.get('region_name', None)
                   for instance in instances]

        # Creating member instances
        minstances = []
        for i in range(0, num_instances):
            if i == 0 and new_cluster:
                member_config = {"id": db_info.id, "instance_type": "master"}
            else:
                member_config = {"id": db_info.id, "instance_type": "member"}
            instance_name = "%s-member-%s" % (db_info.name,
                                              str(i + num_existing + 1))
            minstances.append(
                inst_models.Instance.create(
                    context, instance_name, flavor_id,
                    datastore_version.image_id, [], [], datastore,
                    datastore_version, volume_size, None,
                    nics=nics[i], availability_zone=azs[i],
                    configuration_id=None, cluster_config=member_config,
                    modules=instances[i].get('modules'), locality=locality,
                    region_name=regions[i])
            )
        return minstances

    @classmethod
    def create(cls, context, name, datastore, datastore_version,
               instances, extended_properties, locality):
        LOG.debug("Initiating cluster creation.")

        vertica_conf = CONF.get(datastore_version.manager)
        num_instances = len(instances)

        # Matching number of instances with configured cluster_member_count
        if num_instances != vertica_conf.cluster_member_count:
            raise exception.ClusterNumInstancesNotSupported(
                num_instances=vertica_conf.cluster_member_count)

        db_info = models.DBCluster.create(
            name=name, tenant_id=context.tenant,
            datastore_version_id=datastore_version.id,
            task_status=ClusterTasks.BUILDING_INITIAL)

        cls._create_instances(context, db_info, datastore, datastore_version,
                              instances, extended_properties, locality,
                              new_cluster=True)
        # Calling taskmanager to further proceed for cluster-configuration
        task_api.load(context, datastore_version.manager).create_cluster(
            db_info.id)

        return VerticaCluster(context, db_info, datastore, datastore_version)

    @staticmethod
    def k_safety(n):
        """
        Vertica defines k-safety values of 0, 1 or 2:
        https://my.vertica.com/docs/7.1.x/HTML/Content/Authoring/Glossary/
        K-Safety.htm
        """
        if n < 3:
            return 0
        elif n < 5:
            return 1
        else:
            return 2

    def grow(self, instances):
        LOG.debug("Growing cluster.")

        self.validate_cluster_available()

        context = self.context
        db_info = self.db_info
        datastore = self.ds
        datastore_version = self.ds_version

        db_info.update(task_status=ClusterTasks.GROWING_CLUSTER)

        locality = srv_grp.ServerGroup.convert_to_hint(self.server_group)
        new_instances = self._create_instances(context, db_info, datastore,
                                               datastore_version, instances,
                                               None, locality,
                                               new_cluster=False)

        task_api.load(context, datastore_version.manager).grow_cluster(
            db_info.id, [instance.id for instance in new_instances])

        return VerticaCluster(context, db_info, datastore, datastore_version)

    def shrink(self, instance_ids):
        self.validate_cluster_available()

        context = self.context
        db_info = self.db_info
        datastore_version = self.ds_version

        for db_instance in self.db_instances:
            if db_instance.type == 'master':
                if db_instance.id in instance_ids:
                    raise exception.ClusterShrinkInstanceInUse(
                        id=db_instance.id,
                        reason="Cannot remove master node."
                    )

        all_instance_ids = [db_instance.id for db_instance
                            in self.db_instances]

        left_instances = [instance_id for instance_id
                          in all_instance_ids
                          if instance_id not in instance_ids]

        k = self.k_safety(len(left_instances))

        vertica_conf = CONF.get(datastore_version.manager)
        if k < vertica_conf.min_ksafety:
            raise exception.ClusterNumInstancesBelowSafetyThreshold()

        db_info.update(task_status=ClusterTasks.SHRINKING_CLUSTER)

        task_api.load(context, datastore_version.manager).shrink_cluster(
            self.db_info.id, instance_ids)
        return VerticaCluster(self.context, db_info,
                              self.ds, self.ds_version)


class VerticaClusterView(ClusterView):

    def build_instances(self):
        return self._build_instances(['member', 'master'],
                                     ['member', 'master'])


class VerticaMgmtClusterView(MgmtClusterView):

    def build_instances(self):
        return self._build_instances(['member', 'master'],
                                     ['member', 'master'])
