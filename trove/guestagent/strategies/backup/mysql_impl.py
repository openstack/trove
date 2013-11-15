# Copyright 2013 Hewlett-Packard Development Company, L.P.
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
#

import re

from trove.guestagent.strategies.backup import base
from trove.openstack.common import log as logging

LOG = logging.getLogger(__name__)


class MySQLDump(base.BackupRunner):
    """Implementation of Backup Strategy for MySQLDump """
    __strategy_name__ = 'mysqldump'

    @property
    def cmd(self):
        cmd = ('mysqldump'
               ' --all-databases'
               ' %(extra_opts)s'
               ' --opt'
               ' --password=%(password)s'
               ' -u %(user)s'
               ' 2>/tmp/mysqldump.log')
        return cmd + self.zip_cmd + self.encrypt_cmd


class InnoBackupEx(base.BackupRunner):
    """Implementation of Backup Strategy for InnoBackupEx """
    __strategy_name__ = 'innobackupex'

    @property
    def cmd(self):
        cmd = ('sudo innobackupex'
               ' --stream=xbstream'
               ' %(extra_opts)s'
               ' /var/lib/mysql 2>/tmp/innobackupex.log'
               )
        return cmd + self.zip_cmd + self.encrypt_cmd

    def check_process(self):
        """Check the output from innobackupex for 'completed OK!'"""
        LOG.debug('Checking innobackupex process output')
        with open('/tmp/innobackupex.log', 'r') as backup_log:
            output = backup_log.read()
            LOG.info(output)
            if not output:
                LOG.error("Innobackupex log file empty")
                return False
            last_line = output.splitlines()[-1].strip()
            if not re.search('completed OK!', last_line):
                LOG.error("Innobackupex did not complete successfully")
                return False

        return True

    @property
    def filename(self):
        return '%s.xbstream' % self.base_filename
