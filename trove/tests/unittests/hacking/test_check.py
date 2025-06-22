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
                1, len(list(tc.no_translate_logs(bad, 'f', False))))
            bad = "LOG.%s(_('Bad'))" % level
            self.assertEqual(
                1, len(list(tc.no_translate_logs(bad, 'f', False))))
            ok = 'LOG.%s("OK")' % level
            self.assertEqual(
                0, len(list(tc.no_translate_logs(ok, 'f', False))))
            ok = "LOG.%s(_('OK'))" % level
            self.assertEqual(
                0, len(list(tc.no_translate_logs(ok, 'f', True))))
            ok = "LOG.%s(variable)" % level
            self.assertEqual(
                0, len(list(tc.no_translate_logs(ok, 'f', False))))
            # Do not do validations in tests
            ok = 'LOG.%s(_("OK - unit tests"))' % level
            self.assertEqual(
                0, len(list(tc.no_translate_logs(ok, 'f/tests/f', False))))

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
