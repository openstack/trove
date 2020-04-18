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

import pycodestyle
import textwrap
from unittest import mock

from trove.hacking import checks as tc
from trove.tests.unittests import trove_testtools


class HackingTestCase(trove_testtools.TestCase):

    def assertLinePasses(self, func, *args):
        def check_callable(f, *args):
            return next(f(*args))
        self.assertRaises(StopIteration, check_callable, func, *args)

    def assertLineFails(self, func, *args):
        self.assertIsInstance(next(func(*args)), tuple)

    def test_log_translations(self):
        all_log_levels = (
            'critical',
            'debug',
            'error',
            'exception',
            'info',
            'reserved',
            'warning',
        )
        for level in all_log_levels:
            bad = 'LOG.%s(_("Bad"))' % level
            self.assertEqual(
                1, len(list(tc.no_translate_logs(bad, bad, 'f'))))
            bad = "LOG.%s(_('Bad'))" % level
            self.assertEqual(
                1, len(list(tc.no_translate_logs(bad, bad, 'f'))))
            ok = 'LOG.%s("OK")' % level
            self.assertEqual(
                0, len(list(tc.no_translate_logs(ok, ok, 'f'))))
            ok = "LOG.%s(_('OK'))    # noqa" % level
            self.assertEqual(
                0, len(list(tc.no_translate_logs(ok, ok, 'f'))))
            ok = "LOG.%s(variable)" % level
            self.assertEqual(
                0, len(list(tc.no_translate_logs(ok, ok, 'f'))))
            # Do not do validations in tests
            ok = 'LOG.%s(_("OK - unit tests"))' % level
            self.assertEqual(
                0, len(list(tc.no_translate_logs(ok, ok,
                                                 'f/tests/f'))))

    def test_check_localized_exception_messages(self):
        f = tc.check_raised_localized_exceptions
        self.assertLineFails(f, "     raise KeyError('Error text')", '')
        self.assertLineFails(f, ' raise KeyError("Error text")', '')
        self.assertLinePasses(f, ' raise KeyError(_("Error text"))', '')
        self.assertLinePasses(f, ' raise KeyError(_ERR("Error text"))', '')
        self.assertLinePasses(f, " raise KeyError(translated_msg)", '')
        self.assertLinePasses(f, '# raise KeyError("Not translated")', '')
        self.assertLinePasses(f, 'print("raise KeyError("Not '
                                 'translated")")', '')

    def test_check_localized_exception_message_skip_tests(self):
        f = tc.check_raised_localized_exceptions
        self.assertLinePasses(f, "raise KeyError('Error text')",
                              'neutron_lib/tests/unit/mytest.py')

    def test_no_basestring(self):
        self.assertEqual(
            1,
            len(list(tc.check_no_basestring("isinstance(x, basestring)"))))
        self.assertEqual(
            0,
            len(list(tc.check_no_basestring("this basestring is good)"))))

    # We are patching pycodestyle so that only the check under test is actually
    # installed.
    @mock.patch('pycodestyle._checks',
                {'physical_line': {}, 'logical_line': {}, 'tree': {}})
    def _run_check(self, code, checker, filename=None):
        pycodestyle.register_check(checker)

        lines = textwrap.dedent(code).strip().splitlines(True)

        checker = pycodestyle.Checker(filename=filename, lines=lines)
        # NOTE(sdague): the standard reporter has printing to stdout
        # as a normal part of check_all, which bleeds through to the
        # test output stream in an unhelpful way. This blocks that printing.
        with mock.patch('pycodestyle.StandardReport.get_file_results'):
            checker.check_all()
        checker.report._deferred_print.sort()
        return checker.report._deferred_print

    def _assert_has_errors(self, code, checker, expected_errors=None,
                           filename=None):
        actual_errors = [e[:3] for e in
                         self._run_check(code, checker, filename)]
        self.assertEqual(expected_errors or [], actual_errors)

    def _assert_has_no_errors(self, code, checker, filename=None):
        self._assert_has_errors(code, checker, filename=filename)

    def test_oslo_assert_raises_regexp(self):
        code = """
               self.assertRaisesRegexp(ValueError,
                                       "invalid literal for.*XYZ'$",
                                       int,
                                       'XYZ')
               """
        self._assert_has_errors(code, tc.assert_raises_regexp,
                                expected_errors=[(1, 0, "N335")])
