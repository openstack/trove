# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import re

import pep8

_all_log_levels = {
    'critical': '_',
    'error': '_',
    'exception': '_',
    'info': '_',
    'reserved': '_',
    'warning': '_',
}
_all_hints = set(_all_log_levels.values())


def _regex_for_level(level, hint):
    return r".*LOG\.%(level)s\(\s*((%(wrong_hints)s)\(|'|\")" % {
        'level': level,
        'wrong_hints': '|'.join(_all_hints - set([hint])),
    }


_log_translation_hint = re.compile(
    '|'.join('(?:%s)' % _regex_for_level(level, hint)
             for level, hint in _all_log_levels.items()))

_log_string_interpolation = re.compile(
    r".*LOG\.(error|warning|info|critical|exception|debug)\([^,]*%[^,]*[,)]")


def _translation_is_not_expected(filename):
    # Do not do these validations on tests
    return any(pat in filename for pat in ["/tests/"])


def validate_log_translations(logical_line, physical_line, filename):
    """T101 - Log messages require translation hints.
    :param logical_line: The logical line to check.
    :param physical_line: The physical line to check.
    :param filename: The file name where the logical line exists.
    :returns: None if the logical line passes the check, otherwise a tuple
    is yielded that contains the offending index in logical line and a
    message describe the check validation failure.
    """
    if _translation_is_not_expected(filename):
        return

    if pep8.noqa(physical_line):
        return

    msg = "T101: Untranslated Log message."
    if _log_translation_hint.match(logical_line):
        yield (0, msg)


def no_translate_debug_logs(logical_line, filename):
    """T102 - Don't translate debug level logs.
    Check for 'LOG.debug(_(' and 'LOG.debug(_Lx('
    As per our translation policy,
    https://wiki.openstack.org/wiki/LoggingStandards#Log_Translation
    we shouldn't translate debug level logs.
    * This check assumes that 'LOG' is a logger.
    :param logical_line: The logical line to check.
    :param filename: The file name where the logical line exists.
    :returns: None if the logical line passes the check, otherwise a tuple
    is yielded that contains the offending index in logical line and a
    message describe the check validation failure.
    """
    for hint in _all_hints:
        if logical_line.startswith("LOG.debug(%s(" % hint):
            yield(0, "T102 Don't translate debug level logs")


def check_raised_localized_exceptions(logical_line, filename):
    """T103 - Untranslated exception message.
    :param logical_line: The logical line to check.
    :param filename: The file name where the logical line exists.
    :returns: None if the logical line passes the check, otherwise a tuple
    is yielded that contains the offending index in logical line and a
    message describe the check validation failure.
    """
    if _translation_is_not_expected(filename):
        return

    logical_line = logical_line.strip()
    raised_search = re.compile(
        r"raise (?:\w*)\((.*)\)").match(logical_line)
    if raised_search:
        exception_msg = raised_search.groups()[0]
        if exception_msg.startswith("\"") or exception_msg.startswith("\'"):
            msg = "T103: Untranslated exception message."
            yield (logical_line.index(exception_msg), msg)


def check_no_basestring(logical_line):
    """T104 - Don't use basestring, use six.string_types instead
       basestring is not supported by py3, using six.string_types to ensure
       py3 and py2 compatibility
    """
    if re.search(r"\, basestring\)", logical_line):
        msg = ("T104: basestring is not Python3-compatible, use "
               "six.string_types instead.")
        yield(0, msg)


asse_raises_regexp = re.compile(r"assertRaisesRegexp\(")


def assert_raises_regexp(logical_line):
    """Check for usage of deprecated assertRaisesRegexp

    N335
    """
    res = asse_raises_regexp.search(logical_line)
    if res:
        yield (0, "N335: assertRaisesRegex must be used instead "
                  "of assertRaisesRegexp")


def factory(register):
    register(validate_log_translations)
    register(no_translate_debug_logs)
    register(check_raised_localized_exceptions)
    register(check_no_basestring)
    register(assert_raises_regexp)
