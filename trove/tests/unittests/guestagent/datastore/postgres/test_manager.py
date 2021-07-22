# Copyright 2021 Catalyst Cloud
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
import os
from unittest import mock

from trove.guestagent.datastore.postgres import manager
from trove.guestagent.datastore.postgres import service
from trove.tests.unittests import trove_testtools


class TestPostgresManager(trove_testtools.TestCase):
    def setUp(self):
        super(TestPostgresManager, self).setUp()
        manager.PostgresManager._docker_client = mock.MagicMock()
        self.patch_datastore_manager('postgresql')

    @mock.patch('trove.guestagent.common.operating_system.remove')
    @mock.patch('os.listdir')
    @mock.patch('trove.guestagent.common.operating_system.get_filesystem_size')
    @mock.patch('trove.guestagent.common.operating_system.get_dir_size')
    @mock.patch('trove.guestagent.common.operating_system.exists')
    def test_clean_wal_archives(self, mock_exists, mock_get_dir_size,
                                mock_get_filesystem_size, mock_listdir,
                                mock_remove):
        mock_exists.return_value = True
        mock_get_dir_size.side_effect = [6, 1]
        mock_get_filesystem_size.return_value = 10
        mock_listdir.return_value = [
            '0000000100000002000000D4',
            '00000001000000000000008D',
            '0000000100000000000000A7.00000028.backup',
            '0000000100000000000000A7',
            '0000000100000002000000E7'
        ]

        psql_manager = manager.PostgresManager()
        psql_manager.clean_wal_archives(mock.ANY)

        self.assertEqual(1, mock_remove.call_count)

        archive_path = service.WAL_ARCHIVE_DIR
        expected_calls = [
            mock.call(
                path=os.path.join(archive_path, '00000001000000000000008D'),
                force=True, recursive=False,
                as_root=True),
        ]
        self.assertEqual(expected_calls, mock_remove.call_args_list)

    @mock.patch('trove.guestagent.common.operating_system.remove')
    @mock.patch('os.listdir')
    @mock.patch('trove.guestagent.common.operating_system.get_filesystem_size')
    @mock.patch('trove.guestagent.common.operating_system.get_dir_size')
    @mock.patch('trove.guestagent.common.operating_system.exists')
    def test_clean_wal_archives_no_backups(self, mock_exists,
                                           mock_get_dir_size,
                                           mock_get_filesystem_size,
                                           mock_listdir,
                                           mock_remove):
        mock_exists.return_value = True
        mock_get_dir_size.side_effect = [6, 1]
        mock_get_filesystem_size.return_value = 10
        mock_listdir.return_value = [
            '0000000100000002000000D4',
            '00000001000000000000008D',
            '0000000100000000000000A7',
            '0000000100000002000000E7'
        ]

        psql_manager = manager.PostgresManager()
        psql_manager.clean_wal_archives(mock.ANY)

        self.assertEqual(3, mock_remove.call_count)

        archive_path = service.WAL_ARCHIVE_DIR
        expected_calls = [
            mock.call(
                path=os.path.join(archive_path, '0000000100000002000000D4'),
                force=True, recursive=False,
                as_root=True),
            mock.call(
                path=os.path.join(archive_path, '0000000100000000000000A7'),
                force=True, recursive=False,
                as_root=True),
            mock.call(
                path=os.path.join(archive_path, '00000001000000000000008D'),
                force=True, recursive=False,
                as_root=True),
        ]
        self.assertEqual(expected_calls, mock_remove.call_args_list)
