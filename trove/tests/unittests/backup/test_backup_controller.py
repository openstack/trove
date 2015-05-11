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
import jsonschema
from testtools.matchers import Equals
from trove.backup.service import BackupController
from trove.common import apischema
from trove.tests.unittests import trove_testtools


class TestBackupController(trove_testtools.TestCase):

    def setUp(self):
        super(TestBackupController, self).setUp()
        self.uuid = "d6338c9c-3cc8-4313-b98f-13cc0684cf15"
        self.invalid_uuid = "ead-edsa-e23-sdf-23"
        self.controller = BackupController()

    def test_validate_create_complete(self):
        body = {"backup": {"instance": self.uuid,
                           "name": "testback-backup"}}
        schema = self.controller.get_schema('create', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertTrue(validator.is_valid(body))

    def test_validate_create_with_blankname(self):
        body = {"backup": {"instance": self.uuid,
                           "name": ' '}}
        schema = self.controller.get_schema('create', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertFalse(validator.is_valid(body))
        errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        self.assertEqual(1, len(errors))
        self.assertIn("' ' does not match '^.*[0-9a-zA-Z]+.*$'",
                      errors[0].message)

    def test_validate_create_with_invalidname(self):
        body = {"backup": {"instance": self.uuid,
                           "name": '$#@&?'}}
        schema = self.controller.get_schema('create', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertFalse(validator.is_valid(body))
        errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        self.assertEqual(1, len(errors))
        self.assertIn("'$#@&?' does not match '^.*[0-9a-zA-Z]+.*$'",
                      errors[0].message)

    def test_validate_create_invalid_uuid(self):
        body = {"backup": {"instance": self.invalid_uuid,
                           "name": "testback-backup"}}
        schema = self.controller.get_schema('create', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertFalse(validator.is_valid(body))
        errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        self.assertThat(errors[0].message,
                        Equals("'%s' does not match '%s'" %
                               (self.invalid_uuid, apischema.uuid['pattern'])))

    def test_validate_create_incremental(self):
        body = {"backup": {"instance": self.uuid,
                           "name": "testback-backup",
                           "parent_id": self.uuid}}
        schema = self.controller.get_schema('create', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertTrue(validator.is_valid(body))

    def test_invalid_parent_id(self):
        body = {"backup": {"instance": self.uuid,
                           "name": "testback-backup",
                           "parent_id": self.invalid_uuid}}
        schema = self.controller.get_schema('create', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertFalse(validator.is_valid(body))
        errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        self.assertThat(errors[0].message,
                        Equals("'%s' does not match '%s'" %
                               (self.invalid_uuid, apischema.uuid['pattern'])))
