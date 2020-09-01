# Copyright 2020 Catalyst Cloud
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
import re

from oslo_log import log as logging

from backup import utils
from backup.drivers import base
from backup.utils import postgresql as psql_util

LOG = logging.getLogger(__name__)


class PgBasebackup(base.BaseRunner):
    def __init__(self, *args, **kwargs):
        if not kwargs.get('wal_archive_dir'):
            raise AttributeError('wal_archive_dir attribute missing')
        self.wal_archive_dir = kwargs.pop('wal_archive_dir')
        self.datadir = kwargs.pop(
            'db_datadir', '/var/lib/postgresql/data/pgdata')

        self.label = None
        self.stop_segment = None
        self.start_segment = None
        self.start_wal_file = None
        self.stop_wal_file = None
        self.checkpoint_location = None
        self.metadata = {}

        super(PgBasebackup, self).__init__(*args, **kwargs)

        self.restore_command = (f"{self.decrypt_cmd}tar xzf - -C "
                                f"{self.datadir}")

    @property
    def cmd(self):
        cmd = (f"pg_basebackup -U postgres -Ft -z --wal-method=fetch "
               f"--label={self.filename} --pgdata=-")
        return cmd + self.encrypt_cmd

    @property
    def manifest(self):
        """Target file name."""
        return "%s.tar.gz%s" % (self.filename, self.encrypt_manifest)

    def get_wal_files(self, backup_pos=0):
        """Return the WAL files since the provided last backup.

        pg_archivebackup depends on alphanumeric sorting to decide wal order,
        so we'll do so too:
        https://github.com/postgres/postgres/blob/REL9_4_STABLE/contrib
           /pg_archivecleanup/pg_archivecleanup.c#L122
        """
        backup_file = self.get_backup_file(backup_pos=backup_pos)
        last_wal = backup_file.split('.')[0]
        wal_re = re.compile("^[0-9A-F]{24}$")
        wal_files = [wal_file for wal_file in os.listdir(self.wal_archive_dir)
                     if wal_re.search(wal_file) and wal_file >= last_wal]
        return wal_files

    def get_backup_file(self, backup_pos=0):
        """Look for the most recent .backup file that basebackup creates

        :return: a string like 000000010000000000000006.00000168.backup
        """
        backup_re = re.compile("[0-9A-F]{24}.*.backup")
        wal_files = [wal_file for wal_file in os.listdir(self.wal_archive_dir)
                     if backup_re.search(wal_file)]
        wal_files = sorted(wal_files, reverse=True)
        if not wal_files:
            return None
        return wal_files[backup_pos]

    def get_backup_metadata(self, metadata_file):
        """Parse the contents of the .backup file"""
        metadata = {}

        start_re = re.compile(r"START WAL LOCATION: (.*) \(file (.*)\)")
        stop_re = re.compile(r"STOP WAL LOCATION: (.*) \(file (.*)\)")
        checkpt_re = re.compile("CHECKPOINT LOCATION: (.*)")
        label_re = re.compile("LABEL: (.*)")

        with open(metadata_file, 'r') as file:
            metadata_contents = file.read()

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

    def get_metadata(self):
        """Get metadata.

        pg_basebackup may complete, and we arrive here before the
        history file is written to the wal archive. So we need to
        handle two possibilities:
        - this is the first backup, and no history file exists yet
        - this isn't the first backup, and so the history file we retrieve
        isn't the one we just ran!
         """
        def _metadata_found():
            backup_file = self.get_backup_file()
            if not backup_file:
                return False

            self.metadata = self.get_backup_metadata(
                os.path.join(self.wal_archive_dir, backup_file))
            LOG.info("Metadata for backup: %s.", self.metadata)
            return self.metadata['label'] == self.filename

        try:
            LOG.debug("Polling for backup metadata... ")
            utils.poll_until(_metadata_found, sleep_time=5, time_out=60)
        except Exception as e:
            raise RuntimeError(f"Failed to get backup metadata for backup "
                               f"{self.filename}: {str(e)}")

        return self.metadata

    def check_process(self):
        # If any of the below variables were not set by either metadata()
        # or direct retrieval from the pgsql backup commands, then something
        # has gone wrong
        if not self.start_segment or not self.start_wal_file:
            LOG.error("Unable to determine starting WAL file/segment")
            return False
        if not self.stop_segment or not self.stop_wal_file:
            LOG.error("Unable to determine ending WAL file/segment")
            return False
        if not self.label:
            LOG.error("No backup label found")
            return False
        return True


class PgBasebackupIncremental(PgBasebackup):
    """Incremental backup/restore for PostgreSQL.

    To restore an incremental backup from a previous backup, in PostgreSQL,
    is effectively to replay the WAL entries to a designated point in time.
    All that is required is the most recent base backup, and all WAL files
    """

    def __init__(self, *args, **kwargs):
        self.parent_location = kwargs.pop('parent_location', '')
        self.parent_checksum = kwargs.pop('parent_checksum', '')

        super(PgBasebackupIncremental, self).__init__(*args, **kwargs)

        self.incr_restore_cmd = f'tar -xzf - -C {self.wal_archive_dir}'

    def pre_backup(self):
        with psql_util.PostgresConnection('postgres') as conn:
            self.start_segment = conn.query(
                f"SELECT pg_start_backup('{self.filename}', false, false)"
            )[0][0]
            self.start_wal_file = conn.query(
                f"SELECT pg_walfile_name('{self.start_segment}')")[0][0]
            self.stop_segment = conn.query(
                "SELECT * FROM pg_stop_backup(false, true)")[0][0]

        # We have to hack this because self.command is
        # initialized in the base class before we get here, which is
        # when we will know exactly what WAL files we want to archive
        self.command = self._cmd()

    def _cmd(self):
        wal_file_list = self.get_wal_files(backup_pos=1)
        cmd = (f'tar -czf - -C {self.wal_archive_dir} '
               f'{" ".join(wal_file_list)}')
        return cmd + self.encrypt_cmd

    def get_metadata(self):
        _meta = super(PgBasebackupIncremental, self).get_metadata()
        _meta.update({
            'parent_location': self.parent_location,
            'parent_checksum': self.parent_checksum,
        })
        return _meta

    def incremental_restore_cmd(self, incr=False):
        cmd = self.restore_command
        if incr:
            cmd = self.incr_restore_cmd
        return self.decrypt_cmd + cmd

    def incremental_restore(self, location, checksum):
        """Perform incremental restore.

        For the child backups, restore the wal files to wal archive dir.
        For the base backup, restore to datadir.
        """
        metadata = self.storage.load_metadata(location, checksum)
        if 'parent_location' in metadata:
            LOG.info("Restoring parent: %(parent_location)s, "
                     "checksum: %(parent_checksum)s.", metadata)

            parent_location = metadata['parent_location']
            parent_checksum = metadata['parent_checksum']

            # Restore parents recursively so backup are applied sequentially
            self.incremental_restore(parent_location, parent_checksum)

            command = self.incremental_restore_cmd(incr=True)
        else:
            # For the parent base backup, revert to the default restore cmd
            LOG.info("Restoring back to full backup.")
            command = self.incremental_restore_cmd(incr=False)

        self.restore_content_length += self.unpack(location, checksum, command)

    def run_restore(self):
        """Run incremental restore."""
        LOG.debug('Running incremental restore')
        self.incremental_restore(self.location, self.checksum)
        return self.restore_content_length
