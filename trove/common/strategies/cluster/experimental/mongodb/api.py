# Copyright 2014 eBay Software Foundation
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

from novaclient import exceptions as nova_exceptions

from trove.cluster import models
from trove.cluster.tasks import ClusterTasks
from trove.cluster.views import ClusterView
from trove.common import cfg
from trove.common import exception
from trove.common.i18n import _
from trove.common import remote
from trove.common.strategies.cluster import base
from trove.common import utils
from trove.common import wsgi
from trove.datastore import models as datastore_models
from trove.extensions.mgmt.clusters.views import MgmtClusterView
from trove.instance import models as inst_models
from trove.openstack.common import log as logging
from trove.quota.quota import check_quotas
from trove.taskmanager import api as task_api


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class MongoDbAPIStrategy(base.BaseAPIStrategy):

    @property
    def cluster_class(self):
        return MongoDbCluster

    @property
    def cluster_controller_actions(self):
        return {'add_shard': self._action_add_shard}

    def _action_add_shard(self, cluster, body):
        cluster.add_shard()
        return wsgi.Result(None, 202)

    @property
    def cluster_view_class(self):
        return MongoDbClusterView

    @property
    def mgmt_cluster_view_class(self):
        return MongoDbMgmtClusterView


class MongoDbCluster(models.Cluster):

    @classmethod
    def create(cls, context, name, datastore, datastore_version, instances):

        # TODO(amcreynolds): consider moving into CONF and even supporting
        # TODO(amcreynolds): an array of values, e.g. [3, 5, 7]
        # TODO(amcreynolds): or introduce a min/max num_instances and set
        # TODO(amcreynolds): both to 3
        num_instances = len(instances)
        if num_instances != 3:
            raise exception.ClusterNumInstancesNotSupported(num_instances=3)

        flavor_ids = [instance['flavor_id'] for instance in instances]
        if len(set(flavor_ids)) != 1:
            raise exception.ClusterFlavorsNotEqual()
        flavor_id = flavor_ids[0]
        nova_client = remote.create_nova_client(context)
        try:
            flavor = nova_client.flavors.get(flavor_id)
        except nova_exceptions.NotFound:
            raise exception.FlavorNotFound(uuid=flavor_id)
        mongo_conf = CONF.get(datastore_version.manager)
        num_configsvr = mongo_conf.num_config_servers_per_cluster
        num_mongos = mongo_conf.num_query_routers_per_cluster
        delta_instances = num_instances + num_configsvr + num_mongos
        deltas = {'instances': delta_instances}

        volume_sizes = [instance['volume_size'] for instance in instances
                        if instance.get('volume_size', None)]
        volume_size = None
        if mongo_conf.volume_support:
            if len(volume_sizes) != num_instances:
                raise exception.ClusterVolumeSizeRequired()
            if len(set(volume_sizes)) != 1:
                raise exception.ClusterVolumeSizesNotEqual()
            volume_size = volume_sizes[0]
            models.validate_volume_size(volume_size)
            # TODO(amcreynolds): for now, mongos+configsvr same flavor+disk
            deltas['volumes'] = volume_size * delta_instances
        else:
            # TODO(amcreynolds): is ephemeral possible for mongodb clusters?
            if len(volume_sizes) > 0:
                raise exception.VolumeNotSupported()
            ephemeral_support = mongo_conf.device_path
            if ephemeral_support and flavor.ephemeral == 0:
                raise exception.LocalStorageNotSpecified(flavor=flavor_id)

        check_quotas(context.tenant, deltas)

        nics = [instance.get('nics', None) for instance in instances]

        azs = [instance.get('availability_zone', None)
               for instance in instances]

        db_info = models.DBCluster.create(
            name=name, tenant_id=context.tenant,
            datastore_version_id=datastore_version.id,
            task_status=ClusterTasks.BUILDING_INITIAL)

        replica_set_name = "rs1"
        key = utils.generate_random_password()

        member_config = {"id": db_info.id,
                         "shard_id": utils.generate_uuid(),
                         "instance_type": "member",
                         "replica_set_name": replica_set_name,
                         "key": key}
        for i in range(0, num_instances):
            instance_name = "%s-%s-%s" % (name, replica_set_name, str(i + 1))
            inst_models.Instance.create(context, instance_name,
                                        flavor_id,
                                        datastore_version.image_id,
                                        [], [], datastore,
                                        datastore_version,
                                        volume_size, None,
                                        availability_zone=azs[i],
                                        nics=nics[i],
                                        configuration_id=None,
                                        cluster_config=member_config)

        configsvr_config = {"id": db_info.id,
                            "instance_type": "config_server",
                            "key": key}
        for i in range(1, num_configsvr + 1):
            instance_name = "%s-%s-%s" % (name, "configsvr", str(i))
            inst_models.Instance.create(context, instance_name,
                                        flavor_id,
                                        datastore_version.image_id,
                                        [], [], datastore,
                                        datastore_version,
                                        volume_size, None,
                                        availability_zone=None,
                                        nics=None,
                                        configuration_id=None,
                                        cluster_config=configsvr_config)

        mongos_config = {"id": db_info.id,
                         "instance_type": "query_router",
                         "key": key}
        for i in range(1, num_mongos + 1):
            instance_name = "%s-%s-%s" % (name, "mongos", str(i))
            inst_models.Instance.create(context, instance_name,
                                        flavor_id,
                                        datastore_version.image_id,
                                        [], [], datastore,
                                        datastore_version,
                                        volume_size, None,
                                        availability_zone=None,
                                        nics=None,
                                        configuration_id=None,
                                        cluster_config=mongos_config)

        task_api.load(context, datastore_version.manager).create_cluster(
            db_info.id)

        return MongoDbCluster(context, db_info, datastore, datastore_version)

    def add_shard(self):

        if self.db_info.task_status != ClusterTasks.NONE:
            current_task = self.db_info.task_status.name
            msg = _("This action cannot be performed on the cluster while "
                    "the current cluster task is '%s'.") % current_task
            LOG.error(msg)
            raise exception.UnprocessableEntity(msg)

        db_insts = inst_models.DBInstance.find_all(cluster_id=self.id,
                                                   type='member').all()
        num_unique_shards = len(set([db_inst.shard_id for db_inst
                                     in db_insts]))
        arbitrary_shard_id = db_insts[0].shard_id
        members_in_shard = [db_inst for db_inst in db_insts
                            if db_inst.shard_id == arbitrary_shard_id]
        num_members_per_shard = len(members_in_shard)
        a_member = inst_models.load_any_instance(self.context,
                                                 members_in_shard[0].id)
        deltas = {'instances': num_members_per_shard}
        volume_size = a_member.volume_size
        if volume_size:
            deltas['volumes'] = volume_size * num_members_per_shard
        check_quotas(self.context.tenant, deltas)
        new_replica_set_name = "rs" + str(num_unique_shards + 1)
        new_shard_id = utils.generate_uuid()
        dsv_manager = (datastore_models.DatastoreVersion.
                       load_by_uuid(db_insts[0].datastore_version_id).manager)
        manager = task_api.load(self.context, dsv_manager)
        key = manager.get_key(a_member)
        member_config = {"id": self.id,
                         "shard_id": new_shard_id,
                         "instance_type": "member",
                         "replica_set_name": new_replica_set_name,
                         "key": key}
        for i in range(1, num_members_per_shard + 1):
            instance_name = "%s-%s-%s" % (self.name, new_replica_set_name,
                                          str(i))
            inst_models.Instance.create(self.context, instance_name,
                                        a_member.flavor_id,
                                        a_member.datastore_version.image_id,
                                        [], [], a_member.datastore,
                                        a_member.datastore_version,
                                        volume_size, None,
                                        availability_zone=None,
                                        nics=None,
                                        configuration_id=None,
                                        cluster_config=member_config)

        self.update_db(task_status=ClusterTasks.ADDING_SHARD)
        manager.mongodb_add_shard_cluster(
            self.id,
            new_shard_id,
            new_replica_set_name)


class MongoDbClusterView(ClusterView):

    def build_instances(self):
        return self._build_instances(['query_router'], ['member'])


class MongoDbMgmtClusterView(MgmtClusterView):

    def build_instances(self):
        return self._build_instances(['query_router'],
                                     ['config_server',
                                      'member',
                                      'query_router'])
