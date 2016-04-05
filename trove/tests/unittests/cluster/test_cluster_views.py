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
#

from mock import MagicMock
from mock import Mock
from mock import patch

from trove.cluster.views import ClusterInstanceDetailView
from trove.cluster.views import ClusterView
from trove.cluster.views import load_view
from trove.common import cfg
from trove.common.strategies.cluster.experimental.mongodb.api import (
    MongoDbClusterView)
from trove.tests.unittests import trove_testtools

CONF = cfg.CONF


class ClusterViewTest(trove_testtools.TestCase):

    def setUp(self):
        super(ClusterViewTest, self).setUp()
        self.locality = 'anti-affinity'
        self.cluster = Mock()
        self.cluster.created = 'Yesterday'
        self.cluster.updated = 'Now'
        self.cluster.name = 'cluster1'
        self.cluster.datastore_version = Mock()
        self.cluster.datastore_version.name = 'mysql_test_version'
        self.cluster.instances = []
        self.cluster.instances.append(Mock())
        self.cluster.instances[0].flavor_id = '123'
        self.cluster.instances[0].volume = Mock()
        self.cluster.instances[0].volume.size = 1
        self.cluster.instances[0].slave_of_id = None
        self.cluster.instances[0].slaves = None
        self.cluster.locality = self.locality

    def tearDown(self):
        super(ClusterViewTest, self).tearDown()

    @patch.object(ClusterView, 'build_instances', return_value=('10.0.0.1',
                                                                []))
    @patch.object(ClusterView, '_build_flavor_info')
    @patch.object(ClusterView, '_build_links')
    def test_data(self, mock_build_links,
                  mock_build_flavor_info, mock_build_instances):
        mock_build_instances.return_value = Mock(), Mock()
        view = ClusterView(self.cluster, Mock())
        result = view.data()
        self.assertEqual(self.cluster.created, result['cluster']['created'])
        self.assertEqual(self.cluster.updated, result['cluster']['updated'])
        self.assertEqual(self.cluster.name, result['cluster']['name'])
        self.assertEqual(self.cluster.datastore_version.name,
                         result['cluster']['datastore']['version'])
        self.assertEqual(self.locality, result['cluster']['locality'])

    @patch.object(ClusterView, 'build_instances', return_value=('10.0.0.1',
                                                                []))
    @patch.object(ClusterView, '_build_flavor_info')
    @patch.object(ClusterView, '_build_links')
    def test_load_view(self, *args):
        cluster = Mock()
        cluster.datastore_version.manager = 'mongodb'
        view = load_view(cluster, Mock())
        self.assertIsInstance(view, MongoDbClusterView)

    def test__build_instances(self, *args):
        cluster = Mock()
        cluster.instances = []
        cluster.instances.append(Mock())
        cluster.instances.append(Mock())
        cluster.instances.append(Mock())
        cluster.instances[0].type = 'configsvr'
        cluster.instances[0].get_visible_ip_addresses = lambda: ['1.2.3.4']
        cluster.instances[0].datastore_version.manager = 'mongodb'
        cluster.instances[1].type = 'query_router'
        cluster.instances[1].get_visible_ip_addresses = lambda: ['1.2.3.4']
        cluster.instances[1].datastore_version.manager = 'mongodb'
        cluster.instances[2].type = 'member'
        cluster.instances[2].get_visible_ip_addresses = lambda: ['1.2.3.4']
        cluster.instances[2].datastore_version.manager = 'mongodb'

        def test_case(ip_to_be_published_for,
                      instance_dict_to_be_published_for,
                      number_of_ip_published,
                      number_of_instance_dict_published):
            view = ClusterView(cluster, MagicMock())
            instances, ip_list = view._build_instances(
                ip_to_be_published_for, instance_dict_to_be_published_for)

            self.assertEqual(number_of_ip_published, len(ip_list))
            self.assertEqual(number_of_instance_dict_published, len(instances))

        test_case([], [], 0, 0)
        test_case(['abc'], ['def'], 0, 0)
        test_case(['query_router'], ['member'], 1, 1)
        test_case(['query_router'], ['query_router', 'configsvr', 'member'],
                  1, 3)
        test_case(['query_router', 'member'], ['member'], 2, 1)


class ClusterInstanceDetailViewTest(trove_testtools.TestCase):

    def setUp(self):
        super(ClusterInstanceDetailViewTest, self).setUp()
        self.instance = Mock()
        self.instance.created = 'Yesterday'
        self.instance.updated = 'Now'
        self.instance.datastore_version = Mock()
        self.instance.datastore_version.name = 'mysql_test_version'
        self.instance.hostname = 'test.trove.com'
        self.ip = "1.2.3.4"
        self.instance.addresses = {"private": [{"addr": self.ip}]}
        self.instance.volume_used = '3'
        self.instance.root_password = 'iloveyou'
        self.instance.get_visible_ip_addresses = lambda: ["1.2.3.4"]
        self.instance.slave_of_id = None
        self.instance.slaves = None

    def tearDown(self):
        super(ClusterInstanceDetailViewTest, self).tearDown()

    @patch.object(ClusterInstanceDetailView, '_build_links')
    @patch.object(ClusterInstanceDetailView, '_build_flavor_links')
    @patch.object(ClusterInstanceDetailView, '_build_configuration_info')
    def test_data(self, *args):
        view = ClusterInstanceDetailView(self.instance, Mock())
        result = view.data()
        self.assertEqual(self.instance.created, result['instance']['created'])
        self.assertEqual(self.instance.updated, result['instance']['updated'])
        self.assertEqual(self.instance.datastore_version.name,
                         result['instance']['datastore']['version'])
        self.assertEqual(self.instance.hostname,
                         result['instance']['hostname'])
        self.assertNotIn('ip', result['instance'])

    @patch.object(ClusterInstanceDetailView, '_build_links')
    @patch.object(ClusterInstanceDetailView, '_build_flavor_links')
    @patch.object(ClusterInstanceDetailView, '_build_configuration_info')
    def test_data_ip(self, *args):
        self.instance.hostname = None
        view = ClusterInstanceDetailView(self.instance, Mock())
        result = view.data()
        self.assertEqual(self.instance.created, result['instance']['created'])
        self.assertEqual(self.instance.updated, result['instance']['updated'])
        self.assertEqual(self.instance.datastore_version.name,
                         result['instance']['datastore']['version'])
        self.assertNotIn('hostname', result['instance'])
        self.assertEqual([self.ip], result['instance']['ip'])
