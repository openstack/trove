# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2011 OpenStack, LLC.
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

import testtools
from mock import Mock
import pexpect
from reddwarf.common import utils
from reddwarf.common import exception
from reddwarf.guestagent import pkg
import commands
import re

"""
Unit tests for the classes and functions in pkg.py.
"""


class PkgInstallTestCase(testtools.TestCase):

    def setUp(self):
        super(PkgInstallTestCase, self).setUp()
        self.utils_execute = utils.execute
        self.pexpect_spawn_init = pexpect.spawn.__init__
        self.pexpect_spawn_closed = pexpect.spawn.close
        self.pkg_fix = pkg._fix
        utils.execute = Mock()
        pexpect.spawn.__init__ = Mock(return_value=None)
        pexpect.spawn.closed = Mock(return_value=None)
        pkg._fix = Mock(return_value=None)
        self.pkgName = 'packageName'

    def tearDown(self):
        super(PkgInstallTestCase, self).tearDown()
        utils.execute = self.utils_execute
        pexpect.spawn.__init__ = self.pexpect_spawn_init
        pexpect.spawn.close = self.pexpect_spawn_closed
        pkg._fix = self.pkg_fix

    def test_success_install(self):
        # test
        pexpect.spawn.expect = Mock(return_value=5)
        self.assertTrue(pkg.pkg_install(self.pkgName, 5000) is None)
        # verify

    def test_already_instaled(self):
        # test happy path
        pexpect.spawn.expect = Mock(return_value=6)
        pkg.pkg_install(self.pkgName, 5000)

    def test_permission_error(self):
        # test
        pexpect.spawn.expect = Mock(return_value=0)
        # test and verify
        self.assertRaises(pkg.PkgPermissionError, pkg.pkg_install,
                          self.pkgName, 5000)

    def test_package_not_found_1(self):
        # test
        pexpect.spawn.expect = Mock(return_value=1)
        # test and verify
        self.assertRaises(pkg.PkgNotFoundError, pkg.pkg_install,
                          self.pkgName, 5000)

    def test_package_not_found_2(self):
        # test
        pexpect.spawn.expect = Mock(return_value=2)
        # test and verify
        self.assertRaises(pkg.PkgNotFoundError, pkg.pkg_install,
                          self.pkgName, 5000)

    def test_run_DPKG_bad_State(self):
        # test _fix method is called and PackageStateError is thrown
        pexpect.spawn.expect = Mock(return_value=3)
        # test and verify
        self.assertRaises(pkg.PkgPackageStateError, pkg.pkg_install,
                          self.pkgName, 5000)
        self.assertTrue(pkg._fix.called)

    def test_admin_lock_error(self):
        # test 'Unable to lock the administration directory' error
        pexpect.spawn.expect = Mock(return_value=4)
        # test and verify
        self.assertRaises(pkg.PkgAdminLockError, pkg.pkg_install,
                          self.pkgName, 5000)

    def test_timeout_error(self):
        # test timeout error
        pexpect.spawn.expect = Mock(side_effect=pexpect.
                                    TIMEOUT('timeout error'))
        # test and verify
        self.assertRaises(pkg.PkgTimeout, pkg.pkg_install, self.pkgName, 5000)


class PkgRemoveTestCase(testtools.TestCase):

    def setUp(self):
        super(PkgRemoveTestCase, self).setUp()
        self.utils_execute = utils.execute
        self.pexpect_spawn_init = pexpect.spawn.__init__
        self.pexpect_spawn_closed = pexpect.spawn.close
        self.pkg_version = pkg.pkg_version
        self.pkg_install = pkg._install
        self.pkg_fix = pkg._fix

        utils.execute = Mock()
        pexpect.spawn.__init__ = Mock(return_value=None)
        pexpect.spawn.closed = Mock(return_value=None)
        pkg.pkg_version = Mock(return_value="OK")
        pkg._install = Mock(return_value=None)
        pkg._fix = Mock(return_value=None)

        self.pkgName = 'packageName'

    def tearDown(self):
        super(PkgRemoveTestCase, self).tearDown()
        utils.execute = self.utils_execute
        pexpect.spawn.__init__ = self.pexpect_spawn_init
        pexpect.spawn.close = self.pexpect_spawn_closed
        pkg.pkg_version = self.pkg_version
        pkg._install = self.pkg_install
        pkg._fix = self.pkg_fix

    def test_success_remove(self):
        # test
        pexpect.spawn.expect = Mock(return_value=6)
        self.assertTrue(pkg.pkg_remove(self.pkgName, 5000) is None)

    def test_permission_error(self):
        # test
        pexpect.spawn.expect = Mock(return_value=0)
        # test and verify
        self.assertRaises(pkg.PkgPermissionError, pkg.pkg_remove,
                          self.pkgName, 5000)

    def test_package_not_found(self):
        # test
        pexpect.spawn.expect = Mock(return_value=1)
        # test and verify
        self.assertRaises(pkg.PkgNotFoundError, pkg.pkg_remove,
                          self.pkgName, 5000)

    def test_package_reinstall_first_1(self):
        # test
        pexpect.spawn.expect = Mock(return_value=2)
        # test and verify
        self.assertRaises(pkg.PkgPackageStateError, pkg.pkg_remove,
                          self.pkgName, 5000)
        self.assertTrue(pkg._install.called)
        self.assertFalse(pkg._fix.called)

    def test_package_reinstall_first_2(self):
        # test
        pexpect.spawn.expect = Mock(return_value=3)
        # test and verify
        self.assertRaises(pkg.PkgPackageStateError, pkg.pkg_remove,
                          self.pkgName, 5000)
        self.assertTrue(pkg._install.called)
        self.assertFalse(pkg._fix.called)

    def test_package_DPKG_first(self):
        # test
        pexpect.spawn.expect = Mock(return_value=4)
        # test and verify
        self.assertRaises(pkg.PkgPackageStateError, pkg.pkg_remove,
                          self.pkgName, 5000)
        self.assertFalse(pkg._install.called)
        self.assertTrue(pkg._fix.called)

    def test_admin_lock_error(self):
        # test 'Unable to lock the administration directory' error
        pexpect.spawn.expect = Mock(return_value=5)
        # test and verify
        self.assertRaises(pkg.PkgAdminLockError, pkg.pkg_remove,
                          self.pkgName, 5000)

    def test_timeout_error(self):
        # test timeout error
        pexpect.spawn.expect = Mock(side_effect=pexpect.
                                    TIMEOUT('timeout error'))
        # test and verify
        self.assertRaises(pkg.PkgTimeout, pkg.pkg_remove,
                          self.pkgName, 5000)


class PkgVersionTestCase(testtools.TestCase):

    @staticmethod
    def build_output(packageName, packageVersion, parts=None):
        if parts is None:
            parts = "ii " + packageName + "  " + packageVersion + \
                    "  MySQL database server binaries "\
                    "and system database setup \n"
        cmd_out = "Desired=Unknown/Install/Remove/Purge/Hold\n" \
                  "| Status=Not/Inst/Conf-files/Unpacked/halF-conf/"\
                  "Half-inst/trig-aWait/Trig-pend\n" \
                  "|/ Err?=(none)/Reinst-required "\
                  "(Status,Err: uppercase=bad)\n"\
                  "||/ Name   Version  Description\n" \
                  "+++-==============-================-=============\n" \
                  "=================================\n" + parts
        return cmd_out

    def setUp(self):
        super(PkgVersionTestCase, self).setUp()
        self.pkgName = 'mysql-server-5.5'
        self.pkgVersion = '5.5.28-0'
        self.commands_output = commands.getstatusoutput

    def tearDown(self):
        super(PkgVersionTestCase, self).tearDown()
        commands.getstatusoutput = self.commands_output

    def test_version_success(self):
        cmd_out = self.build_output(self.pkgName, self.pkgVersion)
        commands.getstatusoutput = Mock(return_value=(0, cmd_out))
        version = pkg.pkg_version(self.pkgName)
        self.assertTrue(version)
        self.assertEqual(self.pkgVersion, version)

    def test_version_status_error(self):
        cmd_out = self.build_output(self.pkgName, self.pkgVersion)
        commands.getstatusoutput = Mock(return_value=(1, cmd_out))
        self.assertFalse(pkg.pkg_version(self.pkgName))

    def test_version_no_output(self):
        cmd_out = self.build_output(self.pkgName, self.pkgVersion, "")
        commands.getstatusoutput = Mock(return_value=(0, cmd_out))
        self.assertRaises(exception.GuestError, pkg.pkg_version, self.pkgName)

    def test_version_unexpected_parts(self):
        unexp_parts = "ii   123"
        cmd_out = self.build_output(self.pkgName, self.pkgVersion, unexp_parts)
        commands.getstatusoutput = Mock(return_value=(0, cmd_out))
        self.assertRaises(exception.GuestError, pkg.pkg_version, self.pkgName)

    def test_version_wrong_package(self):
        invalid_pkg = "package_invalid_001"
        cmd_out = self.build_output(invalid_pkg, self.pkgVersion)
        commands.getstatusoutput = Mock(return_value=(0, cmd_out))
        self.assertRaises(exception.GuestError, pkg.pkg_version, self.pkgName)

    def test_version_unknown_package(self):
        unk_parts = "un   " + self.pkgName + "   " + self.pkgVersion + "   \n"
        cmd_out = self.build_output(self.pkgName, self.pkgVersion, unk_parts)
        commands.getstatusoutput = Mock(return_value=(0, cmd_out))
        self.assertFalse(pkg.pkg_version(self.pkgName))

    def test_version_no_version(self):
        cmd_out = self.build_output(self.pkgName, '<none>')
        commands.getstatusoutput = Mock(return_value=(0, cmd_out))
        self.assertFalse(pkg.pkg_version(self.pkgName))
