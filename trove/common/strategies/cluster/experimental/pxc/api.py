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

from novaclient import exceptions as nova_exceptions
from oslo_log import log as logging


from trove.cluster import models
from trove.cluster.tasks import ClusterTasks
from trove.cluster.views import ClusterView
from trove.common import cfg
from trove.common import exception
from trove.common import remote
from trove.common.strategies.cluster import base
from trove.extensions.mgmt.clusters.views import MgmtClusterView
from trove.instance import models as inst_models
from trove.quota.quota import check_quotas
from trove.taskmanager import api as task_api


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class PXCAPIStrategy(base.BaseAPIStrategy):

    @property
    def cluster_class(self):
        return PXCCluster

    @property
    def cluster_controller_actions(self):
        return {}

    @property
    def cluster_view_class(self):
        return PXCClusterView

    @property
    def mgmt_cluster_view_class(self):
        return PXCMgmtClusterView


class PXCCluster(models.Cluster):

    @classmethod
    def create(cls, context, name, datastore, datastore_version, instances):
        LOG.debug("Initiating PXC cluster creation.")
        pxc_conf = CONF.get(datastore_version.manager)
        num_instances = len(instances)

        # Matching number of instances with configured cluster_member_count
        if num_instances != pxc_conf.cluster_member_count:
            raise exception.ClusterNumInstancesNotSupported(
                num_instances=pxc_conf.cluster_member_count)

        # Checking flavors
        flavor_ids = [instance['flavor_id'] for instance in instances]
        if len(set(flavor_ids)) != 1:
            raise exception.ClusterFlavorsNotEqual()
        flavor_id = flavor_ids[0]
        nova_client = remote.create_nova_client(context)
        try:
            flavor = nova_client.flavors.get(flavor_id)
        except nova_exceptions.NotFound:
            raise exception.FlavorNotFound(uuid=flavor_id)
        deltas = {'instances': num_instances}

        # Checking volumes
        volume_sizes = [instance['volume_size'] for instance in instances
                        if instance.get('volume_size', None)]
        volume_size = None
        if pxc_conf.volume_support:
            if len(volume_sizes) != num_instances:
                raise exception.ClusterVolumeSizeRequired()
            if len(set(volume_sizes)) != 1:
                raise exception.ClusterVolumeSizesNotEqual()
            volume_size = volume_sizes[0]
            models.validate_volume_size(volume_size)
            deltas['volumes'] = volume_size * num_instances
        else:
            if len(volume_sizes) > 0:
                raise exception.VolumeNotSupported()
            ephemeral_support = pxc_conf.device_path
            if ephemeral_support and flavor.ephemeral == 0:
                raise exception.LocalStorageNotSpecified(flavor=flavor_id)

        check_quotas(context.tenant, deltas)

        nics = [instance.get('nics', None) for instance in instances]

        azs = [instance.get('availability_zone', None)
               for instance in instances]

        # Updating Cluster Task
        db_info = models.DBCluster.create(
            name=name, tenant_id=context.tenant,
            datastore_version_id=datastore_version.id,
            task_status=ClusterTasks.BUILDING_INITIAL)

        member_config = {"id": db_info.id,
                         "instance_type": "member"}

        # Creating member instances
        for i in range(0, num_instances):
            instance_name = "%s-member-%s" % (name, str(i + 1))
            inst_models.Instance.create(context, instance_name,
                                        flavor_id,
                                        datastore_version.image_id,
                                        [], [], datastore,
                                        datastore_version,
                                        volume_size, None,
                                        nics=nics[i],
                                        availability_zone=azs[i],
                                        configuration_id=None,
                                        cluster_config=member_config)

        # Calling taskmanager to further proceed for cluster-configuration
        task_api.load(context, datastore_version.manager).create_cluster(
            db_info.id)

        return PXCCluster(context, db_info, datastore, datastore_version)


class PXCClusterView(ClusterView):

    def build_instances(self):
        return self._build_instances(['member'], ['member'])


class PXCMgmtClusterView(MgmtClusterView):

    def build_instances(self):
        return self._build_instances(['member'], ['member'])
