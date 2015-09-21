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

from mock import Mock, patch

from trove.common import exception
from trove.extensions.mgmt.clusters.models import MgmtCluster
from trove.extensions.mgmt.clusters.service import MgmtClusterController
from trove.tests.unittests import trove_testtools


class TestClusterController(trove_testtools.TestCase):
    def setUp(self):
        super(TestClusterController, self).setUp()

        self.context = trove_testtools.TroveTestContext(self)
        self.req = Mock()
        self.req.environ = Mock()
        self.req.environ.__getitem__ = Mock(return_value=self.context)

        mock_cluster1 = Mock()
        mock_cluster1.datastore_version.manager = 'vertica'
        mock_cluster1.instances = []
        mock_cluster1.instances_without_server = []
        mock_cluster2 = Mock()
        mock_cluster2.datastore_version.manager = 'vertica'
        mock_cluster2.instances = []
        mock_cluster2.instances_without_server = []
        self.mock_clusters = [mock_cluster1, mock_cluster2]

        self.controller = MgmtClusterController()

    def tearDown(self):
        super(TestClusterController, self).tearDown()

    def test_get_action_schema(self):
        body = {'do_stuff': {}}
        action_schema = Mock()
        action_schema.get = Mock()

        self.controller.get_action_schema(body, action_schema)
        action_schema.get.assert_called_with('do_stuff', {})

    @patch.object(MgmtCluster, 'load')
    def test_show_cluster(self, mock_cluster_load):
        tenant_id = Mock()
        id = Mock()
        mock_cluster_load.return_value = self.mock_clusters[0]

        self.controller.show(self.req, tenant_id, id)
        mock_cluster_load.assert_called_with(self.context, id)

    @patch.object(MgmtCluster, 'load_all')
    def test_index_cluster(self, mock_cluster_load_all):
        tenant_id = Mock()
        mock_cluster_load_all.return_value = self.mock_clusters

        self.controller.index(self.req, tenant_id)
        mock_cluster_load_all.assert_called_with(self.context, deleted=None)

    @patch.object(MgmtCluster, 'load')
    def test_controller_action_found(self, mock_cluster_load):
        body = {'reset-task': {}}
        tenant_id = Mock()
        id = Mock()
        mock_cluster_load.return_value = self.mock_clusters[0]

        result = self.controller.action(self.req, body, tenant_id, id)
        self.assertEqual(202, result.status)
        self.assertIsNotNone(result.data)

    def test_controller_no_body_action_found(self):
        tenant_id = Mock()
        id = Mock()

        self.assertRaisesRegexp(
            exception.BadRequest, 'Invalid request body.',
            self.controller.action, self.req, None, tenant_id, id)

    @patch.object(MgmtCluster, 'load')
    def test_controller_invalid_action_found(self, mock_cluster_load):
        body = {'do_stuff': {}}
        tenant_id = Mock()
        id = Mock()
        mock_cluster_load.return_value = self.mock_clusters[0]

        self.assertRaisesRegexp(
            exception.BadRequest, 'Invalid cluster action requested.',
            self.controller.action, self.req, body, tenant_id, id)
