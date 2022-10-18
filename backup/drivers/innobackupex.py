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


class InnoBackupEx(mysql_base.MySQLBaseRunner):
    """Implementation of Backup and Restore for InnoBackupEx."""
    restore_cmd = ('xbstream -x -C %(restore_location)s --parallel=2')
    prepare_cmd = ('innobackupex'
                   ' --defaults-file=%(restore_location)s/backup-my.cnf'
                   ' --ibbackup=xtrabackup'
                   ' --apply-log'
                   ' %(restore_location)s')

    def __init__(self, *args, **kwargs):
        super(InnoBackupEx, self).__init__(*args, **kwargs)
        self.backup_log = '/tmp/innobackupex.log'
        self._gzip = True

    @property
    def cmd(self):
        cmd = ('innobackupex'
               ' --stream=xbstream'
               ' --parallel=2 ' +
               self.user_and_pass + ' %s' % self.datadir)
        return cmd

    def check_restore_process(self):
        """Check whether xbstream restore is successful."""
        LOG.info('Checking return code of xbstream restore process.')
        return_code = self.process.returncode
        if return_code != 0:
            LOG.error('xbstream exited with %s', return_code)
            return False
        return True

    def post_restore(self):
        """Hook that is called after the restore command."""
        LOG.info("Running innobackupex prepare: %s.", self.prepare_command)
        stdout, stderr = processutils.execute(*self.prepare_command.split())
        LOG.info("the prepare command stdout: %s, stderr: %s", stdout, stderr)
        if not stderr:
            msg = "innobackupex prepare log file empty"
            raise Exception(msg)

        last_line = stderr.splitlines()[-1].strip()
        if not re.search('completed OK!', last_line):
            msg = "innobackupex prepare did not complete successfully"
            raise Exception(msg)


class InnoBackupExIncremental(InnoBackupEx):
    """InnoBackupEx incremental backup."""

    incremental_prep = ('innobackupex'
                        ' --defaults-file=%(restore_location)s/backup-my.cnf'
                        ' --ibbackup=xtrabackup'
                        ' --apply-log'
                        ' --redo-only'
                        ' %(restore_location)s'
                        ' %(incremental_args)s')

    def __init__(self, *args, **kwargs):
        if not kwargs.get('lsn'):
            raise AttributeError('lsn attribute missing')
        self.parent_location = kwargs.pop('parent_location', '')
        self.parent_checksum = kwargs.pop('parent_checksum', '')

        super(InnoBackupExIncremental, self).__init__(*args, **kwargs)

    @property
    def cmd(self):
        cmd = ('innobackupex'
               ' --stream=xbstream'
               ' --incremental'
               ' --incremental-lsn=%(lsn)s ' +
               self.user_and_pass + ' %s' % self.datadir)
        return cmd

    def get_metadata(self):
        _meta = super(InnoBackupExIncremental, self).get_metadata()

        _meta.update({
            'parent_location': self.parent_location,
            'parent_checksum': self.parent_checksum,
        })
        return _meta

    def run_restore(self):
        """Run incremental restore.

        First grab all parents and prepare them with '--redo-only'. After
        all backups are restored the super class InnoBackupEx post_restore
        method is called to do the final prepare with '--apply-log'
        """
        LOG.debug('Running incremental restore')
        self.incremental_restore(self.location, self.checksum)
        return self.restore_content_length
