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
from mock import patch
from trove.extensions.mgmt.upgrade.models import UpgradeMessageSender
from trove import rpc
from trove.tests.unittests import trove_testtools


class TestUpgradeModel(trove_testtools.TestCase):

    def setUp(self):
        super(TestUpgradeModel, self).setUp()

    def tearDown(self):
        super(TestUpgradeModel, self).tearDown()

    def test_validate(self):
        """
        Test validation method
        """
        param = None
        self.assertRaises(
            ValueError, UpgradeMessageSender._validate, param, 36)

        param = ''
        self.assertRaises(
            ValueError, UpgradeMessageSender._validate, param, 36)

        param = '7169f46a-ac53-401a-ba35-f461db948b8c7'
        self.assertRaises(
            ValueError, UpgradeMessageSender._validate, param, 36)

        param = '7169f46a-ac53-401a-ba35-f461db948b8c'
        self.assertTrue(UpgradeMessageSender._validate(param, 36))

        param = '7169f46a-ac53-401a-ba35'
        self.assertTrue(UpgradeMessageSender._validate(param, 36))

    def test_create(self):
        self._assert_create_with_metadata()

    def test_create_with_metadata_none(self):
        self._assert_create_with_metadata(metadata=None)

    def test_create_with_empty_metadata(self):
        self._assert_create_with_metadata(metadata={})

    def test_create_with_metadata(self):
        self._assert_create_with_metadata(
            metadata={"is_public": True,
                      "is_encrypted": True,
                      "config_location": "http://swift/trove-guestagent.conf"})

    @patch('trove.guestagent.api.API.upgrade')
    @patch.object(rpc, 'get_client')
    def _assert_create_with_metadata(self, mock_client, api_upgrade_mock,
                                     metadata=None):
        """Exercise UpgradeMessageSender.create() call.
        """
        context = trove_testtools.TroveTestContext(self)

        instance_id = "27e25b73-88a1-4526-b2b9-919a28b8b33f"
        instance_version = "v1.0.1"
        location = "http://swift/trove-guestagent-v1.0.1.tar.gz"

        func = (UpgradeMessageSender.create(
            context, instance_id, instance_version, location, metadata)
            if metadata is not None else UpgradeMessageSender.create(
                context, instance_id, instance_version, location))

        self.assertTrue(callable(func))
        func()  # This call should translate to the API call asserted below.
        api_upgrade_mock.assert_called_once_with(instance_version, location,
                                                 metadata)
