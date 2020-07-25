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

import abc
import os
import shlex
import six
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


# We removed all translation for messages destinated to log file.
# However we cannot use _(xxx) instead of _("xxxx") because of the
# H701 pep8 checking, so we have to pass different message format
# string and format content here.
def log_and_raise(log_fmt, exc_fmt, fmt_content=None):
    if fmt_content is not None:
        LOG.exception(log_fmt, fmt_content)
        raise_msg = exc_fmt % fmt_content
    else:
        # if fmt_content is not provided, log_fmt and
        # exc_fmt are just plain string messages
        LOG.exception(log_fmt)
        raise_msg = exc_fmt
    raise_msg += _("\nExc: %s") % traceback.format_exc()
    raise exception.GuestError(original_message=raise_msg)


@six.add_metaclass(abc.ABCMeta)
class FSBase(object):

    def __init__(self, fstype, format_options):
        self.fstype = fstype
        self.format_options = format_options

    @abc.abstractmethod
    def format(self, device_path, timeout):
        """
        Format device
        """

    @abc.abstractmethod
    def check_format(self, device_path):
        """
        Check if device is formatted
        """

    @abc.abstractmethod
    def resize(self, device_path, online=False):
        """
        Resize the filesystem on device
        """


class FSExt(FSBase):

    def __init__(self, fstype, format_options):
        super(FSExt, self).__init__(fstype, format_options)

    def format(self, device_path, timeout):
        format_options = shlex.split(self.format_options)
        format_options.append(device_path)
        try:
            utils.execute_with_timeout(
                "mkfs", "--type", self.fstype, *format_options,
                timeout=timeout, run_as_root=True, root_helper="sudo")
        except exception.ProcessExecutionError:
            log_fmt = "Could not format '%s'."
            exc_fmt = _("Could not format '%s'.")
            log_and_raise(log_fmt, exc_fmt, device_path)

    def check_format(self, device_path):
        try:
            stdout, stderr = utils.execute(
                "dumpe2fs", device_path, run_as_root=True, root_helper="sudo")
            if 'has_journal' not in stdout:
                msg = _("Volume '%s' does not appear to be formatted.") % (
                    device_path)
                raise exception.GuestError(original_message=msg)
        except exception.ProcessExecutionError as pe:
            if 'Wrong magic number' in pe.stderr:
                volume_fstype = self.fstype
                log_fmt = "'Device '%(dev)s' did not seem to be '%(type)s'."
                exc_fmt = _("'Device '%(dev)s' did not seem to be '%(type)s'.")
                log_and_raise(log_fmt, exc_fmt, {'dev': device_path,
                                                 'type': volume_fstype})
            log_fmt = "Volume '%s' was not formatted."
            exc_fmt = _("Volume '%s' was not formatted.")
            log_and_raise(log_fmt, exc_fmt, device_path)

    def resize(self, device_path, online=False):
        if not online:
            utils.execute("e2fsck", "-f", "-p", device_path,
                          run_as_root=True, root_helper="sudo")
        utils.execute("resize2fs", device_path,
                      run_as_root=True, root_helper="sudo")


class FSExt3(FSExt):

    def __init__(self, format_options):
        super(FSExt3, self).__init__('ext3', format_options)


class FSExt4(FSExt):

    def __init__(self, format_options):
        super(FSExt4, self).__init__('ext4', format_options)


class FSXFS(FSBase):

    def __init__(self, format_options):
        super(FSXFS, self).__init__('xfs', format_options)

    def format(self, device_path, timeout):
        format_options = shlex.split(self.format_options)
        format_options.append(device_path)
        try:
            utils.execute_with_timeout(
                "mkfs.xfs", *format_options,
                timeout=timeout, run_as_root=True, root_helper="sudo")
        except exception.ProcessExecutionError:
            log_fmt = "Could not format '%s'."
            exc_fmt = _("Could not format '%s'.")
            log_and_raise(log_fmt, exc_fmt, device_path)

    def check_format(self, device_path):
        stdout, stderr = utils.execute(
            "xfs_admin", "-l", device_path,
            run_as_root=True, root_helper="sudo")
        if 'not a valid XFS filesystem' in stdout:
            msg = _("Volume '%s' does not appear to be formatted.") % (
                device_path)
            raise exception.GuestError(original_message=msg)

    def resize(self, device_path, online=False):
        utils.execute("xfs_repair", device_path,
                      run_as_root=True, root_helper="sudo")
        utils.execute("mount", device_path,
                      run_as_root=True, root_helper="sudo")
        utils.execute("xfs_growfs", device_path,
                      run_as_root=True, root_helper="sudo")
        utils.execute("umount", device_path,
                      run_as_root=True, root_helper="sudo")


def VolumeFs(fstype, format_options=''):
    supported_fs = {
        'xfs': FSXFS,
        'ext3': FSExt3,
        'ext4': FSExt4
    }
    return supported_fs[fstype](format_options)


class VolumeDevice(object):

    def __init__(self, device_path):
        self.device_path = device_path
        self.volume_fs = VolumeFs(CONF.volume_fstype,
                                  CONF.format_options)

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
            log_msg = "Could not migrate data."
            exc_msg = _("Could not migrate date.")
            log_and_raise(log_msg, exc_msg)
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
            log_fmt = "Device '%s' is not ready."
            exc_fmt = _("Device '%s' is not ready.")
            log_and_raise(log_fmt, exc_fmt, self.device_path)

    def _check_format(self):
        """Checks that a volume is formatted."""
        LOG.debug("Checking whether '%s' is formatted.", self.device_path)
        self.volume_fs.check_format(self.device_path)

    def _format(self):
        """Calls mkfs to format the device at device_path."""
        LOG.debug("Formatting '%s'.", self.device_path)
        self.volume_fs.format(self.device_path, CONF.volume_format_timeout)

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

    def resize_fs(self, mount_point, online=False):
        """Resize the filesystem on the specified device."""
        self._check_device_exists()
        # Some OS's will mount a file systems after it's attached if
        # an entry is put in the fstab file (like Trove does).
        # Thus it may be necessary to wait for the mount and then unmount
        # the fs again (since the volume was just attached).
        if not online and self._wait_for_mount(mount_point, timeout=2):
            LOG.debug("Unmounting '%s' before resizing.", mount_point)
            self.unmount(mount_point)
        try:
            self.volume_fs.resize(self.device_path, online=online)
        except exception.ProcessExecutionError:
            log_fmt = "Error resizing the filesystem with device '%s'."
            exc_fmt = _("Error resizing the filesystem with device '%s'.")
            log_and_raise(log_fmt, exc_fmt, self.device_path)

    def unmount(self, mount_point):
        if operating_system.is_mount(mount_point):
            try:
                utils.execute("umount", mount_point,
                              run_as_root=True, root_helper='sudo')
            except exception.ProcessExecutionError:
                log_fmt = "Error unmounting '%s'."
                exc_fmt = _("Error unmounting '%s'.")
                log_and_raise(log_fmt, exc_fmt, mount_point)
        else:
            LOG.debug("'%s' is not a mounted fs, cannot unmount", mount_point)

    def unmount_device(self, device_path):
        # unmount if device is already mounted
        mount_points = self.mount_points(device_path)
        for mnt in mount_points:
            LOG.info("Device '%(device)s' is mounted on "
                     "'%(mount_point)s'. Unmounting now.",
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
            log_fmt = ("Error setting readahead size to %(size)s "
                       "for device %(device)s.")
            exc_fmt = _("Error setting readahead size to %(size)s "
                        "for device %(device)s.")
            log_and_raise(log_fmt, exc_fmt, {'size': readahead_size,
                                             'device': self.device_path})


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
            log_fmt = "Could not mount '%s'."
            exc_fmt = _("Could not mount '%s'.")
            log_and_raise(log_fmt, exc_fmt, self.mount_point)

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
            log_fmt = "Could not add '%s' to fstab."
            exc_fmt = _("Could not add '%s' to fstab.")
            log_and_raise(log_fmt, exc_fmt, self.mount_point)
        os.remove(tempfstab.name)
