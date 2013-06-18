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
from testtools import TestCase
from testtools.matchers import Equals
from trove.backup.service import BackupController
from trove.common import apischema


class TestBackupController(TestCase):
    def test_validate_create_complete(self):
        body = {"backup": {"instance": "d6338c9c-3cc8-4313-b98f-13cc0684cf15",
                           "name": "testback-backup"}}
        controller = BackupController()
        schema = controller.get_schema('create', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertTrue(validator.is_valid(body))

    def test_validate_create_invalid_uuid(self):
        invalid_uuid = "ead-edsa-e23-sdf-23"
        body = {"backup": {"instance": invalid_uuid,
                           "name": "testback-backup"}}
        controller = BackupController()
        schema = controller.get_schema('create', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertFalse(validator.is_valid(body))
        errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        self.assertThat(errors[0].message,
                        Equals("'%s' does not match '%s'" %
                               (invalid_uuid, apischema.uuid['pattern'])))
