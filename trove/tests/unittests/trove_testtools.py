# Copyright 2015 Tesora Inc.
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

import abc
import inspect
import mock
import os
import sys
import testtools

from trove.common.context import TroveContext
from trove.common.notification import DBaaSAPINotification
from trove.tests import root_logger


def patch_notifier(test_case):
    notification_notify = mock.patch.object(
        DBaaSAPINotification, "_notify")
    notification_notify.start()
    test_case.addCleanup(notification_notify.stop)


class TroveTestNotification(DBaaSAPINotification):

    @abc.abstractmethod
    def event_type(self):
        return 'test_notification'

    @abc.abstractmethod
    def required_start_traits(self):
        return []


class TroveTestContext(TroveContext):

    def __init__(self, test_case, **kwargs):
        super(TroveTestContext, self).__init__(**kwargs)
        self.notification = TroveTestNotification(
            self, request_id='req_id', flavor_id='7')
        self.notification.server_type = 'api'
        patch_notifier(test_case)


class TestCase(testtools.TestCase):
    """Base class of Trove unit tests.
    Integrates automatic dangling mock detection.
    """

    _NEWLINE = '\n'

    @classmethod
    def setUpClass(cls):
        # Number of nested levels to examine when searching for mocks.
        # Higher setting will potentially uncover more dangling objects,
        # at the cost of increased scanning time.
        cls._max_recursion_depth = int(os.getenv(
            'TROVE_TESTS_UNMOCK_RECURSION_DEPTH', 2))
        # Should we skip the remaining tests after the first failure.
        cls._fail_fast = cls.is_bool(os.getenv(
            'TROVE_TESTS_UNMOCK_FAIL_FAST', False))
        # Should we report only unique dangling mock references.
        cls._only_unique = cls.is_bool(os.getenv(
            'TROVE_TESTS_UNMOCK_ONLY_UNIQUE', True))

        cls._dangling_mocks = set()
        root_logger.DefaultRootLogger(enable_backtrace=False)

    @classmethod
    def is_bool(cls, val):
        return str(val).lower() in ['true', '1', 't', 'y', 'yes', 'on', 'set']

    def setUp(self):
        if self.__class__._fail_fast and self.__class__._dangling_mocks:
            self.skipTest("This test suite already has dangling mock "
                          "references from a previous test case.")

        super(TestCase, self).setUp()
        self.addCleanup(self._assert_modules_unmocked)
        self._mocks_before = self._find_mock_refs()
        root_logger.DefaultRootHandler.set_info(self.id())

    def tearDown(self):
        # yes, this is gross and not thread aware.
        # but the only way to make it thread aware would require that
        # we single thread all testing
        root_logger.DefaultRootHandler.set_info(info=None)
        super(TestCase, self).tearDown()

    def _assert_modules_unmocked(self):
        """Check that all members of loaded modules are currently unmocked.
        Consider only new mocks created since the last setUp() call.
        """
        mocks_after = self._find_mock_refs()
        new_mocks = mocks_after.difference(self._mocks_before)
        if self.__class__._only_unique:
            # Remove mock references that have already been reported once in
            # this test suite (probably defined in setUp()).
            new_mocks.difference_update(self.__class__._dangling_mocks)

        self.__class__._dangling_mocks.update(new_mocks)

        if new_mocks:
            messages = ["Member '%s' needs to be unmocked." % item[0]
                        for item in new_mocks]
            self.fail(self._NEWLINE + self._NEWLINE.join(messages))

    def _find_mock_refs(self):
        discovered_mocks = set()
        for module_name, module in self._get_loaded_modules().items():
            self._find_mocks(module_name, module, discovered_mocks, 1)

        return discovered_mocks

    def _find_mocks(self, parent_name, parent, container, depth):
        """Search for mock members in the parent object.
        Descend into class types.
        """
        if depth <= self.__class__._max_recursion_depth:
            try:
                if isinstance(parent, mock.Mock):
                    # Add just the parent if it's a mock itself.
                    container.add((parent_name, parent))
                else:
                    # Add all mocked members of the parent.
                    for member_name, member in inspect.getmembers(parent):
                        full_name = '%s.%s' % (parent_name, member_name)
                        if isinstance(member, mock.Mock):
                            container.add((full_name, member))
                        elif inspect.isclass(member):
                            self._find_mocks(
                                full_name, member, container, depth + 1)
            except ImportError:
                pass  # Module cannot be imported - ignore it.
            except RuntimeError:
                # Something else went wrong when probing the class member.
                # See: https://bugs.launchpad.net/trove/+bug/1524918
                pass

    def _get_loaded_modules(self):
        return {name: obj for name, obj in sys.modules.items() if obj}
