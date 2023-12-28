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
from unittest.mock import MagicMock, PropertyMock

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


class TestInnoBackupEx(unittest.TestCase):
    def setUp(self):
        self.runner_cls = importutils.import_class(
            driver_mapping['innobackupex'])
        self.params = {}

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
        cmd = ('innobackupex'
               ' --stream=xbstream'
               ' --parallel=2 ' +
               runner.user_and_pass + ' %s' % runner.datadir)
        self.assertEqual(runner.cmd, cmd)

    def test_check_restore_process(self):
        '''Check manifest'''
        runner = self.runner_cls(**self.params)
        runner.process = MagicMock()
        returncode = PropertyMock(return_value=0)
        type(runner.process).returncode = returncode

        # call the method
        self.assertEqual(runner.check_restore_process(), True)


class TestInnoBackupExIncremental(unittest.TestCase):
    def setUp(self):
        self.runner_cls = importutils.import_class(
            driver_mapping['innobackupex_inc'])
        self.params = {
            'lsn': '1234567890',
        }
        self.metadata = {}

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
        cmd = ('innobackupex'
               ' --stream=xbstream'
               ' --incremental'
               ' --incremental-lsn=%(lsn)s ' +
               runner.user_and_pass + ' %s' % runner.datadir)
        self.assertEqual(runner.cmd, cmd)

    def test_get_metadata(self):
        # prepare the test
        runner = self.runner_cls(**self.params)
        runner.get_metadata = MagicMock(return_value=self.metadata)

        # call the method
        ret = runner.get_metadata()

        # assertions
        self.assertEqual(ret, self.metadata)

    def test_run_restore(self):
        # prepare the test
        runner = self.runner_cls(**self.params)
        length = 10
        runner.incremental_restore = MagicMock(return_value=length)
        runner.restore_content_length = length

        # call the method
        ret = runner.run_restore()

        # assertions
        self.assertEqual(ret, length)


if __name__ == '__main__':
    unittest.main()
