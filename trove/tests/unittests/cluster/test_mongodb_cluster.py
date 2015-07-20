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

from trove.cluster import models
from trove.cluster import tasks
from trove.common import cfg
from trove.common import exception
from trove.common import remote
from trove.common.strategies.cluster.experimental.mongodb import api
from trove.instance import models as inst_models
from trove.instance import tasks as inst_tasks
from trove.tests.unittests import trove_testtools


CONF = cfg.CONF


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
        self.datastore_version = self.dv
        self.cluster = api.MongoDbCluster(self.context, self.db_info,
                                          self.datastore,
                                          self.datastore_version)
        self.manager = mock.Mock()
        self.cluster.manager = self.manager
        self.volume_support = CONF.get('mongodb').volume_support
        self.remote_nova = remote.create_nova_client

    def tearDown(self):
        super(MongoDBClusterTest, self).tearDown()

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

        self.assertEqual(mock_prep_resize.called, True)
        mock_create_shard_instances.assert_called_with([instance1, instance2,
                                                        instance3])
        mock_create_query_router_instances.assert_called_with([instance4])
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

        self.assertEqual(mock_prep_resize.called, True)
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
