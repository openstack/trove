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

from oslo_log import log as logging

from trove.cluster import models
from trove.cluster.tasks import ClusterTasks
from trove.cluster.views import ClusterView
from trove.common import cfg
from trove.common import server_group as srv_grp
from trove.common.strategies.cluster import base
from trove.common.strategies.cluster.experimental.cassandra import taskmanager
from trove.common import utils
from trove.extensions.mgmt.clusters.views import MgmtClusterView
from trove.instance import models as inst_models
from trove.quota.quota import check_quotas
from trove.taskmanager import api as task_api


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class CassandraAPIStrategy(base.BaseAPIStrategy):

    @property
    def cluster_class(self):
        return CassandraCluster

    @property
    def cluster_controller_actions(self):
        return {
            'grow': self._action_grow_cluster,
            'shrink': self._action_shrink_cluster
        }

    def _action_grow_cluster(self, cluster, body):
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

    def _action_shrink_cluster(self, cluster, body):
        nodes = body['shrink']
        instance_ids = [node['id'] for node in nodes]
        return cluster.shrink(instance_ids)

    @property
    def cluster_view_class(self):
        return CassandraClusterView

    @property
    def mgmt_cluster_view_class(self):
        return CassandraMgmtClusterView


class CassandraCluster(models.Cluster):

    DEFAULT_DATA_CENTER = "dc1"
    DEFAULT_RACK = "rack1"

    @classmethod
    def create(cls, context, name, datastore, datastore_version,
               instances, extended_properties, locality, configuration,
               image_id=None):
        LOG.debug("Processing a request for creating a new cluster.")

        # Updating Cluster Task.
        db_info = models.DBCluster.create(
            name=name, tenant_id=context.project_id,
            datastore_version_id=datastore_version.id,
            task_status=ClusterTasks.BUILDING_INITIAL,
            configuration_id=configuration)

        cls._create_cluster_instances(
            context, db_info.id, db_info.name,
            datastore, datastore_version, instances, extended_properties,
            locality, configuration)

        # Calling taskmanager to further proceed for cluster-configuration.
        task_api.load(context, datastore_version.manager).create_cluster(
            db_info.id)

        return CassandraCluster(context, db_info, datastore, datastore_version)

    @classmethod
    def _create_cluster_instances(
            cls, context, cluster_id, cluster_name,
            datastore, datastore_version, instances, extended_properties,
            locality, configuration_id):
        LOG.debug("Processing a request for new cluster instances.")

        cassandra_conf = CONF.get(datastore_version.manager)
        eph_enabled = cassandra_conf.device_path
        vol_enabled = cassandra_conf.volume_support

        # Validate instance flavors.
        models.validate_instance_flavors(context, instances,
                                         vol_enabled, eph_enabled)

        # Compute the total volume allocation.
        req_volume_size = models.get_required_volume_size(instances,
                                                          vol_enabled)

        # Check requirements against quota.
        num_new_instances = len(instances)
        deltas = {'instances': num_new_instances, 'volumes': req_volume_size}
        models.assert_homogeneous_cluster(instances)
        check_quotas(context.project_id, deltas)

        # Checking networks are same for the cluster
        models.validate_instance_nics(context, instances)

        # Creating member instances.
        num_instances = len(
            taskmanager.CassandraClusterTasks.find_cluster_node_ids(cluster_id)
        )
        new_instances = []
        for instance_idx, instance in enumerate(instances, num_instances + 1):
            instance_az = instance.get('availability_zone', None)

            member_config = {"id": cluster_id,
                             "instance_type": "member",
                             "dc": cls.DEFAULT_DATA_CENTER,
                             "rack": instance_az or cls.DEFAULT_RACK}

            instance_name = instance.get('name')
            if not instance_name:
                instance_name = cls._build_instance_name(
                    cluster_name, member_config['dc'], member_config['rack'],
                    instance_idx)

            new_instance = inst_models.Instance.create(
                context, instance_name,
                instance['flavor_id'],
                datastore_version.image_id,
                [], [],
                datastore, datastore_version,
                instance['volume_size'], None,
                nics=instance.get('nics', None),
                availability_zone=instance_az,
                configuration_id=configuration_id,
                cluster_config=member_config,
                volume_type=instance.get('volume_type', None),
                modules=instance.get('modules'),
                locality=locality,
                region_name=instance.get('region_name'))

            new_instances.append(new_instance)

        return new_instances

    @classmethod
    def _build_instance_name(cls, cluster_name, dc, rack, instance_idx):
        return "%s-member-%s-%s-%d" % (cluster_name, dc, rack, instance_idx)

    def grow(self, instances):
        LOG.debug("Processing a request for growing cluster: %s", self.id)

        self.validate_cluster_available()

        context = self.context
        db_info = self.db_info
        datastore = self.ds
        datastore_version = self.ds_version

        db_info.update(task_status=ClusterTasks.GROWING_CLUSTER)

        locality = srv_grp.ServerGroup.convert_to_hint(self.server_group)
        configuration_id = self.db_info.configuration_id

        new_instances = self._create_cluster_instances(
            context, db_info.id, db_info.name, datastore, datastore_version,
            instances, None, locality, configuration_id)

        task_api.load(context, datastore_version.manager).grow_cluster(
            db_info.id, [instance.id for instance in new_instances])

        return CassandraCluster(context, db_info, datastore, datastore_version)

    def shrink(self, removal_ids):
        LOG.debug("Processing a request for shrinking cluster: %s", self.id)

        self.validate_cluster_available()

        context = self.context
        db_info = self.db_info
        datastore = self.ds
        datastore_version = self.ds_version

        db_info.update(task_status=ClusterTasks.SHRINKING_CLUSTER)

        task_api.load(context, datastore_version.manager).shrink_cluster(
            db_info.id, removal_ids)

        return CassandraCluster(context, db_info, datastore, datastore_version)

    def restart(self):
        self.rolling_restart()

    def upgrade(self, datastore_version):
        self.rolling_upgrade(datastore_version)

    def configuration_attach(self, configuration_id):
        self.rolling_configuration_update(configuration_id, apply_on_all=False)

    def configuration_detach(self):
        self.rolling_configuration_remove(apply_on_all=False)


class CassandraClusterView(ClusterView):

    def build_instances(self):
        return self._build_instances(['member'], ['member'])


class CassandraMgmtClusterView(MgmtClusterView):

    def build_instances(self):
        return self._build_instances(['member'], ['member'])
