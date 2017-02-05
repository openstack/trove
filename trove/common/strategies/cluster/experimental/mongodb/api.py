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
from oslo_log import log as logging

from trove.cluster import models
from trove.cluster.tasks import ClusterTasks
from trove.cluster.views import ClusterView
from trove.common import cfg
from trove.common import exception
from trove.common.i18n import _
from trove.common.notification import DBaaSClusterGrow
from trove.common.notification import StartNotification
from trove.common import remote
from trove.common import server_group as srv_grp
from trove.common.strategies.cluster import base
from trove.common import utils
from trove.datastore import models as datastore_models
from trove.extensions.mgmt.clusters.views import MgmtClusterView
from trove.instance import models as inst_models
from trove.quota.quota import check_quotas
from trove.taskmanager import api as task_api


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class MongoDbAPIStrategy(base.BaseAPIStrategy):

    @property
    def cluster_class(self):
        return MongoDbCluster

    @property
    def cluster_view_class(self):
        return MongoDbClusterView

    @property
    def mgmt_cluster_view_class(self):
        return MongoDbMgmtClusterView


class MongoDbCluster(models.Cluster):

    @classmethod
    def create(cls, context, name, datastore, datastore_version,
               instances, extended_properties, locality, configuration):

        if configuration:
            raise exception.ConfigurationNotSupported()

        # TODO(amcreynolds): consider moving into CONF and even supporting
        # TODO(amcreynolds): an array of values, e.g. [3, 5, 7]
        # TODO(amcreynolds): or introduce a min/max num_instances and set
        # TODO(amcreynolds): both to 3
        num_instances = len(instances)
        if num_instances != 3:
            raise exception.ClusterNumInstancesNotSupported(num_instances=3)

        mongo_conf = CONF.get(datastore_version.manager)
        num_configsvr = mongo_conf.num_config_servers_per_cluster
        num_mongos = mongo_conf.num_query_routers_per_cluster
        delta_instances = num_instances + num_configsvr + num_mongos

        models.validate_instance_flavors(
            context, instances, mongo_conf.volume_support,
            mongo_conf.device_path)
        models.assert_homogeneous_cluster(instances)

        req_volume_size = models.get_required_volume_size(
            instances, mongo_conf.volume_support)

        deltas = {'instances': delta_instances, 'volumes': req_volume_size}

        check_quotas(context.tenant, deltas)

        flavor_id = instances[0]['flavor_id']
        volume_size = instances[0].get('volume_size', None)

        nics = [instance.get('nics', None) for instance in instances]

        azs = [instance.get('availability_zone', None)
               for instance in instances]

        regions = [instance.get('region_name', None)
                   for instance in instances]

        db_info = models.DBCluster.create(
            name=name, tenant_id=context.tenant,
            datastore_version_id=datastore_version.id,
            task_status=ClusterTasks.BUILDING_INITIAL)

        replica_set_name = "rs1"

        member_config = {"id": db_info.id,
                         "shard_id": utils.generate_uuid(),
                         "instance_type": "member",
                         "replica_set_name": replica_set_name}

        configsvr_config = {"id": db_info.id,
                            "instance_type": "config_server"}

        mongos_config = {"id": db_info.id,
                         "instance_type": "query_router"}

        if mongo_conf.cluster_secure:
            cluster_key = utils.generate_random_password()
            member_config['key'] = cluster_key
            configsvr_config['key'] = cluster_key
            mongos_config['key'] = cluster_key

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
                                        cluster_config=member_config,
                                        modules=instances[i].get('modules'),
                                        locality=locality,
                                        region_name=regions[i])

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
                                        cluster_config=configsvr_config,
                                        locality=locality,
                                        region_name=regions[i])

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
                                        cluster_config=mongos_config,
                                        locality=locality,
                                        region_name=regions[i])

        task_api.load(context, datastore_version.manager).create_cluster(
            db_info.id)

        return MongoDbCluster(context, db_info, datastore, datastore_version)

    def _parse_grow_item(self, item):
        used_keys = []

        def _check_option(key, required=False, valid_values=None):
            if required and key not in item:
                raise exception.TroveError(
                    _('An instance with the options %(given)s is missing '
                      'the MongoDB required option %(expected)s.')
                    % {'given': item.keys(), 'expected': key}
                )
            value = item.get(key, None)
            if valid_values and value not in valid_values:
                raise exception.TroveError(
                    _('The value %(value)s for key %(key)s is invalid. '
                      'Allowed values are %(valid)s.')
                    % {'value': value, 'key': key, 'valid': valid_values}
                )
            used_keys.append(key)
            return value

        flavor_id = utils.get_id_from_href(_check_option('flavorRef',
                                                         required=True))
        volume_size = int(_check_option('volume', required=True)['size'])
        instance_type = _check_option('type', required=True,
                                      valid_values=['replica',
                                                    'query_router'])
        name = _check_option('name')
        related_to = _check_option('related_to')
        nics = _check_option('nics')
        availability_zone = _check_option('availability_zone')

        unused_keys = list(set(item.keys()).difference(set(used_keys)))
        if unused_keys:
            raise exception.TroveError(
                _('The arguments %s are not supported by MongoDB.')
                % unused_keys
            )

        instance = {'flavor_id': flavor_id,
                    'volume_size': volume_size,
                    'instance_type': instance_type}
        if name:
            instance['name'] = name
        if related_to:
            instance['related_to'] = related_to
        if nics:
            instance['nics'] = nics
        if availability_zone:
            instance['availability_zone'] = availability_zone
        return instance

    def action(self, context, req, action, param):
        if action == 'grow':
            context.notification = DBaaSClusterGrow(context, request=req)
            with StartNotification(context, cluster_id=self.id):
                return self.grow([self._parse_grow_item(item)
                                  for item in param])
        elif action == 'add_shard':
            context.notification = DBaaSClusterGrow(context, request=req)
            with StartNotification(context, cluster_id=self.id):
                return self.add_shard()
        else:
            super(MongoDbCluster, self).action(context, req, action, param)

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
        if num_unique_shards == 0:
            msg = _("This action cannot be performed on the cluster as no "
                    "reference shard exists.")
            LOG.error(msg)
            raise exception.UnprocessableEntity(msg)

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
        locality = srv_grp.ServerGroup.convert_to_hint(self.server_group)
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
                                        cluster_config=member_config,
                                        locality=locality)

        self.update_db(task_status=ClusterTasks.ADDING_SHARD)
        manager.mongodb_add_shard_cluster(
            self.id,
            new_shard_id,
            new_replica_set_name)

    def grow(self, instances):
        """Extend a cluster by adding new instances.
        Currently only supports adding a replica set to the cluster.
        """
        if not len(instances) > 0:
            raise exception.TroveError(
                _('Not instances specified for grow operation.')
            )
        self._prep_resize()
        self._check_quotas(self.context, instances)
        query_routers, shards = self._group_instances(instances)
        for shard in shards:
            self._check_instances(
                self.context, shard, self.datastore_version,
                allowed_instance_count=[3]
            )
        if query_routers:
            self._check_instances(self.context, query_routers,
                                  self.datastore_version)
        # all checks are done before any instances are created
        locality = srv_grp.ServerGroup.convert_to_hint(self.server_group)
        instance_ids = []
        for shard in shards:
            instance_ids.extend(self._create_shard_instances(shard, locality))
        if query_routers:
            instance_ids.extend(
                self._create_query_router_instances(query_routers, locality)
            )

        self.update_db(task_status=ClusterTasks.GROWING_CLUSTER)
        self.manager.grow_cluster(self.id, instance_ids)

    def shrink(self, instance_ids):
        """Removes instances from a cluster.
        Currently only supports removing entire replica sets from the cluster.
        """
        if not len(instance_ids) > 0:
            raise exception.TroveError(
                _('Not instances specified for grow operation.')
            )

        self._prep_resize()

        all_member_ids = set([member.id for member in self.members])
        all_query_router_ids = set([query_router.id for query_router
                                    in self.query_routers])
        target_ids = set(instance_ids)
        target_member_ids = target_ids.intersection(all_member_ids)
        target_query_router_ids = target_ids.intersection(all_query_router_ids)
        target_configsvr_ids = target_ids.difference(
            target_member_ids.union(target_query_router_ids)
        )
        if target_configsvr_ids:
            raise exception.ClusterShrinkInstanceInUse(
                id=list(target_configsvr_ids),
                reason="Cannot remove config servers."
            )

        remaining_query_router_ids = all_query_router_ids.difference(
            target_query_router_ids
        )
        if len(remaining_query_router_ids) < 1:
            raise exception.ClusterShrinkInstanceInUse(
                id=list(target_query_router_ids),
                reason="Cannot remove all remaining query routers. At least "
                       "one query router must be available in the cluster."
            )

        if target_member_ids:
            target_members = [member for member in self.members
                              if member.id in target_member_ids]
            target_shards = {}
            for member in target_members:
                if member.shard_id in target_shards:
                    target_shards[member.shard_id].append(member.id)
                else:
                    target_shards[member.shard_id] = [member.id]
            for target_shard_id in target_shards.keys():
                # check the whole shard is being deleted
                target_shard_member_ids = [
                    member.id for member in target_members
                    if member.shard_id == target_shard_id
                ]
                all_shard_member_ids = [
                    member.id for member in self.members
                    if member.shard_id == target_shard_id
                ]
                if set(target_shard_member_ids) != set(all_shard_member_ids):
                    raise exception.TroveError(
                        _('MongoDB cluster shrink only supports removing an '
                          'entire shard. Shard %(shard)s has members: '
                          '%(instances)s')
                        % {'shard': target_shard_id,
                           'instances': all_shard_member_ids}
                    )
                self._check_shard_status(target_shard_member_ids[0])

        # all checks are done by now
        self.update_db(task_status=ClusterTasks.SHRINKING_CLUSTER)
        for instance_id in instance_ids:
            instance = inst_models.load_any_instance(self.context, instance_id)
            instance.delete()
        self.manager.shrink_cluster(self.id, instance_ids)

    def _create_instances(self, instances, cluster_config,
                          default_name_tag, locality, key=None):
        """Loop through the instances and create them in this cluster."""
        cluster_config['id'] = self.id
        if CONF.get(self.datastore_version.manager).cluster_secure:
            if not key:
                key = self.get_guest(self.arbitrary_query_router).get_key()
            cluster_config['key'] = key
        instance_ids = []
        for i, instance in enumerate(instances):
            name = instance.get('name', '%s-%s-%s' % (
                self.name, default_name_tag, i + 1))
            new_instance = inst_models.Instance.create(
                self.context, name, instance['flavor_id'],
                self.datastore_version.image_id, [], [],
                self.datastore, self.datastore_version,
                instance['volume_size'], None,
                availability_zone=instance.get('availability_zone', None),
                nics=instance.get('nics', None),
                cluster_config=cluster_config,
                locality=locality
            )
            instance_ids.append(new_instance.id)
        return instance_ids

    def _create_shard_instances(self, instances, locality,
                                replica_set_name=None, key=None):
        """Create the instances for a new shard in the cluster."""
        shard_id = utils.generate_uuid()
        if not replica_set_name:
            replica_set_name = self._gen_replica_set_name()
        cluster_config = {'shard_id': shard_id,
                          'instance_type': 'member',
                          'replica_set_name': replica_set_name}
        return self._create_instances(instances, cluster_config,
                                      replica_set_name, locality, key=key)

    def _create_query_router_instances(self, instances, locality, key=None):
        """Create the instances for the new query router."""
        cluster_config = {'instance_type': 'query_router'}
        return self._create_instances(instances, cluster_config,
                                      'mongos', locality, key=key)

    def _prep_resize(self):
        """Get information about the cluster's current state."""
        if self.db_info.task_status != ClusterTasks.NONE:
            current_task = self.db_info.task_status.name
            msg = _("This action cannot be performed on the cluster while "
                    "the current cluster task is '%s'.") % current_task
            LOG.error(msg)
            raise exception.UnprocessableEntity(msg)

        def _instances_of_type(instance_type):
            return [db_inst for db_inst in self.db_instances
                    if db_inst.type == instance_type]

        self.config_svrs = _instances_of_type('config_server')
        self.query_routers = _instances_of_type('query_router')
        self.members = _instances_of_type('member')
        self.shard_ids = set([member.shard_id for member in self.members])
        self.arbitrary_query_router = inst_models.load_any_instance(
            self.context, self.query_routers[0].id
        )
        self.manager = task_api.load(self.context,
                                     self.datastore_version.manager)

    def _group_instances(self, instances):
        """Group the instances into logical sets (type, shard, etc)."""
        replicas = []
        query_routers = []
        for item in instances:
            if item['instance_type'] == 'replica':
                replica_requirements = ['related_to', 'name']
                if not all(key in item for key in replica_requirements):
                    raise exception.TroveError(
                        _('Replica instance does not have required field(s) '
                          '%s.') % replica_requirements
                    )
                replicas.append(item)
            elif item['instance_type'] == 'query_router':
                query_routers.append(item)
            else:
                raise exception.TroveError(
                    _('Instance type %s not supported for MongoDB cluster '
                      'grow.') % item['instance_type']
                )
        return query_routers, self._group_shard_instances(replicas)

    def _group_shard_instances(self, instances):
        """Group the replica instances into shards."""
        # Create the sets. Dictionary keys correspond to instance names.
        # Dictionary values are the same if related.
        sets = {}
        specified_names = []
        for instance in instances:
            name = instance['name']
            specified_names.append(name)
            if name in sets:
                sets[name].append(instance)
            else:
                sets[name] = [instance]
            if 'related_to' in instance:
                if instance['related_to'] == instance['name']:
                    continue
                relative = instance['related_to']
                if relative in sets:
                    if sets[relative] is not sets[name]:
                        sets[relative].extend(sets[name])
                        sets[name] = sets[relative]
                else:
                    sets[relative] = sets[name]
        specified_names_set = set(specified_names)
        if len(specified_names) != len(specified_names_set):
            raise exception.TroveError(
                _('Duplicate member names not allowed.')
            )
        unknown_relations = set(sets.keys()).difference((specified_names_set))
        if unknown_relations:
            raise exception.TroveError(
                _('related_to target(s) %(targets)s do not match any '
                  'specified names.')
                % {'targets': list(unknown_relations)}
            )
        # reduce the set to unique values
        shards = []
        for key in sets.keys():
            exists = False
            for item in shards:
                if item is sets[key]:
                    exists = True
                    break
            if exists:
                continue
            shards.append(sets[key])
        for shard in shards:
            flavor = None
            size = None
            for member in shard:
                if ((flavor and member['flavor_id'] != flavor) or (
                        size and member['volume_size'] != size)):
                    raise exception.TroveError(
                        _('Members of the same shard have mismatching '
                          'flavorRef and/or volume values.')
                    )
                flavor = member['flavor_id']
                size = member['volume_size']
        return shards

    def _gen_replica_set_name(self):
        """Check the replica set names of all shards in the cluster to
        determine the next available name.
        Names are in the form 'rsX' where X is an integer.
        """
        used_names = []
        for shard_id in self.shard_ids:
            # query the guest for the replica name on one member of each shard
            members = [mem for mem in self.members
                       if mem.shard_id == shard_id]
            member = inst_models.load_any_instance(self.context, members[0].id)
            used_names.append(self.get_guest(member).get_replica_set_name())
        # find the first unused name
        i = 0
        while True:
            i += 1
            name = 'rs%s' % i
            if name not in used_names:
                return name

    def _check_shard_status(self, member_id):
        member = inst_models.load_any_instance(self.context, member_id)
        guest = self.get_guest(member)
        rs_name = guest.get_replica_set_name()
        if self.get_guest(
                self.arbitrary_query_router).is_shard_active(rs_name):
            raise exception.TroveError(
                _('Shard with instance %s is still active. Please remove the '
                  'shard from the MongoDB cluster before shrinking.')
                % member_id
            )

    @staticmethod
    def _check_quotas(context, instances):
        deltas = {'instances': len(instances),
                  'volumes': sum([instance['volume_size']
                                  for instance in instances])}
        check_quotas(context.tenant, deltas)

    @staticmethod
    def _check_instances(context, instances, datastore_version,
                         allowed_instance_count=None):
        instance_count = len(instances)
        if allowed_instance_count:
            if instance_count not in allowed_instance_count:
                raise exception.ClusterNumInstancesNotSupported(
                    num_instances=allowed_instance_count
                )
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
        volume_sizes = [instance['volume_size'] for instance in instances
                        if instance.get('volume_size', None)]
        if mongo_conf.volume_support:
            if len(volume_sizes) != instance_count:
                raise exception.ClusterVolumeSizeRequired()
            if len(set(volume_sizes)) != 1:
                raise exception.ClusterVolumeSizesNotEqual()
            volume_size = volume_sizes[0]
            models.validate_volume_size(volume_size)
        else:
            # TODO(amcreynolds): is ephemeral possible for mongodb clusters?
            if len(volume_sizes) > 0:
                raise exception.VolumeNotSupported()
            ephemeral_support = mongo_conf.device_path
            if ephemeral_support and flavor.ephemeral == 0:
                raise exception.LocalStorageNotSpecified(flavor=flavor_id)


class MongoDbClusterView(ClusterView):

    def build_instances(self):
        return self._build_instances(['query_router'], ['member'])


class MongoDbMgmtClusterView(MgmtClusterView):

    def build_instances(self):
        return self._build_instances(['query_router'],
                                     ['config_server',
                                      'member',
                                      'query_router'])
