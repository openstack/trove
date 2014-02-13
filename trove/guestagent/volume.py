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

from trove.openstack.common import log as logging
import os
import pexpect

from trove.common import cfg
from trove.common import utils
from trove.common.exception import GuestError
from trove.common.exception import ProcessExecutionError

TMP_MOUNT_POINT = "/mnt/volume"

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class VolumeDevice(object):

    def __init__(self, device_path):
        self.device_path = device_path

    def migrate_data(self, mysql_base):
        """Synchronize the data from the mysql directory to the new volume """
        self.mount(TMP_MOUNT_POINT, write_to_fstab=False)
        if not mysql_base[-1] == '/':
            mysql_base = "%s/" % mysql_base
        utils.execute("sudo", "rsync", "--safe-links", "--perms",
                      "--recursive", "--owner", "--group", "--xattrs",
                      "--sparse", mysql_base, TMP_MOUNT_POINT)
        self.unmount(TMP_MOUNT_POINT)

    def _check_device_exists(self):
        """Check that the device path exists.

        Verify that the device path has actually been created and can report
        it's size, only then can it be available for formatting, retry
        num_tries to account for the time lag.
        """
        try:
            num_tries = CONF.num_tries
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
            volume_fstype = CONF.volume_fstype
            raise IOError('Device path at %s did not seem to be %s.' %
                          (self.device_path, volume_fstype))
        except pexpect.EOF:
            raise IOError("Volume was not formatted.")
        child.expect(pexpect.EOF)

    def _format(self):
        """Calls mkfs to format the device at device_path."""
        volume_fstype = CONF.volume_fstype
        format_options = CONF.format_options
        cmd = "sudo mkfs -t %s %s %s" % (volume_fstype,
                                         format_options, self.device_path)
        volume_format_timeout = CONF.volume_format_timeout
        child = pexpect.spawn(cmd, timeout=volume_format_timeout)
        # child.expect("(y,n)")
        # child.sendline('y')
        child.expect(pexpect.EOF)

    def format(self):
        """Formats the device at device_path and checks the filesystem."""
        self._check_device_exists()
        self._format()
        self._check_format()

    def mount(self, mount_point, write_to_fstab=True):
        """Mounts, and writes to fstab."""
        mount_point = VolumeMountPoint(self.device_path, mount_point)
        mount_point.mount()
        if write_to_fstab:
            mount_point.write_to_fstab()

    def resize_fs(self, mount_point):
        """Resize the filesystem on the specified device"""
        self._check_device_exists()
        try:
            # check if the device is mounted at mount_point before e2fsck
            if not os.path.ismount(mount_point):
                utils.execute("sudo", "e2fsck", "-f", "-n", self.device_path)
            utils.execute("sudo", "resize2fs", self.device_path)
        except ProcessExecutionError as err:
            LOG.error(err)
            raise GuestError("Error resizing the filesystem: %s" %
                             self.device_path)

    def unmount(self, mount_point):
        if os.path.exists(mount_point):
            cmd = "sudo umount %s" % mount_point
            child = pexpect.spawn(cmd)
            child.expect(pexpect.EOF)


class VolumeMountPoint(object):

    def __init__(self, device_path, mount_point):
        self.device_path = device_path
        self.mount_point = mount_point
        self.volume_fstype = CONF.volume_fstype
        self.mount_options = CONF.mount_options

    def mount(self):
        if not os.path.exists(self.mount_point):
            utils.execute("sudo", "mkdir", "-p", self.mount_point)
        LOG.debug("Mounting volume. Device path:%s, mount_point:%s, "
                  "volume_type:%s, mount options:%s" %
                  (self.device_path, self.mount_point, self.volume_fstype,
                   self.mount_options))
        cmd = ("sudo mount -t %s -o %s %s %s" %
               (self.volume_fstype, self.mount_options, self.device_path,
                self.mount_point))
        child = pexpect.spawn(cmd)
        child.expect(pexpect.EOF)

    def write_to_fstab(self):
        fstab_line = ("%s\t%s\t%s\t%s\t0\t0" %
                      (self.device_path, self.mount_point, self.volume_fstype,
                       self.mount_options))
        LOG.debug("Writing new line to fstab:%s" % fstab_line)
        utils.execute("sudo", "cp", "/etc/fstab", "/etc/fstab.orig")
        utils.execute("sudo", "cp", "/etc/fstab", "/tmp/newfstab")
        utils.execute("sudo", "chmod", "666", "/tmp/newfstab")
        with open("/tmp/newfstab", 'a') as new_fstab:
            new_fstab.write("\n" + fstab_line)
        utils.execute("sudo", "chmod", "640", "/tmp/newfstab")
        utils.execute("sudo", "mv", "/tmp/newfstab", "/etc/fstab")
