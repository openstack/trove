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
from testtools import TestCase
from trove.common import cfg
from trove.instance.views import get_ip_address


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
