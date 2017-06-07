#    Copyright 2013 Hewlett-Packard Development Company, L.P.
#    Copyright 2014 Mirantis Inc.
#    All Rights Reserved.
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
#

import re

from oslo_log import log as logging

from trove.common.i18n import _
from trove.guestagent.datastore.mysql.service import MySqlApp
from trove.guestagent.datastore.mysql_common.service import ADMIN_USER_NAME
from trove.guestagent.strategies.backup import base

LOG = logging.getLogger(__name__)


class MySQLDump(base.BackupRunner):
    """Implementation of Backup Strategy for MySQLDump."""
    __strategy_name__ = 'mysqldump'

    @property
    def cmd(self):
        user_and_pass = (
            ' --password=%(password)s -u %(user)s '
            '2>/tmp/mysqldump.log' %
            {'password': MySqlApp.get_auth_password(),
             'user': ADMIN_USER_NAME})
        cmd = ('mysqldump'
               ' --all-databases'
               ' %(extra_opts)s'
               ' --opt' + user_and_pass)
        return cmd + self.zip_cmd + self.encrypt_cmd


class InnoBackupEx(base.BackupRunner):
    """Implementation of Backup Strategy for InnoBackupEx."""
    __strategy_name__ = 'innobackupex'

    @property
    def user_and_pass(self):
        return (' --user=%(user)s --password=%(password)s ' %
                {'user': ADMIN_USER_NAME,
                 'password': MySqlApp.get_auth_password()})

    @property
    def cmd(self):
        cmd = ('sudo innobackupex'
               ' --stream=xbstream'
               ' %(extra_opts)s ' +
               self.user_and_pass +
               MySqlApp.get_data_dir() +
               ' 2>/tmp/innobackupex.log'
               )
        return cmd + self.zip_cmd + self.encrypt_cmd

    def check_process(self):
        """Check the output from innobackupex for 'completed OK!'."""
        LOG.debug('Checking innobackupex process output.')
        with open('/tmp/innobackupex.log', 'r') as backup_log:
            output = backup_log.read()
            LOG.info(output)
            if not output:
                LOG.error(_("Innobackupex log file empty."))
                return False
            last_line = output.splitlines()[-1].strip()
            if not re.search('completed OK!', last_line):
                LOG.error(_("Innobackupex did not complete successfully."))
                return False

        return True

    def metadata(self):
        LOG.debug('Getting metadata from backup.')
        meta = {}
        lsn = re.compile("The latest check point \(for incremental\): '(\d+)'")
        with open('/tmp/innobackupex.log', 'r') as backup_log:
            output = backup_log.read()
            match = lsn.search(output)
            if match:
                meta = {'lsn': match.group(1)}
        LOG.info(_("Metadata for backup: %s."), str(meta))
        return meta

    @property
    def filename(self):
        return '%s.xbstream' % self.base_filename


class InnoBackupExIncremental(InnoBackupEx):
    """InnoBackupEx incremental backup."""

    def __init__(self, *args, **kwargs):
        if not kwargs.get('lsn'):
            raise AttributeError(_('lsn attribute missing, bad parent?'))
        super(InnoBackupExIncremental, self).__init__(*args, **kwargs)
        self.parent_location = kwargs.get('parent_location')
        self.parent_checksum = kwargs.get('parent_checksum')

    @property
    def cmd(self):
        cmd = ('sudo innobackupex'
               ' --stream=xbstream'
               ' --incremental'
               ' --incremental-lsn=%(lsn)s'
               ' %(extra_opts)s ' +
               self.user_and_pass +
               MySqlApp.get_data_dir() +
               ' 2>/tmp/innobackupex.log')
        return cmd + self.zip_cmd + self.encrypt_cmd

    def metadata(self):
        _meta = super(InnoBackupExIncremental, self).metadata()
        _meta.update({
            'parent_location': self.parent_location,
            'parent_checksum': self.parent_checksum,
        })
        return _meta
