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

from hacking import core

_all_log_levels = (
    'critical',
    'debug',
    'error',
    'exception',
    'info',
    'reserved',
    'warning',
)

_translated_log = re.compile(
    r".*LOG\.(%(levels)s)\(\s*_\(\s*('|\")" % {
        'levels': '|'.join(_all_log_levels)})


def _translation_is_not_expected(filename):
    # Do not do these validations on tests
    return any(pat in filename for pat in ["/tests/"])


@core.flake8ext
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


@core.flake8ext
def no_translate_logs(logical_line, filename, noqa):
    """T105 - Log messages shouldn't be translated from the
    Pike release.
    :param logical_line: The logical line to check.
    :param filename: The file name where the logical line exists.
    :param noqa: whether the check should be skipped
    :returns: None if the logical line passes the check, otherwise a tuple
    is yielded that contains the offending index in logical line and a
    message describe the check validation failure.
    """
    if noqa:
        return
    if _translation_is_not_expected(filename):
        return

    msg = "T105: Log message shouldn't be translated."
    if _translated_log.match(logical_line):
        yield (0, msg)
