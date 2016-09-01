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
from trove.common.i18n import _
from trove.common import utils
from trove.guestagent.common import operating_system
from trove.guestagent.datastore.experimental.db2 import service
from trove.guestagent.datastore.experimental.db2 import system
from trove.guestagent.db import models
from trove.guestagent.strategies.backup import base

LOG = logging.getLogger(__name__)


class DB2Backup(base.BackupRunner):
    """
     Base class for DB2 backups
    """
    def __init__(self, *args, **kwargs):
        super(DB2Backup, self).__init__(*args, **kwargs)
        self.admin = service.DB2Admin()
        self.databases = self.list_dbnames()

    def list_dbnames(self):
        dbNames = []
        databases, marker = self.admin.list_databases()
        for database in databases:
            mydb = models.MySQLDatabase()
            mydb.deserialize(database)
            dbNames.append(mydb.name)
        return dbNames

    def estimate_backup_size(self):
        """
           Estimating the size of the backup based on the size of the data
           returned from the get_db_size procedure. The size of the
           backup is always going to be smaller than the size of the data.
        """
        try:
            size = 0
            for dbname in self.databases:
                out = service.run_command(system.GET_DB_SIZE % {'dbname':
                                                                dbname})
                size = size + int(out[0])
        except exception.ProcessExecutionError:
            LOG.exception(_("An error occured while trying to "
                            "estimate backup size"))
        LOG.debug("Estimated size for databases: " + str(size))
        return size

    def estimate_log_size(self):
        return 0.0

    def run_backup(self):
        pass

    def execute_backup_cmd(self, backup_command):
        service.create_db2_dir(system.DB2_BACKUP_DIR)
        for dbName in self.databases:
            service.run_command(backup_command % {'dbname': dbName})

    def _run_pre_backup(self):
        """
        Before performing the actual backup we need to make sure that
        there is enough space to store the backups. The backup size
        is the sum of the size of the databases and if it is an online
        backup, the size of the archived logs is also factored in.
        """
        backup_size_bytes = self.estimate_backup_size()
        log_size_bytes = self.estimate_log_size()
        total_backup_size_gb = utils.to_gb(backup_size_bytes + log_size_bytes)
        free_bytes = operating_system.get_bytes_free_on_fs(system.MOUNT_POINT)
        free_gb = utils.to_gb(free_bytes)

        if total_backup_size_gb > free_gb:
            raise exception.InsufficientSpaceForBackup % {
                'backup_size': total_backup_size_gb,
                'free': free_gb
            }
        self.run_backup()

    @property
    def cmd(self):
        cmd = 'sudo tar cPf - ' + system.DB2_BACKUP_DIR
        return cmd + self.zip_cmd + self.encrypt_cmd

    def cleanup(self):
        service.remove_db2_dir(system.DB2_BACKUP_DIR)

    def _run_post_backup(self):
        self.cleanup()


class DB2OnlineBackup(DB2Backup):
    """
    Implementation of Online Backup Strategy for DB2
    using archive logging.
    """
    __strategy_name__ = 'db2onlinebackup'

    def __init__(self, *args, **kwargs):
        super(DB2OnlineBackup, self).__init__(*args, **kwargs)

    def estimate_log_size(self):
        """
        Estimate the log utilization for all databases. The LOG_UTILIZATION
        administrative view returns information about log utilization for the
        connected database. The TOTAL_LOG_USED_KB returns the log utilization
        in KB.
        """
        log_size = 0
        try:
            for dbname in self.databases:
                out = service.run_command(
                    system.LOG_UTILIZATION % {'dbname': dbname})
                log_size = log_size + int(out[0])
            log_size = log_size * 1024
        except exception.ProcessExecutionError:
            LOG.exception(_("An error occured while trying to estimate log "
                            "size"))
        LOG.debug("Estimated log size for all databases: " + str(log_size))
        return log_size

    def run_backup(self):
        try:
            self.execute_backup_cmd(system.ONLINE_BACKUP_DB)
        except exception.ProcessExecutionError:
            LOG.exception(_("An exception occurred while doing an online "
                            "backup."))
            self.cleanup()
            raise

    def cleanup(self):
        super(DB2OnlineBackup, self).cleanup()
        '''
        After a backup operation, we can delete the archived logs
        from the archived log directory but we do not want to delete
        the directory itself. Since archive logging is enabled for
        all databases, this directory is needed to store archive logs.
        '''
        service.remove_db2_dir(system.DB2_ARCHIVE_LOGS_DIR + "/*")


class DB2OfflineBackup(DB2Backup):
    """
    Implementation of Offline Backup Strategy for DB2 using
    circular logging which is the default.
    """
    __strategy_name__ = 'db2offlinebackup'

    def __init__(self, *args, **kwargs):
        super(DB2OfflineBackup, self).__init__(*args, **kwargs)

    def run_backup(self):
        """Create archival contents in dump dir"""
        try:
            service.run_command(system.QUIESCE_DB2)
            self.execute_backup_cmd(system.OFFLINE_BACKUP_DB)
            service.run_command(system.UNQUIESCE_DB2)
        except exception.ProcessExecutionError:
            LOG.exception(_("An exception occurred while doing an offline "
                            "backup."))
            self.cleanup()
            raise
