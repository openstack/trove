# Copyright 2020 Catalyst Cloud
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

from trove.common import cfg
from trove.common import exception
from trove.guestagent.common import operating_system
from trove.guestagent.datastore.mysql import service
from trove.guestagent.datastore.mysql_common import manager
from trove.guestagent.datastore import service as base_service


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class Manager(manager.MySqlManager):
    def __init__(self):
        status = base_service.BaseDbStatus(self.docker_client)
        app = service.MySqlApp(status, self.docker_client)
        adm = service.MySqlAdmin(app)

        super(Manager, self).__init__(app, status, adm)

    def pre_create_backup(self, context, **kwargs):
        LOG.info("Running pre_create_backup")
        status = {}
        try:
            INFO_FILE = "%s/xtrabackup_binlog_info" % self.app.get_data_dir()
            self.app.execute_sql("FLUSH TABLES WITH READ LOCK;")
            if self.app._is_mysql84():
                stt = self.app.execute_sql("SHOW BINARY LOG STATUS;")
            else:
                stt = self.app.execute_sql("SHOW MASTER STATUS;")
            for row in stt:
                status = {
                    'log_file': row._mapping['File'],
                    'log_position': row._mapping['Position'],
                    'log_executed_gtid_set': row._mapping['Executed_Gtid_Set'],
                }

                binlog = "\t".join(map(str, [
                    status['log_file'],
                    status['log_position'],
                    status['log_executed_gtid_set']]))
                operating_system.write_file(INFO_FILE, binlog, as_root=True)

            mount_point = CONF.get(CONF.datastore_manager).mount_point
            operating_system.sync(mount_point)
            operating_system.fsfreeze(mount_point)
        except Exception as e:
            LOG.error("Run pre_create_backup failed, error: %s" % str(e))
            raise exception.BackupCreationError(str(e))

        return status
