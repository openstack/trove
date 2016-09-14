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

import jsonschema
from testtools.matchers import Is, Equals

from trove.module.service import ModuleController
from trove.tests.unittests import trove_testtools


class TestModuleController(trove_testtools.TestCase):
    def setUp(self):
        super(TestModuleController, self).setUp()
        self.controller = ModuleController()
        self.module = {
            "module": {
                "name": 'test_module',
                "module_type": 'test',
                "contents": 'my_contents\n',
            }
        }

    def test_get_schema_create(self):
        schema = self.controller.get_schema('create', {'module': {}})
        self.assertIsNotNone(schema)
        self.assertTrue('module' in schema['properties'])

    def test_validate_create_complete(self):
        body = self.module
        schema = self.controller.get_schema('create', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertTrue(validator.is_valid(body))

    def test_validate_create_blankname(self):
        body = self.module
        body['module']['name'] = "     "
        schema = self.controller.get_schema('create', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertFalse(validator.is_valid(body))
        errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        self.assertThat(len(errors), Is(1))
        self.assertThat(errors[0].message,
                        Equals("'     ' does not match '^.*[0-9a-zA-Z]+.*$'"))

    def test_validate_create_invalid_name(self):
        body = self.module
        body['module']['name'] = "$#$%^^"
        schema = self.controller.get_schema('create', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertFalse(validator.is_valid(body))
        errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        self.assertEqual(1, len(errors))
        self.assertIn("'$#$%^^' does not match '^.*[0-9a-zA-Z]+.*$'",
                      errors[0].message)
