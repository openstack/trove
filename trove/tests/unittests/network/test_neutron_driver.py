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

from mock import MagicMock
from mock import Mock
from neutronclient.common import exceptions as neutron_exceptions
from neutronclient.v2_0 import client as NeutronClient
from trove.common import exception
from trove.common import remote
from trove.common.models import NetworkRemoteModelBase
from trove.network import neutron
from trove.network.neutron import NeutronDriver as driver
from trove.extensions.security_group.models import RemoteSecurityGroup
from trove.tests.unittests import trove_testtools


class NeutronDriverTest(trove_testtools.TestCase):
    def setUp(self):
        super(NeutronDriverTest, self).setUp()
        self.context = Mock()
        self.orig_neutron_driver = NetworkRemoteModelBase.get_driver
        self.orig_create_sg = driver.create_security_group
        self.orig_add_sg_rule = driver.add_security_group_rule
        self.orig_del_sg_rule = driver.delete_security_group_rule
        self.orig_del_sg = driver.delete_security_group
        NetworkRemoteModelBase.get_driver = Mock(return_value=driver)

    def tearDown(self):
        super(NeutronDriverTest, self).tearDown()
        NetworkRemoteModelBase.get_driver = self.orig_neutron_driver
        driver.create_security_group = self.orig_create_sg
        driver.add_security_group_rule = self.orig_add_sg_rule
        driver.delete_security_group_rule = self.orig_del_sg_rule
        driver.delete_security_group = self.orig_del_sg

    def test_create_security_group(self):
        driver.create_security_group = Mock()
        RemoteSecurityGroup.create(name=Mock(), description=Mock(),
                                   context=self.context)
        self.assertEqual(1, driver.create_security_group.call_count)

    def test_add_security_group_rule(self):
        driver.add_security_group_rule = Mock()
        RemoteSecurityGroup.add_rule(sec_group_id=Mock(), protocol=Mock(),
                                     from_port=Mock(), to_port=Mock(),
                                     cidr=Mock(), context=self.context)
        self.assertEqual(1, driver.add_security_group_rule.call_count)

    def test_delete_security_group_rule(self):
        driver.delete_security_group_rule = Mock()
        RemoteSecurityGroup.delete_rule(sec_group_rule_id=Mock(),
                                        context=self.context)
        self.assertEqual(1, driver.delete_security_group_rule.call_count)

    def test_delete_security_group(self):
        driver.delete_security_group = Mock()
        RemoteSecurityGroup.delete(sec_group_id=Mock(),
                                   context=self.context)
        self.assertEqual(1, driver.delete_security_group.call_count)


class NeutronDriverExceptionTest(trove_testtools.TestCase):
    def setUp(self):
        super(NeutronDriverExceptionTest, self).setUp()
        self.context = Mock()
        self.orig_neutron_driver = NetworkRemoteModelBase.get_driver
        self.orig_NeutronClient = NeutronClient.Client
        self.orig_get_endpoint = remote.get_endpoint
        remote.get_endpoint = MagicMock(return_value="neutron_url")
        mock_driver = neutron.NeutronDriver(self.context)
        NetworkRemoteModelBase.get_driver = MagicMock(
            return_value=mock_driver)

        NeutronClient.Client = Mock(
            side_effect=neutron_exceptions.NeutronClientException())

    def tearDown(self):
        super(NeutronDriverExceptionTest, self).tearDown()
        NetworkRemoteModelBase.get_driver = self.orig_neutron_driver
        NeutronClient.Client = self.orig_NeutronClient
        remote.get_endpoint = self.orig_get_endpoint

    def test_create_sg_with_exception(self):
        self.assertRaises(exception.SecurityGroupCreationError,
                          RemoteSecurityGroup.create,
                          "sg_name", "sg_desc", self.context)

    def test_add_sg_rule_with_exception(self):
        self.assertRaises(exception.SecurityGroupRuleCreationError,
                          RemoteSecurityGroup.add_rule,
                          "12234", "tcp", "22", "22",
                          "0.0.0.0/8", self.context)

    def test_delete_sg_rule_with_exception(self):
        self.assertRaises(exception.SecurityGroupRuleDeletionError,
                          RemoteSecurityGroup.delete_rule,
                          "12234", self.context)

    def test_delete_sg_with_exception(self):
        self.assertRaises(exception.SecurityGroupDeletionError,
                          RemoteSecurityGroup.delete,
                          "123445", self.context)
