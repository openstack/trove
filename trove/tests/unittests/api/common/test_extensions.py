# Copyright 2014 IBM Corp.
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


import mock
import pkg_resources
import testtools

from trove.common import extensions
from trove.extensions.routes.account import Account
from trove.extensions.routes.mgmt import Mgmt
from trove.extensions.routes.mysql import Mysql
from trove.extensions.routes.security_group import Security_group

DEFAULT_EXTENSION_MAP = {
    'Account': [Account, extensions.ExtensionDescriptor],
    'Mgmt': [Mgmt, extensions.ExtensionDescriptor],
    'MYSQL': [Mysql, extensions.ExtensionDescriptor],
    'SecurityGroup': [Security_group, extensions.ExtensionDescriptor]
}

EP_TEXT = '''
account = trove.extensions.routes.account:Account
mgmt = trove.extensions.routes.mgmt:Mgmt
mysql = trove.extensions.routes.mysql:Mysql
security_group = trove.extensions.routes.security_group:Security_group
invalid = trove.tests.unittests.api.common.test_extensions:InvalidExtension
'''


class InvalidExtension(object):
    def get_name(self):
        return "Invalid"

    def get_description(self):
        return "Invalid Extension"

    def get_alias(self):
        return "Invalid"

    def get_namespace(self):
        return "http://TBD"

    def get_updated(self):
        return "2014-08-14T13:25:27-06:00"

    def get_resources(self):
        return []


class TestExtensionLoading(testtools.TestCase):
    def setUp(self):
        super(TestExtensionLoading, self).setUp()

    def tearDown(self):
        super(TestExtensionLoading, self).tearDown()

    def _assert_default_extensions(self, ext_list):
        for alias, ext in ext_list.items():
            for clazz in DEFAULT_EXTENSION_MAP[alias]:
                self.assertIsInstance(ext, clazz, "Improper extension class")

    def test_default_extensions(self):
        extension_mgr = extensions.ExtensionManager()
        self.assertEqual(DEFAULT_EXTENSION_MAP.keys().sort(),
                         extension_mgr.extensions.keys().sort(),
                         "Invalid extension names")
        self._assert_default_extensions(extension_mgr.extensions)

    @mock.patch("pkg_resources.iter_entry_points")
    def test_invalid_extension(self, mock_iter_eps):
        eps = pkg_resources.EntryPoint.parse_group('mock', EP_TEXT)
        mock_iter_eps.return_value = eps.values()
        extension_mgr = extensions.ExtensionManager()
        self.assertEqual(len(extension_mgr.extensions),
                         len(DEFAULT_EXTENSION_MAP.keys()),
                         "Loaded invalid extensions")
        self._assert_default_extensions(extension_mgr.extensions)
