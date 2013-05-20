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

from reddwarf.guestagent.strategies.restore import base
from reddwarf.openstack.common import log as logging
from reddwarf.common import utils
import reddwarf.guestagent.manager.mysql_service as dbaas

LOG = logging.getLogger(__name__)


class MySQLDump(base.RestoreRunner):
    """ Implementation of Restore Strategy for MySQLDump """
    __strategy_name__ = 'mysqldump'
    is_zipped = True
    restore_cmd = ('mysql '
                   '--password=%(password)s '
                   '-u %(user)s')

    def _pre_restore(self):
        pass

    def _post_restore(self):
        pass


class InnoBackupEx(base.RestoreRunner):
    """ Implementation of Restore Strategy for InnoBackupEx """
    __strategy_name__ = 'innobackupex'
    is_zipped = True
    restore_cmd = 'sudo xbstream -x -C %(restore_location)s'
    prepare_cmd = ('sudo innobackupex --apply-log %(restore_location)s '
                   '--ibbackup xtrabackup 2>/tmp/innoprepare.log')

    def _pre_restore(self):
        app = dbaas.MySqlApp(dbaas.MySqlAppStatus.get())
        app.stop_db()

    def _post_restore(self):
        utils.execute_with_timeout("sudo", "chown", "-R", "-f",
                                   "mysql", self.restore_location)
        self._delete_old_binlogs()
        self._reset_root_password()
        app = dbaas.MySqlApp(dbaas.MySqlAppStatus.get())
        app.start_mysql()
