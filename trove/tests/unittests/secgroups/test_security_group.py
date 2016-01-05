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

import uuid

from mock import Mock
from mock import patch
from novaclient import exceptions as nova_exceptions

from trove.common import exception
import trove.common.remote
from trove.extensions.security_group import models as sec_mod
from trove.instance import models as inst_model
from trove.tests.fakes import nova
from trove.tests.unittests import trove_testtools


"""
Unit tests for testing the exceptions raised by Security Groups
"""


class Security_Group_Exceptions_Test(trove_testtools.TestCase):

    def setUp(self):
        super(Security_Group_Exceptions_Test, self).setUp()
        self.createNovaClient = trove.common.remote.create_nova_client
        self.context = Mock()
        self.FakeClient = nova.fake_create_nova_client(self.context)

        fException = Mock(
            side_effect=lambda *args, **kwargs: self._raise(
                nova_exceptions.ClientException("Test")))

        self.FakeClient.security_groups.create = fException
        self.FakeClient.security_groups.delete = fException
        self.FakeClient.security_group_rules.create = fException
        self.FakeClient.security_group_rules.delete = fException

        trove.common.remote.create_nova_client = (
            lambda c: self._return_mocked_nova_client(c))

    def tearDown(self):
        super(Security_Group_Exceptions_Test, self).tearDown()
        trove.common.remote.create_nova_client = self.createNovaClient

    def _return_mocked_nova_client(self, context):
        return self.FakeClient

    def _raise(self, ex):
        raise ex

    @patch('trove.network.nova.LOG')
    def test_failed_to_create_security_group(self, mock_logging):
        self.assertRaises(exception.SecurityGroupCreationError,
                          sec_mod.RemoteSecurityGroup.create,
                          "TestName",
                          "TestDescription",
                          self.context)

    @patch('trove.network.nova.LOG')
    def test_failed_to_delete_security_group(self, mock_logging):
        self.assertRaises(exception.SecurityGroupDeletionError,
                          sec_mod.RemoteSecurityGroup.delete,
                          1, self.context)

    @patch('trove.network.nova.LOG')
    def test_failed_to_create_security_group_rule(self, mock_logging):
        self.assertRaises(exception.SecurityGroupRuleCreationError,
                          sec_mod.RemoteSecurityGroup.add_rule,
                          1, "tcp", 3306, 3306, "0.0.0.0/0", self.context)

    @patch('trove.network.nova.LOG')
    def test_failed_to_delete_security_group_rule(self, mock_logging):
        self.assertRaises(exception.SecurityGroupRuleDeletionError,
                          sec_mod.RemoteSecurityGroup.delete_rule,
                          1, self.context)


class fake_RemoteSecGr(object):
    def data(self):
        self.id = uuid.uuid4()
        return {'id': self.id}

    def delete(self, context):
        pass


class fake_SecGr_Association(object):
    def get_security_group(self):
        return fake_RemoteSecGr()

    def delete(self):
        pass


class SecurityGroupDeleteTest(trove_testtools.TestCase):

    def setUp(self):
        super(SecurityGroupDeleteTest, self).setUp()
        self.inst_model_conf_patch = patch.object(inst_model, 'CONF')
        self.inst_model_conf_mock = self.inst_model_conf_patch.start()
        self.addCleanup(self.inst_model_conf_patch.stop)
        self.context = Mock()
        self.original_find_by = (
            sec_mod.SecurityGroupInstanceAssociation.find_by)
        self.original_delete = sec_mod.SecurityGroupInstanceAssociation.delete
        self.fException = Mock(
            side_effect=lambda *args, **kwargs: self._raise(
                exception.ModelNotFoundError()))

    def tearDown(self):
        super(SecurityGroupDeleteTest, self).tearDown()
        (sec_mod.SecurityGroupInstanceAssociation.
         find_by) = self.original_find_by
        (sec_mod.SecurityGroupInstanceAssociation.
         delete) = self.original_delete

    def _raise(self, ex):
        raise ex

    def test_failed_to_get_assoc_on_delete(self):

        sec_mod.SecurityGroupInstanceAssociation.find_by = self.fException
        self.assertIsNone(
            sec_mod.SecurityGroup.delete_for_instance(
                uuid.uuid4(), self.context))

    def test_get_security_group_from_assoc_with_db_exception(self):

        fException = Mock(
            side_effect=lambda *args, **kwargs: self._raise(
                nova_exceptions.ClientException('TEST')))
        i_id = uuid.uuid4()

        class new_fake_RemoteSecGrAssoc(object):

            def get_security_group(self):
                return None

            def delete(self):
                return fException

        sec_mod.SecurityGroupInstanceAssociation.find_by = Mock(
            return_value=new_fake_RemoteSecGrAssoc())
        self.assertIsNone(
            sec_mod.SecurityGroup.delete_for_instance(
                i_id, self.context))

    def test_delete_secgr_assoc_with_db_exception(self):

        i_id = uuid.uuid4()
        sec_mod.SecurityGroupInstanceAssociation.find_by = Mock(
            return_value=fake_SecGr_Association())
        sec_mod.SecurityGroupInstanceAssociation.delete = self.fException
        self.assertNotEqual(sec_mod.SecurityGroupInstanceAssociation.find_by(
            i_id, deleted=False).get_security_group(), None)
        self.assertTrue(hasattr(sec_mod.SecurityGroupInstanceAssociation.
                                find_by(i_id, deleted=False).
                                get_security_group(), 'delete'))
        self.assertIsNone(
            sec_mod.SecurityGroup.delete_for_instance(
                i_id, self.context))
