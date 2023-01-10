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


import configparser
import os
from unittest import mock

import importlib.metadata as importlib_metadata

import trove
from trove.common import extensions
from trove.extensions.routes.mgmt import Mgmt
from trove.extensions.routes.mysql import Mysql
from trove.tests.unittests import trove_testtools

DEFAULT_EXTENSION_MAP = {
    'Mgmt': [Mgmt, extensions.ExtensionDescriptor],
    'MYSQL': [Mysql, extensions.ExtensionDescriptor]
}

INVALID_EXTENSION_MAP = {
    'mgmt': 'trove.extensions.routes.mgmt:Mgmt',
    'mysql': 'trove.extensions.routes.mysql:Mysql',
    'invalid': 'trove.tests.unittests.api.common.'
               'test_extensions:InvalidExtension'
}


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


class TestExtensionLoading(trove_testtools.TestCase):
    def setUp(self):
        super(TestExtensionLoading, self).setUp()

    def tearDown(self):
        super(TestExtensionLoading, self).tearDown()

    def _assert_default_extensions(self, ext_list):
        for alias, ext in ext_list.items():
            for clazz in DEFAULT_EXTENSION_MAP[alias]:
                self.assertIsInstance(ext, clazz, "Improper extension class")

    @mock.patch("stevedore.enabled.EnabledExtensionManager.list_entry_points")
    def test_default_extensions(self, mock_extensions):
        trove_base = os.path.abspath(os.path.join(
            os.path.dirname(trove.__file__), ".."))
        setup_path = "%s/setup.cfg" % trove_base
        # check if we are running as unit test without module installed
        if os.path.isfile(setup_path):
            parser = configparser.ConfigParser()
            parser.read(setup_path)
            entry_points = parser.get(
                'entry_points', extensions.ExtensionManager.EXT_NAMESPACE)
            test_extensions = list()
            for entry in entry_points.split('\n')[1:]:
                name = entry.split("=")[0].strip()
                value = entry.split("=")[1].strip()
                test_extensions.append(importlib_metadata.EntryPoint(
                    name=name,
                    value=value,
                    group=extensions.ExtensionManager.EXT_NAMESPACE))
        mock_extensions.return_value = test_extensions
        extension_mgr = extensions.ExtensionManager()
        self.assertEqual(sorted(DEFAULT_EXTENSION_MAP.keys()),
                         sorted(extension_mgr.extensions.keys()),
                         "Invalid extension names")
        self._assert_default_extensions(extension_mgr.extensions)

    @mock.patch("stevedore.enabled.EnabledExtensionManager.list_entry_points")
    def test_invalid_extension(self, mock_extensions):
        test_extensions = list()
        for k, v in INVALID_EXTENSION_MAP.items():
            test_extensions.append(importlib_metadata.EntryPoint(
                name=k,
                value=v,
                group=extensions.ExtensionManager.EXT_NAMESPACE))
        mock_extensions.return_value = test_extensions
        extension_mgr = extensions.ExtensionManager()
        self.assertEqual(2, len(extension_mgr.extensions),
                         "Loaded invalid extensions")
        self._assert_default_extensions(extension_mgr.extensions)
