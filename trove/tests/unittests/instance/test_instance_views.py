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
from unittest.mock import Mock
from trove.common import cfg
from trove.instance.views import InstanceDetailView
from trove.instance.views import InstanceView
from trove.tests.unittests import trove_testtools

CONF = cfg.CONF


class InstanceViewsTest(trove_testtools.TestCase):

    def setUp(self):
        super(InstanceViewsTest, self).setUp()
        self.addresses = {"private": [{"addr": "123.123.123.123"}],
                          "internal": [{"addr": "10.123.123.123"}],
                          "public": [{"addr": "15.123.123.123"}]}
        self.orig_ip_regex = CONF.ip_regex

    def tearDown(self):
        super(InstanceViewsTest, self).tearDown()
        CONF.ip_regex = self.orig_ip_regex


class InstanceDetailViewTest(trove_testtools.TestCase):

    def setUp(self):
        super(InstanceDetailViewTest, self).setUp()
        self.build_links_method = InstanceView._build_links
        self.build_config_method = InstanceDetailView._build_configuration_info
        InstanceView._build_links = Mock()
        InstanceDetailView._build_configuration_info = Mock()
        self.instance = Mock()
        self.instance.created = 'Yesterday'
        self.instance.updated = 'Now'
        self.instance.datastore_version = Mock()
        self.instance.datastore_version.name = 'mysql_test_version'
        self.instance.datastore_version.manager = 'mysql'
        self.instance.hostname = 'test.trove.com'
        self.ip = "1.2.3.4"
        self.instance.addresses = {"private": [{"addr": self.ip}]}
        self.instance.volume_used = '3'
        self.instance.root_password = 'iloveyou'
        self.instance.get_visible_ip_addresses.return_value = [
            {'type': 'private', 'address': '1.2.3.4'}]
        self.instance.slave_of_id = None
        self.instance.slaves = []
        self.instance.locality = 'affinity'
        self.instance.server_id = 'server_abc'
        self.instance.volume_id = 'volume_abc'
        self.fault_message = 'Error'
        self.fault_details = 'details'
        self.fault_date = 'now'
        self.instance.fault = Mock()
        self.instance.fault.message = self.fault_message
        self.instance.fault.details = self.fault_details
        self.instance.fault.updated = self.fault_date
        self.context = trove_testtools.TroveTestContext(self)
        self.req = Mock()
        self.req.environ = Mock()
        self.req.environ.__getitem__ = Mock(return_value=self.context)

    def tearDown(self):
        super(InstanceDetailViewTest, self).tearDown()
        InstanceView._build_links = self.build_links_method
        InstanceDetailView._build_configuration_info = self.build_config_method

    def test_data_hostname(self):
        view = InstanceDetailView(self.instance, self.req)
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
        view = InstanceDetailView(self.instance, self.req)
        result = view.data()
        self.assertEqual(self.instance.created, result['instance']['created'])
        self.assertEqual(self.instance.updated, result['instance']['updated'])
        self.assertEqual(self.instance.datastore_version.name,
                         result['instance']['datastore']['version'])
        self.assertNotIn('hostname', result['instance'])
        self.assertEqual([self.ip], result['instance']['ip'])
        self.assertEqual(self.ip,
                         result['instance']['addresses'][0]['address'])

    def test_locality(self):
        self.instance.hostname = None
        view = InstanceDetailView(self.instance, self.req)
        result = view.data()
        self.assertEqual(self.instance.locality,
                         result['instance']['locality'])

    def test_fault(self):
        view = InstanceDetailView(self.instance, self.req)
        result = view.data()
        self.assertEqual(self.fault_message,
                         result['instance']['fault']['message'])
        self.assertEqual(self.fault_details,
                         result['instance']['fault']['details'])
        self.assertEqual(self.fault_date,
                         result['instance']['fault']['created'])

    def test_admin_view(self):
        self.context.is_admin = True
        view = InstanceDetailView(self.instance, self.req)
        result = view.data()
        self.assertIn('server_id', result['instance'])
        self.assertIn('volume_id', result['instance'])

    def test_non_admin_view(self):
        self.context.is_admin = False
        view = InstanceDetailView(self.instance, self.req)
        result = view.data()
        self.assertNotIn('server_id', result['instance'])
        self.assertNotIn('volume_id', result['instance'])
