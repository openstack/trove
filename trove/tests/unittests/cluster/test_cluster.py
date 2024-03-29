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

from unittest.mock import Mock
from unittest.mock import patch
import uuid

from trove.cluster.models import Cluster
from trove.cluster.models import ClusterTasks
from trove.cluster.models import DBCluster
from trove.common import cfg
from trove.common import clients
from trove.common import exception
from trove.common.strategies.cluster.experimental.mongodb import (
    api as mongodb_api)
from trove.common import utils
from trove.datastore import models as datastore_models
from trove.instance import models as inst_models
from trove.instance.models import DBInstance
from trove.instance.tasks import InstanceTasks
from trove.quota.quota import QUOTAS
from trove.taskmanager import api as task_api
from trove.tests.unittests import trove_testtools

CONF = cfg.CONF


class ClusterTest(trove_testtools.TestCase):
    def setUp(self):
        super(ClusterTest, self).setUp()
        self.get_client_patch = patch.object(task_api.API, 'get_client')
        self.get_client_mock = self.get_client_patch.start()
        self.addCleanup(self.get_client_patch.stop)
        self.cluster_id = str(uuid.uuid4())
        self.cluster_name = "Cluster" + self.cluster_id
        self.tenant_id = "23423432"
        self.dv_id = "1"
        self.db_info = DBCluster(ClusterTasks.NONE,
                                 id=self.cluster_id,
                                 name=self.cluster_name,
                                 tenant_id=self.tenant_id,
                                 datastore_version_id=self.dv_id,
                                 task_id=ClusterTasks.NONE._code)
        self.context = trove_testtools.TroveTestContext(self)
        self.datastore = Mock()
        self.dv = Mock()
        self.dv.manager = "mongodb"
        self.datastore_version = self.dv
        self.cluster = mongodb_api.MongoDbCluster(self.context, self.db_info,
                                                  self.datastore,
                                                  self.datastore_version)
        self.cluster._server_group_loaded = True
        self.instances = [{'volume_size': 1, 'flavor_id': '1234'},
                          {'volume_size': 1, 'flavor_id': '1234'},
                          {'volume_size': 1, 'flavor_id': '1234'}]
        self.volume_support = CONF.get(self.dv.manager).volume_support
        self.remote_nova = clients.create_nova_client

    def tearDown(self):
        super(ClusterTest, self).tearDown()
        CONF.get(self.dv.manager).volume_support = self.volume_support
        clients.create_nova_client = self.remote_nova

    def test_create_empty_instances(self):
        self.assertRaises(exception.ClusterNumInstancesNotSupported,
                          Cluster.create,
                          Mock(),
                          self.cluster_name,
                          self.datastore,
                          self.datastore_version,
                          [],
                          {}, None, None)

    @patch.object(clients, 'create_nova_client')
    def test_create_unequal_flavors(self, mock_client):
        instances = self.instances
        instances[0]['flavor_id'] = '4567'
        self.assertRaises(exception.ClusterFlavorsNotEqual,
                          Cluster.create,
                          Mock(),
                          self.cluster_name,
                          self.datastore,
                          self.datastore_version,
                          instances,
                          {}, None, None)

    @patch.object(clients, 'create_nova_client')
    def test_create_unequal_volumes(self,
                                    mock_client):
        instances = self.instances
        instances[0]['volume_size'] = 2
        flavors = Mock()
        mock_client.return_value.flavors = flavors
        self.assertRaises(exception.ClusterVolumeSizesNotEqual,
                          Cluster.create,
                          Mock(),
                          self.cluster_name,
                          self.datastore,
                          self.datastore_version,
                          instances,
                          {}, None, None)

    @patch.object(clients, 'create_nova_client')
    def test_create_storage_not_specified(self,
                                          mock_client):
        class FakeFlavor(object):
            def __init__(self, flavor_id):
                self.flavor_id = flavor_id

            @property
            def id(self):
                return self.flavor.id

            @property
            def ephemeral(self):
                return 0
        instances = [{'flavor_id': '1234'},
                     {'flavor_id': '1234'},
                     {'flavor_id': '1234'}]
        CONF.get(self.dv.manager).volume_support = False
        (mock_client.return_value.
         flavors.get.return_value) = FakeFlavor('1234')
        self.assertRaises(exception.LocalStorageNotSpecified,
                          Cluster.create,
                          Mock(),
                          self.cluster_name,
                          self.datastore,
                          self.datastore_version,
                          instances,
                          {}, None, None)

    @patch('trove.cluster.models.LOG')
    def test_delete_bad_task_status(self, mock_logging):
        self.cluster.db_info.task_status = ClusterTasks.BUILDING_INITIAL
        self.assertRaises(exception.UnprocessableEntity,
                          self.cluster.delete)

    @patch.object(task_api.API, 'delete_cluster')
    @patch.object(Cluster, 'update_db')
    @patch.object(inst_models.DBInstance, 'find_all')
    def test_delete_task_status_none(self,
                                     mock_find_all,
                                     mock_update_db,
                                     mock_delete_cluster):
        self.cluster.db_info.task_status = ClusterTasks.NONE
        self.cluster.delete()
        mock_update_db.assert_called_with(task_status=ClusterTasks.DELETING)

    @patch.object(task_api.API, 'delete_cluster')
    @patch.object(Cluster, 'update_db')
    @patch.object(inst_models.DBInstance, 'find_all')
    def test_delete_task_status_deleting(self,
                                         mock_find_all,
                                         mock_update_db,
                                         mock_delete_cluster):
        self.cluster.db_info.task_status = ClusterTasks.DELETING
        self.cluster.delete()
        mock_update_db.assert_called_with(task_status=ClusterTasks.DELETING)

    @patch('trove.common.strategies.cluster.experimental.mongodb.api.LOG')
    def test_add_shard_bad_task_status(self, mock_logging):
        task_status = ClusterTasks.BUILDING_INITIAL
        self.cluster.db_info.task_status = task_status
        self.assertRaises(exception.UnprocessableEntity,
                          self.cluster.add_shard)

    @patch.object(utils, 'generate_uuid', Mock(return_value='new-shard-id'))
    @patch.object(datastore_models.DatastoreVersion, 'load_by_uuid')
    @patch.object(task_api, 'load')
    @patch.object(Cluster, 'update_db')
    @patch.object(inst_models.Instance, 'create')
    @patch.object(QUOTAS, 'check_quotas')
    @patch.object(inst_models, 'load_any_instance')
    @patch.object(inst_models.DBInstance, 'find_all')
    def test_add_shard(self,
                       mock_find_all,
                       mock_load_any_instance,
                       mock_check_quotas,
                       mock_instance_create,
                       mock_update_db,
                       mock_task_api_load,
                       mock_load_by_uuid):
        self.cluster.db_info.task_status = ClusterTasks.NONE
        (mock_find_all.return_value
         .all.return_value) = [DBInstance(InstanceTasks.NONE,
                                          name="TestInstance1",
                                          shard_id="1", id='1',
                                          datastore_version_id='1'),
                               DBInstance(InstanceTasks.NONE,
                                          name="TestInstance2",
                                          shard_id="1", id='2',
                                          datastore_version_id='1'),
                               DBInstance(InstanceTasks.NONE,
                                          name="TestInstance3",
                                          shard_id="1", id='3',
                                          datastore_version_id='1')]
        mock_datastore_version = Mock()
        mock_datastore_version.manager = 'mongodb'
        mock_load_by_uuid.return_value = mock_datastore_version
        mock_task_api = Mock()
        mock_task_api.mongodb_add_shard_cluster.return_value = None
        mock_task_api_load.return_value = mock_task_api
        self.cluster.add_shard()
        mock_update_db.assert_called_with(
            task_status=ClusterTasks.ADDING_SHARD)
        mock_task_api.mongodb_add_shard_cluster.assert_called_with(
            self.cluster.id, 'new-shard-id', 'rs2')

    @patch('trove.cluster.models.LOG')
    def test_upgrade_not_implemented(self, mock_logging):
        self.assertRaises(exception.BadRequest, self.cluster.upgrade, "foo")
