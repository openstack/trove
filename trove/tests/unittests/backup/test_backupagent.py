#Copyright 2013 Hewlett-Packard Development Company, L.P.

#Licensed under the Apache License, Version 2.0 (the "License");
#you may not use this file except in compliance with the License.
#You may obtain a copy of the License at
#
#http://www.apache.org/licenses/LICENSE-2.0
#
#Unless required by applicable law or agreed to in writing, software
#distributed under the License is distributed on an "AS IS" BASIS,
#WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#See the License for the specific language governing permissions and
#limitations under the License.

from mock import Mock, MagicMock, patch, ANY
from webob.exc import HTTPNotFound

import hashlib
import os
import testtools

from trove.common.context import TroveContext
from trove.conductor import api as conductor_api
from trove.guestagent.strategies.backup import mysql_impl
from trove.guestagent.strategies.restore.base import RestoreRunner
from trove.backup.models import BackupState
from trove.guestagent.backup import backupagent
from trove.guestagent.strategies.backup.base import BackupRunner
from trove.guestagent.strategies.backup.base import UnknownBackupType
from trove.guestagent.strategies.storage.base import Storage

conductor_api.API.update_backup = Mock()


def create_fake_data():
    from random import choice
    from string import ascii_letters

    return ''.join([choice(ascii_letters) for _ in xrange(1024)])


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

    def save(self, filename, stream):
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

    def save(self, filename, stream):
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


class BackupAgentTest(testtools.TestCase):
    def setUp(self):
        super(BackupAgentTest, self).setUp()
        mysql_impl.get_auth_password = MagicMock(return_value='123')
        backupagent.get_storage_strategy = MagicMock(return_value=MockSwift)
        os.statvfs = MagicMock(return_value=MockStats)

    def tearDown(self):
        super(BackupAgentTest, self).tearDown()

    def test_backup_impl_MySQLDump(self):
        """This test is for
           guestagent/strategies/backup/impl
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
        self.assertEqual(mysql_dump.cmd, str_mysql_dump_cmd)
        self.assertIsNotNone(mysql_dump.manifest)
        self.assertEqual(mysql_dump.manifest, 'abc.gz.enc')

    def test_backup_impl_InnoBackupEx(self):
        """This test is for
           guestagent/strategies/backup/impl
        """
        inno_backup_ex = mysql_impl.InnoBackupEx('innobackupex', extra_opts='')
        self.assertIsNotNone(inno_backup_ex.cmd)
        str_innobackup_cmd = ('sudo innobackupex'
                              ' --stream=xbstream'
                              ' %(extra_opts)s'
                              ' /var/lib/mysql 2>/tmp/innobackupex.log'
                              ' | gzip |'
                              ' openssl enc -aes-256-cbc -salt '
                              '-pass pass:default_aes_cbc_key')
        self.assertEqual(inno_backup_ex.cmd, str_innobackup_cmd)
        self.assertIsNotNone(inno_backup_ex.manifest)
        str_innobackup_manifest = 'innobackupex.xbstream.gz.enc'
        self.assertEqual(inno_backup_ex.manifest, str_innobackup_manifest)

    def test_backup_base(self):
        """This test is for
           guestagent/strategies/backup/base
        """
        BackupRunner.cmd = "%s"
        backup_runner = BackupRunner('sample', cmd='echo command')
        if backup_runner.is_zipped:
            self.assertEqual(backup_runner.zip_manifest, '.gz')
            self.assertIsNotNone(backup_runner.zip_manifest)
            self.assertIsNotNone(backup_runner.zip_cmd)
            self.assertEqual(backup_runner.zip_cmd, ' | gzip')
        else:
            self.assertIsNone(backup_runner.zip_manifest)
            self.assertIsNone(backup_runner.zip_cmd)
        self.assertEqual(backup_runner.backup_type, 'BackupRunner')

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

    def test_execute_bad_process_backup(self):
        agent = backupagent.BackupAgent()
        backup_info = {'id': '123',
                       'location': 'fake-location',
                       'type': 'InnoBackupEx',
                       'checksum': 'fake-checksum',
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

    def test_execute_lossy_backup(self):
        """This test verifies that incomplete writes to swift will fail."""
        with patch.object(MockSwift, 'save',
                          return_value=(False, 'Error', 'y', 'z')):

            agent = backupagent.BackupAgent()

            backup_info = {'id': '123',
                           'location': 'fake-location',
                           'type': 'InnoBackupEx',
                           'checksum': 'fake-checksum',
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
                                      '/var/lib/mysql')

    def test_restore_unknown(self):
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
                              restore_location='/var/lib/mysql')

    def test_backup_incremental_metadata(self):
        with patch.object(backupagent, 'get_storage_strategy',
                          return_value=MockSwift):
            MockStorage.save_metadata = Mock()
            with patch.object(MockSwift, 'load_metadata',
                              return_value={'lsn': '54321'}):
                meta = {
                    'lsn': '12345',
                    'parent_location': 'fake',
                    'parent_checksum': 'md5',
                }

                mysql_impl.InnoBackupExIncremental.metadata = MagicMock(
                    return_value=meta)
                mysql_impl.InnoBackupExIncremental.run = MagicMock(
                    return_value=True)
                mysql_impl.InnoBackupExIncremental.__exit__ = MagicMock(
                    return_value=True)

                agent = backupagent.BackupAgent()

                bkup_info = {'id': '123',
                             'location': 'fake-location',
                             'type': 'InnoBackupEx',
                             'checksum': 'fake-checksum',
                             'parent': {'location': 'fake', 'checksum': 'md5'}
                             }

                agent.execute_backup(TroveContext(),
                                     bkup_info,
                                     '/var/lib/mysql')

                self.assertTrue(MockStorage.save_metadata.called_once_with(
                                ANY,
                                meta))

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
