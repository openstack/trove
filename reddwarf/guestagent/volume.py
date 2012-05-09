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

import logging
import os
import pexpect

from reddwarf.common import config
from reddwarf.common import utils
from reddwarf.common.exception import GuestError
from reddwarf.common.exception import ProcessExecutionError

TMP_MOUNT_POINT = "/mnt/volume"

LOG = logging.getLogger(__name__)
CONFIG = config.Config


class VolumeDevice(object):

    def __init__(self, device_path):
        self.device_path = device_path

    def migrate_data(self, mysql_base):
        """ Synchronize the data from the mysql directory to the new volume """
        # Use sudo to have access to this spot.
        utils.execute("sudo", "mkdir", "-p", TMP_MOUNT_POINT)
        self._tmp_mount(TMP_MOUNT_POINT)
        if not mysql_base[-1] == '/':
            mysql_base = "%s/" % mysql_base
        utils.execute("sudo", "rsync", "--safe-links", "--perms",
                      "--recursive", "--owner", "--group", "--xattrs",
                      "--sparse", mysql_base, TMP_MOUNT_POINT)
        self.unmount()

    def _check_device_exists(self):
        """Check that the device path exists.

        Verify that the device path has actually been created and can report
        it's size, only then can it be available for formatting, retry
        num_tries to account for the time lag.
        """
        try:
            num_tries = CONFIG.get('num_tries', 3)
            utils.execute('sudo', 'blockdev', '--getsize64', self.device_path,
                          attempts=num_tries)
        except ProcessExecutionError:
            raise GuestError("InvalidDevicePath(path=%s)" % self.device_path)

    def _check_format(self):
        """Checks that an unmounted volume is formatted."""
        child = pexpect.spawn("sudo dumpe2fs %s" % self.device_path)
        try:
            i = child.expect(['has_journal', 'Wrong magic number'])
            if i == 0:
                return
            volume_fstype = CONFIG.get('volume_fstype', 'ext3')
            raise IOError('Device path at %s did not seem to be %s.' %
                          (self.device_path, volume_fstype))
        except pexpect.EOF:
            raise IOError("Volume was not formatted.")
        child.expect(pexpect.EOF)

    def _format(self):
        """Calls mkfs to format the device at device_path."""
        volume_fstype = CONFIG.get('volume_fstype', 'ext3')
        format_options = CONFIG.get('format_options', '-m 5')
        cmd = "sudo mkfs -t %s %s %s" % (volume_fstype,
                                         format_options, self.device_path)
        volume_format_timeout = CONFIG.get('volume_format_timeout', 120)
        child = pexpect.spawn(cmd, timeout=volume_format_timeout)
        # child.expect("(y,n)")
        # child.sendline('y')
        child.expect(pexpect.EOF)

    def format(self):
        """Formats the device at device_path and checks the filesystem."""
        self._check_device_exists()
        self._format()
        self._check_format()

    def mount(self, mount_point):
        """Mounts, and writes to fstab."""
        mount_point = VolumeMountPoint(self.device_path, mount_point)
        mount_point.mount()
        mount_point.write_to_fstab()

    #TODO(tim.simpson): Are we using this?
    def resize_fs(self):
        """Resize the filesystem on the specified device"""
        self._check_device_exists()
        try:
            utils.execute("sudo", "resize2fs", self.device_path)
        except ProcessExecutionError as err:
            LOG.error(err)
            raise GuestError("Error resizing the filesystem: %s"
                                       % self.device_path)

    def _tmp_mount(self, mount_point):
        """Mounts, but doesn't save to fstab."""
        mount_point = VolumeMountPoint(self.device_path, mount_point)
        mount_point.mount()  # Don't save to fstab.

    def unmount(self):
        if os.path.exists(self.device_path):
            cmd = "sudo umount %s" % self.device_path
            child = pexpect.spawn(cmd)
            child.expect(pexpect.EOF)


class VolumeMountPoint(object):

    def __init__(self, device_path, mount_point):
        self.device_path = device_path
        self.mount_point = mount_point
        self.volume_fstype = CONFIG.get('volume_fstype', 'ext3')
        self.mount_options = CONFIG.get('mount_options', 'defaults,noatime')

    def mount(self):
        if not os.path.exists(self.mount_point):
            os.makedirs(self.mount_point)
        LOG.debug("Adding volume. Device path:%s, mount_point:%s, "
                  "volume_type:%s, mount options:%s" %
                  (self.device_path, self.mount_point, self.volume_fstype,
                   self.mount_options))
        cmd = "sudo mount -t %s -o %s %s %s" % (self.volume_fstype,
            self.mount_options, self.device_path, self.mount_point)
        child = pexpect.spawn(cmd)
        child.expect(pexpect.EOF)

    def write_to_fstab(self):
        fstab_line = "%s\t%s\t%s\t%s\t0\t0" % (self.device_path,
            self.mount_point, self.volume_fstype, self.mount_options)
        LOG.debug("Writing new line to fstab:%s" % fstab_line)
        utils.execute("sudo", "cp", "/etc/fstab", "/etc/fstab.orig")
        utils.execute("sudo", "cp", "/etc/fstab", "/tmp/newfstab")
        utils.execute("sudo", "chmod", "666", "/tmp/newfstab")
        with open("/tmp/newfstab", 'a') as new_fstab:
            new_fstab.write("\n" + fstab_line)
        utils.execute("sudo", "chmod", "640", "/tmp/newfstab")
        utils.execute("sudo", "mv", "/tmp/newfstab", "/etc/fstab")
