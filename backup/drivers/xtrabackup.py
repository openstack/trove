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
import semantic_version

from backup.drivers import mysql_base

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class XtraBackupException(Exception):
    """Exception class for XtraBackup."""


class XtraBackup(mysql_base.MySQLBaseRunner):
    """Implementation of Backup and Restore for XtraBackup 8.0.

    According to
    https://www.percona.com/doc/percona-xtrabackup/8.0/index.html#user-s-manual,
    Percona XtraBackup 8.0 does not support making backups of databases created
    in versions prior to 8.0 of MySQL.

    Percona XtraBackup 8.0.12 supports backup and restore processing for
    versions of MySQL 8.x.

    innobackupex was removed in Percona XtraBackup 8.0.
    """
    restore_cmd = 'xbstream -x -C %(restore_location)s --parallel=2'
    prepare_cmd = 'xtrabackup --target-dir=%(restore_location)s --prepare'

    def __init__(self, *args, **kwargs):
        super(XtraBackup, self).__init__(*args, **kwargs)
        self.backup_log = '/tmp/xtrabackup.log'
        self._gzip = True

    @property
    def cmd(self):
        cmd = (f'xtrabackup --backup --stream=xbstream --parallel=2 '
               f'--datadir=%(datadir)s --user=%(user)s '
               f'--password=%(password)s --host=%(host)s'
               % {
                   'datadir': self.datadir,
                   'user': CONF.db_user,
                   'password': CONF.db_password,
                   'host': CONF.db_host}
               )
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


class XtraBackupIncremental(XtraBackup):
    """XtraBackup incremental backup."""
    prepare_log = '/tmp/prepare.log'
    incremental_prep = (f'xtrabackup --prepare --apply-log-only'
                        f' --target-dir=%(restore_location)s'
                        f' %(incremental_args)s')

    def __init__(self, *args, **kwargs):
        if not kwargs.get('lsn'):
            raise AttributeError('lsn attribute missing')
        self.parent_location = kwargs.pop('parent_location', '')
        self.parent_checksum = kwargs.pop('parent_checksum', '')

        super(XtraBackupIncremental, self).__init__(*args, **kwargs)

    # NOTE: Since 8.0.27, xtrabackup enables strict mode by default.
    @property
    def add_incremental_opts(self) -> bool:
        cmd = ["xtrabackup", "--version"]
        _, stderr = processutils.execute(*cmd)
        xbackup_version = semantic_version.Version.coerce(
            str(stderr).split()[2])
        strict_mode_version = semantic_version.Version("8.0.27")
        return xbackup_version < strict_mode_version

    @property
    def cmd(self):
        cmd = (f'xtrabackup --backup --stream=xbstream '
               f'--incremental-lsn=%(lsn)s '
               f'--datadir={self.datadir} {self.user_and_pass}')
        if self.add_incremental_opts:
            return '{} --incremental'.format(cmd)
        return cmd

    def get_metadata(self):
        _meta = super(XtraBackupIncremental, self).get_metadata()

        _meta.update({
            'parent_location': self.parent_location,
            'parent_checksum': self.parent_checksum,
        })
        return _meta

    def run_restore(self):
        """Run incremental restore.

        https://www.percona.com/doc/percona-xtrabackup/8.0/backup_scenarios/incremental_backup.html
        """
        LOG.debug('Running incremental restore')
        self.incremental_restore(self.location, self.checksum)
        return self.restore_content_length
