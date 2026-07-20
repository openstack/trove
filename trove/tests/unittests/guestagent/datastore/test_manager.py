# Copyright 2026 PS Cloud
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.
from trove.common import ssl
from trove.guestagent.datastore import manager as base_manager
from trove.tests.unittests import trove_testtools


class TestManager(trove_testtools.TestCase):
    def setUp(self):
        super(TestManager, self).setUp()
        self.manager = base_manager.Manager('test')

    def test_ssl_mode_at_least(self):
        self.assertTrue(self.manager.ssl_mode_at_least(
            ssl.MODE_BASIC, ssl.MODE_BASIC))
        self.assertTrue(self.manager.ssl_mode_at_least(
            ssl.MODE_ENFORCED, ssl.MODE_BASIC))
        self.assertTrue(self.manager.ssl_mode_at_least(
            ssl.MODE_ENFORCED, ssl.MODE_ENFORCED))
        self.assertTrue(self.manager.ssl_mode_at_least(
            ssl.MODE_MTLS, ssl.MODE_ENFORCED))
        self.assertFalse(self.manager.ssl_mode_at_least(
            ssl.MODE_BASIC, ssl.MODE_MTLS))
        self.assertFalse(self.manager.ssl_mode_at_least(
            'invalid', ssl.MODE_BASIC))
        self.assertFalse(self.manager.ssl_mode_at_least(
            ssl.MODE_BASIC, 'invalid'))
        self.assertFalse(self.manager.ssl_mode_at_least(
            None, ssl.MODE_BASIC))
