#!/usr/bin/env python
# Copyright 2016 Tesora, Inc.
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from __future__ import print_function

import fnmatch
import json
from collections import OrderedDict
import os
import re
import six
import sys

from pylint import lint
from pylint.reporters import text
from six.moves import cStringIO as csio

DEFAULT_CONFIG_FILE = "tools/trove-pylint.config"
DEFAULT_IGNORED_FILES = ['trove/tests']
DEFAULT_IGNORED_CODES = []
DEFAULT_IGNORED_MESSAGES = []
DEFAULT_ALWAYS_ERROR = [
    "Undefined variable '_'",
    "Undefined variable '_LE'",
    "Undefined variable '_LI'",
    "Undefined variable '_LW'",
    "Undefined variable '_LC'"]

MODE_CHECK = "check"
MODE_REBUILD = "rebuild"

class Config(object):
    def __init__(self, filename=DEFAULT_CONFIG_FILE):

        self.default_config = {
            "include": ["*.py"],
            "folder": "trove",
            "options": ["--rcfile=./pylintrc", "-E"],
            "ignored_files": DEFAULT_IGNORED_FILES,
            "ignored_codes": DEFAULT_IGNORED_CODES,
            "ignored_messages": DEFAULT_IGNORED_MESSAGES,
            "ignored_file_codes": [],
            "ignored_file_messages": [],
            "ignored_file_code_messages": [],
            "always_error_messages": DEFAULT_ALWAYS_ERROR
        }

        self.config = self.default_config

    def sort_config(self):
        sorted_config = OrderedDict()
        for key in sorted(self.config.keys()):
            value = self.get(key)
            if isinstance(value, list) and not isinstance(value,
                                                          six.string_types):
                sorted_config[key] = sorted(value)
            else:
                sorted_config[key] = value

        return sorted_config

    def save(self, filename=DEFAULT_CONFIG_FILE):
        if os.path.isfile(filename):
            os.rename(filename, "%s~" % filename)

        with open(filename, 'w') as fp:
            json.dump(self.sort_config(), fp, encoding="utf-8",
                      indent=2, separators=(',', ': '))

    def load(self, filename=DEFAULT_CONFIG_FILE):
        with open(filename) as fp:
            self.config = json.load(fp, encoding="utf-8")

    def get(self, attribute):
        return self.config[attribute]

    def is_file_ignored(self, f):
        if any(f.startswith(i)
            for i in self.config['ignored_files']):
            return True

        return False

    def is_file_included(self, f):
        if any(fnmatch.fnmatch(f, wc) for wc in self.config['include']):
            return True

        return False

    def is_always_error(self, message):
        if message in self.config['always_error_messages']:
            return True

        return False

    def ignore(self, filename, code, codename, message):
        # the high priority checks
        if self.is_file_ignored(filename):
            return True

        # never ignore messages
        if self.is_always_error(message):
            return False

        if code in self.config['ignored_codes']:
            return True

        if codename in self.config['ignored_codes']:
            return True

        if message and any(message.startswith(ignore_message)
                           for ignore_message
                           in self.config['ignored_messages']):
            return True

        if filename and message and (
                [filename, message] in self.config['ignored_file_messages']):
            return True

        if filename and code and (
                [filename, code] in self.config['ignored_file_codes']):
            return True

        if filename and codename and (
                [filename, codename] in self.config['ignored_file_codes']):
            return True

        for fcm in self.config['ignored_file_code_messages']:
            if filename != fcm[0]:
                # This ignore rule is for a different file.
                continue
            if fcm[1] not in (code, codename):
                # This ignore rule is for a different code or codename.
                continue
            if message.startswith(fcm[2]):
                return True

        return False

    def ignore_code(self, c):
        _c = set(self.config['ignored_codes'])
        _c.add(c)
        self.config['ignored_codes'] = list(_c)

    def ignore_files(self, f):
        _c = set(self.config['ignored_files'])
        _c.add(f)
        self.config['ignored_files'] = list(_c)

    def ignore_message(self, m):
        _c = set(self.config['ignored_messages'])
        _c.add(m)
        self.config['ignored_messages'] = list(_c)

    def ignore_file_code(self, f, c):
        _c = set(self.config['ignored_file_codes'])
        _c.add((f, c))
        self.config['ignored_file_codes'] = list(_c)

    def ignore_file_message(self, f, m):
        _c = set(self.config['ignored_file_messages'])
        _c.add((f, m))
        self.config['ignored_file_messages'] = list(_c)

    def ignore_file_code_message(self, f, c, m, fn):
        _c = set(self.config['ignored_file_code_messages'])
        _c.add((f, c, m, fn))
        self.config['ignored_file_code_messages'] = list(_c)

def main():
    if len(sys.argv) == 1 or sys.argv[1] == "check":
        return check()
    elif sys.argv[1] == "rebuild":
        return rebuild()
    elif sys.argv[1] == "initialize":
        return initialize()
    else:
        return usage()

def usage():
    print("Usage: %s [check|rebuild]" % sys.argv[0])
    print("\tUse this tool to perform a lint check of the trove project.")
    print("\t   check: perform the lint check.")
    print("\t   rebuild: rebuild the list of exceptions to ignore.")
    return 0

class ParseableTextReporter(text.TextReporter):
    name = 'parseable'
    line_format = '{path}:{line}: [{msg_id}({symbol}), {obj}] {msg}'

    # that's it folks


class LintRunner(object):
    def __init__(self):
        self.config = Config()
        self.idline = re.compile("^[*]* Module .*")
        self.detail = re.compile("(\S+):(\d+): \[(\S+)\((\S+)\), (\S+)?] (.*)")

    def dolint(self, filename):
        exceptions = set()

        buffer = csio()
        reporter = ParseableTextReporter(output=buffer)
        options = list(self.config.get('options'))
        options.append(filename)
        lint.Run(options, reporter=reporter, exit=False)

        output = buffer.getvalue()
        buffer.close()

        for line in output.splitlines():
            if self.idline.match(line):
                continue

            if self.detail.match(line):
                mo = self.detail.search(line)
                tokens = mo.groups()
                fn = tokens[0]
                ln = tokens[1]
                code = tokens[2]
                codename = tokens[3]
                func = tokens[4]
                message = tokens[5]

                if not self.config.ignore(fn, code, codename, message):
                    exceptions.add((fn, ln, code, codename, func, message))

        return exceptions

    def process(self, mode=MODE_CHECK):
        files_processed = 0
        files_with_errors = 0
        errors_recorded = 0
        exceptions_recorded = 0
        all_exceptions = []

        for (root, dirs, files) in os.walk(self.config.get('folder')):
            # if we shouldn't even bother about this part of the
            # directory structure, we can punt quietly
            if self.config.is_file_ignored(root):
                continue

            # since we are walking top down, let's clean up the dirs
            # that we will walk by eliminating any dirs that will
            # end up getting ignored
            for d in dirs:
                p = os.path.join(root, d)
                if self.config.is_file_ignored(p):
                    dirs.remove(d)

            # check if we can ignore the file and process if not
            for f in files:
                p = os.path.join(root, f)
                if self.config.is_file_ignored(p):
                    continue

                if not self.config.is_file_included(f):
                    continue

                files_processed += 1
                exceptions = self.dolint(p)
                file_had_errors = 0

                for e in exceptions:
                    # what we do with this exception depents on the
                    # kind of exception, and the mode
                    if self.config.is_always_error(e[5]):
                        all_exceptions.append(e)
                        errors_recorded += 1
                        file_had_errors += 1
                    elif mode == MODE_REBUILD:
                        # parameters to ignore_file_code_message are
                        # filename, code, message and function
                        self.config.ignore_file_code_message(e[0], e[2], e[-1], e[4])
                        self.config.ignore_file_code_message(e[0], e[3], e[-1], e[4])
                        exceptions_recorded += 1
                    elif mode == MODE_CHECK:
                        all_exceptions.append(e)
                        errors_recorded += 1
                        file_had_errors += 1

                if file_had_errors:
                    files_with_errors += 1

        for e in sorted(all_exceptions):
            print("ERROR: %s %s: %s %s, %s: %s" %
                  (e[0], e[1], e[2], e[3], e[4], e[5]))

        return (files_processed, files_with_errors, errors_recorded,
                exceptions_recorded)

    def rebuild(self):
        self.initialize()
        (files_processed,
         files_with_errors,
         errors_recorded,
         exceptions_recorded) = self.process(mode=MODE_REBUILD)

        if files_with_errors > 0:
            print("Rebuild failed. %s files processed, %s had errors, "
                  "%s errors recorded." % (
                      files_processed, files_with_errors, errors_recorded))

            return 1

        self.config.save()
        print("Rebuild completed. %s files processed, %s exceptions recorded." %
              (files_processed, exceptions_recorded))
        return 0

    def check(self):
        self.config.load()
        (files_processed,
         files_with_errors,
         errors_recorded,
         exceptions_recorded) = self.process(mode=MODE_CHECK)

        if files_with_errors > 0:
            print("Check failed. %s files processed, %s had errors, "
                  "%s errors recorded." % (
                      files_processed, files_with_errors, errors_recorded))
            return 1

        print("Check succeeded. %s files processed" % files_processed)
        return 0

    def initialize(self):
        self.config.save()
        return 0

def check():
    exit(LintRunner().check())

def rebuild():
    exit(LintRunner().rebuild())

def initialize():
    exit(LintRunner().initialize())

if __name__ == "__main__":
    main()
