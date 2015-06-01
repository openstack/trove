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
from tempfile import NamedTemporaryFile

import pexpect

from trove.common import cfg
from trove.common.exception import GuestError
from trove.common.exception import ProcessExecutionError
from trove.common.i18n import _
from trove.common import utils
from trove.guestagent.common import operating_system
from trove.openstack.common import log as logging

TMP_MOUNT_POINT = "/mnt/volume"

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class VolumeDevice(object):

    def __init__(self, device_path):
        self.device_path = device_path

    def migrate_data(self, source_dir):
        """Synchronize the data from the source directory to the new
        volume.
        """
        self.mount(TMP_MOUNT_POINT, write_to_fstab=False)
        if not source_dir[-1] == '/':
            source_dir = "%s/" % source_dir
        utils.execute("sudo", "rsync", "--safe-links", "--perms",
                      "--recursive", "--owner", "--group", "--xattrs",
                      "--sparse", source_dir, TMP_MOUNT_POINT)
        self.unmount(TMP_MOUNT_POINT)

    def _check_device_exists(self):
        """Check that the device path exists.

        Verify that the device path has actually been created and can report
        it's size, only then can it be available for formatting, retry
        num_tries to account for the time lag.
        """
        try:
            num_tries = CONF.num_tries
            LOG.debug("Checking if %s exists." % self.device_path)

            utils.execute('sudo', 'blockdev', '--getsize64', self.device_path,
                          attempts=num_tries)
        except ProcessExecutionError:
            LOG.exception(_("Error getting device status"))
            raise GuestError(_("InvalidDevicePath(path=%s)") %
                             self.device_path)

    def _check_format(self):
        """Checks that an unmounted volume is formatted."""
        cmd = "sudo dumpe2fs %s" % self.device_path
        LOG.debug("Checking whether %s is formated: %s." %
                  (self.device_path, cmd))

        child = pexpect.spawn(cmd)
        try:
            i = child.expect(['has_journal', 'Wrong magic number'])
            if i == 0:
                return
            volume_fstype = CONF.volume_fstype
            raise IOError(
                _('Device path at {0} did not seem to be {1}.').format(
                    self.device_path, volume_fstype))

        except pexpect.EOF:
            raise IOError(_("Volume was not formatted."))
        child.expect(pexpect.EOF)

    def _format(self):
        """Calls mkfs to format the device at device_path."""
        volume_fstype = CONF.volume_fstype
        format_options = CONF.format_options
        cmd = "sudo mkfs -t %s %s %s" % (volume_fstype,
                                         format_options, self.device_path)
        volume_format_timeout = CONF.volume_format_timeout
        LOG.debug("Formatting %s. Executing: %s." %
                  (self.device_path, cmd))
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
        LOG.debug("Will mount %s at %s." % (self.device_path, mount_point))

        mount_point = VolumeMountPoint(self.device_path, mount_point)
        mount_point.mount()
        if write_to_fstab:
            mount_point.write_to_fstab()

    def resize_fs(self, mount_point):
        """Resize the filesystem on the specified device."""
        self._check_device_exists()
        try:
            # check if the device is mounted at mount_point before e2fsck
            if not os.path.ismount(mount_point):
                utils.execute("e2fsck", "-f", "-p", self.device_path,
                              run_as_root=True, root_helper="sudo")
            utils.execute("resize2fs", self.device_path,
                          run_as_root=True, root_helper="sudo")
        except ProcessExecutionError:
            LOG.exception(_("Error resizing file system."))
            raise GuestError(_("Error resizing the filesystem: %s") %
                             self.device_path)

    def unmount(self, mount_point):
        if os.path.exists(mount_point):
            cmd = "sudo umount %s" % mount_point
            child = pexpect.spawn(cmd)
            child.expect(pexpect.EOF)

    def unmount_device(self, device_path):
        # unmount if device is already mounted
        mount_points = self.mount_points(device_path)
        for mnt in mount_points:
            LOG.info(_("Device %(device)s is already mounted in "
                       "%(mount_point)s. Unmounting now.") %
                     {'device': device_path, 'mount_point': mnt})
            self.unmount(mnt)

    def mount_points(self, device_path):
        """Returns a list of mount points on the specified device."""
        try:
            cmd = "grep %s /etc/mtab | awk '{print $2}'" % device_path
            stdout, stderr = utils.execute(cmd, shell=True)
            return stdout.strip().split('\n')

        except ProcessExecutionError:
            LOG.exception(_("Error retrieving mount points"))
            raise GuestError(_("Could not obtain a list of mount points for "
                               "device: %s") % device_path)

    def set_readahead_size(self, readahead_size,
                           execute_function=utils.execute):
        """Set the readahead size of disk."""
        self._check_device_exists()
        try:
            execute_function("sudo", "blockdev", "--setra",
                             readahead_size, self.device_path)
        except ProcessExecutionError:
            LOG.exception(_("Error setting readhead size to %(size)s "
                            "for device %(device)s.") %
                          {'size': readahead_size, 'device': self.device_path})
            raise GuestError(_("Error setting readhead size: %s.") %
                             self.device_path)


class VolumeMountPoint(object):

    def __init__(self, device_path, mount_point):
        self.device_path = device_path
        self.mount_point = mount_point
        self.volume_fstype = CONF.volume_fstype
        self.mount_options = CONF.mount_options

    def mount(self):
        if not os.path.exists(self.mount_point):
            operating_system.create_directory(self.mount_point, as_root=True)
        LOG.debug("Mounting volume. Device path:{0}, mount_point:{1}, "
                  "volume_type:{2}, mount options:{3}".format(
                      self.device_path, self.mount_point, self.volume_fstype,
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
        with open('/etc/fstab', "r") as fstab:
            fstab_content = fstab.read()
        with NamedTemporaryFile(delete=False) as tempfstab:
            tempfstab.write(fstab_content + fstab_line)
        utils.execute("sudo", "install", "-o", "root", "-g", "root", "-m",
                      "644", tempfstab.name, "/etc/fstab")
        os.remove(tempfstab.name)
