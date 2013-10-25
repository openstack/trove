# vim: tabstop=4 shiftwidth=4 softtabstop=4

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

"""
Manages packages on the Guest VM.
"""
import commands
import re

import pexpect

from trove.common import exception
from trove.common import utils
from trove.common.exception import ProcessExecutionError
from trove.guestagent.common import operating_system
from trove.openstack.common import log as logging
from trove.openstack.common.gettextutils import _


LOG = logging.getLogger(__name__)
OK = 0
RUN_DPKG_FIRST = 1
REINSTALL_FIRST = 2


class PkgAdminLockError(exception.TroveError):
    pass


class PkgPermissionError(exception.TroveError):
    pass


class PkgPackageStateError(exception.TroveError):
    pass


class PkgNotFoundError(exception.NotFound):
    pass


class PkgTimeout(exception.TroveError):
    pass


class PkgScriptletError(exception.TroveError):
    pass


class PkgTransactionCheckError(exception.TroveError):
    pass


class PkgDownloadError(exception.TroveError):
    pass


class BasePackagerMixin:

    def pexpect_kill_proc(self, child):
        child.delayafterclose = 1
        child.delayafterterminate = 1
        child.close(force=True)

    def pexpect_wait_and_close_proc(self, child):
        child.expect(pexpect.EOF)
        child.close()

    def pexpect_run(self, cmd, output_expects, time_out):
        child = pexpect.spawn(cmd, timeout=time_out)
        try:
            i = child.expect(output_expects)
            self.pexpect_wait_and_close_proc(child)
        except pexpect.TIMEOUT:
            self.pexpect_kill_proc(child)
            raise PkgTimeout("Process timeout after %i seconds." % time_out)
        return i


class RedhatPackagerMixin(BasePackagerMixin):

    def _install(self, package_name, time_out):
        """Attempts to install a package.

        Returns OK if the package installs fine or a result code if a
        recoverable-error occurred.
        Raises an exception if a non-recoverable error or time out occurs.

        """
        cmd = "sudo yum --color=never -y install %s" % package_name
        output_expects = ['\[sudo\] password for .*:',
                          'No package %s available.' % package_name,
                          'Transaction Check Error:',
                          '.*scriptlet failed*',
                          'HTTP Error',
                          'No more mirrors to try.',
                          '.*already installed and latest version',
                          'Updated:',
                          'Installed:']
        i = self.pexpect_run(cmd, output_expects, time_out)
        if i == 0:
            raise PkgPermissionError("Invalid permissions.")
        elif i == 1:
            raise PkgNotFoundError("Could not find pkg %s" % package_name)
        elif i == 2:
            raise PkgTransactionCheckError("Transaction Check Error")
        elif i == 3:
            raise PkgScriptletError("Package scriptlet failed")
        elif i == 4 or i == 5:
            raise PkgDownloadError("Package download problem")
        return OK

    def _remove(self, package_name, time_out):
        """Removes a package.

        Returns OK if the package is removed successfully or a result code if a
        recoverable-error occurs.
        Raises an exception if a non-recoverable error or time out occurs.

        """
        cmd = "sudo yum --color=never -y remove %s" % package_name
        output_expects = ['\[sudo\] password for .*:',
                          'No Packages marked for removal',
                          'Removed:']
        i = self.pexpect_run(cmd, output_expects, time_out)
        if i == 0:
            raise PkgPermissionError("Invalid permissions.")
        elif i == 1:
            raise PkgNotFoundError("Could not find pkg %s" % package_name)
        return OK

    def pkg_install(self, package_name, time_out):
        result = self._install(package_name, time_out)
        if result != OK:
            raise PkgPackageStateError("Package %s is in a bad state."
                                       % package_name)

    def pkg_version(self, package_name):
        cmd_list = ["rpm", "-qa", "--qf", "'%{VERSION}-%{RELEASE}\n'",
                    package_name]
        p = commands.getstatusoutput(' '.join(cmd_list))
        # Need to capture the version string
        # check the command output
        std_out = p[1]
        for line in std_out.split("\n"):
            regex = re.compile("[0-9.]+-.*")
            matches = regex.match(line)
            if matches:
                line = matches.group()
                return line
        msg = _("version() saw unexpected output from rpm!")
        LOG.error(msg)

    def pkg_remove(self, package_name, time_out):
        """Removes a package."""
        if self.pkg_version(package_name) is None:
            return
        result = self._remove(package_name, time_out)
        if result != OK:
            raise PkgPackageStateError("Package %s is in a bad state."
                                       % package_name)


class DebianPackagerMixin(BasePackagerMixin):

    def _fix(self, time_out):
        """Sometimes you have to run this command before a pkg will install."""
        try:
            utils.execute("dpkg", "--configure", "-a", run_as_root=True,
                          root_helper="sudo")
        except ProcessExecutionError:
            LOG.error(_("Error fixing dpkg"))

    def _install(self, package_name, time_out):
        """Attempts to install a package.

        Returns OK if the package installs fine or a result code if a
        recoverable-error occurred.
        Raises an exception if a non-recoverable error or time out occurs.

        """
        cmd = "sudo -E DEBIAN_FRONTEND=noninteractive " \
              "apt-get -y --allow-unauthenticated install %s" % package_name
        output_expects = ['.*password*',
                          'E: Unable to locate package %s' % package_name,
                          "Couldn't find package % s" % package_name,
                          ("dpkg was interrupted, you must manually run "
                           "'sudo dpkg --configure -a'"),
                          "Unable to lock the administration directory",
                          "Setting up %s*" % package_name,
                          "is already the newest version"]
        i = self.pexpect_run(cmd, output_expects, time_out)
        if i == 0:
            raise PkgPermissionError("Invalid permissions.")
        elif i == 1 or i == 2:
            raise PkgNotFoundError("Could not find apt %s" % package_name)
        elif i == 3:
            return RUN_DPKG_FIRST
        elif i == 4:
            raise PkgAdminLockError()
        return OK

    def _remove(self, package_name, time_out):
        """Removes a package.

        Returns OK if the package is removed successfully or a result code if a
        recoverable-error occurs.
        Raises an exception if a non-recoverable error or time out occurs.

        """
        cmd = "sudo -E apt-get -y --allow-unauthenticated remove %s" \
              % package_name
        output_expects = ['.*password*',
                          'E: Unable to locate package %s' % package_name,
                          'Package is in a very bad inconsistent state',
                          'Sub-process /usr/bin/dpkg returned an error code',
                          ("dpkg was interrupted, you must manually run "
                           "'sudo dpkg --configure -a'"),
                          "Unable to lock the administration directory",
                          "Removing %s*" % package_name]
        i = self.pexpect_run(cmd, output_expects, time_out)
        if i == 0:
            raise PkgPermissionError("Invalid permissions.")
        elif i == 1:
            raise PkgNotFoundError("Could not find pkg %s" % package_name)
        elif i == 2 or i == 3:
            return REINSTALL_FIRST
        elif i == 4:
            return RUN_DPKG_FIRST
        elif i == 5:
            raise PkgAdminLockError()
        return OK

    def pkg_install(self, package_name, time_out):
        """Installs a package."""
        try:
            utils.execute("apt-get", "update", run_as_root=True,
                          root_helper="sudo")
        except ProcessExecutionError:
            LOG.error(_("Error updating the apt sources"))

        result = self._install(package_name, time_out)
        if result != OK:
            if result == RUN_DPKG_FIRST:
                self._fix(time_out)
            result = self._install(package_name, time_out)
            if result != OK:
                raise PkgPackageStateError("Package %s is in a bad state."
                                           % package_name)

    def pkg_version(self, package_name):
        cmd_list = ["dpkg", "-l", package_name]
        p = commands.getstatusoutput(' '.join(cmd_list))
        # check the command status code
        if not p[0] == 0:
            return None
        # Need to capture the version string
        # check the command output
        std_out = p[1]
        patterns = ['.*No packages found matching.*',
                    "\w\w\s+(\S+)\s+(\S+)\s+(.*)$"]
        for line in std_out.split("\n"):
            for p in patterns:
                regex = re.compile(p)
                matches = regex.match(line)
                if matches:
                    line = matches.group()
                    parts = line.split()
                    if not parts:
                        msg = _("returned nothing")
                        LOG.error(msg)
                        raise exception.GuestError(msg)
                    if len(parts) <= 2:
                        msg = _("Unexpected output.")
                        LOG.error(msg)
                        raise exception.GuestError(msg)
                    if parts[1] != package_name:
                        msg = _("Unexpected output:[1] = %s") % str(parts[1])
                        LOG.error(msg)
                        raise exception.GuestError(msg)
                    if parts[0] == 'un' or parts[2] == '<none>':
                        return None
                    return parts[2]
        msg = _("version() saw unexpected output from dpkg!")
        LOG.error(msg)

    def pkg_remove(self, package_name, time_out):
        """Removes a package."""
        if self.pkg_version(package_name) is None:
            return
        result = self._remove(package_name, time_out)

        if result != OK:
            if result == REINSTALL_FIRST:
                self._install(package_name, time_out)
            elif result == RUN_DPKG_FIRST:
                self._fix(time_out)
            result = self._remove(package_name, time_out)
            if result != OK:
                raise PkgPackageStateError("Package %s is in a bad state."
                                           % package_name)


class BasePackage(type):

    def __new__(meta, name, bases, dct):
        if operating_system.get_os() == operating_system.REDHAT:
            bases += (RedhatPackagerMixin, )
        else:
            # The default is debian
            bases += (DebianPackagerMixin,)
        return super(BasePackage, meta).__new__(meta, name, bases, dct)


class Package(object):

    __metaclass__ = BasePackage
