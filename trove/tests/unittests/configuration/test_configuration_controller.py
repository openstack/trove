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
from testtools import TestCase
from trove.configuration.service import ConfigurationsController
from trove.extensions.mgmt.configuration import service
from trove.common import configurations


class TestConfigurationParser(TestCase):
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
        self.assertEqual(d_parsed["pid-file"], "/var/run/mysqld/mysqld.pid")
        self.assertEqual(d_parsed["connect_timeout"], '15')
        self.assertEqual(d_parsed["skip-external-locking"], '1')


class TestConfigurationController(TestCase):
    def setUp(self):
        super(TestConfigurationController, self).setUp()
        self.controller = ConfigurationsController()

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
        schema = self.controller.get_schema('create', body)
        self.assertIsNotNone(schema)
        validator = jsonschema.Draft4Validator(schema)
        self.assertTrue(validator.is_valid(body))

    def test_validate_create_configuration_no_datastore(self):
        body = {
            "configuration": {
                "values": {},
                "name": "test"
            }
        }
        schema = self.controller.get_schema('create', body)
        self.assertIsNotNone(schema)
        validator = jsonschema.Draft4Validator(schema)
        self.assertTrue(validator.is_valid(body))

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
        schema = self.controller.get_schema('create', body)
        self.assertIsNotNone(schema)
        validator = jsonschema.Draft4Validator(schema)
        self.assertFalse(validator.is_valid(body))
        errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        error_messages = [error.message for error in errors]
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
        schema = self.controller.get_schema('create', body)
        self.assertIsNotNone(schema)
        validator = jsonschema.Draft4Validator(schema)
        self.assertFalse(validator.is_valid(body))
        errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        error_messages = [error.message for error in errors]
        self.assertIn("'' is too short", error_messages)

    def test_validate_edit_configuration(self):
        body = {
            "configuration": {
                "values": {}
            }
        }
        schema = self.controller.get_schema('edit', body)
        self.assertIsNotNone(schema)
        validator = jsonschema.Draft4Validator(schema)
        self.assertTrue(validator.is_valid(body))


class TestConfigurationsParameterController(TestCase):
    def setUp(self):
        super(TestConfigurationsParameterController, self).setUp()
        self.controller = service.ConfigurationsParameterController()

    def test_validate_create_configuration_param(self):
        body = {
            'configuration-parameter': {
                'name': 'test',
                'restart_required': 1,
                'data_type': 'string',
                'min_size': '0',
                'max_size': '255'
            }
        }
        schema = self.controller.get_schema('create', body)
        self.assertIsNotNone(schema)
        validator = jsonschema.Draft4Validator(schema)
        self.assertTrue(validator.is_valid(body))

    def test_validate_create_invalid_restart_required(self):
        body = {
            'configuration-parameter': {
                'name': 'test',
                'restart_required': 5,
                'data_type': 'string',
                'min_size': 0,
                'max_size': 255
            }
        }
        schema = self.controller.get_schema('create', body)
        self.assertIsNotNone(schema)
        validator = jsonschema.Draft4Validator(schema)
        self.assertFalse(validator.is_valid(body))
        errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        error_messages = [error.message for error in errors]
        self.assertIn("5 is greater than the maximum of 1", error_messages)
        self.assertIn("0 is not of type 'string'", error_messages)
        self.assertIn("255 is not of type 'string'", error_messages)

    def test_validate_create_invalid_restart_required_2(self):
        body = {
            'configuration-parameter': {
                'name': 'test',
                'restart_required': -1,
                'data_type': 'string',
                'min_size': '0',
                'max_size': '255'
            }
        }
        schema = self.controller.get_schema('create', body)
        self.assertIsNotNone(schema)
        validator = jsonschema.Draft4Validator(schema)
        self.assertFalse(validator.is_valid(body))
        errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        error_messages = [error.message for error in errors]
        self.assertIn("-1 is less than the minimum of 0", error_messages)

    def test_validate_create_invalid_restart_required_3(self):
        body = {
            'configuration-parameter': {
                'name': 'test',
                'restart_required': 'yes',
                'data_type': 'string',
                'min_size': '0',
                'max_size': '255'
            }
        }
        schema = self.controller.get_schema('create', body)
        self.assertIsNotNone(schema)
        validator = jsonschema.Draft4Validator(schema)
        self.assertFalse(validator.is_valid(body))
        errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        error_messages = [error.message for error in errors]
        self.assertIn("'yes' is not of type 'integer'", error_messages)
