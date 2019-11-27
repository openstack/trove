# Copyright 2019 Catalyst Cloud Ltd.
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

from oslo_log import log as logging

from trove.guestagent.datastore.mysql import service as mysql_service
from trove.guestagent.datastore.mysql_common import service as common_service
from trove.guestagent.strategies.backup import base

LOG = logging.getLogger(__name__)
BACKUP_LOG = '/tmp/mariabackup.log'


class MariaBackup(base.BackupRunner):
    """Implementation of Backup Strategy for mariabackup."""
    __strategy_name__ = 'mariabackup'

    @property
    def user_and_pass(self):
        return (' --user=%(user)s --password=%(password)s --host=127.0.0.1 ' %
                {'user': common_service.ADMIN_USER_NAME,
                 'password': mysql_service.MySqlApp.get_auth_password()})

    @property
    def cmd(self):
        cmd = ('sudo mariabackup --backup --stream=xbstream' +
               self.user_and_pass + ' 2>' + BACKUP_LOG)
        return cmd + self.zip_cmd + self.encrypt_cmd

    def check_process(self):
        """Check the output of mariabackup command for 'completed OK!'.

        Return True if no error, otherwise return False.
        """
        LOG.debug('Checking mariabackup process output.')

        with open(BACKUP_LOG, 'r') as backup_log:
            output = backup_log.read()
            if not output:
                LOG.error("mariabackup log file empty.")
                return False

            LOG.debug(output)

            last_line = output.splitlines()[-1].strip()
            if not re.search('completed OK!', last_line):
                LOG.error("mariabackup command failed.")
                return False

        return True

    @property
    def filename(self):
        return '%s.xbstream' % self.base_filename


class MariaBackupIncremental(MariaBackup):
    pass
