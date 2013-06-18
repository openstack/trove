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
#    under the License

import reddwarf.guestagent.strategies.backup.base as backupBase
import reddwarf.guestagent.strategies.restore.base as restoreBase
import testtools
from reddwarf.common import utils

BACKUP_XTRA_CLS = "reddwarf.guestagent.strategies.backup.impl.InnoBackupEx"
RESTORE_XTRA_CLS = "reddwarf.guestagent.strategies.restore.impl.InnoBackupEx"
BACKUP_SQLDUMP_CLS = "reddwarf.guestagent.strategies.backup.impl.MySQLDump"
RESTORE_SQLDUMP_CLS = "reddwarf.guestagent.strategies.restore.impl.MySQLDump"
PIPE = " | "
ZIP = "gzip"
UNZIP = "gzip -d -c"
ENCRYPT = "openssl enc -aes-256-cbc -salt -pass pass:default_aes_cbc_key"
DECRYPT = "openssl enc -d -aes-256-cbc -salt -pass pass:default_aes_cbc_key"
XTRA_BACKUP = "sudo innobackupex --stream=xbstream /var/lib/mysql 2>/" \
              "tmp/innobackupex.log"
SQLDUMP_BACKUP = "/usr/bin/mysqldump --all-databases --opt " \
                 "--password=password -u user"
XTRA_RESTORE = "sudo xbstream -x -C /var/lib/mysql"
SQLDUMP_RESTORE = "mysql --password=password -u user"
PREPARE = "sudo innobackupex --apply-log /var/lib/mysql " \
          "--defaults-file=/var/lib/mysql/backup-my.cnf " \
          "--ibbackup xtrabackup 2>/tmp/innoprepare.log"
CRYPTO_KEY = "default_aes_cbc_key"


class GuestAgentBackupTest(testtools.TestCase):
    def test_backup_decrypted_xtrabackup_command(self):
        backupBase.BackupRunner.is_zipped = True
        backupBase.BackupRunner.is_encrypted = False
        RunnerClass = utils.import_class(BACKUP_XTRA_CLS)
        bkup = RunnerClass(12345, user="user", password="password")
        self.assertEqual(bkup.command, XTRA_BACKUP + PIPE + ZIP)
        self.assertEqual(bkup.manifest, "12345.xbstream.gz")

    def test_backup_encrypted_xtrabackup_command(self):
        backupBase.BackupRunner.is_zipped = True
        backupBase.BackupRunner.is_encrypted = True
        backupBase.BackupRunner.encrypt_key = CRYPTO_KEY
        RunnerClass = utils.import_class(BACKUP_XTRA_CLS)
        bkup = RunnerClass(12345, user="user", password="password")
        self.assertEqual(bkup.command,
                         XTRA_BACKUP + PIPE + ZIP + PIPE + ENCRYPT)
        self.assertEqual(bkup.manifest, "12345.xbstream.gz.enc")

    def test_backup_decrypted_mysqldump_command(self):
        backupBase.BackupRunner.is_zipped = True
        backupBase.BackupRunner.is_encrypted = False
        RunnerClass = utils.import_class(BACKUP_SQLDUMP_CLS)
        bkup = RunnerClass(12345, user="user", password="password")
        self.assertEqual(bkup.command, SQLDUMP_BACKUP + PIPE + ZIP)
        self.assertEqual(bkup.manifest, "12345.gz")

    def test_backup_encrypted_mysqldump_command(self):
        backupBase.BackupRunner.is_zipped = True
        backupBase.BackupRunner.is_encrypted = True
        backupBase.BackupRunner.encrypt_key = CRYPTO_KEY
        RunnerClass = utils.import_class(BACKUP_SQLDUMP_CLS)
        bkup = RunnerClass(12345, user="user", password="password")
        self.assertEqual(bkup.command,
                         SQLDUMP_BACKUP + PIPE + ZIP + PIPE + ENCRYPT)
        self.assertEqual(bkup.manifest, "12345.gz.enc")

    def test_restore_decrypted_xtrabackup_command(self):
        restoreBase.RestoreRunner.is_zipped = True
        restoreBase.RestoreRunner.is_encrypted = False
        RunnerClass = utils.import_class(RESTORE_XTRA_CLS)
        restr = RunnerClass(None, restore_location="/var/lib/mysql")
        self.assertEqual(restr.restore_cmd, UNZIP + PIPE + XTRA_RESTORE)
        self.assertEqual(restr.prepare_cmd, PREPARE)

    def test_restore_encrypted_xtrabackup_command(self):
        restoreBase.RestoreRunner.is_zipped = True
        restoreBase.RestoreRunner.is_encrypted = True
        restoreBase.RestoreRunner.decrypt_key = CRYPTO_KEY
        RunnerClass = utils.import_class(RESTORE_XTRA_CLS)
        restr = RunnerClass(None, restore_location="/var/lib/mysql")
        self.assertEqual(restr.restore_cmd,
                         DECRYPT + PIPE + UNZIP + PIPE + XTRA_RESTORE)
        self.assertEqual(restr.prepare_cmd, PREPARE)

    def test_restore_decrypted_mysqldump_command(self):
        restoreBase.RestoreRunner.is_zipped = True
        restoreBase.RestoreRunner.is_encrypted = False
        RunnerClass = utils.import_class(RESTORE_SQLDUMP_CLS)
        restr = RunnerClass(None, restore_location="/var/lib/mysql",
                            user="user", password="password")
        self.assertEqual(restr.restore_cmd, UNZIP + PIPE + SQLDUMP_RESTORE)
        self.assertIsNone(restr.prepare_cmd)

    def test_restore_encrypted_mysqldump_command(self):
        restoreBase.RestoreRunner.is_zipped = True
        restoreBase.RestoreRunner.is_encrypted = True
        restoreBase.RestoreRunner.decrypt_key = CRYPTO_KEY
        RunnerClass = utils.import_class(RESTORE_SQLDUMP_CLS)
        restr = RunnerClass(None, restore_location="/var/lib/mysql",
                            user="user", password="password")
        self.assertEqual(restr.restore_cmd,
                         DECRYPT + PIPE + UNZIP + PIPE + SQLDUMP_RESTORE)
        self.assertIsNone(restr.prepare_cmd)
