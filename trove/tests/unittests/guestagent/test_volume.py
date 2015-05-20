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
import os

from mock import Mock, MagicMock, patch, mock_open
import pexpect
import testtools

from trove.common.exception import GuestError, ProcessExecutionError
from trove.common import utils
from trove.guestagent import volume


def _setUp_fake_spawn(return_val=0):
    fake_spawn = pexpect.spawn('echo')
    fake_spawn.expect = Mock(return_value=return_val)
    pexpect.spawn = Mock(return_value=fake_spawn)
    return fake_spawn


class VolumeDeviceTest(testtools.TestCase):

    def setUp(self):
        super(VolumeDeviceTest, self).setUp()
        self.volumeDevice = volume.VolumeDevice('/dev/vdb')

    def tearDown(self):
        super(VolumeDeviceTest, self).tearDown()

    def test_migrate_data(self):
        origin_execute = utils.execute
        utils.execute = Mock()
        origin_os_path_exists = os.path.exists
        os.path.exists = Mock()
        fake_spawn = _setUp_fake_spawn()

        origin_unmount = self.volumeDevice.unmount
        self.volumeDevice.unmount = MagicMock()
        self.volumeDevice.migrate_data('/')
        self.assertEqual(1, fake_spawn.expect.call_count)
        self.assertEqual(1, utils.execute.call_count)
        self.assertEqual(1, self.volumeDevice.unmount.call_count)
        utils.execute = origin_execute
        self.volumeDevice.unmount = origin_unmount
        os.path.exists = origin_os_path_exists

    def test__check_device_exists(self):
        origin_execute = utils.execute
        utils.execute = Mock()
        self.volumeDevice._check_device_exists()
        self.assertEqual(1, utils.execute.call_count)
        utils.execute = origin_execute

    def test_fail__check_device_exists(self):
        with patch.object(utils, 'execute', side_effect=ProcessExecutionError):
            self.assertRaises(GuestError,
                              self.volumeDevice._check_device_exists)

    def test__check_format(self):
        fake_spawn = _setUp_fake_spawn()

        self.volumeDevice._check_format()
        self.assertEqual(1, fake_spawn.expect.call_count)

    def test__check_format_2(self):
        fake_spawn = _setUp_fake_spawn(return_val=1)

        self.assertEqual(0, fake_spawn.expect.call_count)
        self.assertRaises(IOError, self.volumeDevice._check_format)

    def test__format(self):
        fake_spawn = _setUp_fake_spawn()

        self.volumeDevice._format()

        self.assertEqual(1, fake_spawn.expect.call_count)
        self.assertEqual(1, pexpect.spawn.call_count)

    def test_format(self):
        origin_check_device_exists = self.volumeDevice._check_device_exists
        origin_format = self.volumeDevice._format
        origin_check_format = self.volumeDevice._check_format
        self.volumeDevice._check_device_exists = MagicMock()
        self.volumeDevice._check_format = MagicMock()
        self.volumeDevice._format = MagicMock()

        self.volumeDevice.format()
        self.assertEqual(1, self.volumeDevice._check_device_exists.call_count)
        self.assertEqual(1, self.volumeDevice._format.call_count)
        self.assertEqual(1, self.volumeDevice._check_format.call_count)

        self.volumeDevice._check_device_exists = origin_check_device_exists
        self.volumeDevice._format = origin_format
        self.volumeDevice._check_format = origin_check_format

    def test_mount(self):
        origin_ = volume.VolumeMountPoint.mount
        volume.VolumeMountPoint.mount = Mock()
        origin_os_path_exists = os.path.exists
        os.path.exists = Mock()
        origin_write_to_fstab = volume.VolumeMountPoint.write_to_fstab
        volume.VolumeMountPoint.write_to_fstab = Mock()

        self.volumeDevice.mount(Mock)
        self.assertEqual(1, volume.VolumeMountPoint.mount.call_count)
        self.assertEqual(1, volume.VolumeMountPoint.write_to_fstab.call_count)
        volume.VolumeMountPoint.mount = origin_
        volume.VolumeMountPoint.write_to_fstab = origin_write_to_fstab
        os.path.exists = origin_os_path_exists

    def test_resize_fs(self):
        origin_check_device_exists = self.volumeDevice._check_device_exists
        origin_execute = utils.execute
        utils.execute = Mock()
        self.volumeDevice._check_device_exists = MagicMock()
        origin_os_path_exists = os.path.exists
        os.path.exists = Mock()

        self.volumeDevice.resize_fs('/mnt/volume')

        self.assertEqual(1, self.volumeDevice._check_device_exists.call_count)
        self.assertEqual(2, utils.execute.call_count)
        self.volumeDevice._check_device_exists = origin_check_device_exists
        os.path.exists = origin_os_path_exists
        utils.execute = origin_execute

    @patch.object(os.path, 'ismount', return_value=True)
    @patch.object(utils, 'execute', side_effect=ProcessExecutionError)
    def test_fail_resize_fs(self, mock_execute, mock_mount):
        with patch.object(self.volumeDevice, '_check_device_exists'):
            self.assertRaises(GuestError,
                              self.volumeDevice.resize_fs, '/mnt/volume')
            self.assertEqual(1,
                             self.volumeDevice._check_device_exists.call_count)
            self.assertEqual(1, mock_mount.call_count)

    def test_unmount_positive(self):
        self._test_unmount()

    def test_unmount_negative(self):
        self._test_unmount(False)

    def _test_unmount(self, positive=True):
        origin_ = os.path.exists
        os.path.exists = MagicMock(return_value=positive)
        fake_spawn = _setUp_fake_spawn()

        self.volumeDevice.unmount('/mnt/volume')
        COUNT = 1
        if not positive:
            COUNT = 0
        self.assertEqual(COUNT, fake_spawn.expect.call_count)
        os.path.exists = origin_

    @patch.object(utils, 'execute', return_value=('/var/lib/mysql', ''))
    def test_mount_points(self, mock_execute):
        mount_point = self.volumeDevice.mount_points('/dev/vdb')
        self.assertEqual(['/var/lib/mysql'], mount_point)

    @patch.object(utils, 'execute', side_effect=ProcessExecutionError)
    def test_fail_mount_points(self, mock_execute):
        self.assertRaises(GuestError, self.volumeDevice.mount_points,
                          '/mnt/volume')

    def test_set_readahead_size(self):
        origin_check_device_exists = self.volumeDevice._check_device_exists
        self.volumeDevice._check_device_exists = MagicMock()
        mock_execute = MagicMock(return_value=None)
        readahead_size = 2048
        self.volumeDevice.set_readahead_size(readahead_size,
                                             execute_function=mock_execute)
        blockdev = mock_execute.call_args_list[0]

        blockdev.assert_called_with("sudo", "blockdev", "--setra",
                                    readahead_size, "/dev/vdb")
        self.volumeDevice._check_device_exists = origin_check_device_exists

    def test_fail_set_readahead_size(self):
        mock_execute = MagicMock(side_effect=ProcessExecutionError)
        readahead_size = 2048
        with patch.object(self.volumeDevice, '_check_device_exists'):
            self.assertRaises(GuestError, self.volumeDevice.set_readahead_size,
                              readahead_size, execute_function=mock_execute)
            self.volumeDevice._check_device_exists.assert_any_call()


class VolumeMountPointTest(testtools.TestCase):
    def setUp(self):
        super(VolumeMountPointTest, self).setUp()
        self.volumeMountPoint = volume.VolumeMountPoint('/mnt/device',
                                                        '/dev/vdb')

    def tearDown(self):
        super(VolumeMountPointTest, self).tearDown()

    def test_mount(self):
        origin_ = os.path.exists
        os.path.exists = MagicMock(return_value=False)
        fake_spawn = _setUp_fake_spawn()

        utils.execute_with_timeout = Mock()

        self.volumeMountPoint.mount()

        self.assertEqual(1, os.path.exists.call_count)
        self.assertEqual(1, utils.execute_with_timeout.call_count)
        self.assertEqual(1, fake_spawn.expect.call_count)

        os.path.exists = origin_

    def test_write_to_fstab(self):
        origin_execute = utils.execute
        utils.execute = Mock()
        m = mock_open()
        with patch('%s.open' % volume.__name__, m, create=True):
            self.volumeMountPoint.write_to_fstab()

        self.assertEqual(1, utils.execute.call_count)
        utils.execute = origin_execute
