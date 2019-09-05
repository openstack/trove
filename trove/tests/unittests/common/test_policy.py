# Copyright 2016 Tesora Inc.
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

from mock import MagicMock
from mock import NonCallableMock
from mock import patch

from trove.common import exception as trove_exceptions
from trove.common import policy as trove_policy
from trove.tests.unittests import trove_testtools


class TestPolicy(trove_testtools.TestCase):

    def setUp(self):
        super(TestPolicy, self).setUp()
        self.context = trove_testtools.TroveTestContext(self)
        self.mock_enforcer = MagicMock()
        get_enforcer_patch = patch.object(trove_policy, 'get_enforcer',
                                          return_value=self.mock_enforcer)
        self.addCleanup(get_enforcer_patch.stop)
        self.mock_get_enforcer = get_enforcer_patch.start()

    def test_authorize_on_tenant(self):
        test_rule = NonCallableMock()
        trove_policy.authorize_on_tenant(self.context, test_rule)
        self.mock_get_enforcer.assert_called_once_with()
        self.mock_enforcer.authorize.assert_called_once_with(
            test_rule,
            {'tenant': self.context.project_id},
            self.context.to_dict(),
            do_raise=True, exc=trove_exceptions.PolicyNotAuthorized,
            action=test_rule
        )

    def test_authorize_on_target(self):
        test_rule = NonCallableMock()
        test_target = NonCallableMock()
        trove_policy.authorize_on_target(self.context, test_rule, test_target)
        self.mock_get_enforcer.assert_called_once_with()
        self.mock_enforcer.authorize.assert_called_once_with(
            test_rule, test_target, self.context.to_dict(),
            do_raise=True, exc=trove_exceptions.PolicyNotAuthorized,
            action=test_rule)
