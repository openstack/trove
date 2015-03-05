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

from mock import Mock
from mock import patch
from testtools import TestCase
from trove.cluster.views import ClusterInstanceDetailView
from trove.cluster.views import ClusterView
from trove.cluster.views import load_view
from trove.common import cfg
from trove.common.strategies.cluster.experimental.mongodb.api import (
    MongoDbClusterView)

CONF = cfg.CONF


class ClusterViewTest(TestCase):

    def setUp(self):
        super(ClusterViewTest, self).setUp()
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

    @patch.object(ClusterView, 'build_instances', return_value=('10.0.0.1',
                                                                []))
    @patch.object(ClusterView, '_build_flavor_info')
    @patch.object(ClusterView, '_build_links')
    def test_load_view(self, *args):
        cluster = Mock()
        cluster.datastore_version.manager = 'mongodb'
        view = load_view(cluster, Mock())
        self.assertTrue(isinstance(view, MongoDbClusterView))


class ClusterInstanceDetailViewTest(TestCase):

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
