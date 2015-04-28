# Copyright (c) 2011 OpenStack Foundation
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

import os
import subprocess
import testtools
from mock import Mock, MagicMock, patch
import pexpect
import commands
import re

from trove.common import exception
from trove.common import utils
from trove.guestagent import pkg

"""
Unit tests for the classes and functions in pkg.py.
"""


class PkgDEBInstallTestCase(testtools.TestCase):

    def setUp(self):
        super(PkgDEBInstallTestCase, self).setUp()
        self.pkg = pkg.DebianPackagerMixin()
        self.pkg_fix = self.pkg._fix
        self.pkg_fix_package_selections = self.pkg._fix_package_selections

        p0 = patch('pexpect.spawn')
        p0.start()
        self.addCleanup(p0.stop)

        p1 = patch('trove.common.utils.execute')
        p1.start()
        self.addCleanup(p1.stop)

        self.pkg._fix = Mock(return_value=None)
        self.pkg._fix_package_selections = Mock(return_value=None)
        self.pkgName = 'packageName'

    def tearDown(self):
        super(PkgDEBInstallTestCase, self).tearDown()
        self.pkg._fix = self.pkg_fix
        self.pkg._fix_package_selections = self.pkg_fix_package_selections

    def test_pkg_is_installed_no_packages(self):
        packages = []
        self.assertTrue(self.pkg.pkg_is_installed(packages))

    def test_pkg_is_installed_yes(self):
        packages = ["package1=1.0", "package2"]
        self.pkg.pkg_version = MagicMock(side_effect=["1.0", "2.0"])
        self.assertTrue(self.pkg.pkg_is_installed(packages))

    def test_pkg_is_installed_no(self):
        packages = ["package1=1.0", "package2", "package3=3.1"]
        self.pkg.pkg_version = MagicMock(side_effect=["1.0", "2.0", "3.0"])
        self.assertFalse(self.pkg.pkg_is_installed(packages))

    def test_success_install(self):
        # test
        pexpect.spawn.return_value.expect.return_value = 7
        pexpect.spawn.return_value.match = False
        self.assertTrue(self.pkg.pkg_install(self.pkgName, {}, 5000) is None)

    def test_success_install_with_config_opts(self):
        # test
        config_opts = {'option': 'some_opt'}
        pexpect.spawn.return_value.expect.return_value = 7
        pexpect.spawn.return_value.match = False
        self.assertTrue(
            self.pkg.pkg_install(self.pkgName, config_opts, 5000) is None)

    def test_permission_error(self):
        # test
        pexpect.spawn.return_value.expect.return_value = 0
        pexpect.spawn.return_value.match = False
        # test and verify
        self.assertRaises(pkg.PkgPermissionError, self.pkg.pkg_install,
                          self.pkgName, {}, 5000)

    def test_package_not_found_1(self):
        # test
        pexpect.spawn.return_value.expect.return_value = 1
        pexpect.spawn.return_value.match = re.match('(.*)', self.pkgName)
        # test and verify
        self.assertRaises(pkg.PkgNotFoundError, self.pkg.pkg_install,
                          self.pkgName, {}, 5000)

    def test_package_not_found_2(self):
        # test
        pexpect.spawn.return_value.expect.return_value = 2
        pexpect.spawn.return_value.match = re.match('(.*)', self.pkgName)
        # test and verify
        self.assertRaises(pkg.PkgNotFoundError, self.pkg.pkg_install,
                          self.pkgName, {}, 5000)

    def test_run_DPKG_bad_State(self):
        # test _fix method is called and PackageStateError is thrown
        pexpect.spawn.return_value.expect.return_value = 4
        pexpect.spawn.return_value.match = False
        # test and verify
        self.assertRaises(pkg.PkgPackageStateError, self.pkg.pkg_install,
                          self.pkgName, {}, 5000)
        self.assertTrue(self.pkg._fix.called)

    def test_admin_lock_error(self):
        # test 'Unable to lock the administration directory' error
        pexpect.spawn.return_value.expect.return_value = 5
        pexpect.spawn.return_value.match = False
        # test and verify
        self.assertRaises(pkg.PkgAdminLockError, self.pkg.pkg_install,
                          self.pkgName, {}, 5000)

    def test_package_broken_error(self):
        pexpect.spawn.return_value.expect.return_value = 6
        pexpect.spawn.return_value.match = False
        # test and verify
        self.assertRaises(pkg.PkgBrokenError, self.pkg.pkg_install,
                          self.pkgName, {}, 5000)

    def test_timeout_error(self):
        # test timeout error
        pexpect.spawn.return_value.expect.side_effect = (
            pexpect.TIMEOUT('timeout error'))
        # test and verify
        self.assertRaises(pkg.PkgTimeout, self.pkg.pkg_install,
                          self.pkgName, {}, 5000)


class PkgDEBRemoveTestCase(testtools.TestCase):

    def setUp(self):
        super(PkgDEBRemoveTestCase, self).setUp()
        self.pkg = pkg.DebianPackagerMixin()
        self.pkg_version = self.pkg.pkg_version
        self.pkg_install = self.pkg._install
        self.pkg_fix = self.pkg._fix

        p0 = patch('pexpect.spawn')
        p0.start()
        self.addCleanup(p0.stop)

        p1 = patch('trove.common.utils.execute')
        p1.start()
        self.addCleanup(p1.stop)

        self.pkg.pkg_version = Mock(return_value="OK")
        self.pkg._install = Mock(return_value=None)
        self.pkg._fix = Mock(return_value=None)

        self.pkgName = 'packageName'

    def tearDown(self):
        super(PkgDEBRemoveTestCase, self).tearDown()
        self.pkg.pkg_version = self.pkg_version
        self.pkg._install = self.pkg_install
        self.pkg._fix = self.pkg_fix

    def test_remove_no_pkg_version(self):
        # test
        pexpect.spawn.return_value.expect.return_value = 6
        pexpect.spawn.return_value.match = False
        with patch.object(self.pkg, 'pkg_version', return_value=None):
            self.assertTrue(self.pkg.pkg_remove(self.pkgName, 5000) is None)

    def test_success_remove(self):
        # test
        pexpect.spawn.return_value.expect.return_value = 6
        pexpect.spawn.return_value.match = False
        self.assertTrue(self.pkg.pkg_remove(self.pkgName, 5000) is None)

    def test_permission_error(self):
        # test
        pexpect.spawn.return_value.expect.return_value = 0
        pexpect.spawn.return_value.match = False
        # test and verify
        self.assertRaises(pkg.PkgPermissionError, self.pkg.pkg_remove,
                          self.pkgName, 5000)

    def test_package_not_found(self):
        # test
        pexpect.spawn.return_value.expect.return_value = 1
        pexpect.spawn.return_value.match = False
        # test and verify
        self.assertRaises(pkg.PkgNotFoundError, self.pkg.pkg_remove,
                          self.pkgName, 5000)

    def test_package_reinstall_first_1(self):
        # test
        pexpect.spawn.return_value.expect.return_value = 2
        pexpect.spawn.return_value.match = False
        # test and verify
        self.assertRaises(pkg.PkgPackageStateError, self.pkg.pkg_remove,
                          self.pkgName, 5000)
        self.assertTrue(self.pkg._install.called)
        self.assertFalse(self.pkg._fix.called)

    def test_package_reinstall_first_2(self):
        # test
        pexpect.spawn.return_value.expect.return_value = 3
        pexpect.spawn.return_value.match = False
        # test and verify
        self.assertRaises(pkg.PkgPackageStateError, self.pkg.pkg_remove,
                          self.pkgName, 5000)
        self.assertTrue(self.pkg._install.called)
        self.assertFalse(self.pkg._fix.called)

    def test_package_DPKG_first(self):
        # test
        pexpect.spawn.return_value.expect.return_value = 4
        pexpect.spawn.return_value.match = False
        # test and verify
        self.assertRaises(pkg.PkgPackageStateError, self.pkg.pkg_remove,
                          self.pkgName, 5000)
        self.assertFalse(self.pkg._install.called)
        self.assertTrue(self.pkg._fix.called)

    def test_admin_lock_error(self):
        # test 'Unable to lock the administration directory' error
        pexpect.spawn.return_value.expect.return_value = 5
        pexpect.spawn.return_value.match = False
        # test and verify
        self.assertRaises(pkg.PkgAdminLockError, self.pkg.pkg_remove,
                          self.pkgName, 5000)

    def test_timeout_error(self):
        # test timeout error
        pexpect.spawn.return_value.expect.side_effect = (
            pexpect.TIMEOUT('timeout error'))
        # test and verify
        self.assertRaises(pkg.PkgTimeout, self.pkg.pkg_remove,
                          self.pkgName, 5000)

    @patch.object(subprocess, 'call')
    def test_timeout_error_with_exception(self, mock_call):
        # test timeout error
        pexpect.spawn.return_value.expect.side_effect = (
            pexpect.TIMEOUT('timeout error'))
        pexpect.spawn.return_value.close.side_effect = (
            pexpect.ExceptionPexpect('error'))
        # test and verify
        self.assertRaises(pkg.PkgTimeout, self.pkg.pkg_remove,
                          self.pkgName, 5000)
        self.assertEqual(1, mock_call.call_count)


class PkgDEBVersionTestCase(testtools.TestCase):

    def setUp(self):
        super(PkgDEBVersionTestCase, self).setUp()
        self.pkgName = 'mysql-server-5.5'
        self.pkgVersion = '5.5.28-0'
        self.commands_output = commands.getstatusoutput

    def tearDown(self):
        super(PkgDEBVersionTestCase, self).tearDown()
        commands.getstatusoutput = self.commands_output

    def test_version_success(self):
        cmd_out = "%s:\n  Installed: %s\n" % (self.pkgName, self.pkgVersion)
        commands.getstatusoutput = Mock(return_value=(0, cmd_out))
        version = pkg.DebianPackagerMixin().pkg_version(self.pkgName)
        self.assertTrue(version)
        self.assertEqual(self.pkgVersion, version)

    def test_version_unknown_package(self):
        cmd_out = "N: Unable to locate package %s" % self.pkgName
        commands.getstatusoutput = Mock(return_value=(0, cmd_out))
        self.assertFalse(pkg.DebianPackagerMixin().pkg_version(self.pkgName))

    def test_version_no_version(self):
        cmd_out = "%s:\n  Installed: %s\n" % (self.pkgName, "(none)")
        commands.getstatusoutput = Mock(return_value=(0, cmd_out))
        self.assertFalse(pkg.DebianPackagerMixin().pkg_version(self.pkgName))


class PkgRPMVersionTestCase(testtools.TestCase):

    def setUp(self):
        super(PkgRPMVersionTestCase, self).setUp()
        self.pkgName = 'python-requests'
        self.pkgVersion = '0.14.2-1.el6'
        self.commands_output = commands.getstatusoutput

    def tearDown(self):
        super(PkgRPMVersionTestCase, self).tearDown()
        commands.getstatusoutput = self.commands_output

    def test_version_no_output(self):
        cmd_out = ''
        commands.getstatusoutput = Mock(return_value=(0, cmd_out))
        self.assertIsNone(pkg.RedhatPackagerMixin().pkg_version(self.pkgName))

    def test_version_success(self):
        cmd_out = self.pkgVersion
        commands.getstatusoutput = Mock(return_value=(0, cmd_out))
        version = pkg.RedhatPackagerMixin().pkg_version(self.pkgName)
        self.assertTrue(version)
        self.assertEqual(self.pkgVersion, version)


class PkgRPMInstallTestCase(testtools.TestCase):

    def setUp(self):
        super(PkgRPMInstallTestCase, self).setUp()
        self.pkg = pkg.RedhatPackagerMixin()
        self.commands_output = commands.getstatusoutput
        self.pkgName = 'packageName'

        p0 = patch('pexpect.spawn')
        p0.start()
        self.addCleanup(p0.stop)

        p1 = patch('trove.common.utils.execute')
        p1.start()
        self.addCleanup(p1.stop)

    def tearDown(self):
        super(PkgRPMInstallTestCase, self).tearDown()
        commands.getstatusoutput = self.commands_output

    def test_pkg_is_installed_no_packages(self):
        packages = []
        self.assertTrue(self.pkg.pkg_is_installed(packages))

    def test_pkg_is_installed_yes(self):
        packages = ["package1=1.0", "package2"]
        commands.getstatusoutput = MagicMock(return_value={1: "package1=1.0\n"
                                                           "package2=2.0"})
        self.assertTrue(self.pkg.pkg_is_installed(packages))

    def test_pkg_is_installed_no(self):
        packages = ["package1=1.0", "package2", "package3=3.0"]
        commands.getstatusoutput = MagicMock(return_value={1: "package1=1.0\n"
                                                           "package2=2.0"})
        self.assertFalse(self.pkg.pkg_is_installed(packages))

    def test_permission_error(self):
        # test
        pexpect.spawn.return_value.expect.return_value = 0
        pexpect.spawn.return_value.match = False
        # test and verify
        self.assertRaises(pkg.PkgPermissionError, self.pkg.pkg_install,
                          self.pkgName, {}, 5000)

    def test_package_not_found(self):
        # test
        pexpect.spawn.return_value.expect.return_value = 1
        pexpect.spawn.return_value.match = re.match('(.*)', self.pkgName)
        # test and verify
        self.assertRaises(pkg.PkgNotFoundError, self.pkg.pkg_install,
                          self.pkgName, {}, 5000)

    def test_package_conflict_remove(self):
        # test
        pexpect.spawn.return_value.expect.return_value = 2
        pexpect.spawn.return_value.match = re.match('(.*)', self.pkgName)
        self.pkg._rpm_remove_nodeps = Mock()
        # test and verify
        self.pkg._install(self.pkgName, 5000)
        self.assertTrue(self.pkg._rpm_remove_nodeps.called)

    def test_package_conflict_remove_install(self):
        with patch.object(self.pkg, '_install', side_effect=[3, 3, 0]):
            self.assertTrue(
                self.pkg.pkg_install(self.pkgName, {}, 5000) is None)
            self.assertEqual(3, self.pkg._install.call_count)

    @patch.object(utils, 'execute')
    def test__rpm_remove_nodeps(self, mock_execute):
        self.pkg._rpm_remove_nodeps(self.pkgName)
        mock_execute.assert_called_with('rpm', '-e', '--nodeps', self.pkgName,
                                        run_as_root=True, root_helper='sudo')

    def test_package_scriptlet_error(self):
        # test
        pexpect.spawn.return_value.expect.return_value = 5
        pexpect.spawn.return_value.match = False
        # test and verify
        self.assertRaises(pkg.PkgScriptletError, self.pkg.pkg_install,
                          self.pkgName, {}, 5000)

    def test_package_http_error(self):
        # test
        pexpect.spawn.return_value.expect.return_value = 6
        pexpect.spawn.return_value.match = False
        # test and verify
        self.assertRaises(pkg.PkgDownloadError, self.pkg.pkg_install,
                          self.pkgName, {}, 5000)

    def test_package_nomirrors_error(self):
        # test
        pexpect.spawn.return_value.expect.return_value = 7
        pexpect.spawn.return_value.match = False
        # test and verify
        self.assertRaises(pkg.PkgDownloadError, self.pkg.pkg_install,
                          self.pkgName, {}, 5000)

    def test_package_sign_error(self):
        # test
        pexpect.spawn.return_value.expect.return_value = 8
        pexpect.spawn.return_value.match = False
        # test and verify
        self.assertRaises(pkg.PkgSignError, self.pkg.pkg_install,
                          self.pkgName, {}, 5000)

    def test_package_already_installed(self):
        # test
        pexpect.spawn.return_value.expect.return_value = 9
        pexpect.spawn.return_value.match = False
        # test and verify
        self.assertTrue(self.pkg.pkg_install(self.pkgName, {}, 5000) is None)

    def test_package_success_updated(self):
        # test
        pexpect.spawn.return_value.expect.return_value = 10
        pexpect.spawn.return_value.match = False
        # test and verify
        self.assertTrue(self.pkg.pkg_install(self.pkgName, {}, 5000) is None)

    def test_package_success_installed(self):
        # test
        pexpect.spawn.return_value.expect.return_value = 11
        pexpect.spawn.return_value.match = False
        # test and verify
        self.assertTrue(self.pkg.pkg_install(self.pkgName, {}, 5000) is None)

    def test_timeout_error(self):
        # test timeout error
        pexpect.spawn.return_value.expect.side_effect = (
            pexpect.TIMEOUT('timeout error'))
        pexpect.spawn.return_value.match = False
        # test and verify
        self.assertRaises(pkg.PkgTimeout, self.pkg.pkg_install,
                          self.pkgName, {}, 5000)


class PkgRPMRemoveTestCase(testtools.TestCase):

    def setUp(self):
        super(PkgRPMRemoveTestCase, self).setUp()
        self.pkg = pkg.RedhatPackagerMixin()
        self.pkg_version = self.pkg.pkg_version
        self.pkg_install = self.pkg._install

        p0 = patch('pexpect.spawn')
        p0.start()
        self.addCleanup(p0.stop)

        p1 = patch('trove.common.utils.execute')
        p1.start()
        self.addCleanup(p1.stop)

        self.pkg.pkg_version = Mock(return_value="OK")
        self.pkg._install = Mock(return_value=None)
        self.pkgName = 'packageName'

    def tearDown(self):
        super(PkgRPMRemoveTestCase, self).tearDown()
        self.pkg.pkg_version = self.pkg_version
        self.pkg._install = self.pkg_install

    def test_permission_error(self):
        # test
        pexpect.spawn.return_value.expect.return_value = 0
        pexpect.spawn.return_value.match = False
        # test and verify
        self.assertRaises(pkg.PkgPermissionError, self.pkg.pkg_remove,
                          self.pkgName, 5000)

    def test_package_not_found(self):
        # test
        pexpect.spawn.return_value.expect.return_value = 1
        pexpect.spawn.return_value.match = False
        # test and verify
        self.assertRaises(pkg.PkgNotFoundError, self.pkg.pkg_remove,
                          self.pkgName, 5000)

    def test_remove_no_pkg_version(self):
        # test
        pexpect.spawn.return_value.expect.return_value = 2
        pexpect.spawn.return_value.match = False
        with patch.object(self.pkg, 'pkg_version', return_value=None):
            self.assertTrue(self.pkg.pkg_remove(self.pkgName, 5000) is None)

    def test_success_remove(self):
        # test
        pexpect.spawn.return_value.expect.return_value = 2
        pexpect.spawn.return_value.match = False
        self.assertTrue(self.pkg.pkg_remove(self.pkgName, 5000) is None)

    def test_timeout_error(self):
        # test timeout error
        pexpect.spawn.return_value.expect.side_effect = (
            pexpect.TIMEOUT('timeout error'))
        pexpect.spawn.return_value.match = False
        # test and verify
        self.assertRaises(pkg.PkgTimeout, self.pkg.pkg_remove,
                          self.pkgName, 5000)


class PkgDEBFixPackageSelections(testtools.TestCase):

    def setUp(self):
        super(PkgDEBFixPackageSelections, self).setUp()
        self.pkg = pkg.DebianPackagerMixin()
        self.commands_output = commands.getstatusoutput

    def tearDown(self):
        super(PkgDEBFixPackageSelections, self).tearDown()
        commands.getstatusoutput = self.commands_output

    @patch.object(os, 'remove')
    @patch.object(pkg, 'NamedTemporaryFile')
    @patch.object(utils, 'execute')
    def test__fix_package_selections(self, mock_execute, mock_temp_file,
                                     mock_remove):
        packages = ["package1"]
        config_opts = {'option': 'some_opt'}
        commands.getstatusoutput = Mock(
            return_value=(0, "* package1/option: some_opt"))
        self.pkg._fix_package_selections(packages, config_opts)
        self.assertEqual(2, mock_execute.call_count)
        self.assertEqual(1, mock_remove.call_count)

    @patch.object(os, 'remove')
    @patch.object(pkg, 'NamedTemporaryFile')
    @patch.object(utils, 'execute',
                  side_effect=exception.ProcessExecutionError)
    def test_fail__fix_package_selections(self, mock_execute, mock_temp_file,
                                          mock_remove):
        packages = ["package1"]
        config_opts = {'option': 'some_opt'}
        commands.getstatusoutput = Mock(
            return_value=(0, "* package1/option: some_opt"))
        self.assertRaises(pkg.PkgConfigureError,
                          self.pkg._fix_package_selections,
                          packages, config_opts)
        self.assertEqual(1, mock_remove.call_count)

    @patch.object(utils, 'execute')
    def test__fix(self, mock_execute):
        self.pkg._fix(30)
        mock_execute.assert_called_with('dpkg', '--configure', '-a',
                                        run_as_root=True, root_helper='sudo')
