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

from trove.guestagent.strategies.backup import base
from trove.openstack.common import log as logging


LOG = logging.getLogger(__name__)


class MySQLDump(base.BackupRunner):
    """ Implementation of Backup Strategy for MySQLDump """
    __strategy_name__ = 'mysqldump'

    @property
    def cmd(self):
        cmd = '/usr/bin/mysqldump'\
            ' --all-databases'\
            ' --opt'\
            ' --password=%(password)s'\
            ' -u %(user)s'
        return cmd + self.zip_cmd + self.encrypt_cmd

    @property
    def manifest(self):
        manifest = '%s' % self.filename
        return manifest + self.zip_manifest + self.encrypt_manifest


class InnoBackupEx(base.BackupRunner):
    """ Implementation of Backup Strategy for InnoBackupEx """
    __strategy_name__ = 'innobackupex'

    @property
    def cmd(self):
        cmd = 'sudo innobackupex'\
            ' --stream=xbstream'\
            ' /var/lib/mysql 2>/tmp/innobackupex.log'
        return cmd + self.zip_cmd + self.encrypt_cmd

    @property
    def manifest(self):
        manifest = '%s.xbstream' % self.filename
        return manifest + self.zip_manifest + self.encrypt_manifest
