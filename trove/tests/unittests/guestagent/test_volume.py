#    Copyright 2012 OpenStack Foundation
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

from mock import ANY, call, DEFAULT, patch, mock_open

from trove.common import cfg
from trove.common import exception
from trove.common import utils
from trove.guestagent.common import operating_system
from trove.guestagent import volume
from trove.tests.unittests import trove_testtools


CONF = cfg.CONF


class VolumeDeviceTest(trove_testtools.TestCase):

    def setUp(self):
        super(VolumeDeviceTest, self).setUp()
        self.patch_conf_property('volume_fstype', 'ext3')
        self.patch_conf_property('format_options', '-m 5')
        self.volumeDevice = volume.VolumeDevice('/dev/vdb')

        self.exec_patcher = patch.object(
            utils, 'execute', return_value=('has_journal', ''))
        self.mock_exec = self.exec_patcher.start()
        self.addCleanup(self.exec_patcher.stop)
        self.ismount_patcher = patch.object(operating_system, 'is_mount')
        self.mock_ismount = self.ismount_patcher.start()
        self.addCleanup(self.ismount_patcher.stop)

    def tearDown(self):
        super(VolumeDeviceTest, self).tearDown()

    def test_migrate_data(self):
        with patch.multiple(self.volumeDevice,
                            mount=DEFAULT, unmount=DEFAULT) as mocks:
            self.volumeDevice.migrate_data('/')
            self.assertEqual(1, mocks['mount'].call_count)
            self.assertEqual(1, mocks['unmount'].call_count)
            self.assertEqual(1, self.mock_exec.call_count)
            calls = [
                call('rsync', '--safe-links', '--perms', '--recursive',
                     '--owner', '--group', '--xattrs',
                     '--sparse', '/', '/mnt/volume',
                     root_helper='sudo', run_as_root=True),
            ]
            self.mock_exec.assert_has_calls(calls)

    def test__check_device_exists(self):
        self.volumeDevice._check_device_exists()
        self.assertEqual(1, self.mock_exec.call_count)
        calls = [
            call('blockdev', '--getsize64', '/dev/vdb', attempts=3,
                 root_helper='sudo', run_as_root=True)
        ]
        self.mock_exec.assert_has_calls(calls)

    @patch('trove.guestagent.volume.LOG')
    def test_fail__check_device_exists(self, mock_logging):
        with patch.object(utils, 'execute',
                          side_effect=exception.ProcessExecutionError):
            self.assertRaises(exception.GuestError,
                              self.volumeDevice._check_device_exists)

    def test__check_format(self):
        self.volumeDevice._check_format()
        self.assertEqual(1, self.mock_exec.call_count)
        calls = [
            call('dumpe2fs', '/dev/vdb', root_helper='sudo', run_as_root=True)
        ]
        self.mock_exec.assert_has_calls(calls)

    @patch('trove.guestagent.volume.LOG')
    def test__check_format_2(self, mock_logging):
        self.assertEqual(0, self.mock_exec.call_count)
        proc_err = exception.ProcessExecutionError()
        proc_err.stderr = 'Wrong magic number'
        self.mock_exec.side_effect = proc_err
        self.assertRaises(exception.GuestError,
                          self.volumeDevice._check_format)

    def test__format(self):
        self.volumeDevice._format()
        self.assertEqual(1, self.mock_exec.call_count)
        calls = [
            call('mkfs', '--type', 'ext3', '-m', '5', '/dev/vdb',
                 root_helper='sudo', run_as_root=True)
        ]
        self.mock_exec.assert_has_calls(calls)

    def test_format(self):
        self.volumeDevice.format()
        self.assertEqual(3, self.mock_exec.call_count)
        calls = [
            call('blockdev', '--getsize64', '/dev/vdb', attempts=3,
                 root_helper='sudo', run_as_root=True),
            call('mkfs', '--type', 'ext3', '-m', '5', '/dev/vdb',
                 root_helper='sudo', run_as_root=True),
            call('dumpe2fs', '/dev/vdb', root_helper='sudo', run_as_root=True)
        ]
        self.mock_exec.assert_has_calls(calls)

    def test_mount(self):
        with patch.multiple(volume.VolumeMountPoint,
                            mount=DEFAULT, write_to_fstab=DEFAULT) as mocks:
            self.volumeDevice.mount('/dev/vba')
            self.assertEqual(1, mocks['mount'].call_count,
                             "Wrong number of calls to mount()")
            self.assertEqual(1, mocks['write_to_fstab'].call_count,
                             "Wrong number of calls to write_to_fstab()")
            self.mock_exec.assert_not_called()

    def test_resize_fs(self):
        with patch.object(operating_system, 'is_mount', return_value=True):
            mount_point = '/mnt/volume'
            self.volumeDevice.resize_fs(mount_point)
            self.assertEqual(4, self.mock_exec.call_count)
            calls = [
                call('blockdev', '--getsize64', '/dev/vdb', attempts=3,
                     root_helper='sudo', run_as_root=True),
                call("umount", mount_point, run_as_root=True,
                     root_helper='sudo'),
                call('e2fsck', '-f', '-p', '/dev/vdb', root_helper='sudo',
                     run_as_root=True),
                call('resize2fs', '/dev/vdb', root_helper='sudo',
                     run_as_root=True)
            ]
            self.mock_exec.assert_has_calls(calls)

    @patch.object(utils, 'execute',
                  side_effect=exception.ProcessExecutionError)
    @patch('trove.guestagent.volume.LOG')
    def test_fail_resize_fs(self, mock_logging, mock_execute):
        with patch.object(self.volumeDevice, '_check_device_exists'):
            self.assertRaises(exception.GuestError,
                              self.volumeDevice.resize_fs, '/mnt/volume')
            self.assertEqual(1,
                             self.volumeDevice._check_device_exists.call_count)
            self.assertEqual(2, self.mock_ismount.call_count)

    def test_unmount_positive(self):
        self._test_unmount()

    def test_unmount_negative(self):
        self._test_unmount(has_mount=False)

    def _test_unmount(self, has_mount=True):
        with patch.object(operating_system, 'is_mount',
                          return_value=has_mount):
            self.volumeDevice.unmount('/mnt/volume')
            if has_mount:
                self.assertEqual(1, self.mock_exec.call_count)
            else:
                self.mock_exec.assert_not_called()

    def test_mount_points(self):
        self.mock_exec.return_value = (
            ("/dev/vdb /var/lib/mysql xfs rw 0 0", ""))
        mount_point = self.volumeDevice.mount_points('/dev/vdb')
        self.assertEqual(['/var/lib/mysql'], mount_point)
        self.assertEqual(1, self.mock_exec.call_count)
        calls = [
            call("grep '^/dev/vdb ' /etc/mtab", check_exit_code=[0, 1],
                 shell=True)
        ]
        self.mock_exec.assert_has_calls(calls)

    def test_set_readahead_size(self):
        readahead_size = 2048
        self.volumeDevice.set_readahead_size(readahead_size)
        self.assertEqual(2, self.mock_exec.call_count)
        calls = [
            call('blockdev', '--getsize64', '/dev/vdb', attempts=3,
                 root_helper='sudo', run_as_root=True),
            call('blockdev', '--setra', readahead_size, '/dev/vdb',
                 root_helper='sudo', run_as_root=True),
        ]
        self.mock_exec.assert_has_calls(calls)

    @patch('trove.guestagent.volume.LOG')
    def test_fail_set_readahead_size(self, mock_logging):
        self.mock_exec.side_effect = exception.ProcessExecutionError
        readahead_size = 2048
        self.assertRaises(exception.GuestError,
                          self.volumeDevice.set_readahead_size,
                          readahead_size)
        self.assertEqual(1, self.mock_exec.call_count)
        calls = [
            call('blockdev', '--getsize64', '/dev/vdb', attempts=3,
                 root_helper='sudo', run_as_root=True),
        ]
        self.mock_exec.assert_has_calls(calls)


class VolumeDeviceTestXFS(trove_testtools.TestCase):

    def setUp(self):
        super(VolumeDeviceTestXFS, self).setUp()
        self.patch_conf_property('volume_fstype', 'xfs')
        self.patch_conf_property('format_options', '')
        self.volumeDevice = volume.VolumeDevice('/dev/vdb')

        self.exec_patcher = patch.object(
            utils, 'execute', return_value=('', ''))
        self.mock_exec = self.exec_patcher.start()
        self.addCleanup(self.exec_patcher.stop)
        self.ismount_patcher = patch.object(operating_system, 'is_mount')
        self.mock_ismount = self.ismount_patcher.start()
        self.addCleanup(self.ismount_patcher.stop)

    def tearDown(self):
        super(VolumeDeviceTestXFS, self).tearDown()
        self.volumeDevice = None

    def test__check_format(self):
        self.volumeDevice._check_format()
        self.assertEqual(1, self.mock_exec.call_count)
        calls = [
            call('xfs_admin', '-l', '/dev/vdb',
                 root_helper='sudo', run_as_root=True)
        ]
        self.mock_exec.assert_has_calls(calls)

    @patch('trove.guestagent.volume.LOG')
    @patch.object(utils, 'execute',
                  return_value=('not a valid XFS filesystem', ''))
    def test__check_format_2(self, mock_logging, mock_exec):
        self.assertRaises(exception.GuestError,
                          self.volumeDevice._check_format)

    def test__format(self):
        self.volumeDevice._format()
        self.assertEqual(1, self.mock_exec.call_count)
        calls = [
            call('mkfs.xfs', '/dev/vdb',
                 root_helper='sudo', run_as_root=True)
        ]
        self.mock_exec.assert_has_calls(calls)

    def test_resize_fs(self):
        with patch.object(operating_system, 'is_mount', return_value=True):
            mount_point = '/mnt/volume'
            self.volumeDevice.resize_fs(mount_point)
            self.assertEqual(6, self.mock_exec.call_count)
            calls = [
                call('blockdev', '--getsize64', '/dev/vdb', attempts=3,
                     root_helper='sudo', run_as_root=True),
                call("umount", mount_point, run_as_root=True,
                     root_helper='sudo'),
                call('xfs_repair', '/dev/vdb', root_helper='sudo',
                     run_as_root=True),
                call('mount', '/dev/vdb', root_helper='sudo',
                     run_as_root=True),
                call('xfs_growfs', '/dev/vdb', root_helper='sudo',
                     run_as_root=True),
                call('umount', '/dev/vdb', root_helper='sudo',
                     run_as_root=True)
            ]
            self.mock_exec.assert_has_calls(calls)


class VolumeMountPointTest(trove_testtools.TestCase):

    def setUp(self):
        super(VolumeMountPointTest, self).setUp()
        self.patch_conf_property('volume_fstype', 'ext3')
        self.patch_conf_property('format_options', '-m 5')
        self.volumeMountPoint = volume.VolumeMountPoint('/mnt/device',
                                                        '/dev/vdb')
        self.exec_patcher = patch.object(utils, 'execute',
                                         return_value=('', ''))
        self.mock_exec = self.exec_patcher.start()
        self.addCleanup(self.exec_patcher.stop)

    def tearDown(self):
        super(VolumeMountPointTest, self).tearDown()

    def test_mount(self):
        with patch.object(operating_system, 'exists', return_value=False):
            self.volumeMountPoint.mount()
            self.assertEqual(2, self.mock_exec.call_count)
            calls = [
                call('mkdir', '-p', '/dev/vdb', root_helper='sudo',
                     run_as_root=True),
                call('mount', '-t', 'ext3', '-o', 'defaults,noatime',
                     '/mnt/device', '/dev/vdb', root_helper='sudo',
                     run_as_root=True)
            ]
            self.mock_exec.assert_has_calls(calls)

    def test_write_to_fstab(self):
        mock_file = mock_open()
        with patch('%s.open' % volume.__name__, mock_file, create=True):
            self.volumeMountPoint.write_to_fstab()
            self.assertEqual(1, self.mock_exec.call_count)
            calls = [
                call('install', '-o', 'root', '-g', 'root', '-m', '644',
                     ANY, '/etc/fstab', root_helper='sudo',
                     run_as_root=True)
            ]
            self.mock_exec.assert_has_calls(calls)
