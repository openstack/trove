#!/usr/bin/env python

# Copyright 2014 OpenStack Foundation
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

import run_tests
import argparse
import os
import sys


def import_tests():
    from trove.tests.examples import snippets
    snippets.monkey_patch_uuid_and_date()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate Example Snippets')
    parser.add_argument('--fix-examples', action='store_true',
                        help='Fix the examples rather than failing tests.')

    args = parser.parse_args()
    if args.fix_examples:
        os.environ['TESTS_FIX_EXAMPLES'] = 'True'
        # Remove the '--fix-examples' argument from sys.argv as it is not a
        # valid argument in the run_tests module.
        sys.argv.pop(sys.argv.index('--fix-examples'))

    run_tests.main(import_tests)
