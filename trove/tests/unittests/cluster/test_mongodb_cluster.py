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

import mock
import uuid

from novaclient import exceptions as nova_exceptions

from trove.cluster import models
from trove.cluster import tasks
from trove.common import cfg
from trove.common import exception
from trove.common import remote
from trove.common.strategies.cluster.experimental.mongodb import api
from trove.instance import models as inst_models
from trove.instance import tasks as inst_tasks
from trove.quota.quota import QUOTAS
from trove.taskmanager import api as task_api
from trove.tests.unittests import trove_testtools


CONF = cfg.CONF


class FakeOptGroup(object):
    def __init__(self, num_config_servers_per_cluster=3,
                 num_query_routers_per_cluster=1,
                 config_servers_volume_size=10,
                 query_routers_volume_size=10,
                 cluster_secure=True, volume_support=True,
                 device_path='/dev/vdb'):
        self.num_config_servers_per_cluster = num_config_servers_per_cluster
        self.num_query_routers_per_cluster = num_query_routers_per_cluster
        self.config_servers_volume_size = config_servers_volume_size
        self.query_routers_volume_size = query_routers_volume_size
        self.cluster_secure = cluster_secure
        self.volume_support = volume_support
        self.device_path = device_path


class MongoDBClusterTest(trove_testtools.TestCase):
    def setUp(self):
        super(MongoDBClusterTest, self).setUp()
        self.cluster_id = str(uuid.uuid4())
        self.cluster_name = "Cluster" + self.cluster_id
        self.tenant_id = "23423432"
        self.dv_id = "1"
        self.db_info = models.DBCluster(models.ClusterTasks.NONE,
                                        id=self.cluster_id,
                                        name=self.cluster_name,
                                        tenant_id=self.tenant_id,
                                        datastore_version_id=self.dv_id,
                                        task_id=models.ClusterTasks.NONE._code)
        self.context = mock.Mock()
        self.datastore = mock.Mock()
        self.dv = mock.Mock()
        self.dv.manager = "mongodb"
        self.datastore_version = self.dv
        self.cluster = api.MongoDbCluster(self.context, self.db_info,
                                          self.datastore,
                                          self.datastore_version)
        self.cluster._server_group_loaded = True
        self.manager = mock.Mock()
        self.cluster.manager = self.manager
        self.volume_support = CONF.get('mongodb').volume_support
        self.remote_nova = remote.create_nova_client
        self.instances = [
            {'volume_size': 1, 'flavor_id': '1234',
             'nics': [{"net-id": "foo-bar"}],
             'region_name': "foo-region"},
            {'volume_size': 1, 'flavor_id': '1234',
             'nics': [{"net-id": "foo-bar"}],
             'region_name': "foo-region"},
            {'volume_size': 1, 'flavor_id': '1234',
             'nics': [{"net-id": "foo-bar"}],
             'region_name': "foo-region"}]

    def tearDown(self):
        super(MongoDBClusterTest, self).tearDown()

    def test_create_configuration_specified(self):
        configuration = "foo-config"
        self.assertRaises(exception.ConfigurationNotSupported,
                          models.Cluster.create,
                          mock.Mock(),
                          self.cluster_name,
                          self.datastore,
                          self.datastore_version,
                          self.instances, {}, None,
                          configuration)

    def test_create_invalid_instance_numbers_specified(self):
        instance = [
            {'volume_size': 1, 'flavor_id': '1234',
             'nics': [{"net-id": "foo-bar"}]}
        ]
        self.assertRaises(exception.ClusterNumInstancesNotSupported,
                          models.Cluster.create,
                          mock.Mock(),
                          self.cluster_name,
                          self.datastore,
                          self.datastore_version,
                          instance, {}, None, None)

    @mock.patch.object(remote, 'create_nova_client')
    def test_create_invalid_flavor_specified(self, mock_client):
        (mock_client.return_value.flavors.get) = mock.Mock(
            side_effect=nova_exceptions.NotFound(
                404, "Flavor id not found."))
        self.assertRaises(exception.FlavorNotFound,
                          models.Cluster.create,
                          mock.Mock(),
                          self.cluster_name,
                          self.datastore,
                          self.datastore_version,
                          self.instances, {}, None, None)

    @mock.patch.object(remote, 'create_nova_client')
    def test_create_flavor_not_equal(self, mock_client):
        instances = self.instances
        instances[0]['flavor_id'] = '4321'
        flavors = mock.Mock()
        mock_client.return_value.flavors = flavors
        self.assertRaises(exception.ClusterFlavorsNotEqual,
                          models.Cluster.create,
                          mock.Mock(),
                          self.cluster_name,
                          self.datastore,
                          self.datastore_version,
                          instances, {}, None, None)

    @mock.patch.object(remote, 'create_nova_client')
    def test_create_volume_not_equal(self, mock_client):
        instances = self.instances
        instances[0]['volume_size'] = 2
        flavors = mock.Mock()
        mock_client.return_value.flavors = flavors
        self.assertRaises(exception.ClusterVolumeSizesNotEqual,
                          models.Cluster.create,
                          mock.Mock(),
                          self.cluster_name,
                          self.datastore,
                          self.datastore_version,
                          instances, {}, None, None)

    @mock.patch.object(remote, 'create_nova_client')
    def test_create_volume_not_specified(self, mock_client):
        instances = [
            {'flavor_id': '1234',
             'nics': [{"net-id": "foo-bar"}],
             'region_name': "foo-region"},
            {'flavor_id': '1234',
             'nics': [{"net-id": "foo-bar"}],
             'region_name': "foo-region"},
            {'flavor_id': '1234',
             'nics': [{"net-id": "foo-bar"}],
             'region_name': "foo-region"}]
        flavors = mock.Mock()
        mock_client.return_value.flavors = flavors
        self.assertRaises(exception.ClusterVolumeSizeRequired,
                          models.Cluster.create,
                          mock.Mock(),
                          self.cluster_name,
                          self.datastore,
                          self.datastore_version,
                          instances, {}, None, None)

    @mock.patch.object(remote, 'create_nova_client')
    @mock.patch.object(api, 'CONF')
    def test_create_storage_specified_with_no_volume_support(self,
                                                             mock_conf,
                                                             mock_client):
        mock_conf.get = mock.Mock(
            return_value=FakeOptGroup(volume_support=False))
        flavors = mock.Mock()
        mock_client.return_value.flavors = flavors
        self.assertRaises(exception.VolumeNotSupported,
                          models.Cluster.create,
                          mock.Mock(),
                          self.cluster_name,
                          self.datastore,
                          self.datastore_version,
                          self.instances, {}, None, None)

    @mock.patch.object(task_api, 'load')
    @mock.patch.object(inst_models.Instance, 'create')
    @mock.patch.object(models.DBCluster, 'create')
    @mock.patch.object(remote, 'create_neutron_client')
    @mock.patch.object(remote, 'create_nova_client')
    @mock.patch.object(api, 'check_quotas')
    def test_create_validate_volumes_deltas(self, mock_check_quotas, *args):
        extended_properties = {
            "configsvr_volume_size": 5,
            "mongos_volume_size": 7}
        self.cluster.create(mock.Mock(),
                            self.cluster_name,
                            self.datastore,
                            self.datastore_version,
                            self.instances,
                            extended_properties, None, None)
        deltas = {'instances': 7, 'volumes': 25}  # volumes=1*3+5*3+7*1
        mock_check_quotas.assert_called_with(mock.ANY, deltas)

    @mock.patch.object(task_api, 'load')
    @mock.patch.object(inst_models.Instance, 'create')
    @mock.patch.object(models.DBCluster, 'create')
    @mock.patch.object(QUOTAS, 'check_quotas')
    @mock.patch.object(remote, 'create_nova_client')
    @mock.patch.object(remote, 'create_neutron_client')
    def test_create(self, mock_neutron_client, mock_nova_client,
                    mock_check_quotas, mock_db_create,
                    mock_ins_create, mock_task_api):
        instances = self.instances
        flavors = mock.Mock()
        networks = mock.Mock()
        mock_neutron_client.return_value.find_resource = networks
        mock_nova_client.return_value.flavors = flavors
        self.cluster.create(mock.Mock(),
                            self.cluster_name,
                            self.datastore,
                            self.datastore_version,
                            instances, {}, None, None)
        mock_task_api.return_value.create_cluster.assert_called_with(
            mock_db_create.return_value.id)
        self.assertEqual(7, mock_ins_create.call_count)

    @mock.patch.object(task_api, 'load')
    @mock.patch.object(models.DBCluster, 'create')
    @mock.patch.object(models, 'validate_instance_nics')
    @mock.patch.object(QUOTAS, 'check_quotas')
    @mock.patch.object(models, 'validate_instance_flavors')
    @mock.patch.object(inst_models.Instance, 'create')
    def test_create_with_correct_nics(self, mock_ins_create, *args):
        self.cluster.create(mock.Mock(),
                            self.cluster_name,
                            self.datastore,
                            self.datastore_version,
                            self.instances, {}, None, None)
        nics = [{"net-id": "foo-bar"}]
        nics_count = [kw.get('nics') for _, kw in
                      mock_ins_create.call_args_list].count(nics)
        self.assertEqual(7, nics_count)

    @mock.patch.object(task_api, 'load')
    @mock.patch.object(models.DBCluster, 'create')
    @mock.patch.object(models, 'validate_instance_nics')
    @mock.patch.object(QUOTAS, 'check_quotas')
    @mock.patch.object(models, 'validate_instance_flavors')
    @mock.patch.object(inst_models.Instance, 'create')
    def test_create_with_extended_properties(self, mock_ins_create, *args):
        extended_properties = {
            "num_configsvr": 5,
            "num_mongos": 7,
            "configsvr_volume_size": 8,
            "configsvr_volume_type": "foo_type",
            "mongos_volume_size": 9,
            "mongos_volume_type": "bar_type"}
        self.cluster.create(mock.Mock(),
                            self.cluster_name,
                            self.datastore,
                            self.datastore_version,
                            self.instances,
                            extended_properties, None, None)
        volume_args_list = [
            (arg[8], kw['volume_type']) for arg, kw in
            mock_ins_create.call_args_list
        ]
        self.assertEqual(5, volume_args_list.count((8, "foo_type")))
        self.assertEqual(7, volume_args_list.count((9, "bar_type")))

    @mock.patch.object(task_api, 'load')
    @mock.patch.object(inst_models.Instance, 'create')
    @mock.patch.object(models.DBCluster, 'create')
    @mock.patch.object(QUOTAS, 'check_quotas')
    @mock.patch.object(remote, 'create_nova_client')
    @mock.patch.object(remote, 'create_neutron_client')
    @mock.patch.object(api, 'CONF')
    def test_create_with_lower_configsvr(self, mock_conf, mock_neutron_client,
                                         mock_nova_client, ock_check_quotas,
                                         mock_db_create, mock_ins_create,
                                         mock_task_api):
        mock_conf.get = mock.Mock(
            return_value=FakeOptGroup(num_config_servers_per_cluster=1))
        instances = self.instances
        flavors = mock.Mock()
        networks = mock.Mock()
        mock_nova_client.return_value.flavors = flavors
        mock_neutron_client.return_value.find_resource = networks
        self.cluster.create(mock.Mock(),
                            self.cluster_name,
                            self.datastore,
                            self.datastore_version,
                            instances, {}, None, None)
        mock_task_api.return_value.create_cluster.assert_called_with(
            mock_db_create.return_value.id)
        self.assertEqual(5, mock_ins_create.call_count)

    @mock.patch.object(task_api, 'load')
    @mock.patch.object(inst_models.Instance, 'create')
    @mock.patch.object(models.DBCluster, 'create')
    @mock.patch.object(QUOTAS, 'check_quotas')
    @mock.patch.object(remote, 'create_nova_client')
    @mock.patch.object(remote, 'create_neutron_client')
    @mock.patch.object(api, 'CONF')
    def test_create_with_higher_configsvr(self, mock_conf, mock_neutron_client,
                                          mock_nova_client, mock_check_quotas,
                                          mock_db_create, mock_ins_create,
                                          mock_task_api):
        mock_conf.get = mock.Mock(
            return_value=FakeOptGroup(num_config_servers_per_cluster=5))
        instances = self.instances
        flavors = mock.Mock()
        networks = mock.Mock()
        mock_nova_client.return_value.flavors = flavors
        mock_neutron_client.return_value.find_resource = networks
        self.cluster.create(mock.Mock(),
                            self.cluster_name,
                            self.datastore,
                            self.datastore_version,
                            instances, {}, None, None)
        mock_task_api.return_value.create_cluster.assert_called_with(
            mock_db_create.return_value.id)
        self.assertEqual(9, mock_ins_create.call_count)

    @mock.patch.object(task_api, 'load')
    @mock.patch.object(inst_models.Instance, 'create')
    @mock.patch.object(models.DBCluster, 'create')
    @mock.patch.object(QUOTAS, 'check_quotas')
    @mock.patch.object(remote, 'create_nova_client')
    @mock.patch.object(remote, 'create_neutron_client')
    @mock.patch.object(api, 'CONF')
    def test_create_with_higher_mongos(self, mock_conf, mock_neutron_client,
                                       mock_nova_client, mock_check_quotas,
                                       mock_db_create, mock_ins_create,
                                       mock_task_api):
        mock_conf.get = mock.Mock(
            return_value=FakeOptGroup(num_query_routers_per_cluster=4))
        instances = self.instances
        flavors = mock.Mock()
        networks = mock.Mock()
        mock_nova_client.return_value.flavors = flavors
        mock_neutron_client.return_value.find_resource = networks
        self.cluster.create(mock.Mock(),
                            self.cluster_name,
                            self.datastore,
                            self.datastore_version,
                            instances, {}, None, None)
        mock_task_api.return_value.create_cluster.assert_called_with(
            mock_db_create.return_value.id)
        self.assertEqual(10, mock_ins_create.call_count)

    @mock.patch.object(api.MongoDbCluster, '_prep_resize')
    @mock.patch.object(api.MongoDbCluster, '_check_quotas')
    @mock.patch.object(api.MongoDbCluster, '_check_instances')
    @mock.patch.object(api.MongoDbCluster, '_create_shard_instances',
                       return_value=['id1', 'id2', 'id3'])
    @mock.patch.object(api.MongoDbCluster, '_create_query_router_instances',
                       return_value=['id4'])
    @mock.patch.object(api.MongoDbCluster, 'update_db')
    def test_grow(self, mock_update_db,
                  mock_create_query_router_instances,
                  mock_create_shard_instances,
                  mock_check_instances, mock_check_quotas, mock_prep_resize):
        instance1 = {'name': 'replicaA', 'flavor_id': 1, 'volume_size': 5,
                     'instance_type': 'replica', 'related_to': 'replicaC'}
        instance2 = {'name': 'replicaB', 'flavor_id': 1, 'volume_size': 5,
                     'instance_type': 'replica', 'related_to': 'replicaA'}
        instance3 = {'name': 'replicaC', 'flavor_id': 1, 'volume_size': 5,
                     'instance_type': 'replica', 'related_to': 'replicaA'}
        instance4 = {'flavor_id': 1, 'volume_size': 5,
                     'instance_type': 'query_router'}

        self.cluster.grow([instance1, instance2, instance3, instance4])

        self.assertTrue(mock_prep_resize.called)
        mock_create_shard_instances.assert_called_with([instance1, instance2,
                                                        instance3], None)
        mock_create_query_router_instances.assert_called_with([instance4],
                                                              None)
        mock_update_db.assert_called_with(
            task_status=tasks.ClusterTasks.GROWING_CLUSTER
        )
        self.manager.grow_cluster.assert_called_with(
            self.cluster_id, ['id1', 'id2', 'id3', 'id4']
        )

    @mock.patch.object(api.MongoDbCluster, '_prep_resize')
    @mock.patch.object(api.MongoDbCluster, '_check_quotas')
    def test_grow_invalid_type(self, mock_check_quotas, mock_prep_resize):
        instance1 = {'flavor_id': 1, 'volume_size': 5,
                     'instance_type': 'config_server'}
        self.assertRaises(exception.TroveError,
                          self.cluster.grow,
                          [instance1])

    @mock.patch.object(api.MongoDbCluster, '_prep_resize')
    @mock.patch.object(api.MongoDbCluster, '_check_quotas')
    def test_grow_invalid_shard_size(self, mock_check_quotas,
                                     mock_prep_resize):
        instance1 = {'name': 'replicaA', 'flavor_id': 1, 'volume_size': 5,
                     'instance_type': 'replica', 'related_to': 'replicaB'}
        instance2 = {'name': 'replicaB', 'flavor_id': 1, 'volume_size': 5,
                     'instance_type': 'replica', 'related_to': 'replicaA'}
        self.assertRaises(exception.TroveError,
                          self.cluster.grow,
                          [instance1, instance2])

    @mock.patch.object(api.MongoDbCluster, '_prep_resize')
    @mock.patch.object(api.MongoDbCluster, '_check_quotas')
    def test_grow_no_name(self, mock_check_quotas, mock_prep_resize):
        instance1 = {'flavor_id': 1, 'volume_size': 5,
                     'instance_type': 'replica', 'related_to': 'replicaC'}
        self.assertRaises(exception.TroveError,
                          self.cluster.grow,
                          [instance1])

    @mock.patch.object(api.MongoDbCluster, '_prep_resize')
    @mock.patch.object(api.MongoDbCluster, '_check_quotas')
    def test_grow_repeated_name(self, mock_check_quotas, mock_prep_resize):
        instance1 = {'name': 'replicaA', 'flavor_id': 1, 'volume_size': 5,
                     'instance_type': 'replica', 'related_to': 'replicaC'}
        instance1 = {'name': 'replicaA', 'flavor_id': 1, 'volume_size': 5,
                     'instance_type': 'replica', 'related_to': 'replicaC'}
        instance1 = {'name': 'replicaC', 'flavor_id': 1, 'volume_size': 5,
                     'instance_type': 'replica', 'related_to': 'replicaC'}
        self.assertRaises(exception.TroveError,
                          self.cluster.grow,
                          [instance1])

    @mock.patch.object(api.MongoDbCluster, '_prep_resize')
    @mock.patch.object(api.MongoDbCluster, '_check_quotas')
    def test_grow_bad_relations(self, mock_check_quotas, mock_prep_resize):
        instance1 = {'name': 'replicaA', 'flavor_id': 1, 'volume_size': 5,
                     'instance_type': 'replica', 'related_to': 'replicaB'}
        instance2 = {'name': 'replicaB', 'flavor_id': 1, 'volume_size': 5,
                     'instance_type': 'replica', 'related_to': 'replicaC'}
        instance3 = {'name': 'replicaC', 'flavor_id': 1, 'volume_size': 5,
                     'instance_type': 'replica', 'related_to': 'replicaD'}
        self.assertRaises(exception.TroveError,
                          self.cluster.grow,
                          [instance1, instance2, instance3])

    @mock.patch.object(api.MongoDbCluster, '_prep_resize')
    @mock.patch.object(api.MongoDbCluster, '_check_shard_status')
    @mock.patch.object(api.MongoDbCluster, 'update_db')
    @mock.patch.object(inst_models, 'load_any_instance')
    def test_shrink(self, mock_load_any_instance, mock_update_db,
                    mock_check_shard_status, mock_prep_resize):
        self._mock_db_instances()
        self.cluster.query_routers.append(
            inst_models.DBInstance(inst_tasks.InstanceTasks.NONE,
                                   id='id6',
                                   cluster_id=self.cluster_id,
                                   type='query_router')
        )

        self.cluster.shrink(['id1', 'id2', 'id3', 'id4'])

        self.assertTrue(mock_prep_resize.called)
        mock_check_shard_status.assert_called_with('id1')
        mock_update_db.assert_called_with(
            task_status=tasks.ClusterTasks.SHRINKING_CLUSTER
        )
        self.assertEqual(4, mock_load_any_instance().delete.call_count)
        self.manager.shrink_cluster.assert_called_with(
            self.cluster_id, ['id1', 'id2', 'id3', 'id4']
        )

    @mock.patch.object(api.MongoDbCluster, '_prep_resize')
    def test_shrink_invalid_type(self, mock_prep_resize):
        self._mock_db_instances()
        self.assertRaises(exception.TroveError,
                          self.cluster.shrink,
                          ['id5'])

    @mock.patch.object(api.MongoDbCluster, '_prep_resize')
    def test_shrink_incomplete_shard(self, mock_prep_resize):
        self._mock_db_instances()
        self.assertRaises(exception.TroveError,
                          self.cluster.shrink,
                          ['id1', 'id2'])

    def _mock_db_instances(self):
        self.shard_id = uuid.uuid4()
        self.cluster.members = [
            inst_models.DBInstance(inst_tasks.InstanceTasks.NONE,
                                   id='id1',
                                   cluster_id=self.cluster_id,
                                   shard_id=self.shard_id,
                                   type='member'),
            inst_models.DBInstance(inst_tasks.InstanceTasks.NONE,
                                   id='id2',
                                   cluster_id=self.cluster_id,
                                   shard_id=self.shard_id,
                                   type='member'),
            inst_models.DBInstance(inst_tasks.InstanceTasks.NONE,
                                   id='id3',
                                   cluster_id=self.cluster_id,
                                   shard_id=self.shard_id,
                                   type='member'),
        ]
        self.cluster.query_routers = [
            inst_models.DBInstance(inst_tasks.InstanceTasks.NONE,
                                   id='id4',
                                   cluster_id=self.cluster_id,
                                   type='query_router')
        ]
        self.cluster.config_svrs = [
            inst_models.DBInstance(inst_tasks.InstanceTasks.NONE,
                                   id='id5',
                                   cluster_id=self.cluster_id,
                                   type='config_server')
        ]
