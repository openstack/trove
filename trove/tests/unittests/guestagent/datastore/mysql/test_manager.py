# Copyright 2026 OpenStack Foundation
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

from trove.common import cfg
from trove.guestagent.datastore.mysql import manager
from trove.tests.unittests import trove_testtools


class TestMySqlManager(trove_testtools.TestCase):
    def setUp(self):
        super(TestMySqlManager, self).setUp()
        manager.Manager._docker_client = mock.MagicMock()
        self.patch_datastore_manager('mysql')
        self.mysql_manager = manager.Manager()

    def test_get_datastore_log_defs_owner_fallback(self):
        """The log file owner should fall back to the DEFAULT group value
        when 'database_service_uid' is not set in the datastore group.
        """
        self.mysql_manager.app.get_data_dir = mock.Mock(
            return_value='/var/lib/mysql/data')
        self.mysql_manager.build_log_file_name = mock.Mock(
            side_effect=lambda log_name, owner, **kwargs:
                '/var/lib/mysql/data/mysql-%s.log' % log_name)
        self.mysql_manager.validate_log_file = mock.Mock(
            return_value='/var/log/mysqld.log')

        log_defs = self.mysql_manager.get_datastore_log_defs()

        expected_owner = cfg.CONF.database_service_uid
        self.assertIsNotNone(expected_owner)
        self.mysql_manager.build_log_file_name.assert_any_call(
            self.mysql_manager.GUEST_LOG_DEFS_GENERAL_LABEL, expected_owner,
            group=expected_owner, datastore_dir='/var/lib/mysql/data')
        self.mysql_manager.validate_log_file.assert_called_once_with(
            '/var/log/mysqld.log', expected_owner, group=expected_owner)
        for log_def in log_defs.values():
            self.assertEqual(
                expected_owner,
                log_def[self.mysql_manager.GUEST_LOG_USER_LABEL])

    def test_get_datastore_log_defs_separate_group(self):
        """A datastore-specific gid different from the uid should be passed
        through as the group when creating log files.
        """
        cfg.CONF.set_override('database_service_uid', '1100', 'mysql')
        self.addCleanup(
            cfg.CONF.clear_override, 'database_service_uid', 'mysql')
        cfg.CONF.set_override('database_service_gid', '1101', 'mysql')
        self.addCleanup(
            cfg.CONF.clear_override, 'database_service_gid', 'mysql')
        self.mysql_manager.app.get_data_dir = mock.Mock(
            return_value='/var/lib/mysql/data')
        self.mysql_manager.build_log_file_name = mock.Mock(
            side_effect=lambda log_name, owner, **kwargs:
                '/var/lib/mysql/data/mysql-%s.log' % log_name)
        self.mysql_manager.validate_log_file = mock.Mock(
            return_value='/var/log/mysqld.log')

        self.mysql_manager.get_datastore_log_defs()

        self.mysql_manager.build_log_file_name.assert_any_call(
            self.mysql_manager.GUEST_LOG_DEFS_GENERAL_LABEL, '1100',
            group='1101', datastore_dir='/var/lib/mysql/data')
        self.mysql_manager.validate_log_file.assert_called_once_with(
            '/var/log/mysqld.log', '1100', group='1101')
