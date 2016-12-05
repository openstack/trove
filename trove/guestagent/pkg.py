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
import os
import re
import subprocess
from tempfile import NamedTemporaryFile

from oslo_log import log as logging
import pexpect

from trove.common import exception
from trove.common.exception import ProcessExecutionError
from trove.common.i18n import _
from trove.common import utils
from trove.guestagent.common import operating_system


LOG = logging.getLogger(__name__)
OK = 0
RUN_DPKG_FIRST = 1
REINSTALL_FIRST = 2
CONFLICT_REMOVED = 3


def getoutput(*cmd):
    """Get the stdout+stderr of a command, ignore errors.

    Similar to commands.getstatusoutput(cmd)[1] of Python 2.
    """

    try:
        proc = subprocess.Popen(cmd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
    except OSError:
        # ignore errors like program not found
        return b''
    stdout = proc.communicate()[0]
    return stdout


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


class PkgDownloadError(exception.TroveError):
    pass


class PkgSignError(exception.TroveError):
    pass


class PkgBrokenError(exception.TroveError):
    pass


class PkgConfigureError(exception.TroveError):
    pass


class BasePackagerMixin(object):

    def pexpect_kill_proc(self, child):
        child.delayafterclose = 1
        child.delayafterterminate = 1
        try:
            child.close(force=True)
        except pexpect.ExceptionPexpect:
            # Close fails to terminate a sudo process on some OSes.
            subprocess.call(['sudo', 'kill', str(child.pid)])

    def pexpect_wait_and_close_proc(self, child):
        child.expect(pexpect.EOF)
        child.close()

    def pexpect_run(self, cmd, output_expects, time_out):
        child = pexpect.spawn(cmd, timeout=time_out)
        try:
            i = child.expect(output_expects)
            match = child.match
            self.pexpect_wait_and_close_proc(child)
        except pexpect.TIMEOUT:
            self.pexpect_kill_proc(child)
            raise PkgTimeout(_("Process timeout after %i seconds.") % time_out)
        return (i, match)


class RPMPackagerMixin(BasePackagerMixin):

    def _rpm_remove_nodeps(self, package_name):
        """
        Sometimes transaction errors happens, easy way is to remove
        conflicted package without dependencies and hope it will replaced
        by another package
        """
        try:
            utils.execute("rpm", "-e", "--nodeps", package_name,
                          run_as_root=True, root_helper="sudo")
        except ProcessExecutionError:
            LOG.exception(_("Error removing conflict %(package)s") %
                          package_name)

    def _install(self, packages, time_out):
        """must be overridden by an RPM based PackagerMixin"""
        raise NotImplementedError()

    def _remove(self, package_name, time_out):
        """must be overridden by an RPM based PackagerMixin"""
        raise NotImplementedError()

    def pkg_install(self, packages, config_opts, time_out):
        result = self._install(packages, time_out)
        if result != OK:
            while result == CONFLICT_REMOVED:
                result = self._install(packages, time_out)
            if result != OK:
                raise PkgPackageStateError(_("Cannot install packages."))

    def pkg_is_installed(self, packages):
        packages = packages if isinstance(packages, list) else packages.split()
        std_out = getoutput("rpm", "-qa")
        for pkg in packages:
            found = False
            for line in std_out.split("\n"):
                if line.find(pkg) != -1:
                    found = True
                    break
            if not found:
                return False
        return True

    def pkg_version(self, package_name):
        std_out = getoutput("rpm", "-qa",
                            "--qf", "'%{VERSION}-%{RELEASE}\n'",
                            package_name)
        # Need to capture the version string
        # check the command output
        for line in std_out.split("\n"):
            regex = re.compile("[0-9.]+-.*")
            matches = regex.match(line)
            if matches:
                line = matches.group()
                return line

        LOG.error(_("Unexpected output from rpm command. (%(output)s)") %
                  {'output': std_out})

    def pkg_remove(self, package_name, time_out):
        """Removes a package."""
        if self.pkg_version(package_name) is None:
            return
        result = self._remove(package_name, time_out)
        if result != OK:
            raise PkgPackageStateError(_("Package %s is in a bad state.")
                                       % package_name)


class RedhatPackagerMixin(RPMPackagerMixin):
    def _install(self, packages, time_out):
        """Attempts to install packages.

        Returns OK if the packages are installed or a result code if a
        recoverable-error occurred.
        Raises an exception if a non-recoverable error or timeout occurs.

        """
        cmd = "sudo yum --color=never -y install %s" % " ".join(packages)
        output_expects = ['\[sudo\] password for .*:',
                          'No package (.*) available.',
                          ('file .* from install of .* conflicts with file'
                           ' from package (.*?)\r\n'),
                          'Error: (.*?) conflicts with .*?\r\n',
                          'Processing Conflict: .* conflicts (.*?)\r\n',
                          '.*scriptlet failed*',
                          'HTTP Error',
                          'No more mirrors to try.',
                          'GPG key retrieval failed:',
                          '.*already installed and latest version',
                          'Updated:',
                          'Installed:']
        LOG.debug("Running package install command: %s" % cmd)
        i, match = self.pexpect_run(cmd, output_expects, time_out)
        if i == 0:
            raise PkgPermissionError(_("Invalid permissions."))
        elif i == 1:
            raise PkgNotFoundError(_("Could not find package %s") %
                                   match.group(1))
        elif i == 2 or i == 3 or i == 4:
            self._rpm_remove_nodeps(match.group(1))
            return CONFLICT_REMOVED
        elif i == 5:
            raise PkgScriptletError(_("Package scriptlet failed"))
        elif i == 6 or i == 7:
            raise PkgDownloadError(_("Package download problem"))
        elif i == 8:
            raise PkgSignError(_("GPG key retrieval failed"))
        return OK

    def _remove(self, package_name, time_out):
        """Removes a package.

        Returns OK if the package is removed successfully or a result code if a
        recoverable-error occurs.
        Raises an exception if a non-recoverable error or timeout occurs.

        """
        cmd = "sudo yum --color=never -y remove %s" % package_name
        LOG.debug("Running package remove command: %s" % cmd)
        output_expects = ['\[sudo\] password for .*:',
                          'No Packages marked for removal',
                          'Removed:']
        i, match = self.pexpect_run(cmd, output_expects, time_out)
        if i == 0:
            raise PkgPermissionError(_("Invalid permissions."))
        elif i == 1:
            raise PkgNotFoundError(_("Could not find package %s") %
                                   package_name)
        return OK


class DebianPackagerMixin(BasePackagerMixin):

    def _fix(self, time_out):
        """Sometimes you have to run this command before a
            package will install.
        """
        try:
            utils.execute("dpkg", "--configure", "-a", run_as_root=True,
                          root_helper="sudo")
        except ProcessExecutionError:
            LOG.exception(_("Error fixing dpkg"))

    def _fix_package_selections(self, packages, config_opts):
        """
        Sometimes you have to run this command before a package will install.
        This command sets package selections to configure package.
        """
        selections = ""
        for package in packages:
            m = re.match('(.+)=(.+)', package)
            if m:
                package_name = m.group(1)
            else:
                package_name = package
            std_out = getoutput("sudo", "debconf-show", package_name)
            for line in std_out.split("\n"):
                for selection, value in config_opts.items():
                    m = re.match(".* (.*/%s):.*" % selection, line)
                    if m:
                        selections += ("%s %s string '%s'\n" %
                                       (package_name, m.group(1), value))
        if selections:
            with NamedTemporaryFile(delete=False) as f:
                fname = f.name
                f.write(selections)
            try:
                utils.execute("debconf-set-selections", fname,
                              run_as_root=True, root_helper="sudo")
                utils.execute("dpkg", "--configure", "-a",
                              run_as_root=True, root_helper="sudo")
            except ProcessExecutionError:
                raise PkgConfigureError(_("Error configuring package."))
            finally:
                os.remove(fname)

    def _install(self, packages, time_out):
        """Attempts to install packages.

        Returns OK if the packages are installed or a result code if a
        recoverable-error occurred.
        Raises an exception if a non-recoverable error or timeout occurs.

        """
        cmd = "sudo -E DEBIAN_FRONTEND=noninteractive apt-get -y " \
              "--force-yes --allow-unauthenticated -o " \
              "DPkg::options::=--force-confmiss --reinstall " \
              "install %s" % " ".join(packages)
        output_expects = ['.*password*',
                          'E: Unable to locate package (.*)',
                          "Couldn't find package (.*)",
                          "E: Version '.*' for '(.*)' was not found",
                          ("dpkg was interrupted, you must manually run "
                           "'sudo dpkg --configure -a'"),
                          "Unable to lock the administration directory",
                          ("E: Unable to correct problems, you have held "
                           "broken packages."),
                          "Setting up (.*)",
                          "is already the newest version"]
        LOG.debug("Running package install command: %s" % cmd)
        i, match = self.pexpect_run(cmd, output_expects, time_out)
        if i == 0:
            raise PkgPermissionError(_("Invalid permissions."))
        elif i == 1 or i == 2 or i == 3:
            raise PkgNotFoundError(_("Could not find package %s") %
                                   match.group(1))
        elif i == 4:
            return RUN_DPKG_FIRST
        elif i == 5:
            raise PkgAdminLockError()
        elif i == 6:
            raise PkgBrokenError()
        return OK

    def _remove(self, package_name, time_out):
        """Removes a package.

        Returns OK if the package is removed successfully or a result code if a
        recoverable-error occurs.
        Raises an exception if a non-recoverable error or timeout occurs.

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
        LOG.debug("Running remove package command %s" % cmd)
        i, match = self.pexpect_run(cmd, output_expects, time_out)
        if i == 0:
            raise PkgPermissionError(_("Invalid permissions."))
        elif i == 1:
            raise PkgNotFoundError(_("Could not find package %s") %
                                   package_name)
        elif i == 2 or i == 3:
            return REINSTALL_FIRST
        elif i == 4:
            return RUN_DPKG_FIRST
        elif i == 5:
            raise PkgAdminLockError()
        return OK

    def pkg_install(self, packages, config_opts, time_out):
        """Installs packages."""
        try:
            utils.execute("apt-get", "update", run_as_root=True,
                          root_helper="sudo")
        except ProcessExecutionError:
            LOG.exception(_("Error updating the apt sources"))

        result = self._install(packages, time_out)
        if result != OK:
            if result == RUN_DPKG_FIRST:
                self._fix(time_out)
            result = self._install(packages, time_out)
            if result != OK:
                raise PkgPackageStateError(_("Packages are in a bad state."))
        # even after successful install, packages can stay unconfigured
        # config_opts - is dict with name/value for questions asked by
        # interactive configure script
        if config_opts:
            self._fix_package_selections(packages, config_opts)

    def pkg_version(self, package_name):
        std_out = getoutput("apt-cache", "policy", package_name)
        for line in std_out.split("\n"):
            m = re.match("\s+Installed: (.*)", line)
            if m:
                version = m.group(1)
                if version == "(none)":
                    version = None
                return version

    def pkg_is_installed(self, packages):
        packages = packages if isinstance(packages, list) else packages.split()
        for pkg in packages:
            m = re.match('(.+)=(.+)', pkg)
            if m:
                package_name = m.group(1)
                package_version = m.group(2)
            else:
                package_name = pkg
                package_version = None
            installed_version = self.pkg_version(package_name)
            if ((package_version and installed_version == package_version) or
               (installed_version and not package_version)):
                LOG.debug("Package %s already installed." % package_name)
            else:
                return False
        return True

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
                raise PkgPackageStateError(_("Package %s is in a bad state.")
                                           % package_name)


if operating_system.get_os() == operating_system.REDHAT:
    class Package(RedhatPackagerMixin):
        pass
else:
    class Package(DebianPackagerMixin):
        pass
