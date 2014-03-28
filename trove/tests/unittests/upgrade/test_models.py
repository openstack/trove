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
from mock import Mock
from testtools import TestCase
from trove.extensions.mgmt.upgrade.models import UpgradeMessageSender


class TestUpgradeModel(TestCase):

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
        """
        Test creating notification
        """
        context = Mock()

        instance_id = "27e25b73-88a1-4526-b2b9-919a28b8b33f",
        instance_version = "v1.0.1",
        location = "http://swift/trove-guestagent-v1.0.1.tar.gz"

        _create_resource = Mock(return_value=None)
        UpgradeMessageSender.create = Mock(return_value=_create_resource)

        func = UpgradeMessageSender.create(context, instance_id,
                                           instance_version, location)

        self.assertEqual(_create_resource, func)

        UpgradeMessageSender.create.assert_called_with(
            context, instance_id, instance_version, location)

    def test_create_with_metadata_none(self):
        """
        Test creating notification with metadata is None
        """
        context = Mock()

        instance_id = "27e25b73-88a1-4526-b2b9-919a28b8b33f",
        instance_version = "v1.0.1",
        location = "http://swift/trove-guestagent-v1.0.1.tar.gz"
        metadata = None

        _create_resource = Mock(return_value=None)
        UpgradeMessageSender.create = Mock(return_value=_create_resource)

        func = UpgradeMessageSender.create(
            context, instance_id, instance_version, location, metadata)

        self.assertEqual(_create_resource, func)

        UpgradeMessageSender.create.assert_called_with(
            context, instance_id, instance_version, location, metadata)

    def test_create_with_empty_metadata(self):
        """
        Test creating notification with metadata {}
        """
        context = Mock()

        instance_id = "27e25b73-88a1-4526-b2b9-919a28b8b33f",
        instance_version = "v1.0.1",
        location = "http://swift/trove-guestagent-v1.0.1.tar.gz"
        metadata = {}

        _create_resource = Mock(return_value=None)
        UpgradeMessageSender.create = Mock(return_value=_create_resource)

        func = UpgradeMessageSender.create(
            context, instance_id, instance_version, location, metadata)

        self.assertEqual(_create_resource, func)

        UpgradeMessageSender.create.assert_called_with(
            context, instance_id, instance_version, location, metadata)

    def test_create_with_metadata(self):
        """
        Test creating notification with metadata
        """
        context = Mock()

        instance_id = "27e25b73-88a1-4526-b2b9-919a28b8b33f",
        instance_version = "v1.0.1",
        location = "http://swift/trove-guestagent-v1.0.1.tar.gz"
        metadata = {"is_public": True,
                    "is_encrypted": True,
                    "config_location": "http://swift/trove-guestagent.conf"}

        _create_resource = Mock(return_value=None)
        UpgradeMessageSender.create = Mock(return_value=_create_resource)

        func = UpgradeMessageSender.create(
            context, instance_id, instance_version, location, metadata)

        self.assertEqual(_create_resource, func)

        UpgradeMessageSender.create.assert_called_with(
            context, instance_id, instance_version, location, metadata)
