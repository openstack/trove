# Copyright 2026 PS Cloud Services
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

from backup.drivers import base
from oslo_log import log as logging

LOG = logging.getLogger(__name__)


class RedisBaseBackup(base.BaseRunner):
    DATASTORE_NAME = 'redis'
    """Backup/restore for Redis-based datastores.

    Backuping Redis-based datastores is a very simple process.
    We need to run SAVE or BGSAVE command and copy dump.rdb and config files.
    """

    """Implementation of Backup and Restore using tar command."""
    cmd = 'tar -cO %(restore_location)s'
    restore_cmd = 'tar xf - -C /'

    def __init__(self, *args, **kwargs):
        self.datadir = kwargs.pop(
            'db_datadir', f'/var/lib/{self.DATASTORE_NAME}')
        LOG.info("Datadir: %s", self.datadir)
        self.backup_log = '%s/backup.log' % (self.datadir)
        super(RedisBaseBackup, self).__init__(*args, **kwargs)

    def pre_backup(self):
        self._gzip = True

    def run_restore(self):
        self._gzip = True
        return self.unpack(self.location, self.checksum, self.restore_command)
