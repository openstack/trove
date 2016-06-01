# Copyright 2013 Hewlett-Packard Development Company, L.P.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import hashlib
import mock
import os

from mock import Mock, MagicMock, patch, ANY, DEFAULT
from oslo_utils import netutils
from webob.exc import HTTPNotFound

from trove.backup.state import BackupState
from trove.common.context import TroveContext
from trove.common.strategies.storage.base import Storage
from trove.common import utils
from trove.conductor import api as conductor_api
from trove.guestagent.backup import backupagent
from trove.guestagent.common import configuration
from trove.guestagent.common.configuration import ImportOverrideStrategy
from trove.guestagent.strategies.backup.base import BackupRunner
from trove.guestagent.strategies.backup.base import UnknownBackupType
from trove.guestagent.strategies.backup.experimental import couchbase_impl
from trove.guestagent.strategies.backup.experimental import db2_impl
from trove.guestagent.strategies.backup.experimental import mongo_impl
from trove.guestagent.strategies.backup.experimental import redis_impl
from trove.guestagent.strategies.backup import mysql_impl
from trove.guestagent.strategies.backup.mysql_impl import MySqlApp
from trove.guestagent.strategies.restore.base import RestoreRunner
from trove.tests.unittests import trove_testtools


def create_fake_data():
    from random import choice
    from string import ascii_letters

    return ''.join([choice(ascii_letters) for _ in range(1024)])


class MockBackup(BackupRunner):
    """Create a large temporary file to 'backup' with subprocess."""

    backup_type = 'mock_backup'

    def __init__(self, *args, **kwargs):
        self.data = create_fake_data()
        self.cmd = 'echo %s' % self.data
        super(MockBackup, self).__init__(*args, **kwargs)

    def cmd(self):
        return self.cmd


class MockCheckProcessBackup(MockBackup):
    """Backup runner that fails confirming the process."""

    def check_process(self):
        return False


class MockLossyBackup(MockBackup):
    """Fake Incomplete writes to swift."""

    def read(self, *args):
        results = super(MockLossyBackup, self).read(*args)
        if results:
            # strip a few chars from the stream
            return results[20:]


class MockSwift(object):
    """Store files in String."""

    def __init__(self, *args, **kwargs):
        self.store = ''
        self.containers = []
        self.container = "database_backups"
        self.url = 'http://mockswift/v1'
        self.etag = hashlib.md5()

    def put_container(self, container):
        if container not in self.containers:
            self.containers.append(container)
        return None

    def put_object(self, container, obj, contents, **kwargs):
        if container not in self.containers:
            raise HTTPNotFound
        while True:
            if not hasattr(contents, 'read'):
                break
            content = contents.read(2 ** 16)
            if not content:
                break
            self.store += content
        self.etag.update(self.store)
        return self.etag.hexdigest()

    def save(self, filename, stream, metadata=None):
        location = '%s/%s/%s' % (self.url, self.container, filename)
        return True, 'w00t', 'fake-checksum', location

    def load(self, context, storage_url, container, filename, backup_checksum):
        pass

    def load_metadata(self, location, checksum):
        return {}

    def save_metadata(self, location, metadata):
        pass


class MockStorage(Storage):

    def __call__(self, *args, **kwargs):
        return self

    def load(self, location, backup_checksum):
        pass

    def save(self, filename, stream, metadata=None):
        pass

    def load_metadata(self, location, checksum):
        return {}

    def save_metadata(self, location, metadata={}):
        pass

    def is_enabled(self):
        return True


class MockRestoreRunner(RestoreRunner):

    def __init__(self, storage, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def restore(self):
        pass

    def is_zipped(self):
        return False


class MockStats:
    f_blocks = 1024 ** 2
    f_bsize = 4096
    f_bfree = 512 * 1024


class BackupAgentTest(trove_testtools.TestCase):

    def setUp(self):
        super(BackupAgentTest, self).setUp()
        self.patch_ope = patch.multiple('os.path',
                                        exists=DEFAULT)
        self.mock_ope = self.patch_ope.start()
        self.addCleanup(self.patch_ope.stop)
        self.patch_pc = patch('trove.guestagent.datastore.service.'
                              'BaseDbStatus.prepare_completed')
        self.mock_pc = self.patch_pc.start()
        self.mock_pc.__get__ = Mock(return_value=True)
        self.addCleanup(self.patch_pc.stop)
        self.get_auth_pwd_patch = patch.object(
            MySqlApp, 'get_auth_password', MagicMock(return_value='123'))
        self.get_auth_pwd_mock = self.get_auth_pwd_patch.start()
        self.addCleanup(self.get_auth_pwd_patch.stop)
        self.get_ss_patch = patch.object(
            backupagent, 'get_storage_strategy',
            MagicMock(return_value=MockSwift))
        self.get_ss_mock = self.get_ss_patch.start()
        self.addCleanup(self.get_ss_patch.stop)
        self.statvfs_patch = patch.object(
            os, 'statvfs', MagicMock(return_value=MockStats))
        self.statvfs_mock = self.statvfs_patch.start()
        self.addCleanup(self.statvfs_patch.stop)
        self.orig_utils_execute_with_timeout = utils.execute_with_timeout
        self.orig_os_get_ip_address = netutils.get_my_ipv4

    def tearDown(self):
        super(BackupAgentTest, self).tearDown()
        utils.execute_with_timeout = self.orig_utils_execute_with_timeout
        netutils.get_my_ipv4 = self.orig_os_get_ip_address

    def test_backup_impl_MySQLDump(self):
        """This test is for
           guestagent/strategies/backup/mysql_impl
        """
        mysql_dump = mysql_impl.MySQLDump(
            'abc', extra_opts='')
        self.assertIsNotNone(mysql_dump.cmd)
        str_mysql_dump_cmd = ('mysqldump'
                              ' --all-databases'
                              ' %(extra_opts)s'
                              ' --opt'
                              ' --password=123'
                              ' -u os_admin'
                              ' 2>/tmp/mysqldump.log'
                              ' | gzip |'
                              ' openssl enc -aes-256-cbc -salt '
                              '-pass pass:default_aes_cbc_key')
        self.assertEqual(str_mysql_dump_cmd, mysql_dump.cmd)
        self.assertIsNotNone(mysql_dump.manifest)
        self.assertEqual('abc.gz.enc', mysql_dump.manifest)

    @mock.patch.object(
        MySqlApp, 'get_data_dir', return_value='/var/lib/mysql/data')
    def test_backup_impl_InnoBackupEx(self, mock_datadir):
        """This test is for
           guestagent/strategies/backup/mysql_impl
        """
        inno_backup_ex = mysql_impl.InnoBackupEx('innobackupex', extra_opts='')
        self.assertIsNotNone(inno_backup_ex.cmd)
        str_innobackup_cmd = ('sudo innobackupex'
                              ' --stream=xbstream'
                              ' %(extra_opts)s'
                              ' /var/lib/mysql/data 2>/tmp/innobackupex.log'
                              ' | gzip |'
                              ' openssl enc -aes-256-cbc -salt '
                              '-pass pass:default_aes_cbc_key')
        self.assertEqual(str_innobackup_cmd, inno_backup_ex.cmd)
        self.assertIsNotNone(inno_backup_ex.manifest)
        str_innobackup_manifest = 'innobackupex.xbstream.gz.enc'
        self.assertEqual(str_innobackup_manifest, inno_backup_ex.manifest)

    def test_backup_impl_CbBackup(self):
        netutils.get_my_ipv4 = Mock(return_value="1.1.1.1")
        utils.execute_with_timeout = Mock(return_value=None)
        cbbackup = couchbase_impl.CbBackup('cbbackup', extra_opts='')
        self.assertIsNotNone(cbbackup)
        str_cbbackup_cmd = ("tar cpPf - /tmp/backups | "
                            "gzip | openssl enc -aes-256-cbc -salt -pass "
                            "pass:default_aes_cbc_key")
        self.assertEqual(str_cbbackup_cmd, cbbackup.cmd)
        self.assertIsNotNone(cbbackup.manifest)
        self.assertIn('gz.enc', cbbackup.manifest)

    def test_backup_impl_DB2Backup(self):
        netutils.get_my_ipv4 = Mock(return_value="1.1.1.1")
        db2_backup = db2_impl.DB2Backup('db2backup', extra_opts='')
        self.assertIsNotNone(db2_backup)
        str_db2_backup_cmd = ("sudo tar cPf - /home/db2inst1/db2inst1/backup "
                              "| gzip | openssl enc -aes-256-cbc -salt -pass "
                              "pass:default_aes_cbc_key")
        self.assertEqual(str_db2_backup_cmd, db2_backup.cmd)
        self.assertIsNotNone(db2_backup.manifest)
        self.assertIn('gz.enc', db2_backup.manifest)

    @mock.patch.object(ImportOverrideStrategy, '_initialize_import_directory')
    def test_backup_impl_MongoDump(self, _):
        netutils.get_my_ipv4 = Mock(return_value="1.1.1.1")
        utils.execute_with_timeout = Mock(return_value=None)
        mongodump = mongo_impl.MongoDump('mongodump', extra_opts='')
        self.assertIsNotNone(mongodump)
        str_mongodump_cmd = ("sudo tar cPf - /var/lib/mongodb/dump | "
                             "gzip | openssl enc -aes-256-cbc -salt -pass "
                             "pass:default_aes_cbc_key")
        self.assertEqual(str_mongodump_cmd, mongodump.cmd)
        self.assertIsNotNone(mongodump.manifest)
        self.assertIn('gz.enc', mongodump.manifest)

    @patch.object(utils, 'execute_with_timeout', return_value=('0', ''))
    @patch.object(configuration.ConfigurationManager, 'parse_configuration',
                  Mock(return_value={'dir': '/var/lib/redis',
                                     'dbfilename': 'dump.rdb'}))
    def test_backup_impl_RedisBackup(self, *mocks):
        netutils.get_my_ipv4 = Mock(return_value="1.1.1.1")
        redis_backup = redis_impl.RedisBackup('redisbackup', extra_opts='')
        self.assertIsNotNone(redis_backup)
        str_redis_backup_cmd = ("sudo cat /var/lib/redis/dump.rdb | "
                                "gzip | openssl enc -aes-256-cbc -salt -pass "
                                "pass:default_aes_cbc_key")
        self.assertEqual(str_redis_backup_cmd, redis_backup.cmd)
        self.assertIsNotNone(redis_backup.manifest)
        self.assertIn('gz.enc', redis_backup.manifest)

    def test_backup_base(self):
        """This test is for
           guestagent/strategies/backup/base
        """
        BackupRunner.cmd = "%s"
        backup_runner = BackupRunner('sample', cmd='echo command')
        if backup_runner.is_zipped:
            self.assertEqual('.gz', backup_runner.zip_manifest)
            self.assertIsNotNone(backup_runner.zip_manifest)
            self.assertIsNotNone(backup_runner.zip_cmd)
            self.assertEqual(' | gzip', backup_runner.zip_cmd)
        else:
            self.assertIsNone(backup_runner.zip_manifest)
            self.assertIsNone(backup_runner.zip_cmd)
        self.assertEqual('BackupRunner', backup_runner.backup_type)

    @patch.object(conductor_api.API, 'get_client', Mock(return_value=Mock()))
    @patch.object(conductor_api.API, 'update_backup',
                  Mock(return_value=Mock()))
    def test_execute_backup(self):
        """This test should ensure backup agent
                ensures that backup and storage is not running
                resolves backup instance
                starts backup
                starts storage
                reports status
        """
        agent = backupagent.BackupAgent()
        backup_info = {'id': '123',
                       'location': 'fake-location',
                       'type': 'InnoBackupEx',
                       'checksum': 'fake-checksum',
                       'datastore': 'mysql',
                       'datastore_version': '5.5'
                       }
        agent.execute_backup(context=None, backup_info=backup_info,
                             runner=MockBackup)

        self.assertTrue(
            conductor_api.API.update_backup.called_once_with(
                ANY,
                backup_id=backup_info['id'],
                state=BackupState.NEW))

        self.assertTrue(
            conductor_api.API.update_backup.called_once_with(
                ANY,
                backup_id=backup_info['id'],
                size=ANY,
                state=BackupState.BUILDING))

        self.assertTrue(
            conductor_api.API.update_backup.called_once_with(
                ANY,
                backup_id=backup_info['id'],
                checksum=ANY,
                location=ANY,
                note=ANY,
                backup_type=backup_info['type'],
                state=BackupState.COMPLETED))

    @patch.object(conductor_api.API, 'get_client', Mock(return_value=Mock()))
    @patch.object(conductor_api.API, 'update_backup',
                  Mock(return_value=Mock()))
    def test_execute_bad_process_backup(self):
        agent = backupagent.BackupAgent()
        backup_info = {'id': '123',
                       'location': 'fake-location',
                       'type': 'InnoBackupEx',
                       'checksum': 'fake-checksum',
                       'datastore': 'mysql',
                       'datastore_version': '5.5'
                       }

        self.assertRaises(backupagent.BackupError, agent.execute_backup,
                          context=None, backup_info=backup_info,
                          runner=MockCheckProcessBackup)

        self.assertTrue(
            conductor_api.API.update_backup.called_once_with(
                ANY,
                backup_id=backup_info['id'],
                state=BackupState.NEW))

        self.assertTrue(
            conductor_api.API.update_backup.called_once_with(
                ANY,
                backup_id=backup_info['id'],
                size=ANY,
                state=BackupState.BUILDING))

        self.assertTrue(
            conductor_api.API.update_backup.called_once_with(
                ANY,
                backup_id=backup_info['id'],
                checksum=ANY,
                location=ANY,
                note=ANY,
                backup_type=backup_info['type'],
                state=BackupState.FAILED))

    @patch.object(conductor_api.API, 'get_client', Mock(return_value=Mock()))
    @patch.object(conductor_api.API, 'update_backup',
                  Mock(return_value=Mock()))
    @patch('trove.guestagent.backup.backupagent.LOG')
    def test_execute_lossy_backup(self, mock_logging):
        """This test verifies that incomplete writes to swift will fail."""
        with patch.object(MockSwift, 'save',
                          return_value=(False, 'Error', 'y', 'z')):

            agent = backupagent.BackupAgent()

            backup_info = {'id': '123',
                           'location': 'fake-location',
                           'type': 'InnoBackupEx',
                           'checksum': 'fake-checksum',
                           'datastore': 'mysql',
                           'datastore_version': '5.5'
                           }

            self.assertRaises(backupagent.BackupError, agent.execute_backup,
                              context=None, backup_info=backup_info,
                              runner=MockLossyBackup)

            self.assertTrue(
                conductor_api.API.update_backup.called_once_with(
                    ANY,
                    backup_id=backup_info['id'],
                    state=BackupState.FAILED))

    def test_execute_restore(self):
        """This test should ensure backup agent
                resolves backup instance
                determines backup/restore type
                transfers/downloads data and invokes the restore module
                reports status
        """
        with patch.object(backupagent, 'get_storage_strategy',
                          return_value=MockStorage):

            with patch.object(backupagent, 'get_restore_strategy',
                              return_value=MockRestoreRunner):

                agent = backupagent.BackupAgent()

                bkup_info = {'id': '123',
                             'location': 'fake-location',
                             'type': 'InnoBackupEx',
                             'checksum': 'fake-checksum',
                             }
                agent.execute_restore(TroveContext(),
                                      bkup_info,
                                      '/var/lib/mysql/data')

    @patch('trove.guestagent.backup.backupagent.LOG')
    def test_restore_unknown(self, mock_logging):
        with patch.object(backupagent, 'get_restore_strategy',
                          side_effect=ImportError):

            agent = backupagent.BackupAgent()

            bkup_info = {'id': '123',
                         'location': 'fake-location',
                         'type': 'foo',
                         'checksum': 'fake-checksum',
                         }

            self.assertRaises(UnknownBackupType, agent.execute_restore,
                              context=None, backup_info=bkup_info,
                              restore_location='/var/lib/mysql/data')

    @patch.object(MySqlApp, 'get_data_dir', return_value='/var/lib/mysql/data')
    @patch.object(conductor_api.API, 'get_client', Mock(return_value=Mock()))
    @patch.object(MockSwift, 'load_metadata', return_value={'lsn': '54321'})
    @patch.object(MockStorage, 'save_metadata')
    @patch.object(backupagent, 'get_storage_strategy', return_value=MockSwift)
    @patch('trove.guestagent.backup.backupagent.LOG')
    def test_backup_incremental_metadata(self, mock_logging,
                                         get_storage_strategy_mock,
                                         save_metadata_mock,
                                         load_metadata_mock,
                                         get_datadir_mock):
        meta = {
            'lsn': '12345',
            'parent_location': 'fake',
            'parent_checksum': 'md5',
        }
        with patch.multiple(mysql_impl.InnoBackupExIncremental,
                            metadata=MagicMock(return_value=meta),
                            _run=MagicMock(return_value=True),
                            __exit__=MagicMock(return_value=True)):
            agent = backupagent.BackupAgent()

            bkup_info = {'id': '123',
                         'location': 'fake-location',
                         'type': 'InnoBackupEx',
                         'checksum': 'fake-checksum',
                         'parent': {'location': 'fake', 'checksum': 'md5'},
                         'datastore': 'mysql',
                         'datastore_version': 'bo.gus'
                         }

            agent.execute_backup(TroveContext(),
                                 bkup_info,
                                 '/var/lib/mysql/data')

            self.assertTrue(MockStorage.save_metadata.called_once_with(
                            ANY,
                            meta))

    @patch.object(conductor_api.API, 'get_client', Mock(return_value=Mock()))
    def test_backup_incremental_bad_metadata(self):
        with patch.object(backupagent, 'get_storage_strategy',
                          return_value=MockSwift):

            agent = backupagent.BackupAgent()

            bkup_info = {'id': '123',
                         'location': 'fake-location',
                         'type': 'InnoBackupEx',
                         'checksum': 'fake-checksum',
                         'parent': {'location': 'fake', 'checksum': 'md5'}
                         }

            self.assertRaises(
                AttributeError,
                agent.execute_backup, TroveContext(), bkup_info, 'location')
