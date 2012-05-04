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


class VolumeHelper(object):

    @staticmethod
    def _has_volume_device(device_path):
        return not device_path is None

    @staticmethod
    def migrate_data(device_path, mysql_base):
        """ Synchronize the data from the mysql directory to the new volume """
        utils.execute("sudo", "mkdir", "-p", TMP_MOUNT_POINT)
        VolumeHelper.mount(device_path, TMP_MOUNT_POINT)
        if not mysql_base[-1] == '/':
            mysql_base = "%s/" % mysql_base
        utils.execute("sudo", "rsync", "--safe-links", "--perms",
                      "--recursive", "--owner", "--group", "--xattrs",
                      "--sparse", mysql_base, TMP_MOUNT_POINT)
        VolumeHelper.unmount(device_path)

    @staticmethod
    def _check_device_exists(device_path):
        """Check that the device path exists.

        Verify that the device path has actually been created and can report
        it's size, only then can it be available for formatting, retry
        num_tries to account for the time lag.
        """
        try:
            num_tries = CONFIG.get('num_tries', 3)
            utils.execute('sudo', 'blockdev', '--getsize64', device_path,
                          attempts=num_tries)
        except ProcessExecutionError:
            raise GuestError("InvalidDevicePath(path=%s)" % device_path)

    @staticmethod
    def _check_format(device_path):
        """Checks that an unmounted volume is formatted."""
        child = pexpect.spawn("sudo dumpe2fs %s" % device_path)
        try:
            i = child.expect(['has_journal', 'Wrong magic number'])
            if i == 0:
                return
            volume_fstype = CONFIG.get('volume_fstype', 'ext3')
            raise IOError('Device path at %s did not seem to be %s.' %
                          (device_path, volume_fstype))
        except pexpect.EOF:
            raise IOError("Volume was not formatted.")
        child.expect(pexpect.EOF)

    @staticmethod
    def _format(device_path):
        """Calls mkfs to format the device at device_path."""
        volume_fstype = CONFIG.get('volume_fstype', 'ext3')
        format_options = CONFIG.get('format_options', '-m 5')
        cmd = "sudo mkfs -t %s %s %s" % (volume_fstype,
                                         format_options, device_path)
        volume_format_timeout = CONFIG.get('volume_format_timeout', 120)
        child = pexpect.spawn(cmd, timeout=volume_format_timeout)
        # child.expect("(y,n)")
        # child.sendline('y')
        child.expect(pexpect.EOF)

    @staticmethod
    def format(device_path):
        """Formats the device at device_path and checks the filesystem."""
        VolumeHelper._check_device_exists(device_path)
        VolumeHelper._format(device_path)
        VolumeHelper._check_format(device_path)

    @staticmethod
    def mount(device_path, mount_point):
        if not os.path.exists(mount_point):
            os.makedirs(mount_point)
        volume_fstype = CONFIG.get('volume_fstype', 'ext3')
        mount_options = CONFIG.get('mount_options', 'noatime')
        cmd = "sudo mount -t %s -o %s %s %s" % (volume_fstype,
                                                mount_options,
                                                device_path, mount_point)
        child = pexpect.spawn(cmd)
        child.expect(pexpect.EOF)

    @staticmethod
    def unmount(mount_point):
        if os.path.exists(mount_point):
            cmd = "sudo umount %s" % mount_point
            child = pexpect.spawn(cmd)
            child.expect(pexpect.EOF)

    @staticmethod
    def resize_fs(device_path):
        """Resize the filesystem on the specified device"""
        VolumeHelper._check_device_exists(device_path)
        try:
            utils.execute("sudo", "resize2fs", device_path)
        except ProcessExecutionError as err:
            LOG.error(err)
            raise GuestError("Error resizing the filesystem: %s"
                                       % device_path)
