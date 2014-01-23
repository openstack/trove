# Copyright 2013 Hewlett-Packard Development Company, L.P.
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
from testtools import TestCase
from trove.common import cfg
from trove.instance.views import get_ip_address
from trove.instance.views import filter_ips
from trove.instance.views import InstanceView
from trove.instance.views import InstanceDetailView

CONF = cfg.CONF


class InstanceViewsTest(TestCase):

    def setUp(self):
        super(InstanceViewsTest, self).setUp()
        self.addresses = {"private": [{"addr": "123.123.123.123"}],
                          "internal": [{"addr": "10.123.123.123"}],
                          "public": [{"addr": "15.123.123.123"}]}
        self.orig_conf = CONF.network_label_regex

    def tearDown(self):
        super(InstanceViewsTest, self).tearDown()
        CONF.network_label_regex = self.orig_conf
        CONF.ip_start = None

    def test_one_network_label_exact(self):
        CONF.network_label_regex = '^internal$'
        ip = get_ip_address(self.addresses)
        self.assertEqual(['10.123.123.123'], ip)

    def test_one_network_label(self):
        CONF.network_label_regex = 'public'
        ip = get_ip_address(self.addresses)
        self.assertEqual(['15.123.123.123'], ip)

    def test_two_network_labels(self):
        CONF.network_label_regex = '^(private|public)$'
        ip = get_ip_address(self.addresses)
        self.assertTrue(len(ip) == 2)
        self.assertTrue('123.123.123.123' in ip)
        self.assertTrue('15.123.123.123' in ip)

    def test_all_network_labels(self):
        CONF.network_label_regex = '.*'
        ip = get_ip_address(self.addresses)
        self.assertTrue(len(ip) == 3)
        self.assertTrue('10.123.123.123' in ip)
        self.assertTrue('123.123.123.123' in ip)
        self.assertTrue('15.123.123.123' in ip)

    def test_filter_ips(self):
        CONF.network_label_regex = '.*'
        CONF.ip_regex = '^(15.|123.)'
        ip = get_ip_address(self.addresses)
        ip = filter_ips(ip, CONF.ip_regex)
        self.assertTrue(len(ip) == 2)
        self.assertTrue('123.123.123.123' in ip)
        self.assertTrue('15.123.123.123' in ip)


class InstanceDetailViewTest(TestCase):

    def setUp(self):
        super(InstanceDetailViewTest, self).setUp()
        self.build_links_method = InstanceView._build_links
        self.build_flavor_links_method = InstanceView._build_flavor_links
        InstanceView._build_links = Mock()
        InstanceView._build_flavor_links = Mock()
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

    def tearDown(self):
        super(InstanceDetailViewTest, self).tearDown()
        InstanceView._build_links = self.build_links_method
        InstanceView._build_flavor_links = self.build_flavor_links_method

    def test_data_hostname(self):
        view = InstanceDetailView(self.instance, Mock())
        result = view.data()
        self.assertEqual(self.instance.created, result['instance']['created'])
        self.assertEqual(self.instance.updated, result['instance']['updated'])
        self.assertEqual(self.instance.datastore_version.name,
                         result['instance']['datastore']['version'])
        self.assertEqual(self.instance.hostname,
                         result['instance']['hostname'])
        self.assertNotIn('ip', result['instance'])

    def test_data_ip(self):
        self.instance.hostname = None
        view = InstanceDetailView(self.instance, Mock())
        result = view.data()
        self.assertEqual(self.instance.created, result['instance']['created'])
        self.assertEqual(self.instance.updated, result['instance']['updated'])
        self.assertEqual(self.instance.datastore_version.name,
                         result['instance']['datastore']['version'])
        self.assertNotIn('hostname', result['instance'])
        self.assertEqual([self.ip], result['instance']['ip'])
