# Copyright 2016 Tesora, Inc.
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

from unittest.mock import Mock, patch
from trove.flavor.views import FlavorView
from trove.tests.unittests import trove_testtools


class FlavorViewsTest(trove_testtools.TestCase):

    def setUp(self):
        super(FlavorViewsTest, self).setUp()
        self.flavor = Mock()
        self.flavor.id = 10
        self.flavor.str_id = '10'
        self.flavor.name = 'test_flavor'
        self.flavor.ram = 512
        self.links = 'my_links'
        self.flavor.vcpus = '10'
        self.flavor.disk = '0'
        self.flavor.ephemeral = '0'

    def tearDown(self):
        super(FlavorViewsTest, self).tearDown()

    def test_data(self):
        data = [
            {'flavor_id': 10,
             'expected_id': 10,
             'expected_str_id': '10'},
            {'flavor_id': 'uuid-10',
             'expected_id': None,
             'expected_str_id': 'uuid-10'},
            {'flavor_id': '02',
             'expected_id': None,
             'expected_str_id': '02'},
        ]

        for datum in data:
            flavor_id = datum['flavor_id']
            expected_id = datum['expected_id']
            expected_str_id = datum['expected_str_id']
            msg = "Testing flavor_id: %s - " % flavor_id
            self.flavor.id = flavor_id
            with patch.object(FlavorView, '_build_links',
                              Mock(return_value=(self.links))):
                view = FlavorView(self.flavor)
                result = view.data()
                self.assertEqual(expected_id, result['flavor']['id'],
                                 msg + 'invalid id')
                self.assertEqual(expected_str_id, result['flavor']['str_id'],
                                 msg + 'invalid str_id')
                self.assertEqual(self.flavor.name, result['flavor']['name'],
                                 msg + 'invalid name')
                self.assertEqual(self.flavor.ram, result['flavor']['ram'],
                                 msg + 'invalid ram')
                self.assertEqual(self.flavor.vcpus, result['flavor']['vcpus'],
                                 msg + 'invalid vcpus')
                self.assertEqual(self.flavor.disk, result['flavor']['disk'],
                                 msg + 'invalid disk')
                self.assertEqual(self.flavor.ephemeral,
                                 result['flavor']['ephemeral'],
                                 msg + 'invalid ephemeral')
                self.assertEqual(self.links, result['flavor']['links'],
                                 msg + 'invalid links')
