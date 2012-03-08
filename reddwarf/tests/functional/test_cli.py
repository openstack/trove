# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack LLC.
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

import datetime

import reddwarf
from reddwarf import tests
from reddwarf.common import config
from reddwarf.tests import functional


def run_reddwarf_manage(command):
    reddwarf_manage = tests.reddwarf_bin_path('reddwarf-manage')
    config_file = tests.test_config_file()
    return functional.execute("%(reddwarf_manage)s %(command)s "
                              "--config-file=%(config_file)s" % locals())


class TestDBSyncCLI(tests.BaseTest):

    def test_db_sync_executes(self):
        exitcode, out, err = run_reddwarf_manage("db_sync")
        self.assertEqual(exitcode, 0)


class TestDBUpgradeCLI(tests.BaseTest):

    def test_db_upgrade_executes(self):
        exitcode, out, err = run_reddwarf_manage("db_upgrade")
        self.assertEqual(exitcode, 0)
