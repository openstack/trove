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

from oslo_log import log as logging

from trove.guestagent.common import operating_system
from trove.guestagent.datastore.experimental.mariadb import service
from trove.guestagent.datastore.mysql_common import service as mysql_service
from trove.guestagent.strategies.restore import mysql_impl

LOG = logging.getLogger(__name__)


class MariaBackup(mysql_impl.InnoBackupEx):
    __strategy_name__ = 'mariabackup'
    base_restore_cmd = ('sudo mbstream -x -C %(restore_location)s '
                        '2>/tmp/xbstream_extract.log')

    @property
    def app(self):
        if self._app is None:
            self._app = service.MariaDBApp(
                mysql_service.BaseMySqlAppStatus.get()
            )
        return self._app

    def post_restore(self):
        operating_system.chown(self.restore_location, 'mysql', None,
                               force=True, as_root=True)

        # When using Mariabackup from versions prior to MariaDB 10.2.10, you
        # would also have to remove any pre-existing InnoDB redo log files.
        self._delete_old_binlogs()
        self.app.start_mysql()
        LOG.debug("Finished post restore.")

    def check_process(self):
        LOG.debug('Checking return code of mbstream restore process.')
        return_code = self.process.wait()
        if return_code != 0:
            LOG.error('mbstream exited with %s', return_code)
            return False

        return True


class MariaBackupIncremental(MariaBackup):
    pass
