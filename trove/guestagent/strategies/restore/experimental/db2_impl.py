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
from trove.common.i18n import _
from trove.common import utils
from trove.guestagent.common import operating_system
from trove.guestagent.datastore.experimental.db2 import service
from trove.guestagent.datastore.experimental.db2 import system
from trove.guestagent.strategies.restore import base

LOG = logging.getLogger(__name__)
CONF = cfg.CONF
DB2_DBPATH = CONF.db2.mount_point
DB2_BACKUP_DIR = DB2_DBPATH + "/backup"


class DB2Backup(base.RestoreRunner):
    """Implementation of Restore Strategy for DB2."""
    __strategy_name__ = 'db2backup'
    base_restore_cmd = 'sudo tar xPf -'

    def __init__(self, *args, **kwargs):
        super(DB2Backup, self).__init__(*args, **kwargs)
        self.appStatus = service.DB2AppStatus()
        self.app = service.DB2App(self.appStatus)
        self.admin = service.DB2Admin()
        self.restore_location = DB2_BACKUP_DIR

    def post_restore(self):
        """
        Restore from the directory that we untarred into
        """
        out, err = utils.execute_with_timeout(system.GET_DB_NAMES,
                                              shell=True)
        dbNames = out.split()
        for dbName in dbNames:
            service.run_command(system.RESTORE_DB % {'dbname': dbName,
                                                     'dir': DB2_BACKUP_DIR})

        LOG.info(_("Cleaning out restore location post: %s."), DB2_BACKUP_DIR)
        operating_system.remove(DB2_BACKUP_DIR, force=True, as_root=True)
