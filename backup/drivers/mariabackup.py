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

from oslo_config import cfg
from oslo_log import log as logging

from backup.drivers import mysql_base

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class MariaBackup(mysql_base.MySQLBaseRunner):
    """Implementation of Backup and Restore using mariabackup."""
    backup_log = '/tmp/mariabackup.log'
    restore_log = '/tmp/mbstream_extract.log'
    restore_cmd = ('mbstream -x -C %(restore_location)s 2>' + restore_log)
    prepare_cmd = ''

    @property
    def cmd(self):
        cmd = ('mariabackup --backup --stream=xbstream ' +
               self.user_and_pass + ' 2>' + self.backup_log)
        return cmd + self.zip_cmd + self.encrypt_cmd

    def check_restore_process(self):
        LOG.debug('Checking return code of mbstream restore process.')
        return_code = self.process.wait()
        if return_code != 0:
            LOG.error('mbstream exited with %s', return_code)
            return False

        return True


class MariaBackupIncremental(MariaBackup):
    """Incremental backup and restore using mariabackup."""
    incremental_prep = ('mariabackup --prepare '
                        '--target-dir=%(restore_location)s '
                        '%(incremental_args)s '
                        '2>/tmp/innoprepare.log')

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
            self.user_and_pass +
            ' 2>' +
            self.backup_log
        )
        return cmd + self.zip_cmd + self.encrypt_cmd

    def get_metadata(self):
        meta = super(MariaBackupIncremental, self).get_metadata()

        meta.update({
            'parent_location': self.parent_location,
            'parent_checksum': self.parent_checksum,
        })
        return meta

    def run_restore(self):
        """Run incremental restore."""
        LOG.debug('Running incremental restore')
        self.incremental_restore(self.location, self.checksum)
        return self.restore_content_length
