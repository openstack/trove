# vim: tabstop=4 shiftwidth=4 softtabstop=4
# Copyright 2011 OpenStack LLC.
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

import logging
import unittest

from reddwarf.common import exception

LOG = logging.getLogger(__name__)


class ExceptionTest(unittest.TestCase):

    def test_exception_with_message_no_args(self):
        test_message = "test message no args"
        exc = exception.ReddwarfError(test_message)
        self.assertEqual(str(exc), test_message)

    def test_exception_with_message_args(self):
        test_message = "test message %(one)s %(two)s"
        test_args = {'one': 1, 'two': 2}
        exc = exception.ReddwarfError(test_message, one=1, two=2)
        self.assertEqual(str(exc), test_message % test_args)
