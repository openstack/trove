#!/usr/bin/env python

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
#
# Copyright 2010 OpenStack Foundation
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

"""
Installation script for Trove's development virtualenv
"""

import os
import subprocess
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
VENV = os.path.join(ROOT, '.venv')
PIP_REQUIRES = os.path.join(ROOT, 'requirements.txt')
TEST_REQUIRES = os.path.join(ROOT, 'test-requirements.txt')
PY_VERSION = "python%s.%s" % (sys.version_info[0], sys.version_info[1])


def die(message, *args):
    print(message % args, file=sys.stderr)
    sys.exit(1)


def run_command(cmd, redirect_output=True, check_exit_code=True):
    """
    Runs a command in an out-of-process shell, returning the
    output of that command.  Working directory is ROOT.
    """
    if redirect_output:
        stdout = subprocess.PIPE
    else:
        stdout = None

    proc = subprocess.Popen(cmd, cwd=ROOT, stdout=stdout)
    output = proc.communicate()[0]
    if check_exit_code and proc.returncode != 0:
        die('Command "%s" failed.\n%s', ' '.join(cmd), output)
    return output


HAS_EASY_INSTALL = bool(run_command(['which', 'easy_install'],
    check_exit_code=False).strip())
HAS_VIRTUALENV = bool(run_command(['which', 'virtualenv'],
    check_exit_code=False).strip())


def check_dependencies():
    """Make sure virtualenv is in the path."""

    if not HAS_VIRTUALENV:
        print('not found.')
        # Try installing it via easy_install...
        if HAS_EASY_INSTALL:
            print('Installing virtualenv via easy_install...'),
            if not (run_command(['which', 'easy_install']) and
                    run_command(['easy_install', 'virtualenv'])):
                die('ERROR: virtualenv not found.\nTrove development'
                    ' requires virtualenv, please install it using your'
                    ' favorite package management tool')
            print('done.')
    print('done.')


def create_virtualenv(venv=VENV):
    """Creates the virtual environment and installs PIP only into the
    virtual environment
    """
    print('Creating venv...'),
    run_command(['virtualenv', '-q', '--no-site-packages', VENV])
    print('done.')
    print('Installing pip in virtualenv...'),
    if not run_command(['tools/with_venv.sh', 'easy_install', 'pip']).strip():
        die("Failed to install pip.")
    print('done.')


def install_dependencies(venv=VENV):
    print('Installing dependencies with pip (this can take a while)...')
    # Install greenlet by hand - just listing it in the requires file does not
    # get it in stalled in the right order
    run_command(['tools/with_venv.sh', '-E', venv, 'pip', 'install',
                 'greenlet'], redirect_output=False)
    for requires in (PIP_REQUIRES, TEST_REQUIRES):
        run_command(['tools/with_venv.sh', '-E', venv, 'pip', 'install', '-r',
                     requires], redirect_output=False)

    # Tell the virtual env how to "import trove"
    pthfile = os.path.join(venv, "lib", PY_VERSION, "site-packages",
        "trove.pth")
    f = open(pthfile, 'w')
    f.write("%s\n" % ROOT)


def print_help():
    help = """
    Trove development environment setup is complete.

    Trove development uses virtualenv to track and manage Python
    dependencies while in development and testing.

    To activate the Trove virtualenv for the extent of your current shell
    session you can run:

    $ . .venv/bin/activate

    Or, if you prefer, you can run commands in the virtualenv on a case by case
    basis by running:

    $ tools/with_venv.sh <your command>

    Also, make test will automatically use the virtualenv.
    """
    print(help)


def main(argv):
    check_dependencies()
    create_virtualenv()
    install_dependencies()
    print_help()

if __name__ == '__main__':
    main(sys.argv)
