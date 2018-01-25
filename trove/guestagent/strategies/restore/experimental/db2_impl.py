# Copyright 2016 IBM Corp
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from oslo_log import log as logging

from trove.common import exception
from trove.common import utils
from trove.guestagent.datastore.experimental.db2 import service
from trove.guestagent.datastore.experimental.db2 import system
from trove.guestagent.strategies.restore import base

LOG = logging.getLogger(__name__)


class DB2Backup(base.RestoreRunner):
    """
    Base class implementation of Restore strategy for DB2
    """
    base_restore_cmd = 'sudo tar xPf -'

    def __init__(self, *args, **kwargs):
        super(DB2Backup, self).__init__(*args, **kwargs)
        self.appStatus = service.DB2AppStatus()
        self.app = service.DB2App(self.appStatus)
        self.admin = service.DB2Admin()
        self.restore_location = system.DB2_BACKUP_DIR

    def _post_restore(self, restore_command, rollforward_command=None):
        """
        Restore from the directory that we untarred into
        """
        out = ""
        try:
            out, err = utils.execute_with_timeout(system.GET_DB_NAMES,
                                                  shell=True)
        except exception.ProcessExecutionError:
            LOG.exception("Couldn't find any databases.")

        dbNames = out.split()
        for dbName in dbNames:
            service.run_command(restore_command % {'dbname': dbName})
            if rollforward_command:
                service.run_command(system.ROLL_FORWARD_DB % {'dbname':
                                                              dbName})

        LOG.info("Cleaning out restore location: %s.",
                 system.DB2_BACKUP_DIR)
        service.remove_db2_dir(system.DB2_BACKUP_DIR)


class DB2OfflineBackup(DB2Backup):
    """
    Implementation of Restore Strategy for full offline backups
    using the default circular logging
    """
    __strategy_name__ = 'db2offlinebackup'

    def post_restore(self):
        self._post_restore(system.RESTORE_OFFLINE_DB)


class DB2OnlineBackup(DB2Backup):
    """
    Implementation of restore strategy for full online backups using
    archived logging.
    """
    __strategy_name__ = 'db2onlinebackup'

    def post_restore(self):
        """
        Once the databases are restored from a backup, we have to roll
        forward the logs to the point of where the backup was taken. This
        brings the database to a state were it can used, otherwise it
        remains in a BACKUP PENDING state. After roll forwarding the logs,
        we can delete the archived logs.
        """
        self._post_restore(system.RESTORE_ONLINE_DB, system.ROLL_FORWARD_DB)
        service.remove_db2_dir(system.DB2_ARCHIVE_LOGS_DIR + '/*')
