#    Copyright 2012 OpenStack Foundation
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
from trove.guestagent import service
from trove.tests.unittests import trove_testtools


class ServiceTest(trove_testtools.TestCase):
    def setUp(self):
        super(ServiceTest, self).setUp()

    def tearDown(self):
        super(ServiceTest, self).tearDown()

    @patch.object(service.API, '_instance_router')
    def test_app_factory(self, instance_router_mock):
        service.app_factory(Mock)
        self.assertEqual(1, instance_router_mock.call_count)
