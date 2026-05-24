#    Copyright 2026 PS Cloud Services
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

from unittest import mock

import testtools

from oslo_concurrency import processutils

from trove.common import exception
from trove.guestagent import volume


class FSExtTest(testtools.TestCase):

    def setUp(self):
        super(FSExtTest, self).setUp()

        self.fs = volume.FSExt("ext4", "")
        self.device_path = "/dev/vdb"

    @mock.patch.object(volume.utils, "execute")
    def test_check_format_blkid_success(self, mock_execute):
        mock_execute.side_effect = [
            ("ext4\n", ""),
            ("", ""),
        ]

        self.fs.check_format(self.device_path)

        mock_execute.assert_has_calls([
            mock.call(
                "blkid", "-o", "value", "-s", "TYPE",
                self.device_path,
                run_as_root=True,
                root_helper="sudo"),
            mock.call(
                "e2fsck", "-p", self.device_path,
                run_as_root=True,
                root_helper="sudo"),
        ])

    # blkid exit code 2 -  Not Found / Cannot Read. FORMATTING REQUIRED.
    @mock.patch.object(volume.utils, "execute")
    def test_check_format_blkid_exit_code_2(self, mock_execute):
        mock_execute.side_effect = processutils.ProcessExecutionError(
            exit_code=2)

        self.assertRaises(
            exception.GuestError,
            self.fs.check_format,
            self.device_path)

        mock_execute.assert_called_once_with(
            "blkid", "-o", "value", "-s", "TYPE",
            self.device_path,
            run_as_root=True,
            root_helper="sudo")

    # blkid exit code 4 - Usage Error. No formatting. Just throw error.
    @mock.patch.object(volume.utils, "execute")
    def test_check_format_blkid_exit_code_4(self, mock_execute):
        mock_execute.side_effect = processutils.ProcessExecutionError(
            exit_code=4)

        self.assertRaises(
            exception.ProcessExecutionError,
            self.fs.check_format,
            self.device_path)

        mock_execute.assert_called_once()

    # blkid exit code 8 - Ambivalent Result. No formatting. Just throw error.
    @mock.patch.object(volume.utils, "execute")
    def test_check_format_blkid_exit_code_8(self, mock_execute):
        mock_execute.side_effect = processutils.ProcessExecutionError(
            exit_code=8)

        self.assertRaises(
            exception.ProcessExecutionError,
            self.fs.check_format,
            self.device_path)

        mock_execute.assert_called_once()

    @mock.patch.object(volume.utils, "execute")
    def test_check_format_e2fsck_success(self, mock_execute):
        mock_execute.side_effect = [
            ("ext4\n", ""),
            ("", ""),
        ]

        self.fs.check_format(self.device_path)

        self.assertEqual(2, mock_execute.call_count)

    @mock.patch.object(volume.utils, "execute")
    def test_check_format_e2fsck_exit_codes(self, mock_execute):
        exit_codes = {
            1: False,
            2: False,
            4: True,
            8: True,
            16: True,
            32: True,
            128: True,
        }

        for exit_code, should_raise in exit_codes.items():
            mock_execute.reset_mock()
            mock_execute.side_effect = [
                ("ext4\n", ""),
                processutils.ProcessExecutionError(
                    exit_code=exit_code),
            ]

            if should_raise:
                self.assertRaises(
                    processutils.ProcessExecutionError,
                    self.fs.check_format,
                    self.device_path)
            else:
                self.fs.check_format(self.device_path)

            self.assertEqual(2, mock_execute.call_count)
