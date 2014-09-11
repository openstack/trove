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
from trove.guestagent.backup.backupagent import BackupAgent
from trove.guestagent.common import operating_system
from trove.guestagent.strategies import backup
from trove.guestagent.strategies.replication import base
from trove.guestagent.strategies.storage import get_storage_strategy
from trove.openstack.common import log as logging
from trove.openstack.common.gettextutils import _

AGENT = BackupAgent()
CONF = cfg.CONF
MANAGER = 'mysql' if not CONF.datastore_manager else CONF.datastore_manager

MASTER_CONFIG = """
[mysqld]
log_bin = /var/lib/mysql/mysql-bin.log
"""
SLAVE_CONFIG = """
[mysqld]
log_bin = /var/lib/mysql/mysql-bin.log
relay_log = /var/lib/mysql/mysql-relay-bin.log
read_only = true
"""

REPL_BACKUP_NAMESPACE = 'trove.guestagent.strategies.backup.mysql_impl'
REPL_BACKUP_STRATEGY = 'InnoBackupEx'
REPL_BACKUP_RUNNER = backup.get_backup_strategy(REPL_BACKUP_STRATEGY,
                                                REPL_BACKUP_NAMESPACE)
REPL_EXTRA_OPTS = CONF.backup_runner_options.get(REPL_BACKUP_STRATEGY, '')

LOG = logging.getLogger(__name__)


class MysqlBinlogReplication(base.Replication):
    """MySql Replication coordinated by binlog position."""

    class UnableToDetermineBinlogPosition(exception.TroveError):
        message = _("Unable to determine binlog position "
                    "(from file %(binlog_file)).")

    def get_master_ref(self, service, snapshot_info):
        master_ref = {
            'host': operating_system.get_ip_address(),
            'port': service.get_port()
        }
        return master_ref

    def snapshot_for_replication(self, context, service,
                                 location, snapshot_info):
        snapshot_id = snapshot_info['id']

        storage = get_storage_strategy(
            CONF.storage_strategy,
            CONF.storage_namespace)(context)

        AGENT.stream_backup_to_storage(snapshot_info, REPL_BACKUP_RUNNER,
                                       storage, {}, REPL_EXTRA_OPTS)

        # With streamed InnobackupEx, the log position is in
        # the stream and will be decoded by the slave
        log_position = {}
        return snapshot_id, log_position

    def enable_as_master(self, service, snapshot_info):
        service.write_replication_overrides(MASTER_CONFIG)
        service.restart()
        service.grant_replication_privilege()

    def enable_as_slave(self, service, snapshot):
        service.write_replication_overrides(SLAVE_CONFIG)
        service.restart()
        service.change_master_for_binlog(
            snapshot['master']['host'],
            snapshot['master']['port'],
            self._read_log_position())
        service.start_slave()

    def detach_slave(self, service):
        service.stop_slave()
        service.remove_replication_overrides()
        service.restart()

    def demote_master(self, service):
        service.revoke_replication_privilege()
        service.remove_replication_overrides()
        service.restart()

    def _read_log_position(self):
        INFO_FILE = '/var/lib/mysql/xtrabackup_binlog_info'
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
