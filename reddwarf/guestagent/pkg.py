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
import commands
import pexpect
import re

from reddwarf.common import exception
from reddwarf.common import utils
from reddwarf.common.exception import ProcessExecutionError
from reddwarf.openstack.common import log as logging
from reddwarf.openstack.common.gettextutils import _


LOG = logging.getLogger(__name__)


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


def _fix(time_out):
    """Sometimes you have to run this command before a pkg will install."""
    #sudo dpkg --configure -a
    child = pexpect.spawn("sudo -E dpkg --configure -a")
    wait_and_close_proc(child, time_out)


def _install(package_name, time_out):
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
                          ("dpkg was interrupted, you must manually run "
                           "'sudo dpkg --configure -a'"),
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
    except pexpect.TIMEOUT:
        kill_proc(child)
        raise PkgTimeout("Process timeout after %i seconds." % time_out)
    try:
        wait_and_close_proc(child)
    except pexpect.TIMEOUT as e:
        LOG.error("wait_and_close_proc failed: %s" % e)
        #TODO(tim.simpson): As of RDL, and on my machine exclusively (in
        #                   both Virtual Box and VmWare!) this fails, but
        #                   the package is installed.
    return OK


def _remove(package_name, time_out):
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
                          ("Sub-process /usr/bin/dpkg returned an error "
                           "code"),
                          ("dpkg was interrupted, you must manually run "
                           "'sudo dpkg --configure -a'"),
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


def pkg_install(package_name, time_out):
    """Installs a package."""
    try:
        utils.execute("apt-get", "update", run_as_root=True,
                      root_helper="sudo")
    except ProcessExecutionError as e:
        LOG.error(_("Error updating the apt sources"))

    result = _install(package_name, time_out)
    if result != OK:
        if result == RUN_DPKG_FIRST:
            _fix(time_out)
        result = _install(package_name, time_out)
        if result != OK:
            raise PkgPackageStateError("Package %s is in a bad state."
                                       % package_name)


def pkg_version(package_name):
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
                    msg = _("Unexpected output:[1] = %s" % str(parts[1]))
                    LOG.error(msg)
                    raise exception.GuestError(msg)
                if parts[0] == 'un' or parts[2] == '<none>':
                    return None
                return parts[2]
    msg = _("version() saw unexpected output from dpkg!")
    LOG.error(msg)
    raise exception.GuestError(msg)


def pkg_remove(package_name, time_out):
    """Removes a package."""
    if pkg_version(package_name) is None:
        return
    result = _remove(package_name, time_out)

    if result != OK:
        if result == REINSTALL_FIRST:
            _install(package_name, time_out)
        elif result == RUN_DPKG_FIRST:
            _fix(time_out)
        result = _remove(package_name, time_out)
        if result != OK:
            raise PkgPackageStateError("Package %s is in a bad state."
                                       % package_name)
