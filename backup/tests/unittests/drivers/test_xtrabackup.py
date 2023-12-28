# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import unittest
from unittest.mock import MagicMock, Mock, PropertyMock, patch

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import importutils

LOG = logging.getLogger(__name__)
CONF = cfg.CONF
CONF.backup_encryption_key = None
CONF.backup_id = "backup_unittest"
CONF.db_user = "db_user"
CONF.db_password = "db_password"
CONF.db_host = "db_host"

driver_mapping = {
    'innobackupex': 'backup.drivers.innobackupex.InnoBackupEx',
    'innobackupex_inc': 'backup.drivers.innobackupex.InnoBackupExIncremental',
    'mariabackup': 'backup.drivers.mariabackup.MariaBackup',
    'mariabackup_inc': 'backup.drivers.mariabackup.MariaBackupIncremental',
    'pg_basebackup': 'backup.drivers.postgres.PgBasebackup',
    'pg_basebackup_inc': 'backup.drivers.postgres.PgBasebackupIncremental',
    'xtrabackup': 'backup.drivers.xtrabackup.XtraBackup',
    'xtrabackup_inc': 'backup.drivers.xtrabackup.XtraBackupIncremental'
}

from backup.drivers.xtrabackup import XtraBackupException


class TestXtraBackup(unittest.TestCase):
    def setUp(self):
        self.runner_cls = importutils.import_class(
            driver_mapping['xtrabackup'])
        self.params = {
            'db_datadir': '/var/lib/mysql/data'
        }
        # assertions
        self.assertIsNotNone(self.runner_cls)

    def tearDown(self):
        pass

    def test_instance(self):
        '''Check instance'''
        # call the method
        runner = self.runner_cls(**self.params)

        # assertions
        self.assertIsNotNone(runner)

    def test_cmd(self):
        '''Check cmd property'''
        # call the method
        runner = self.runner_cls(**self.params)

        # assertions
        cmd = (f'xtrabackup --backup --stream=xbstream --parallel=2 '
               f'--datadir=%(datadir)s --user=%(user)s '
               f'--password=%(password)s --host=%(host)s'
               % {
                   'datadir': runner.datadir,
                   'user': CONF.db_user,
                   'password': CONF.db_password,
                   'host': CONF.db_host}
               )
        self.assertEqual(runner.cmd, cmd)

    def test_check_restore_process(self):
        '''Check manifest'''
        # call the method
        runner = self.runner_cls(**self.params)
        runner.process = MagicMock()
        returncode = PropertyMock(return_value=0)
        type(runner.process).returncode = returncode

        # assertions
        self.assertEqual(runner.check_restore_process(), True)

    def test_post_restore(self):
        '''Check manifest'''
        runner = self.runner_cls(**self.params)
        mock = Mock(side_effect=XtraBackupException(
            'Prepare did not complete successfully'))
        runner.post_restore = mock

        # call the method
        with self.assertRaises(
            XtraBackupException,
                msg="Prepare did not complete successfully"):
            runner.post_restore()


# Manually import XtraBackupIncremental to prevent from running
# xtrabackup --version when calling the TestXtraBackupIncremental
# constructor
from backup.drivers.xtrabackup import XtraBackupIncremental


class TestXtraBackupIncremental(unittest.TestCase):
    def setUp(self):
        self.runner_cls = importutils.import_class(
            driver_mapping['xtrabackup_inc'])
        self.params = {
            'lsn': '1234567890',
            'parent_location': '',
            'parent_checksum': '',
        }
        self.metadata = {
            'lsn': '1234567890',
            'parent_location': 'https://example.com/location',
            'parent_checksum': 'f1508ecf362a364c5aae008b4b5a9cb9',
        }

    def tearDown(self):
        pass

    def test_instance(self):
        '''Check instance and add_incremental_opts'''
        # call the method
        with patch(
            'backup.drivers.xtrabackup.XtraBackupIncremental.'
            'add_incremental_opts', new_callable=PropertyMock
        ) as XtraBackupIncremental_add_incremental_opts:
            XtraBackupIncremental_add_incremental_opts.return_value = True
            runner = XtraBackupIncremental(**self.params)
            # assertions
            self.assertIsNotNone(runner)

    def test_cmd(self):
        '''Check cmd property'''
        # call the method
        with patch(
            'backup.drivers.xtrabackup.XtraBackupIncremental.'
            'add_incremental_opts', new_callable=PropertyMock
        ) as XtraBackupIncremental_add_incremental_opts:
            XtraBackupIncremental_add_incremental_opts.return_value = True
            runner = XtraBackupIncremental(**self.params)

            # assertions
            self.assertIsNotNone(runner)
            # assertions
            cmd = (f'xtrabackup --backup --stream=xbstream '
                   f'--incremental-lsn=%(lsn)s '
                   f'--datadir={runner.datadir} {runner.user_and_pass}')
            if runner.add_incremental_opts:
                cmd = '{} --incremental'.format(cmd)
            self.assertEqual(runner.cmd, cmd)

    def test_get_metadata(self):
        '''Check get_metadata'''
        with patch(
            'backup.drivers.xtrabackup.XtraBackupIncremental.'
            'add_incremental_opts', new_callable=PropertyMock
        ) as XtraBackupIncremental_add_incremental_opts:
            XtraBackupIncremental_add_incremental_opts.return_value = True
            runner = XtraBackupIncremental(**self.params)
            runner.get_metadata = MagicMock(return_value=self.metadata)

            # assertions
            self.assertIsNotNone(runner)
            ret = runner.get_metadata()
            self.assertEqual(ret, self.metadata)

    def test_run_restore(self):
        '''Check run_restore'''
        with patch(
            'backup.drivers.xtrabackup.XtraBackupIncremental.'
            'add_incremental_opts', new_callable=PropertyMock
        ) as XtraBackupIncremental_add_incremental_opts:
            XtraBackupIncremental_add_incremental_opts.return_value = True
            runner = XtraBackupIncremental(**self.params)
            length = 10
            runner.incremental_restore = MagicMock(return_value=length)
            runner.restore_content_length = length
            # call the method
            ret = runner.run_restore()
            # assertions
            self.assertEqual(ret, length)


if __name__ == '__main__':
    unittest.main()
