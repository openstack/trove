# Copyright 2014 Rackspace
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
import jsonschema
from unittest.mock import MagicMock

from trove.common import configurations
from trove.common.exception import UnprocessableEntity
from trove.configuration.service import ConfigurationsController
from trove.extensions.mgmt.configuration import service
from trove.tests.unittests import trove_testtools


class TestConfigurationParser(trove_testtools.TestCase):

    def setUp(self):
        super(TestConfigurationParser, self).setUp()

    def test_parse_my_cnf_correctly(self):
        config = """
        [mysqld]
        pid-file = /var/run/mysqld/mysqld.pid
        connect_timeout = 15
        # we need to test no value params
        skip-external-locking
        ;another comment
        !includedir /etc/mysql/conf.d/
        """
        cfg_parser = configurations.MySQLConfParser(config)
        parsed = cfg_parser.parse()
        d_parsed = dict(parsed)
        self.assertIsNotNone(d_parsed)
        self.assertEqual("/var/run/mysqld/mysqld.pid", d_parsed["pid-file"])
        self.assertEqual(15, d_parsed["connect_timeout"])
        self.assertEqual('1', d_parsed["skip-external-locking"])


class TestConfigurationController(trove_testtools.TestCase):

    def setUp(self):
        super(TestConfigurationController, self).setUp()
        self.controller = ConfigurationsController()

    def _test_validate_configuration_with_action(self, body, action,
                                                 is_valid=True):
        schema = self.controller.get_schema(action, body)
        self.assertIsNotNone(schema)
        validator = jsonschema.Draft4Validator(schema)
        if is_valid:
            self.assertTrue(validator.is_valid(body))
        else:
            self.assertFalse(validator.is_valid(body))
            errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
            error_messages = [error.message for error in errors]
            return error_messages

    def test_validate_create_configuration(self):
        body = {
            "configuration": {
                "values": {},
                "name": "test",
                "datastore": {
                    "type": "test_type",
                    "version": "test_version"
                }
            }
        }
        self._test_validate_configuration_with_action(body, action='create')

    def test_validate_create_configuration_no_datastore(self):
        body = {
            "configuration": {
                "values": {},
                "name": "test"
            }
        }
        self._test_validate_configuration_with_action(body, action='create')

    def test_validate_create_invalid_values_param(self):
        body = {
            "configuration": {
                "values": '',
                "name": "test",
                "datastore": {
                    "type": "test_type",
                    "version": "test_version"
                }
            }
        }
        error_messages = (
            self._test_validate_configuration_with_action(body,
                                                          action='create',
                                                          is_valid=False))
        self.assertIn("'' is not of type 'object'", error_messages)

    def test_validate_create_invalid_name_param(self):
        body = {
            "configuration": {
                "values": {},
                "name": "",
                "datastore": {
                    "type": "test_type",
                    "version": "test_version"
                }
            }
        }
        error_messages = (
            self._test_validate_configuration_with_action(body,
                                                          action='create',
                                                          is_valid=False))
        self.assertIn("'' is too short", error_messages)

    def test_validate_edit_configuration(self):
        body = {
            "configuration": {
                "values": {}
            }
        }
        self._test_validate_configuration_with_action(body, action="edit")

    def _test_validate_configuration(self, input_values, config_rules=None):
        if config_rules is None:
            config_val1 = MagicMock()
            config_val1.name = 'max_connections'
            config_val1.restart_required = 'false'
            config_val1.datastore_version_id = 5.5
            config_val1.max = 1
            config_val1.min = 0
            config_val1.data_type = 'integer'
            config_rules = [config_val1]

        data_version = MagicMock()
        data_version.id = 42
        data_version.name = 5.5
        data_version.datastore_name = 'test'

        self.assertRaises(UnprocessableEntity,
                          ConfigurationsController._validate_configuration,
                          input_values,
                          data_version,
                          config_rules)

    def test_validate_configuration_with_no_rules(self):
        self._test_validate_configuration({'max_connections': 5}, [])

    def test_validate_configuration_with_invalid_param(self):
        self._test_validate_configuration({'test': 5})

    def test_validate_configuration_with_invalid_type(self):
        self._test_validate_configuration({'max_connections': '1'})

    def test_validate_configuration_with_invalid_max(self):
        self._test_validate_configuration({'max_connections': 5})

    def test_validate_configuration_with_invalid_min(self):
        self._test_validate_configuration({'max_connections': -1})

    def test_validate_long_value(self):
        config_val1 = MagicMock()
        config_val1.name = 'myisam_sort_buffer_size'
        config_val1.max_size = 18446744073709551615
        config_val1.min_size = 4096
        config_val1.data_type = 'integer'
        config_rules = [config_val1]

        ConfigurationsController._validate_configuration(
            {'myisam_sort_buffer_size': 18446744073709551615},
            None, config_rules)


class TestConfigurationsParameterController(trove_testtools.TestCase):

    def setUp(self):
        super(TestConfigurationsParameterController, self).setUp()
        self.controller = service.ConfigurationsParameterController()

    def _test_validate_configuration_with_action(self, body, action,
                                                 is_valid=True):
        schema = self.controller.get_schema(action, body)
        self.assertIsNotNone(schema)
        validator = jsonschema.Draft4Validator(schema)
        if is_valid:
            self.assertTrue(validator.is_valid(body))
        else:
            self.assertFalse(validator.is_valid(body))
            errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
            error_messages = [error.message for error in errors]
            return error_messages

    def test_validate_create_configuration_param(self):
        body = {
            'configuration-parameter': {
                'name': 'test',
                'restart_required': 1,
                'data_type': 'string',
                'min': '0',
                'max': '255'
            }
        }

        self._test_validate_configuration_with_action(body, action='create')

    def test_validate_create_invalid_restart_required(self):
        body = {
            'configuration-parameter': {
                'name': 'test',
                'restart_required': 5,
                'data_type': 'string',
                'min': 0,
                'max': 255
            }
        }
        error_messages = (
            self._test_validate_configuration_with_action(body,
                                                          action='create',
                                                          is_valid=False))
        self.assertIn("5 is greater than the maximum of 1", error_messages)
        self.assertIn("0 is not of type 'string'", error_messages)
        self.assertIn("255 is not of type 'string'", error_messages)

    def test_validate_create_invalid_restart_required_2(self):
        body = {
            'configuration-parameter': {
                'name': 'test',
                'restart_required': -1,
                'data_type': 'string',
                'min': '0',
                'max': '255'
            }
        }
        error_messages = (
            self._test_validate_configuration_with_action(body,
                                                          action='create',
                                                          is_valid=False))
        self.assertIn("-1 is less than the minimum of 0", error_messages)

    def test_validate_create_invalid_restart_required_3(self):
        body = {
            'configuration-parameter': {
                'name': 'test',
                'restart_required': 'yes',
                'data_type': 'string',
                'min': '0',
                'max': '255'
            }
        }
        error_messages = (
            self._test_validate_configuration_with_action(body,
                                                          action='create',
                                                          is_valid=False))
        self.assertIn("'yes' is not of type 'integer'", error_messages)
