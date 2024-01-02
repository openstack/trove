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
import re

from oslo_concurrency import processutils
from oslo_config import cfg
from oslo_log import log as logging

from backup.drivers import mysql_base

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class MariaBackup(mysql_base.MySQLBaseRunner):
    """Implementation of Backup and Restore using mariabackup."""
    restore_cmd = ('mbstream -x -C %(restore_location)s')
    prepare_cmd = 'mariabackup --prepare --target--dir=%(restore_location)s'

    def __init__(self, *args, **kwargs):
        super(MariaBackup, self).__init__(*args, **kwargs)
        self.backup_log = '/tmp/mariabackup.log'
        self._gzip = True

    @property
    def cmd(self):
        cmd = ('mariabackup --backup --stream=xbstream ' +
               self.user_and_pass)
        return cmd

    def check_restore_process(self):
        LOG.info('Checking return code of mbstream restore process.')
        return_code = self.process.returncode
        if return_code != 0:
            LOG.error('mbstream exited with %s', return_code)
            return False

        return True

    def post_restore(self):
        """Prepare after data restore."""
        LOG.info("Running prepare command: %s.", self.prepare_command)
        stdout, stderr = processutils.execute(*self.prepare_command.split())
        LOG.info("The command: %s : stdout: %s, stderr: %s",
                 self.prepare_command, stdout, stderr)
        LOG.info("Checking prepare log")
        if not stderr:
            msg = "Empty prepare log file"
            raise Exception(msg)
        last_line = stderr.splitlines()[-1].strip()
        if not re.search('completed OK!', last_line):
            msg = "Prepare did not complete successfully"
            raise Exception(msg)


class MariaBackupIncremental(MariaBackup):
    """Incremental backup and restore using mariabackup."""
    incremental_prep = ('mariabackup --prepare '
                        '--target-dir=%(restore_location)s '
                        '%(incremental_args)s')

    def __init__(self, *args, **kwargs):
        if not kwargs.get('lsn'):
            raise AttributeError('lsn attribute missing')
        self.parent_location = kwargs.pop('parent_location', '')
        self.parent_checksum = kwargs.pop('parent_checksum', '')

        super(MariaBackupIncremental, self).__init__(*args, **kwargs)

    @property
    def cmd(self):
        cmd = (
            'mariabackup --backup --stream=xbstream'
            ' --incremental-lsn=%(lsn)s ' +
            self.user_and_pass
        )
        LOG.info('cmd:{}'.format(cmd))
        return cmd

    def get_metadata(self):
        meta = super(MariaBackupIncremental, self).get_metadata()

        meta.update({
            'parent_location': self.parent_location,
            'parent_checksum': self.parent_checksum,
        })
        return meta

    def run_restore(self):
        """Run incremental restore."""
        LOG.info('Running incremental restore')
        self.incremental_restore(self.location, self.checksum)
        return self.restore_content_length
