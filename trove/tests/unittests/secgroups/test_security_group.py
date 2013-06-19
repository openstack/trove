#    Copyright 2012 OpenStack Foundation
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

import testtools
import trove.common.remote
from mock import Mock
from trove.extensions.security_group import models
from trove.common import exception
from trove.tests.fakes import nova

from novaclient import exceptions as nova_exceptions


"""
Unit tests for testing the exceptions raised by Security Groups
"""


class Security_Group_Exceptions_Test(testtools.TestCase):

    def setUp(self):
        super(Security_Group_Exceptions_Test, self).setUp()
        self.createNovaClient = trove.common.remote.create_nova_client
        self.context = Mock()
        self.FakeClient = nova.fake_create_nova_client(self.context)

        fException = Mock(side_effect=
                          lambda *args, **kwargs:
                          self._raise(nova_exceptions.ClientException("Test")))

        self.FakeClient.security_groups.create = fException
        self.FakeClient.security_groups.delete = fException
        self.FakeClient.security_group_rules.create = fException
        self.FakeClient.security_group_rules.delete = fException

        trove.common.remote.create_nova_client = \
            lambda c: self._return_mocked_nova_client(c)

    def tearDown(self):
        super(Security_Group_Exceptions_Test, self).tearDown()
        trove.common.remote.create_nova_client = self.createNovaClient

    def _return_mocked_nova_client(self, context):
        return self.FakeClient

    def _raise(self, ex):
        raise ex

    def test_failed_to_create_security_group(self):
        self.assertRaises(exception.SecurityGroupCreationError,
                          models.RemoteSecurityGroup.create,
                          "TestName",
                          "TestDescription",
                          self.context)

    def test_failed_to_delete_security_group(self):
        self.assertRaises(exception.SecurityGroupDeletionError,
                          models.RemoteSecurityGroup.delete,
                          1, self.context)

    def test_failed_to_create_security_group_rule(self):
        self.assertRaises(exception.SecurityGroupRuleCreationError,
                          models.RemoteSecurityGroup.add_rule,
                          1, "tcp", 3306, 3306, "0.0.0.0/0", self.context)

    def test_failed_to_delete_security_group_rule(self):
        self.assertRaises(exception.SecurityGroupRuleDeletionError,
                          models.RemoteSecurityGroup.delete_rule,
                          1, self.context)
