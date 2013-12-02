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

import trove.guestagent.strategies.backup.base as backupBase
import trove.guestagent.strategies.restore.base as restoreBase
import testtools
from trove.common import utils

BACKUP_XTRA_CLS = ("trove.guestagent.strategies.backup."
                   "mysql_impl.InnoBackupEx")
RESTORE_XTRA_CLS = ("trove.guestagent.strategies.restore."
                    "mysql_impl.InnoBackupEx")
BACKUP_XTRA_INCR_CLS = ("trove.guestagent.strategies.backup."
                        "mysql_impl.InnoBackupExIncremental")
RESTORE_XTRA_INCR_CLS = ("trove.guestagent.strategies.restore."
                         "mysql_impl.InnoBackupExIncremental")
BACKUP_SQLDUMP_CLS = ("trove.guestagent.strategies.backup."
                      "mysql_impl.MySQLDump")
RESTORE_SQLDUMP_CLS = ("trove.guestagent.strategies.restore."
                       "mysql_impl.MySQLDump")
PIPE = " | "
ZIP = "gzip"
UNZIP = "gzip -d -c"
ENCRYPT = "openssl enc -aes-256-cbc -salt -pass pass:default_aes_cbc_key"
DECRYPT = "openssl enc -d -aes-256-cbc -salt -pass pass:default_aes_cbc_key"
XTRA_BACKUP_RAW = ("sudo innobackupex --stream=xbstream %(extra_opts)s"
                   " /var/lib/mysql 2>/tmp/innobackupex.log")
XTRA_BACKUP = XTRA_BACKUP_RAW % {'extra_opts': ''}
XTRA_BACKUP_EXTRA_OPTS = XTRA_BACKUP_RAW % {'extra_opts': '--no-lock'}
XTRA_BACKUP_INCR = ('sudo innobackupex --stream=xbstream'
                    ' --incremental --incremental-lsn=%(lsn)s'
                    ' %(extra_opts)s /var/lib/mysql 2>/tmp/innobackupex.log')
SQLDUMP_BACKUP_RAW = ("mysqldump --all-databases %(extra_opts)s "
                      "--opt --password=password -u user"
                      " 2>/tmp/mysqldump.log")
SQLDUMP_BACKUP = SQLDUMP_BACKUP_RAW % {'extra_opts': ''}
SQLDUMP_BACKUP_EXTRA_OPTS = (SQLDUMP_BACKUP_RAW %
                             {'extra_opts': '--events --routines --triggers'})
XTRA_RESTORE_RAW = "sudo xbstream -x -C %(restore_location)s"
XTRA_RESTORE = XTRA_RESTORE_RAW % {'restore_location': '/var/lib/mysql'}
XTRA_INCR_PREPARE = ("sudo innobackupex --apply-log"
                     " --redo-only /var/lib/mysql"
                     " --defaults-file=/var/lib/mysql/backup-my.cnf"
                     " --ibbackup xtrabackup %(incr)s"
                     " 2>/tmp/innoprepare.log")
SQLDUMP_RESTORE = "sudo mysql"
PREPARE = ("sudo innobackupex --apply-log /var/lib/mysql "
           "--defaults-file=/var/lib/mysql/backup-my.cnf "
           "--ibbackup xtrabackup 2>/tmp/innoprepare.log")
CRYPTO_KEY = "default_aes_cbc_key"


class GuestAgentBackupTest(testtools.TestCase):
    def test_backup_decrypted_xtrabackup_command(self):
        backupBase.BackupRunner.is_zipped = True
        backupBase.BackupRunner.is_encrypted = False
        RunnerClass = utils.import_class(BACKUP_XTRA_CLS)
        bkup = RunnerClass(12345, user="user",
                           password="password", extra_opts="")
        self.assertEqual(bkup.command, XTRA_BACKUP + PIPE + ZIP)
        self.assertEqual(bkup.manifest, "12345.xbstream.gz")

    def test_backup_decrypted_xtrabackup_with_extra_opts_command(self):
        backupBase.BackupRunner.is_zipped = True
        backupBase.BackupRunner.is_encrypted = False
        RunnerClass = utils.import_class(BACKUP_XTRA_CLS)
        bkup = RunnerClass(12345, user="user",
                           password="password", extra_opts="--no-lock")
        self.assertEqual(bkup.command, XTRA_BACKUP_EXTRA_OPTS + PIPE + ZIP)
        self.assertEqual(bkup.manifest, "12345.xbstream.gz")

    def test_backup_encrypted_xtrabackup_command(self):
        backupBase.BackupRunner.is_zipped = True
        backupBase.BackupRunner.is_encrypted = True
        backupBase.BackupRunner.encrypt_key = CRYPTO_KEY
        RunnerClass = utils.import_class(BACKUP_XTRA_CLS)
        bkup = RunnerClass(12345, user="user",
                           password="password", extra_opts="")
        self.assertEqual(bkup.command,
                         XTRA_BACKUP + PIPE + ZIP + PIPE + ENCRYPT)
        self.assertEqual(bkup.manifest, "12345.xbstream.gz.enc")

    def test_backup_xtrabackup_incremental(self):
        backupBase.BackupRunner.is_zipped = True
        backupBase.BackupRunner.is_encrypted = False
        RunnerClass = utils.import_class(BACKUP_XTRA_INCR_CLS)
        opts = {'lsn': '54321', 'extra_opts': ''}

        expected = (XTRA_BACKUP_INCR % opts) + PIPE + ZIP

        bkup = RunnerClass(12345, user="user", password="password",
                           extra_opts="", lsn="54321")
        self.assertEqual(expected, bkup.command)
        self.assertEqual("12345.xbstream.gz", bkup.manifest)

    def test_backup_xtrabackup_incremental_with_extra_opts_command(self):
        backupBase.BackupRunner.is_zipped = True
        backupBase.BackupRunner.is_encrypted = False
        RunnerClass = utils.import_class(BACKUP_XTRA_INCR_CLS)
        opts = {'lsn': '54321', 'extra_opts': '--no-lock'}

        expected = (XTRA_BACKUP_INCR % opts) + PIPE + ZIP

        bkup = RunnerClass(12345, user="user", password="password",
                           extra_opts="--no-lock", lsn="54321")
        self.assertEqual(expected, bkup.command)
        self.assertEqual("12345.xbstream.gz", bkup.manifest)

    def test_backup_xtrabackup_incremental_encrypted(self):
        backupBase.BackupRunner.is_zipped = True
        backupBase.BackupRunner.is_encrypted = True
        backupBase.BackupRunner.encrypt_key = CRYPTO_KEY
        RunnerClass = utils.import_class(BACKUP_XTRA_INCR_CLS)
        opts = {'lsn': '54321', 'extra_opts': ''}

        expected = (XTRA_BACKUP_INCR % opts) + PIPE + ZIP + PIPE + ENCRYPT

        bkup = RunnerClass(12345, user="user", password="password",
                           extra_opts="", lsn="54321")

        self.assertEqual(expected, bkup.command)
        self.assertEqual("12345.xbstream.gz.enc", bkup.manifest)

    def test_backup_decrypted_mysqldump_command(self):
        backupBase.BackupRunner.is_zipped = True
        backupBase.BackupRunner.is_encrypted = False
        RunnerClass = utils.import_class(BACKUP_SQLDUMP_CLS)
        bkup = RunnerClass(12345, user="user",
                           password="password", extra_opts="")
        self.assertEqual(bkup.command, SQLDUMP_BACKUP + PIPE + ZIP)
        self.assertEqual(bkup.manifest, "12345.gz")

    def test_backup_decrypted_mysqldump_with_extra_opts_command(self):
        backupBase.BackupRunner.is_zipped = True
        backupBase.BackupRunner.is_encrypted = False
        RunnerClass = utils.import_class(BACKUP_SQLDUMP_CLS)
        bkup = RunnerClass(12345, user="user",
                           password="password",
                           extra_opts="--events --routines --triggers")
        self.assertEqual(bkup.command, SQLDUMP_BACKUP_EXTRA_OPTS + PIPE + ZIP)
        self.assertEqual(bkup.manifest, "12345.gz")

    def test_backup_encrypted_mysqldump_command(self):
        backupBase.BackupRunner.is_zipped = True
        backupBase.BackupRunner.is_encrypted = True
        backupBase.BackupRunner.encrypt_key = CRYPTO_KEY
        RunnerClass = utils.import_class(BACKUP_SQLDUMP_CLS)
        bkup = RunnerClass(12345, user="user",
                           password="password", extra_opts="")
        self.assertEqual(bkup.command,
                         SQLDUMP_BACKUP + PIPE + ZIP + PIPE + ENCRYPT)
        self.assertEqual(bkup.manifest, "12345.gz.enc")

    def test_restore_decrypted_xtrabackup_command(self):
        restoreBase.RestoreRunner.is_zipped = True
        restoreBase.RestoreRunner.is_encrypted = False
        RunnerClass = utils.import_class(RESTORE_XTRA_CLS)
        restr = RunnerClass(None, restore_location="/var/lib/mysql",
                            location="filename", checksum="md5")
        self.assertEqual(restr.restore_cmd, UNZIP + PIPE + XTRA_RESTORE)
        self.assertEqual(restr.prepare_cmd, PREPARE)

    def test_restore_encrypted_xtrabackup_command(self):
        restoreBase.RestoreRunner.is_zipped = True
        restoreBase.RestoreRunner.is_encrypted = True
        restoreBase.RestoreRunner.decrypt_key = CRYPTO_KEY
        RunnerClass = utils.import_class(RESTORE_XTRA_CLS)
        restr = RunnerClass(None, restore_location="/var/lib/mysql",
                            location="filename", checksum="md5")
        self.assertEqual(restr.restore_cmd,
                         DECRYPT + PIPE + UNZIP + PIPE + XTRA_RESTORE)
        self.assertEqual(restr.prepare_cmd, PREPARE)

    def test_restore_xtrabackup_incremental_prepare_command(self):
        RunnerClass = utils.import_class(RESTORE_XTRA_INCR_CLS)
        restr = RunnerClass(None, restore_location="/var/lib/mysql",
                            location="filename", checksum="m5d")
        # Final prepare command (same as normal xtrabackup)
        self.assertEqual(PREPARE, restr.prepare_cmd)
        # Incremental backup prepare command
        expected = XTRA_INCR_PREPARE % {'incr': '--incremental-dir=/foo/bar/'}
        observed = restr._incremental_prepare_cmd('/foo/bar/')
        self.assertEqual(expected, observed)
        # Full backup prepare command
        expected = XTRA_INCR_PREPARE % {'incr': ''}
        observed = restr._incremental_prepare_cmd(None)
        self.assertEqual(expected, observed)

    def test_restore_decrypted_xtrabackup_incremental_command(self):
        restoreBase.RestoreRunner.is_zipped = True
        restoreBase.RestoreRunner.is_encrypted = False
        RunnerClass = utils.import_class(RESTORE_XTRA_INCR_CLS)
        restr = RunnerClass(None, restore_location="/var/lib/mysql",
                            location="filename", checksum="m5d")
        # Full restore command
        expected = UNZIP + PIPE + XTRA_RESTORE
        self.assertEqual(expected, restr.restore_cmd)
        # Incremental backup restore command
        opts = {'restore_location': '/foo/bar/'}
        expected = UNZIP + PIPE + (XTRA_RESTORE_RAW % opts)
        observed = restr._incremental_restore_cmd('/foo/bar/')
        self.assertEqual(expected, observed)

    def test_restore_encrypted_xtrabackup_incremental_command(self):
        restoreBase.RestoreRunner.is_zipped = True
        restoreBase.RestoreRunner.is_encrypted = True
        restoreBase.RestoreRunner.decrypt_key = CRYPTO_KEY
        RunnerClass = utils.import_class(RESTORE_XTRA_INCR_CLS)
        restr = RunnerClass(None, restore_location="/var/lib/mysql",
                            location="filename", checksum="md5")
        # Full restore command
        expected = DECRYPT + PIPE + UNZIP + PIPE + XTRA_RESTORE
        self.assertEqual(expected, restr.restore_cmd)
        # Incremental backup restore command
        opts = {'restore_location': '/foo/bar/'}
        expected = DECRYPT + PIPE + UNZIP + PIPE + (XTRA_RESTORE_RAW % opts)
        observed = restr._incremental_restore_cmd('/foo/bar/')
        self.assertEqual(expected, observed)

    def test_restore_decrypted_mysqldump_command(self):
        restoreBase.RestoreRunner.is_zipped = True
        restoreBase.RestoreRunner.is_encrypted = False
        RunnerClass = utils.import_class(RESTORE_SQLDUMP_CLS)
        restr = RunnerClass(None, restore_location="/var/lib/mysql",
                            location="filename", checksum="md5",
                            user="user", password="password")
        self.assertEqual(restr.restore_cmd, UNZIP + PIPE + SQLDUMP_RESTORE)

    def test_restore_encrypted_mysqldump_command(self):
        restoreBase.RestoreRunner.is_zipped = True
        restoreBase.RestoreRunner.is_encrypted = True
        restoreBase.RestoreRunner.decrypt_key = CRYPTO_KEY
        RunnerClass = utils.import_class(RESTORE_SQLDUMP_CLS)
        restr = RunnerClass(None, restore_location="/var/lib/mysql",
                            location="filename", checksum="md5",
                            user="user", password="password")
        self.assertEqual(restr.restore_cmd,
                         DECRYPT + PIPE + UNZIP + PIPE + SQLDUMP_RESTORE)
