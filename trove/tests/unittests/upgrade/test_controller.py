# Copyright 2014 Hewlett-Packard Development Company, L.P.
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
from unittest.mock import Mock, MagicMock, patch

from trove.extensions.mgmt.upgrade.models import UpgradeMessageSender
from trove.extensions.mgmt.upgrade.service import UpgradeController
from trove.tests.unittests import trove_testtools


class TestUpgradeController(trove_testtools.TestCase):

    def setUp(self):
        super(TestUpgradeController, self).setUp()
        self.controller = UpgradeController()

        self.body = {
            "upgrade": {
                "instance_id": "27e25b73-88a1-4526-b2b9-919a28b8b33f",
                "instance_version": "v1.0.1",
                "location": "http://swift/trove-guestagent-v1.0.1.tar.gz"}
        }

    def tearDown(self):
        super(TestUpgradeController, self).tearDown()
        self.body = {}

    def _get_validator(self, body):
        """
        Helper method to return a validator
        """
        schema = self.controller.get_schema('create', body)
        return jsonschema.Draft4Validator(schema)

    def test_validate_create(self):
        """
        Test for valid payload in body
        """
        validator = self._get_validator(self.body)
        self.assertTrue(validator.is_valid(self.body))

    def test_validate_create_additional_params(self):
        """
        Test for valid payload with additional params
        """
        self.body["upgrade"]["description"] = "upgrade"
        validator = self._get_validator(self.body)
        self.assertTrue(validator.is_valid(self.body))

    @patch.object(UpgradeMessageSender, 'create', Mock(return_value=Mock()))
    def test_controller_with_no_metadata(self):
        """
        Test the mock controller w/out metadata
        """
        tenant_id = '77889991010'
        instance_id = '27e25b73-88a1-4526-b2b9-919a28b8b33f'
        context = Mock()

        req = Mock()
        req.environ = MagicMock()
        req.environ.get = Mock(return_value=context)

        resp = self.controller.create(req, self.body, tenant_id, instance_id)

        instance_version = self.body["upgrade"]["instance_version"]
        location = self.body["upgrade"]["location"]

        metadata = None
        UpgradeMessageSender.create.assert_called_once_with(
            context, instance_id, instance_version, location, metadata)
        self.assertEqual(202, resp.status)

    @patch.object(UpgradeMessageSender, 'create', Mock(return_value=Mock()))
    def test_controller_with_metadata(self):
        """
        Test the mock controller with metadata
        """
        tenant_id = '77889991010'
        instance_id = '27e25b73-88a1-4526-b2b9-919a28b8b33f'
        context = Mock()

        req = Mock()
        req.environ = MagicMock()
        req.environ.get = Mock(return_value=context)

        # append the body w/ metadata
        self.body["upgrade"]["metadata"] = {
            "config_location": "swift://my.conf.location",
            "is_public": True,
            "is_encypted": True}

        resp = self.controller.create(req, self.body, tenant_id, instance_id)

        instance_version = self.body["upgrade"]["instance_version"]
        location = self.body["upgrade"]["location"]
        metadata = self.body["upgrade"]["metadata"]

        UpgradeMessageSender.create.assert_called_once_with(
            context, instance_id, instance_version, location, metadata)
        self.assertEqual(202, resp.status)

    @patch.object(UpgradeMessageSender, 'create', Mock(return_value=Mock()))
    def test_controller_with_empty_metadata(self):
        """
        Test the mock controller with metadata
        """
        tenant_id = '77889991010'
        instance_id = '27e25b73-88a1-4526-b2b9-919a28b8b33f'
        context = Mock()

        req = Mock()
        req.environ = MagicMock()
        req.environ.get = Mock(return_value=context)

        # append the body w/ empty metadata
        self.body["upgrade"]["metadata"] = {}

        resp = self.controller.create(req, self.body, tenant_id, instance_id)

        instance_version = self.body["upgrade"]['instance_version']
        location = self.body["upgrade"]["location"]
        metadata = self.body["upgrade"]["metadata"]

        UpgradeMessageSender.create.assert_called_once_with(
            context, instance_id, instance_version, location, metadata)
        self.assertEqual(202, resp.status)
