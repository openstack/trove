# Copyright [2015] Hewlett-Packard Development Company, L.P.
# Copyright 2016 Tesora Inc.
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


from trove.cluster import models as cluster_models
from trove.cluster.tasks import ClusterTasks
from trove.cluster.views import ClusterView
from trove.common import cfg
from trove.common import exception
from trove.common import remote
from trove.common import server_group as srv_grp
from trove.common.strategies.cluster import base as cluster_base
from trove.extensions.mgmt.clusters.views import MgmtClusterView
from trove.instance.models import DBInstance
from trove.instance.models import Instance
from trove.quota.quota import check_quotas
from trove.taskmanager import api as task_api


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class GaleraCommonAPIStrategy(cluster_base.BaseAPIStrategy):

    @property
    def cluster_class(self):
        return GaleraCommonCluster

    @property
    def cluster_view_class(self):
        return GaleraCommonClusterView

    @property
    def mgmt_cluster_view_class(self):
        return GaleraCommonMgmtClusterView


class GaleraCommonCluster(cluster_models.Cluster):

    @staticmethod
    def _validate_cluster_instances(context, instances, datastore,
                                    datastore_version):
        """Validate the flavor and volume"""
        ds_conf = CONF.get(datastore_version.manager)
        num_instances = len(instances)

        # Check number of instances is at least min_cluster_member_count
        if num_instances < ds_conf.min_cluster_member_count:
            raise exception.ClusterNumInstancesNotLargeEnough(
                num_instances=ds_conf.min_cluster_member_count)

        # Checking flavors and get delta for quota check
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

        # Checking volumes and get delta for quota check
        volume_sizes = [instance['volume_size'] for instance in instances
                        if instance.get('volume_size', None)]
        volume_size = None
        if ds_conf.volume_support:
            if len(volume_sizes) != num_instances:
                raise exception.ClusterVolumeSizeRequired()
            if len(set(volume_sizes)) != 1:
                raise exception.ClusterVolumeSizesNotEqual()
            volume_size = volume_sizes[0]
            cluster_models.validate_volume_size(volume_size)
            deltas['volumes'] = volume_size * num_instances
        else:
            if len(volume_sizes) > 0:
                raise exception.VolumeNotSupported()
            ephemeral_support = ds_conf.device_path
            if ephemeral_support and flavor.ephemeral == 0:
                raise exception.LocalStorageNotSpecified(flavor=flavor_id)

        # quota check
        check_quotas(context.tenant, deltas)

        # Checking networks are same for the cluster
        instance_nics = []
        for instance in instances:
            nics = instance.get('nics')
            if nics:
                instance_nics.append(nics[0].get('net-id'))
        if len(set(instance_nics)) > 1:
            raise exception.ClusterNetworksNotEqual()
        if not instance_nics:
            return
        instance_nic = instance_nics[0]
        try:
            nova_client.networks.get(instance_nic)
        except nova_exceptions.NotFound:
            raise exception.NetworkNotFound(uuid=instance_nic)

    @staticmethod
    def _create_instances(context, db_info, datastore, datastore_version,
                          instances, extended_properties, locality):
        member_config = {"id": db_info.id,
                         "instance_type": "member"}
        name_index = 1
        for instance in instances:
            if not instance.get("name"):
                instance['name'] = "%s-member-%s" % (db_info.name,
                                                     str(name_index))
                name_index += 1

        return [Instance.create(context,
                                instance['name'],
                                instance['flavor_id'],
                                datastore_version.image_id,
                                [], [],
                                datastore, datastore_version,
                                instance.get('volume_size', None),
                                None,
                                availability_zone=instance.get(
                                    'availability_zone', None),
                                nics=instance.get('nics', None),
                                configuration_id=None,
                                cluster_config=member_config,
                                locality=locality
                                )
                for instance in instances]

    @classmethod
    def create(cls, context, name, datastore, datastore_version,
               instances, extended_properties, locality):
        LOG.debug("Initiating Galera cluster creation.")
        cls._validate_cluster_instances(context, instances, datastore,
                                        datastore_version)
        # Updating Cluster Task
        db_info = cluster_models.DBCluster.create(
            name=name, tenant_id=context.tenant,
            datastore_version_id=datastore_version.id,
            task_status=ClusterTasks.BUILDING_INITIAL)

        cls._create_instances(context, db_info, datastore, datastore_version,
                              instances, extended_properties, locality)

        # Calling taskmanager to further proceed for cluster-configuration
        task_api.load(context, datastore_version.manager).create_cluster(
            db_info.id)

        return cls(context, db_info, datastore, datastore_version)

    def _get_cluster_network_interfaces(self):
        nova_client = remote.create_nova_client(self.context)
        nova_instance_id = self.db_instances[0].compute_instance_id
        interfaces = nova_client.virtual_interfaces.list(nova_instance_id)
        ret = [{"net-id": getattr(interface, 'net_id')}
               for interface in interfaces]
        return ret

    def grow(self, instances):
        LOG.debug("Growing cluster %s." % self.id)

        self.validate_cluster_available()

        context = self.context
        db_info = self.db_info
        datastore = self.ds
        datastore_version = self.ds_version

        db_info.update(task_status=ClusterTasks.GROWING_CLUSTER)
        try:
            # Get the network of the existing cluster instances.
            interface_ids = self._get_cluster_network_interfaces()
            for instance in instances:
                instance["nics"] = interface_ids

            locality = srv_grp.ServerGroup.convert_to_hint(self.server_group)
            new_instances = self._create_instances(
                context, db_info, datastore, datastore_version, instances,
                None, locality)

            task_api.load(context, datastore_version.manager).grow_cluster(
                db_info.id, [instance.id for instance in new_instances])
        except Exception:
            db_info.update(task_status=ClusterTasks.NONE)

        return self.__class__(context, db_info,
                              datastore, datastore_version)

    def shrink(self, instances):
        """Removes instances from a cluster."""
        LOG.debug("Shrinking cluster %s." % self.id)

        self.validate_cluster_available()
        removal_instances = [Instance.load(self.context, inst_id)
                             for inst_id in instances]
        db_instances = DBInstance.find_all(cluster_id=self.db_info.id).all()
        if len(db_instances) - len(removal_instances) < 1:
            raise exception.ClusterShrinkMustNotLeaveClusterEmpty()

        self.db_info.update(task_status=ClusterTasks.SHRINKING_CLUSTER)
        try:
            task_api.load(self.context, self.ds_version.manager
                          ).shrink_cluster(self.db_info.id,
                                           [instance.id
                                            for instance in removal_instances])
        except Exception:
            self.db_info.update(task_status=ClusterTasks.NONE)

        return self.__class__(self.context, self.db_info,
                              self.ds, self.ds_version)


class GaleraCommonClusterView(ClusterView):

    def build_instances(self):
        return self._build_instances(['member'], ['member'])


class GaleraCommonMgmtClusterView(MgmtClusterView):

    def build_instances(self):
        return self._build_instances(['member'], ['member'])
