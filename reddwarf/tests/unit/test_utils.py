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
import time
import unittest

from reddwarf.common import utils

LOG = logging.getLogger(__name__)


class TestMethodInspector(unittest.TestCase):

    def test_method_without_optional_args(self):
        def foo(bar):
            """This is a method"""

        method = utils.MethodInspector(foo)

        self.assertEqual(method.required_args, ['bar'])
        self.assertEqual(method.optional_args, [])

    def test_method_with_optional_args(self):
        def foo(bar, baz=1):
            """This is a method"""

        method = utils.MethodInspector(foo)

        self.assertEqual(method.required_args, ['bar'])
        self.assertEqual(method.optional_args, [('baz', 1)])

    def test_instance_method_with_optional_args(self):
        class Foo():
            def bar(self, baz, qux=2):
                """This is a method"""

        method = utils.MethodInspector(Foo().bar)

        self.assertEqual(method.required_args, ['baz'])
        self.assertEqual(method.optional_args, [('qux', 2)])

    def test_method_without_args(self):
        def foo():
            """This is a method"""

        method = utils.MethodInspector(foo)

        self.assertEqual(method.required_args, [])
        self.assertEqual(method.optional_args, [])

    def test_instance_method_without_args(self):
        class Foo():
            def bar(self):
                """This is a method"""

        method = utils.MethodInspector(Foo().bar)

        self.assertEqual(method.required_args, [])
        self.assertEqual(method.optional_args, [])

    def test_method_str(self):
        class Foo():
            def bar(self, baz, qux=None):
                """This is a method"""

        method = utils.MethodInspector(Foo().bar)

        self.assertEqual(str(method), "bar baz=<baz> [qux=<qux>]")


class StringifyExcludeTest(unittest.TestCase):

    def test_empty_stringify_keys(self):
        self.assertEqual(utils.stringify_keys(None), None)

    def test_empty_exclude(self):
        self.assertEqual(utils.exclude(None), None)

    def test_exclude_keys(self):
        exclude_keys = ['one']
        key_values = {'one': 1, 'two': 2 }
        new_keys = utils.exclude(key_values, *exclude_keys)
        self.assertEqual(len(new_keys), 1)
        self.assertEqual(new_keys, {'two': 2 })
