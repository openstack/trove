#    Copyright 2014 Rackspace Hosting
#    Copyright 2014 Hewlett-Packard Development Company, L.P.
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
from testtools import TestCase
from trove.common import cfg
from trove.instance.models import filter_ips
from trove.instance.models import DBInstance
from trove.instance.models import Instance
from trove.instance.models import SimpleInstance
from trove.instance.tasks import InstanceTasks

CONF = cfg.CONF


class SimpleInstanceTest(TestCase):

    def setUp(self):
        super(SimpleInstanceTest, self).setUp()
        db_info = DBInstance(InstanceTasks.BUILDING, name="TestInstance")
        self.instance = SimpleInstance(None, db_info, "BUILD",
                                       ds_version=Mock(), ds=Mock())
        db_info.addresses = {"private": [{"addr": "123.123.123.123"}],
                             "internal": [{"addr": "10.123.123.123"}],
                             "public": [{"addr": "15.123.123.123"}]}
        self.orig_conf = CONF.network_label_regex
        self.orig_ip_regex = CONF.ip_regex

    def tearDown(self):
        super(SimpleInstanceTest, self).tearDown()
        CONF.network_label_regex = self.orig_conf
        CONF.ip_start = None
        CONF.ip_regex = self.orig_ip_regex

    def test_get_root_on_create(self):
        root_on_create_val = Instance.get_root_on_create('redis')
        self.assertFalse(root_on_create_val)

    def test_filter_ips(self):
        CONF.network_label_regex = '.*'
        CONF.ip_regex = '^(15.|123.)'
        ip = self.instance.get_visible_ip_addresses()
        ip = filter_ips(ip, CONF.ip_regex)
        self.assertTrue(len(ip) == 2)
        self.assertTrue('123.123.123.123' in ip)
        self.assertTrue('15.123.123.123' in ip)

    def test_one_network_label_exact(self):
        CONF.network_label_regex = '^internal$'
        ip = self.instance.get_visible_ip_addresses()
        self.assertEqual(['10.123.123.123'], ip)

    def test_one_network_label(self):
        CONF.network_label_regex = 'public'
        ip = self.instance.get_visible_ip_addresses()
        self.assertEqual(['15.123.123.123'], ip)

    def test_two_network_labels(self):
        CONF.network_label_regex = '^(private|public)$'
        ip = self.instance.get_visible_ip_addresses()
        self.assertTrue(len(ip) == 2)
        self.assertTrue('123.123.123.123' in ip)
        self.assertTrue('15.123.123.123' in ip)

    def test_all_network_labels(self):
        CONF.network_label_regex = '.*'
        ip = self.instance.get_visible_ip_addresses()
        self.assertTrue(len(ip) == 3)
        self.assertTrue('10.123.123.123' in ip)
        self.assertTrue('123.123.123.123' in ip)
        self.assertTrue('15.123.123.123' in ip)
