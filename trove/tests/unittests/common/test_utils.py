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

from unittest.mock import Mock
from unittest.mock import patch

from testtools import ExpectedException
from trove.common import exception
from trove.common import utils
from trove.tests.unittests import trove_testtools
from trove.tests.util import utils as test_utils
import webob


class TestUtils(trove_testtools.TestCase):

    def setUp(self):
        super(TestUtils, self).setUp()
        self.orig_utils_execute = utils.execute
        self.orig_utils_log_error = utils.LOG.error

    def tearDown(self):
        super(TestUtils, self).tearDown()
        utils.execute = self.orig_utils_execute
        utils.LOG.error = self.orig_utils_log_error

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
            u"Command '%(cmd)s' failed. %(description)s Exit code: "
            u"%(exit_code)s\nstderr: %(stderr)s\nstdout: %(stdout)s",
            {'description': 'test-desc', 'stderr': 'err', 'exit_code': 42,
             'stdout': 'out', 'cmd': 'test'})

    def test_unpack_singleton(self):
        self.assertEqual([1, 2, 3], utils.unpack_singleton([1, 2, 3]))
        self.assertEqual(0, utils.unpack_singleton([0]))
        self.assertEqual('test', utils.unpack_singleton('test'))
        self.assertEqual('test', utils.unpack_singleton(['test']))
        self.assertEqual([], utils.unpack_singleton([]))
        self.assertIsNone(utils.unpack_singleton(None))
        self.assertEqual([None, None], utils.unpack_singleton([None, None]))
        self.assertEqual('test', utils.unpack_singleton([['test']]))
        self.assertEqual([1, 2, 3], utils.unpack_singleton([[1, 2, 3]]))
        self.assertEqual(1, utils.unpack_singleton([[[1]]]))
        self.assertEqual([[1], [2]], utils.unpack_singleton([[1], [2]]))
        self.assertEqual(['a', 'b'], utils.unpack_singleton(['a', 'b']))

    def test_pagination_limit(self):
        self.assertEqual(5, utils.pagination_limit(5, 9))
        self.assertEqual(5, utils.pagination_limit(9, 5))

    def test_format_output(self):
        data = [
            ['', ''],
            ['Single line', 'Single line'],
            ['Long line no breaks ' * 10, 'Long line no breaks ' * 10],
            ['Long line. Has breaks ' * 5,
             'Long line.\nHas breaks ' * 2 + 'Long line. Has breaks ' * 3],
            ['Long line with semi: ' * 4,
             'Long line with semi:\n    ' +
             'Long line with semi: ' * 3],
            ['Long line with brack (' * 4,
             'Long line with brack\n(' +
             'Long line with brack (' * 3],
        ]
        for index, datum in enumerate(data):
            self.assertEqual(datum[1], utils.format_output(datum[0]),
                             "Error formatting line %d of data" % index)

    def test_to_gb(self):
        result = utils.to_gb(123456789)
        self.assertEqual(0.11, result)

    def test_to_gb_small(self):
        result = utils.to_gb(2)
        self.assertEqual(0.01, result)

    def test_to_gb_zero(self):
        result = utils.to_gb(0)
        self.assertEqual(0.0, result)

    def test_to_mb(self):
        result = utils.to_mb(123456789)
        self.assertEqual(117.74, result)

    def test_to_mb_small(self):
        result = utils.to_mb(2)
        self.assertEqual(0.01, result)

    def test_to_mb_zero(self):
        result = utils.to_mb(0)
        self.assertEqual(0.0, result)

    @patch('trove.common.utils.LOG')
    def test_retry_decorator(self, _):

        class TestEx1(Exception):
            pass

        class TestEx2(Exception):
            pass

        class TestEx3(Exception):
            pass

        class TestExecutor(object):

            def _test_foo(self, arg):
                return arg

            @test_utils.retry(TestEx1, retries=5, delay_fun=lambda n: 0.2)
            def test_foo_1(self, arg):
                return self._test_foo(arg)

            @test_utils.retry((TestEx1, TestEx2), delay_fun=lambda n: 0.2)
            def test_foo_2(self, arg):
                return self._test_foo(arg)

        def assert_retry(fun, side_effect, exp_call_num, exp_exception):
            with patch.object(te, '_test_foo', side_effect=side_effect) as f:
                mock_arg = Mock()
                if exp_exception:
                    self.assertRaises(exp_exception, fun, mock_arg)
                else:
                    fun(mock_arg)

                f.assert_called_with(mock_arg)
                self.assertEqual(exp_call_num, f.call_count)

        te = TestExecutor()
        assert_retry(te.test_foo_1, [TestEx1, None], 2, None)
        assert_retry(te.test_foo_1, TestEx3, 1, TestEx3)
        assert_retry(te.test_foo_1, TestEx1, 5, TestEx1)
        assert_retry(te.test_foo_1, [TestEx1, TestEx3], 2, TestEx3)
        assert_retry(te.test_foo_2, [TestEx1, TestEx2, None], 3, None)
        assert_retry(te.test_foo_2, TestEx3, 1, TestEx3)
        assert_retry(te.test_foo_2, TestEx2, 3, TestEx2)
        assert_retry(te.test_foo_2, [TestEx1, TestEx3, TestEx2], 2, TestEx3)

    def test_req_to_text(self):
        req = webob.Request.blank('/')
        expected = u'GET / HTTP/1.0\r\nHost: localhost:80'
        self.assertEqual(expected, utils.req_to_text(req))

        # add a header containing unicode characters
        req.headers.update({
            'X-Auth-Project-Id': u'\u6d4b\u8bd5'})
        expected = (u'GET / HTTP/1.0\r\nHost: localhost:80\r\n'
                    u'X-Auth-Project-Id: \u6d4b\u8bd5')
        self.assertEqual(expected, utils.req_to_text(req))
