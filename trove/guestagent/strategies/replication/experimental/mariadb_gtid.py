# Copyright 2016 Tesora, Inc.
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

from oslo_log import log as logging

from trove.common import cfg
from trove.guestagent.backup.backupagent import BackupAgent
from trove.guestagent.strategies import backup
from trove.guestagent.strategies.replication import mysql_base

AGENT = BackupAgent()
CONF = cfg.CONF

REPL_BACKUP_NAMESPACE = 'trove.guestagent.strategies.backup' \
                        '.experimental.mariadb_impl'

LOG = logging.getLogger(__name__)


class MariaDBGTIDReplication(mysql_base.MysqlReplicationBase):
    """MariaDB Replication coordinated by GTIDs."""

    @property
    def repl_backup_runner(self):
        return backup.get_backup_strategy('MariaDBInnoBackupEx',
                                          REPL_BACKUP_NAMESPACE)

    @property
    def repl_incr_backup_runner(self):
        return backup.get_backup_strategy('MariaDBInnoBackupExIncremental',
                                          REPL_BACKUP_NAMESPACE)

    @property
    def repl_backup_extra_opts(self):
        return CONF.backup_runner_options.get('MariaDBInnoBackupEx', '')

    def connect_to_master(self, service, snapshot):
        logging_config = snapshot['log_position']
        LOG.debug("connect_to_master %s" % logging_config['replication_user'])
        change_master_cmd = (
            "CHANGE MASTER TO MASTER_HOST='%(host)s', "
            "MASTER_PORT=%(port)s, "
            "MASTER_USER='%(user)s', "
            "MASTER_PASSWORD='%(password)s', "
            "MASTER_USE_GTID=slave_pos" %
            {
                'host': snapshot['master']['host'],
                'port': snapshot['master']['port'],
                'user': logging_config['replication_user']['name'],
                'password': logging_config['replication_user']['password']
            })
        service.execute_on_client(change_master_cmd)
        service.start_slave()
