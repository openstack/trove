# Copyright 2014 Tesora, Inc.
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

import csv

from trove.common import cfg
from trove.common import exception
from trove.common import utils
from trove.common.i18n import _
from trove.guestagent.backup.backupagent import BackupAgent
from trove.guestagent.strategies.replication import mysql_base
from trove.openstack.common import log as logging

AGENT = BackupAgent()
CONF = cfg.CONF

LOG = logging.getLogger(__name__)


class MysqlBinlogReplication(mysql_base.MysqlReplicationBase):
    """MySql Replication coordinated by binlog position."""

    class UnableToDetermineBinlogPosition(exception.TroveError):
        message = _("Unable to determine binlog position "
                    "(from file %(binlog_file)).")

    def connect_to_master(self, service, snapshot):
        logging_config = snapshot['log_position']
        logging_config.update(self._read_log_position())
        change_master_cmd = (
            "CHANGE MASTER TO MASTER_HOST='%(host)s', "
            "MASTER_PORT=%(port)s, "
            "MASTER_USER='%(user)s', "
            "MASTER_PASSWORD='%(password)s', "
            "MASTER_LOG_FILE='%(log_file)s', "
            "MASTER_LOG_POS=%(log_pos)s" %
            {
                'host': snapshot['master']['host'],
                'port': snapshot['master']['port'],
                'user': logging_config['replication_user']['name'],
                'password': logging_config['replication_user']['password'],
                'log_file': logging_config['log_file'],
                'log_pos': logging_config['log_position']
            })
        service.execute_on_client(change_master_cmd)
        service.start_slave()

    def _read_log_position(self):
        INFO_FILE = '/var/lib/mysql/data/xtrabackup_binlog_info'
        LOG.info(_("Setting read permissions on %s") % INFO_FILE)
        utils.execute_with_timeout("sudo", "chmod", "+r", INFO_FILE)
        LOG.info(_("Reading log position from %s") % INFO_FILE)
        try:
            with open(INFO_FILE, 'rb') as f:
                row = csv.reader(f, delimiter='\t',
                                 skipinitialspace=True).next()
                return {
                    'log_file': row[0],
                    'log_position': int(row[1])
                }
        except (IOError, IndexError) as ex:
            LOG.exception(ex)
            raise self.UnableToDetermineBinlogPosition(
                {'info_file': INFO_FILE})
