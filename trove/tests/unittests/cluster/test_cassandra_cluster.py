# Copyright 2016 Tesora Inc.
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

from mock import ANY
from mock import MagicMock
from mock import Mock
from mock import patch

from trove.cluster import models
from trove.common.strategies.cluster.experimental.cassandra.api \
    import CassandraCluster
from trove.common.strategies.cluster.experimental.cassandra.taskmanager \
    import CassandraClusterTasks
from trove.instance import models as inst_models
from trove.quota import quota
from trove.tests.unittests import trove_testtools


class ClusterTest(trove_testtools.TestCase):

    def setUp(self):
        super(ClusterTest, self).setUp()
        self.context = trove_testtools.TroveTestContext(self)

    def tearDown(self):
        super(ClusterTest, self).tearDown()

    @patch.object(inst_models.Instance, 'create')
    @patch.object(quota.QUOTAS, 'check_quotas')
    @patch.object(models, 'get_flavors_from_instance_defs')
    @patch.object(models, 'get_required_volume_size', return_value=3)
    def test_create_cluster_instances(self, get_vol_size, _, check_quotas,
                                      inst_create):
        test_instances = [MagicMock(), MagicMock()]
        num_instances = len(test_instances)
        datastore = Mock(manager='cassandra')
        datastore_version = Mock(manager='cassandra')

        with patch.object(CassandraClusterTasks, 'find_cluster_node_ids',
                          return_value=[inst.id for inst in test_instances]):
            CassandraCluster._create_cluster_instances(
                self.context, 'test_cluster_id', 'test_cluster',
                datastore, datastore_version,
                test_instances, None, None)

        check_quotas.assert_called_once_with(
            ANY, instances=num_instances, volumes=get_vol_size.return_value)
        self.assertEqual(num_instances, inst_create.call_count,
                         "Unexpected number of instances created.")

    def test_choose_seed_nodes(self):
        nodes = self._build_mock_nodes(3)

        seeds = CassandraClusterTasks.choose_seed_nodes(nodes)
        self.assertEqual(1, len(seeds),
                         "Only one seed node should be selected for a "
                         "single-rack-single-dc cluster.")

        nodes = self._build_mock_nodes(3)
        nodes[0]['rack'] = 'rack1'
        nodes[1]['rack'] = 'rack2'
        seeds = CassandraClusterTasks.choose_seed_nodes(nodes)
        self.assertEqual(2, len(seeds),
                         "There should be exactly two seed nodes. "
                         "One from each rack.")

        nodes = self._build_mock_nodes(3)
        nodes[0]['rack'] = 'rack1'
        nodes[1]['rack'] = 'rack2'
        nodes[2]['dc'] = 'dc2'
        seeds = CassandraClusterTasks.choose_seed_nodes(nodes)
        self.assertEqual(3, len(seeds),
                         "There should be exactly three seed nodes. "
                         "One from each rack and data center.")

    def _build_mock_nodes(self, num_nodes):
        nodes = []
        for _ in range(num_nodes):
            mock_instance = MagicMock()
            nodes.append({'instance': mock_instance,
                          'guest': MagicMock(),
                          'id': mock_instance.id,
                          'ip': '%s_IP' % mock_instance.id,
                          'dc': 'dc1',
                          'rack': 'rack1'
                          })
        return nodes
