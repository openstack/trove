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
import uuid

from trove.common import cfg
from trove.common import exception
from trove.common import utils
from trove.guestagent.backup.backupagent import BackupAgent
from trove.guestagent.common import operating_system
from trove.guestagent.datastore.mysql.service import MySqlAdmin
from trove.guestagent.db import models
from trove.guestagent.strategies import backup
from trove.guestagent.strategies.replication import base
from trove.guestagent.strategies.storage import get_storage_strategy
from trove.openstack.common import log as logging
from trove.common.i18n import _

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

    def _create_replication_user(self):
        replication_user = None
        replication_password = utils.generate_random_password(16)

        mysql_user = models.MySQLUser()
        mysql_user.password = replication_password

        retry_count = 0

        while replication_user is None:
            try:
                mysql_user.name = 'slave_' + str(uuid.uuid4())[:8]
                MySqlAdmin().create_user([mysql_user.serialize()])
                LOG.debug("Trying to create replication user " +
                          mysql_user.name)
                replication_user = {
                    'name': mysql_user.name,
                    'password': replication_password
                }
            except Exception:
                retry_count += 1
                if retry_count > 5:
                    LOG.error(_("Replication user retry count exceeded"))
                    raise

        return replication_user

    def snapshot_for_replication(self, context, service,
                                 location, snapshot_info):
        snapshot_id = snapshot_info['id']

        storage = get_storage_strategy(
            CONF.storage_strategy,
            CONF.storage_namespace)(context)

        AGENT.stream_backup_to_storage(snapshot_info, REPL_BACKUP_RUNNER,
                                       storage, {}, REPL_EXTRA_OPTS)

        replication_user = self._create_replication_user()
        service.grant_replication_privilege(replication_user)

        # With streamed InnobackupEx, the log position is in
        # the stream and will be decoded by the slave
        log_position = {
            'replication_user': replication_user
        }
        return snapshot_id, log_position

    def enable_as_master(self, service, snapshot_info, master_config):
        if not master_config:
            master_config = MASTER_CONFIG
        service.write_replication_overrides(master_config)
        service.restart()

    def enable_as_slave(self, service, snapshot, slave_config):
        if not slave_config:
            slave_config = SLAVE_CONFIG
        service.write_replication_overrides(slave_config)
        service.restart()
        logging_config = snapshot['log_position']
        logging_config.update(self._read_log_position())
        service.change_master_for_binlog(
            snapshot['master']['host'],
            snapshot['master']['port'],
            logging_config)
        service.start_slave()

    def detach_slave(self, service):
        replica_info = service.stop_slave()
        service.remove_replication_overrides()
        service.restart()
        return replica_info

    def cleanup_source_on_replica_detach(self, admin_service, replica_info):
        admin_service.delete_user_by_name(replica_info['replication_user'])

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
