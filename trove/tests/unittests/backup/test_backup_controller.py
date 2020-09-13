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
from unittest import mock
import uuid

import jsonschema
from testtools.matchers import Equals

from trove.backup import models
from trove.backup import state
from trove.backup.service import BackupController
from trove.common import apischema
from trove.common import context
from trove.common import wsgi
from trove.tests.unittests import trove_testtools
from trove.tests.unittests.util import util


class TestBackupController(trove_testtools.TestCase):
    def setUp(self):
        super(TestBackupController, self).setUp()
        self.uuid = "d6338c9c-3cc8-4313-b98f-13cc0684cf15"
        self.invalid_uuid = "ead-edsa-e23-sdf-23"
        self.controller = BackupController()
        self.context = context.TroveContext(project_id=str(uuid.uuid4()))
        util.init_db()

    def tearDown(self):
        super(TestBackupController, self).tearDown()
        backups = models.DBBackup.find_all(tenant_id=self.context.project_id)
        for backup in backups:
            backup.delete()

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

    def test_list_by_project(self):
        req = mock.MagicMock(GET={'project_id': self.context.project_id},
                             environ={wsgi.CONTEXT_KEY: self.context},
                             url='http://localhost')
        instance_id = str(uuid.uuid4())
        backup_name = str(uuid.uuid4())
        location = 'https://object-storage.com/tenant/database_backups/backup'
        models.DBBackup.create(tenant_id=self.context.project_id,
                               name=backup_name,
                               state=state.BackupState.NEW,
                               instance_id=instance_id,
                               deleted=False,
                               size=2.0,
                               location=location)

        res = self.controller.index(req, 'fake_tenant_id')

        self.assertEqual(200, res.status)
        backups = res.data(None)['backups']
        self.assertGreaterEqual(len(backups), 1)
        our_backup = None
        for backup in backups:
            if backup['name'] == backup_name:
                our_backup = backup
                break
        self.assertIsNotNone(our_backup)
        expected = {
            'name': backup_name,
            'locationRef': location,
            'instance_id': instance_id,
            'size': 2.0,
            'status': 'NEW',
        }
        self.assertTrue(
            set(expected.items()).issubset(set(our_backup.items()))
        )

        # Get backups of unknown project
        req = mock.MagicMock(GET={'project_id': str(uuid.uuid4())},
                             environ={wsgi.CONTEXT_KEY: self.context},
                             url='http://localhost')

        res = self.controller.index(req, 'fake_tenant_id')

        self.assertEqual(200, res.status)
        backups = res.data(None)['backups']
        self.assertEqual(0, len(backups))
