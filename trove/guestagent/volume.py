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
import shlex
from tempfile import NamedTemporaryFile
import traceback

from oslo_log import log as logging

from trove.common import cfg
from trove.common import exception
from trove.common.i18n import _
from trove.common import utils
from trove.guestagent.common import operating_system

TMP_MOUNT_POINT = "/mnt/volume"

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


def log_and_raise(message):
    LOG.exception(message)
    raise_msg = message + _("\nExc: %s") % traceback.format_exc()
    raise exception.GuestError(original_message=raise_msg)


class VolumeDevice(object):

    def __init__(self, device_path):
        self.device_path = device_path

    def migrate_data(self, source_dir, target_subdir=None):
        """Synchronize the data from the source directory to the new
        volume; optionally to a new sub-directory on the new volume.
        """
        self.mount(TMP_MOUNT_POINT, write_to_fstab=False)
        if not source_dir[-1] == '/':
            source_dir = "%s/" % source_dir
        target_dir = TMP_MOUNT_POINT
        if target_subdir:
            target_dir = target_dir + "/" + target_subdir
        try:
            utils.execute("rsync", "--safe-links", "--perms",
                          "--recursive", "--owner", "--group", "--xattrs",
                          "--sparse", source_dir, target_dir,
                          run_as_root=True, root_helper="sudo")
        except exception.ProcessExecutionError:
            msg = _("Could not migrate data.")
            log_and_raise(msg)
        self.unmount(TMP_MOUNT_POINT)

    def _check_device_exists(self):
        """Check that the device path exists.

        Verify that the device path has actually been created and can report
        its size, only then can it be available for formatting, retry
        num_tries to account for the time lag.
        """
        try:
            num_tries = CONF.num_tries
            LOG.debug("Checking if %s exists.", self.device_path)

            utils.execute("blockdev", "--getsize64", self.device_path,
                          run_as_root=True, root_helper="sudo",
                          attempts=num_tries)
        except exception.ProcessExecutionError:
            msg = _("Device '%s' is not ready.") % self.device_path
            log_and_raise(msg)

    def _check_format(self):
        """Checks that a volume is formatted."""
        LOG.debug("Checking whether '%s' is formatted.", self.device_path)
        try:
            stdout, stderr = utils.execute(
                "dumpe2fs", self.device_path,
                run_as_root=True, root_helper="sudo")
            if 'has_journal' not in stdout:
                msg = _("Volume '%s' does not appear to be formatted.") % (
                    self.device_path)
                raise exception.GuestError(original_message=msg)
        except exception.ProcessExecutionError as pe:
            if 'Wrong magic number' in pe.stderr:
                volume_fstype = CONF.volume_fstype
                msg = _("'Device '%(dev)s' did not seem to be '%(type)s'.") % (
                    {'dev': self.device_path, 'type': volume_fstype})
                log_and_raise(msg)
            msg = _("Volume '%s' was not formatted.") % self.device_path
            log_and_raise(msg)

    def _format(self):
        """Calls mkfs to format the device at device_path."""
        volume_fstype = CONF.volume_fstype
        format_options = shlex.split(CONF.format_options)
        format_options.append(self.device_path)
        volume_format_timeout = CONF.volume_format_timeout
        LOG.debug("Formatting '%s'.", self.device_path)
        try:
            utils.execute_with_timeout(
                "mkfs", "--type", volume_fstype, *format_options,
                run_as_root=True, root_helper="sudo",
                timeout=volume_format_timeout)
        except exception.ProcessExecutionError:
            msg = _("Could not format '%s'.") % self.device_path
            log_and_raise(msg)

    def format(self):
        """Formats the device at device_path and checks the filesystem."""
        self._check_device_exists()
        self._format()
        self._check_format()

    def mount(self, mount_point, write_to_fstab=True):
        """Mounts, and writes to fstab."""
        LOG.debug("Will mount %(path)s at %(mount_point)s.",
                  {'path': self.device_path, 'mount_point': mount_point})

        mount_point = VolumeMountPoint(self.device_path, mount_point)
        mount_point.mount()
        if write_to_fstab:
            mount_point.write_to_fstab()

    def _wait_for_mount(self, mount_point, timeout=2):
        """Wait for a fs to be mounted."""
        def wait_for_mount():
            return operating_system.is_mount(mount_point)

        try:
            utils.poll_until(wait_for_mount, sleep_time=1, time_out=timeout)
        except exception.PollTimeOut:
            return False

        return True

    def resize_fs(self, mount_point):
        """Resize the filesystem on the specified device."""
        self._check_device_exists()
        # Some OS's will mount a file systems after it's attached if
        # an entry is put in the fstab file (like Trove does).
        # Thus it may be necessary to wait for the mount and then unmount
        # the fs again (since the volume was just attached).
        if self._wait_for_mount(mount_point, timeout=2):
            LOG.debug("Unmounting '%s' before resizing.", mount_point)
            self.unmount(mount_point)
        try:
            utils.execute("e2fsck", "-f", "-p", self.device_path,
                          run_as_root=True, root_helper="sudo")
            utils.execute("resize2fs", self.device_path,
                          run_as_root=True, root_helper="sudo")
        except exception.ProcessExecutionError:
            msg = _("Error resizing the filesystem with device '%s'.") % (
                self.device_path)
            log_and_raise(msg)

    def unmount(self, mount_point):
        if operating_system.is_mount(mount_point):
            try:
                utils.execute("umount", mount_point,
                              run_as_root=True, root_helper='sudo')
            except exception.ProcessExecutionError:
                msg = _("Error unmounting '%s'.") % mount_point
                log_and_raise(msg)
        else:
            LOG.debug("'%s' is not a mounted fs, cannot unmount", mount_point)

    def unmount_device(self, device_path):
        # unmount if device is already mounted
        mount_points = self.mount_points(device_path)
        for mnt in mount_points:
            LOG.info(_("Device '%(device)s' is mounted on "
                       "'%(mount_point)s'. Unmounting now."),
                     {'device': device_path, 'mount_point': mnt})
            self.unmount(mnt)

    def mount_points(self, device_path):
        """Returns a list of mount points on the specified device."""
        stdout, stderr = utils.execute(
            "grep '^%s ' /etc/mtab" % device_path,
            shell=True, check_exit_code=[0, 1])
        return [entry.strip().split()[1] for entry in stdout.splitlines()]

    def set_readahead_size(self, readahead_size):
        """Set the readahead size of disk."""
        self._check_device_exists()
        try:
            utils.execute("blockdev", "--setra",
                          readahead_size, self.device_path,
                          run_as_root=True, root_helper="sudo")
        except exception.ProcessExecutionError:
            msg = _("Error setting readahead size to %(size)s "
                    "for device %(device)s.") % {
                'size': readahead_size, 'device': self.device_path}
            log_and_raise(msg)


class VolumeMountPoint(object):

    def __init__(self, device_path, mount_point):
        self.device_path = device_path
        self.mount_point = mount_point
        self.volume_fstype = CONF.volume_fstype
        self.mount_options = CONF.mount_options

    def mount(self):
        if not operating_system.exists(self.mount_point, is_directory=True,
                                       as_root=True):
            operating_system.create_directory(self.mount_point, as_root=True)
        LOG.debug("Mounting volume. Device path:{0}, mount_point:{1}, "
                  "volume_type:{2}, mount options:{3}".format(
                      self.device_path, self.mount_point, self.volume_fstype,
                      self.mount_options))
        try:
            utils.execute("mount", "-t", self.volume_fstype,
                          "-o", self.mount_options,
                          self.device_path, self.mount_point,
                          run_as_root=True, root_helper="sudo")
        except exception.ProcessExecutionError:
            msg = _("Could not mount '%s'.") % self.mount_point
            log_and_raise(msg)

    def write_to_fstab(self):
        fstab_line = ("%s\t%s\t%s\t%s\t0\t0" %
                      (self.device_path, self.mount_point, self.volume_fstype,
                       self.mount_options))
        LOG.debug("Writing new line to fstab:%s", fstab_line)
        with open('/etc/fstab', "r") as fstab:
            fstab_content = fstab.read()
        with NamedTemporaryFile(mode='w', delete=False) as tempfstab:
            tempfstab.write(fstab_content + fstab_line)
        try:
            utils.execute("install", "-o", "root", "-g", "root",
                          "-m", "644", tempfstab.name, "/etc/fstab",
                          run_as_root=True, root_helper="sudo")
        except exception.ProcessExecutionError:
            msg = _("Could not add '%s' to fstab.") % self.mount_point
            log_and_raise(msg)
        os.remove(tempfstab.name)
