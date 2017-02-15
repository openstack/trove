# Copyright (c) 2013 OpenStack Foundation
# All Rights Reserved.
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
import re
import stat

from oslo_log import log as logging

from trove.common import cfg
from trove.common import exception
from trove.common.i18n import _
from trove.common import utils
from trove.guestagent.common import operating_system
from trove.guestagent.common.operating_system import FileMode
from trove.guestagent.datastore.experimental.postgresql.service import PgSqlApp
from trove.guestagent.strategies.backup import base

CONF = cfg.CONF
LOG = logging.getLogger(__name__)
WAL_ARCHIVE_DIR = CONF.postgresql.wal_archive_location


class PgDump(base.BackupRunner):
    """Implementation of Backup Strategy for pg_dump."""
    __strategy_name__ = 'pg_dump'

    @property
    def cmd(self):
        cmd = 'sudo -u postgres pg_dumpall '
        return cmd + self.zip_cmd + self.encrypt_cmd


class PgBaseBackupUtil(object):

    def most_recent_backup_wal(self, pos=0):
        """
        Return the WAL file for the most recent backup
        """
        mrb_file = self.most_recent_backup_file(pos=pos)
        # just return the first part of the filename
        return mrb_file.split('.')[0]

    def most_recent_backup_file(self, pos=0):
        """
        Look for the most recent .backup file that basebackup creates
        :return: a string like 000000010000000000000006.00000168.backup
        """
        walre = re.compile("[0-9A-F]{24}.*.backup")
        wal_files = [wal_file for wal_file in os.listdir(WAL_ARCHIVE_DIR)
                     if walre.search(wal_file)]
        wal_files = sorted(wal_files, reverse=True)
        if not wal_files:
            return None
        return wal_files[pos]

    def log_files_since_last_backup(self, pos=0):
        """Return the WAL files since the provided last backup
        pg_archivebackup depends on alphanumeric sorting to decide wal order,
        so we'll do so too:
        https://github.com/postgres/postgres/blob/REL9_4_STABLE/contrib
           /pg_archivecleanup/pg_archivecleanup.c#L122
        """
        last_wal = self.most_recent_backup_wal(pos=pos)
        walre = re.compile("^[0-9A-F]{24}$")
        wal_files = [wal_file for wal_file in os.listdir(WAL_ARCHIVE_DIR)
                     if walre.search(wal_file) and wal_file >= last_wal]
        return wal_files


class PgBaseBackup(base.BackupRunner, PgBaseBackupUtil):
    """Base backups are taken with the pg_basebackup filesystem-level backup
     tool pg_basebackup creates a copy of the binary files in the PostgreSQL
     cluster data directory and enough WAL segments to allow the database to
     be brought back to a consistent state. Associated with each backup is a
     log location, normally indicated by the WAL file name and the position
     inside the file.
     """
    __strategy_name__ = 'pg_basebackup'

    def __init__(self, *args, **kwargs):
        self._app = None
        super(PgBaseBackup, self).__init__(*args, **kwargs)
        self.label = None
        self.stop_segment = None
        self.start_segment = None
        self.start_wal_file = None
        self.stop_wal_file = None
        self.checkpoint_location = None
        self.mrb = None

    @property
    def app(self):
        if self._app is None:
            self._app = self._build_app()
        return self._app

    def _build_app(self):
        return PgSqlApp()

    @property
    def cmd(self):
        cmd = ("pg_basebackup -h %s -U %s --pgdata=-"
               " --label=%s --format=tar --xlog " %
               (self.app.pgsql_run_dir, self.app.ADMIN_USER,
                self.base_filename))

        return cmd + self.zip_cmd + self.encrypt_cmd

    def base_backup_metadata(self, metadata_file):
        """Parse the contents of the .backup file"""
        metadata = {}
        operating_system.chmod(
            metadata_file, FileMode(add=[stat.S_IROTH]), as_root=True)

        start_re = re.compile("START WAL LOCATION: (.*) \(file (.*)\)")
        stop_re = re.compile("STOP WAL LOCATION: (.*) \(file (.*)\)")
        checkpt_re = re.compile("CHECKPOINT LOCATION: (.*)")
        label_re = re.compile("LABEL: (.*)")

        metadata_contents = operating_system.read_file(metadata_file)
        match = start_re.search(metadata_contents)
        if match:
            self.start_segment = match.group(1)
            metadata['start-segment'] = self.start_segment
            self.start_wal_file = match.group(2)
            metadata['start-wal-file'] = self.start_wal_file

        match = stop_re.search(metadata_contents)
        if match:
            self.stop_segment = match.group(1)
            metadata['stop-segment'] = self.stop_segment
            self.stop_wal_file = match.group(2)
            metadata['stop-wal-file'] = self.stop_wal_file

        match = checkpt_re.search(metadata_contents)
        if match:
            self.checkpoint_location = match.group(1)
            metadata['checkpoint-location'] = self.checkpoint_location

        match = label_re.search(metadata_contents)
        if match:
            self.label = match.group(1)
            metadata['label'] = self.label
        return metadata

    def check_process(self):
        # If any of the below variables were not set by either metadata()
        # or direct retrieval from the pgsql backup commands, then something
        # has gone wrong
        if not self.start_segment or not self.start_wal_file:
            LOG.info(_("Unable to determine starting WAL file/segment"))
            return False
        if not self.stop_segment or not self.stop_wal_file:
            LOG.info(_("Unable to determine ending WAL file/segment"))
            return False
        if not self.label:
            LOG.info(_("No backup label found"))
            return False
        return True

    def metadata(self):
        """pg_basebackup may complete, and we arrive here before the
        history file is written to the wal archive. So we need to
        handle two possibilities:
        - this is the first backup, and no history file exists yet
        - this isn't the first backup, and so the history file we retrieve
        isn't the one we just ran!
         """
        def _metadata_found():
            LOG.debug("Polling for backup metadata... ")
            self.mrb = self.most_recent_backup_file()
            if not self.mrb:
                LOG.debug("No history files found!")
                return False
            metadata = self.base_backup_metadata(
                os.path.join(WAL_ARCHIVE_DIR, self.mrb))
            LOG.debug("Label to pg_basebackup: %(base_filename)s "
                      "label found: %(label)s",
                      {'base_filename': self.base_filename,
                       'label': metadata['label']})
            LOG.info(_("Metadata for backup: %s."), str(metadata))
            return metadata['label'] == self.base_filename

        try:
            utils.poll_until(_metadata_found, sleep_time=5, time_out=60)
        except exception.PollTimeOut:
            raise RuntimeError(_("Timeout waiting for backup metadata for"
                                 " backup %s") % self.base_filename)

        return self.base_backup_metadata(
            os.path.join(WAL_ARCHIVE_DIR, self.mrb))

    def _run_post_backup(self):
        """Get rid of WAL data we don't need any longer"""
        arch_cleanup_bin = os.path.join(self.app.pgsql_extra_bin_dir,
                                        "pg_archivecleanup")
        bk_file = os.path.basename(self.most_recent_backup_file())
        cmd_full = " ".join((arch_cleanup_bin, WAL_ARCHIVE_DIR, bk_file))
        utils.execute("sudo", "su", "-", self.app.pgsql_owner, "-c",
                      "%s" % cmd_full)


class PgBaseBackupIncremental(PgBaseBackup):
    """To restore an incremental backup from a previous backup, in PostgreSQL,
       is effectively to replay the WAL entries to a designated point in time.
       All that is required is the most recent base backup, and all WAL files
     """

    def __init__(self, *args, **kwargs):
        if (not kwargs.get('parent_location') or
                not kwargs.get('parent_checksum')):
            raise AttributeError(_('Parent missing!'))

        super(PgBaseBackupIncremental, self).__init__(*args, **kwargs)
        self.parent_location = kwargs.get('parent_location')
        self.parent_checksum = kwargs.get('parent_checksum')

    def _run_pre_backup(self):
        self.backup_label = self.base_filename
        self.start_segment = self.app.pg_start_backup(self.backup_label)

        self.start_wal_file = self.app.pg_xlogfile_name(self.start_segment)

        self.stop_segment = self.app.pg_stop_backup()

        # We have to hack this because self.command is
        # initialized in the base class before we get here, which is
        # when we will know exactly what WAL files we want to archive
        self.command = self._cmd()

    def _cmd(self):
        wal_file_list = self.log_files_since_last_backup(pos=1)
        cmd = 'sudo tar -cf - -C {wal_dir} {wal_list} '.format(
            wal_dir=WAL_ARCHIVE_DIR,
            wal_list=" ".join(wal_file_list))
        return cmd + self.zip_cmd + self.encrypt_cmd

    def metadata(self):
        _meta = super(PgBaseBackupIncremental, self).metadata()
        _meta.update({
            'parent_location': self.parent_location,
            'parent_checksum': self.parent_checksum,
        })
        return _meta
