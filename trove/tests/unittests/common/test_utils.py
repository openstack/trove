# Copyright 2014 SUSE Linux GmbH.
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

from trove.common import exception
import trove.common.utils as utils

from mock import Mock
import testtools
from testtools import ExpectedException


class TestTroveExecuteWithTimeout(testtools.TestCase):
    def test_throws_process_execution_error(self):
        utils.execute = Mock(
            side_effect=exception.ProcessExecutionError(
                description='test-desc', exit_code=42, stderr='err',
                stdout='out', cmd='test'))

        with ExpectedException(
                exception.ProcessExecutionError,
                "test-desc\nCommand: test\nExit code: 42\n"
                "Stdout: 'out'\nStderr: 'err'"):
            utils.execute_with_timeout('/usr/bin/foo')

    def test_log_error_when_log_output_on_error_is_true(self):
        utils.execute = Mock(
            side_effect=exception.ProcessExecutionError(
                description='test-desc', exit_code=42, stderr='err',
                stdout='out', cmd='test'))
        utils.LOG.error = Mock()

        with ExpectedException(
                exception.ProcessExecutionError,
                "test-desc\nCommand: test\nExit code: 42\n"
                "Stdout: 'out'\nStderr: 'err'"):
            utils.execute_with_timeout(
                '/usr/bin/foo', log_output_on_error=True)

        utils.LOG.error.assert_called_with(
            u"Command 'test' failed. test-desc Exit code: 42\n"
            "stderr: err\nstdout: out")
