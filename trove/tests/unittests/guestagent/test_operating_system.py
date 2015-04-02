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

import itertools
from mock import call, patch
from oslo_concurrency.processutils import UnknownArgumentError
import stat
import testtools
from testtools import ExpectedException
from trove.common import utils
from trove.common import exception
from trove.guestagent.common import operating_system
from trove.guestagent.common.operating_system import FileMode


class TestOperatingSystem(testtools.TestCase):

    def test_modes(self):
        self._assert_modes(None, None, None, operating_system.FileMode())
        self._assert_modes(None, None, None,
                           operating_system.FileMode([], [], []))
        self._assert_modes(0o770, 0o4, 0o3, operating_system.FileMode(
            [stat.S_IRWXU, stat.S_IRWXG],
            [stat.S_IROTH],
            [stat.S_IWOTH | stat.S_IXOTH])
        )
        self._assert_modes(0o777, None, None, operating_system.FileMode(
            [stat.S_IRWXU, stat.S_IRWXG, stat.S_IRWXO])
        )
        self._assert_modes(0o777, None, None, operating_system.FileMode(
            reset=[stat.S_IRWXU, stat.S_IRWXG, stat.S_IRWXO])
        )
        self._assert_modes(None, 0o777, None, operating_system.FileMode(
            add=[stat.S_IRWXU, stat.S_IRWXG, stat.S_IRWXO])
        )
        self._assert_modes(None, None, 0o777, operating_system.FileMode(
            remove=[stat.S_IRWXU, stat.S_IRWXG, stat.S_IRWXO])
        )

        self.assertEqual(
            operating_system.FileMode(add=[stat.S_IRUSR, stat.S_IWUSR]),
            operating_system.FileMode(add=[stat.S_IWUSR, stat.S_IRUSR]))

        self.assertEqual(
            hash(operating_system.FileMode(add=[stat.S_IRUSR, stat.S_IWUSR])),
            hash(operating_system.FileMode(add=[stat.S_IWUSR, stat.S_IRUSR])))

        self.assertNotEqual(
            operating_system.FileMode(add=[stat.S_IRUSR, stat.S_IWUSR]),
            operating_system.FileMode(reset=[stat.S_IRUSR, stat.S_IWUSR]))

        self.assertNotEqual(
            hash(operating_system.FileMode(add=[stat.S_IRUSR, stat.S_IWUSR])),
            hash(operating_system.FileMode(reset=[stat.S_IRUSR, stat.S_IWUSR]))
        )

    def _assert_modes(self, ex_reset, ex_add, ex_remove, actual):
        self.assertEqual(bool(ex_reset or ex_add or ex_remove),
                         actual.has_any())
        self.assertEqual(ex_reset, actual.get_reset_mode())
        self.assertEqual(ex_add, actual.get_add_mode())
        self.assertEqual(ex_remove, actual.get_remove_mode())

    def test_chmod(self):
        self._assert_execute_call(
            [['chmod', '-R', '=777', 'path']],
            [{'run_as_root': True, 'root_helper': 'sudo'}],
            operating_system.chmod, None,
            'path', FileMode.SET_FULL,
            as_root=True)

        self._assert_execute_call(
            [['chmod', '-f', '=777', 'path']],
            [{'run_as_root': True, 'root_helper': 'sudo'}],
            operating_system.chmod, None,
            'path', FileMode.SET_FULL,
            as_root=True, recursive=False, force=True)

        self._assert_execute_call(
            [['chmod', '-R', '=777', 'path']],
            [{'timeout': 100}],
            operating_system.chmod, None,
            'path', FileMode.SET_FULL,
            timeout=100)

        self._assert_execute_call(
            [['chmod', '-R', '=777', 'path']],
            [{'run_as_root': True, 'root_helper': 'sudo', 'timeout': None}],
            operating_system.chmod, None,
            'path', FileMode.SET_FULL,
            as_root=True, timeout=None)

        self._assert_execute_call(
            None, None,
            operating_system.chmod,
            ExpectedException(exception.UnprocessableEntity,
                              "No file mode specified."),
            'path', FileMode())

        self._assert_execute_call(
            None, None,
            operating_system.chmod,
            ExpectedException(exception.UnprocessableEntity,
                              "No file mode specified."),
            'path', None)

        self._assert_execute_call(
            None, None,
            operating_system.chmod,
            ExpectedException(exception.UnprocessableEntity,
                              "Cannot change mode of a blank file."),
            '', FileMode.SET_FULL)

        self._assert_execute_call(
            None, None,
            operating_system.chmod,
            ExpectedException(exception.UnprocessableEntity,
                              "Cannot change mode of a blank file."),
            None, FileMode.SET_FULL)

        self._assert_execute_call(
            None, None,
            operating_system.chmod,
            ExpectedException(UnknownArgumentError,
                              "Got unknown keyword args: {'_unknown_kw': 0}"),
            'path', FileMode.SET_FULL, _unknown_kw=0)

    def test_remove(self):
        self._assert_execute_call(
            [['rm', '-R', 'path']],
            [{'run_as_root': True, 'root_helper': 'sudo'}],
            operating_system.remove, None, 'path', as_root=True)

        self._assert_execute_call(
            [['rm', '-f', 'path']],
            [{'run_as_root': True, 'root_helper': 'sudo'}],
            operating_system.remove, None, 'path', recursive=False, force=True,
            as_root=True)

        self._assert_execute_call(
            [['rm', '-R', 'path']],
            [{'timeout': 100}],
            operating_system.remove, None,
            'path', timeout=100)

        self._assert_execute_call(
            [['rm', '-R', 'path']],
            [{'run_as_root': True, 'root_helper': 'sudo', 'timeout': None}],
            operating_system.remove, None, 'path', timeout=None, as_root=True)

        self._assert_execute_call(
            None, None,
            operating_system.remove,
            ExpectedException(exception.UnprocessableEntity,
                              "Cannot remove a blank file."), '')

        self._assert_execute_call(
            None, None,
            operating_system.remove,
            ExpectedException(exception.UnprocessableEntity,
                              "Cannot remove a blank file."), None)

        self._assert_execute_call(
            None, None,
            operating_system.remove,
            ExpectedException(UnknownArgumentError,
                              "Got unknown keyword args: {'_unknown_kw': 0}"),
            'path', _unknown_kw=0)

    def _assert_execute_call(self, exec_args, exec_kwargs,
                             fun, return_value, *args, **kwargs):
        """
        Execute a function with given arguments.
        Assert a return value and appropriate sequence of calls to the
        'utils.execute_with_timeout' interface as the result.

        :param exec_args:         Expected arguments to the execute calls.
                                  This is a list-of-list where each sub-list
                                  represent a single call to
                                  'utils.execute_with_timeout'.
        :type exec_args:          list-of-lists

        :param exec_kwargs:       Expected keywords to the execute call.
                                  This is a list-of-dicts where each dict
                                  represent a single call to
                                  'utils.execute_with_timeout'.
        :type exec_kwargs:        list-of-dicts

        :param fun:               Tested function call.
        :type fun:                callable

        :param return_value:      Expected return value or exception
                                  from the tested call if any.
        :type return_value:       object

        :param args:              Arguments passed to the tested call.
        :type args:               list

        :param kwargs:            Keywords passed to the tested call.
        :type kwargs:             dict
        """

        with patch.object(utils, 'execute_with_timeout') as exec_call:
            if isinstance(return_value, ExpectedException):
                with return_value:
                    fun(*args, **kwargs)
            else:
                actual_value = fun(*args, **kwargs)
                if return_value is not None:
                    self.assertEqual(return_value, actual_value,
                                     "Return value mismatch.")
                expected_calls = []
                for arg, kw in itertools.izip(exec_args, exec_kwargs):
                    expected_calls.append(call(*arg, **kw))

                self.assertEqual(expected_calls, exec_call.mock_calls,
                                 "Mismatch in calls to "
                                 "'execute_with_timeout'.")
