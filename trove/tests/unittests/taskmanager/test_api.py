# Copyright 2014 eBay Software Foundation
# Copyright [2015] Hewlett-Packard Development Company, L.P.
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

from mock import Mock
from mock import patch

from trove.common import context
from trove.common import exception
from trove.common.rpc.version import RPC_API_VERSION
from trove.common.strategies.cluster.experimental.mongodb.taskmanager import (
    MongoDbTaskManagerAPI)
from trove.guestagent import models as agent_models
from trove.taskmanager import api as task_api
from trove.tests.unittests import trove_testtools


class ApiTest(trove_testtools.TestCase):
    def setUp(self, *args):
        super(ApiTest, self).setUp()
        self.context = context.TroveContext()
        self.api = task_api.API(self.context)
        self._mock_rpc_client()

    def _verify_rpc_prepare_before_cast(self):
        self.api.client.prepare.assert_called_once_with(
            version=RPC_API_VERSION)

    def _verify_cast(self, *args, **kwargs):
        self.call_context.cast.assert_called_once_with(self.context, *args,
                                                       **kwargs)

    def _mock_rpc_client(self):
        self.call_context = Mock()
        self.api.client.prepare = Mock(return_value=self.call_context)
        self.call_context.cast = Mock()

    def test_detach_replica(self):
        self.api.detach_replica('some-instance-id')

        self._verify_rpc_prepare_before_cast()
        self._verify_cast('detach_replica', instance_id='some-instance-id')

    def test_promote_to_replica_source(self):
        self.api.promote_to_replica_source('some-instance-id')

        self._verify_rpc_prepare_before_cast()
        self._verify_cast('promote_to_replica_source',
                          instance_id='some-instance-id')

    def test_eject_replica_source(self):
        self.api.eject_replica_source('some-instance-id')

        self._verify_rpc_prepare_before_cast()
        self._verify_cast('eject_replica_source',
                          instance_id='some-instance-id')

    def test_create_cluster(self):
        self.api.create_cluster('some-cluster-id')

        self._verify_rpc_prepare_before_cast()
        self._verify_cast('create_cluster', cluster_id='some-cluster-id')

    def test_delete_cluster(self):
        self.api.delete_cluster('some-cluster-id')

        self._verify_rpc_prepare_before_cast()
        self._verify_cast('delete_cluster', cluster_id='some-cluster-id')

    @patch.object(agent_models, 'AgentHeartBeat')
    def test_delete_heartbeat(self, mock_agent_heart_beat):
        self.api._delete_heartbeat('some-cluster-id')
        mock_agent_heart_beat.return_value.delete.assert_called()

    @patch.object(agent_models, 'AgentHeartBeat')
    def test_exception_delete_heartbeat(self, mock_agent_heart_beat):
        mock_agent_heart_beat.return_value.find_by_instance_id.side_effect = (
            exception.ModelNotFoundError)
        self.api._delete_heartbeat('some-cluster-id')
        mock_agent_heart_beat.return_value.delete.assert_not_called()

    def test_transform_obj(self):
        flavor = Mock()
        self.assertRaisesRegexp(ValueError,
                                ('Could not transform %s' % flavor),
                                self.api._transform_obj, flavor)


class TestAPI(trove_testtools.TestCase):

    @patch.object(task_api.API, 'get_client')
    def test_load_api(self, get_client_mock):
        context = Mock()
        manager = 'mongodb'

        self.assertTrue(isinstance(task_api.load(context), task_api.API))
        self.assertTrue(isinstance(task_api.load(context, manager),
                                   MongoDbTaskManagerAPI))
