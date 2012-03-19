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

"""
Manages packages on the Guest VM.
"""
import logging
import pexpect

from reddwarf.common import exception


LOG = logging.getLogger(__name__)
# FLAGS = flags.FLAGS


class PkgAdminLockError(exception.ReddwarfError):
    pass


class PkgPermissionError(exception.ReddwarfError):
    pass


class PkgPackageStateError(exception.ReddwarfError):
    pass


class PkgNotFoundError(exception.NotFound):
    pass


class PkgTimeout(exception.ReddwarfError):
    pass


OK = 0
RUN_DPKG_FIRST = 1
REINSTALL_FIRST = 2


def kill_proc(child):
    child.delayafterclose = 1
    child.delayafterterminate = 1
    child.close(force=True)


def wait_and_close_proc(child, time_out=-1):
    child.expect(pexpect.EOF, timeout=time_out)
    child.close()


class PkgAgent(object):
    """ Agent Controller which can maintain package installs on a guest."""

    def _fix(self, time_out):
        """Sometimes you have to run this command before a pkg will install."""
        #sudo dpkg --configure -a
        child = pexpect.spawn("sudo -E dpkg --configure -a")
        wait_and_close_proc(child, time_out)

    def _install(self, package_name, time_out):
        """Attempts to install a package.

        Returns OK if the package installs fine or a result code if a
        recoverable-error occurred.
        Raises an exception if a non-recoverable error or time out occurs.

        """
        child = pexpect.spawn("sudo -E DEBIAN_FRONTEND=noninteractive "
                              "apt-get -y --allow-unauthenticated install %s"
                              % package_name)
        try:
            i = child.expect(['.*password*',
                              'E: Unable to locate package %s' % package_name,
                              "Couldn't find package % s" % package_name,
                              "dpkg was interrupted, you must manually run "
                                "'sudo dpkg --configure -a'",
                              "Unable to lock the administration directory",
                              "Setting up %s*" % package_name,
                              "is already the newest version"],
                             timeout=time_out)
            if i == 0:
                raise PkgPermissionError("Invalid permissions.")
            elif i == 1 or i == 2:
                raise PkgNotFoundError("Could not find apt %s" % package_name)
            elif i == 3:
                return RUN_DPKG_FIRST
            elif i == 4:
                raise PkgAdminLockError()
            wait_and_close_proc(child)
        except pexpect.TIMEOUT:
            kill_proc(child)
            raise PkgTimeout("Process timeout after %i seconds." % time_out)
        return OK

    def _remove(self, package_name, time_out):
        """Removes a package.

        Returns OK if the package is removed successfully or a result code if a
        recoverable-error occurs.
        Raises an exception if a non-recoverable error or time out occurs.

        """
        child = pexpect.spawn("sudo -E apt-get -y --allow-unauthenticated "
                              "remove %s" % package_name)
        try:
            i = child.expect(['.*password*',
                              'E: Unable to locate package %s' % package_name,
                              'Package is in a very bad inconsistent state',
                              "Sub-process /usr/bin/dpkg returned an "
                                "error code",
                              "dpkg was interrupted, you must manually run "
                                "'sudo dpkg --configure -a'",
                              "Unable to lock the administration directory",
                              #'The following packages will be REMOVED',
                              "Removing %s*" % package_name],
                             timeout=time_out)
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
            wait_and_close_proc(child)
        except pexpect.TIMEOUT:
            kill_proc(child)
            raise PkgTimeout("Process timeout after %i seconds." % time_out)
        return OK

    def pkg_install(self, package_name, time_out):
        """Installs a package."""
        result = self._install(package_name, time_out)
        if result != OK:
            if result == RUN_DPKG_FIRST:
                self._fix(time_out)
            result = self._install(package_name, time_out)
            if result != OK:
                raise PkgPackageStateError("Package %s is in a bad state."
                                           % package_name)

    def pkg_version(self, package_name):
        """Returns the installed version of the given package.

        It is sometimes impossible to know if a package is completely
        unavailable before you attempt to install.  Some packages may return
        no information from the dpkg command but then install fine with apt-get
        install.

        """
        child = pexpect.spawn("dpkg -l %s" % package_name)
        i = child.expect([".*No packages found matching*", "\+\+\+\-"])
        if i == 0:
            #raise PkgNotFoundError()
            return None
        # Need to capture the version string
        child.expect("\n")
        i = child.expect(["<none>", ".*"])
        if i == 0:
            return None
        line = child.match.group()
        parts = line.split()
        # Should be something like:
        # ['un', 'cowsay', '<none>', '(no', 'description', 'available)']
        try:
            wait_and_close_proc(child)
        except pexpect.TIMEOUT:
            kill_proc(child)
            raise PkgTimeout("Remove process took too long.")
        if len(parts) <= 2:
            raise Error("Unexpected output.")
        if parts[1] != package_name:
            raise Error("Unexpected output:[1] == " + str(parts[1]))
        if parts[0] == 'un' or parts[2] == '<none>':
            return None
        return parts[2]

    def pkg_remove(self, package_name, time_out):
        """Removes a package."""
        if self.pkg_version(package_name) == None:
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
