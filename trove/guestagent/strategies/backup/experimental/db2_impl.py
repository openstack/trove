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
from trove.common import cfg
from trove.common import exception
from trove.common.i18n import _
from trove.guestagent.common import operating_system
from trove.guestagent.datastore.experimental.db2 import service
from trove.guestagent.datastore.experimental.db2 import system
from trove.guestagent.db import models
from trove.guestagent.strategies.backup import base

CONF = cfg.CONF
DB2_DBPATH = CONF.db2.mount_point
DB2_BACKUP_DIR = DB2_DBPATH + "/backup"
LOG = logging.getLogger(__name__)


class DB2Backup(base.BackupRunner):
    """Implementation of Backup Strategy for DB2."""
    __Strategy_name__ = 'db2backup'

    def __init__(self, *args, **kwargs):
        self.admin = service.DB2Admin()
        super(DB2Backup, self).__init__(*args, **kwargs)

    def _run_pre_backup(self):
        """Create archival contents in dump dir"""
        try:
            est_dump_size = self.estimate_dump_size()
            avail = operating_system.get_bytes_free_on_fs(DB2_DBPATH)
            if est_dump_size > avail:
                self.cleanup()
                raise OSError(_("Need more free space to backup db2 database,"
                                " estimated %(est_dump_size)s"
                                " and found %(avail)s bytes free ") %
                              {'est_dump_size': est_dump_size,
                               'avail': avail})

            operating_system.create_directory(DB2_BACKUP_DIR,
                                              system.DB2_INSTANCE_OWNER,
                                              system.DB2_INSTANCE_OWNER,
                                              as_root=True)

            service.run_command(system.QUIESCE_DB2)
            dbNames = self.list_dbnames()
            for dbName in dbNames:
                service.run_command(system.BACKUP_DB % {
                    'dbname': dbName, 'dir': DB2_BACKUP_DIR})

            service.run_command(system.UNQUIESCE_DB2)
        except exception.ProcessExecutionError:
            LOG.debug("Caught exception when preparing the directory")
            self.cleanup()
            raise

    @property
    def cmd(self):
        cmd = 'sudo tar cPf - ' + DB2_BACKUP_DIR
        return cmd + self.zip_cmd + self.encrypt_cmd

    def cleanup(self):
        operating_system.remove(DB2_BACKUP_DIR, force=True, as_root=True)

    def _run_post_backup(self):
        self.cleanup()

    def list_dbnames(self):
        dbNames = []
        databases, marker = self.admin.list_databases()
        for database in databases:
            mydb = models.MySQLDatabase()
            mydb.deserialize(database)
            dbNames.append(mydb.name)
        return dbNames

    def estimate_dump_size(self):
        """
           Estimating the size of the backup based on the size of the data
           returned from the get_db_size procedure. The size of the
           backup is always going to be smaller than the size of the data.
        """
        try:
            dbs = self.list_dbnames()
            size = 0
            for dbname in dbs:
                out = service.run_command(system.GET_DB_SIZE % {'dbname':
                                                                dbname})
                size = size + out
        except exception.ProcessExecutionError:
            LOG.debug("Error while trying to get db size info")
        LOG.debug("Estimated size for databases: " + str(size))
        return size
