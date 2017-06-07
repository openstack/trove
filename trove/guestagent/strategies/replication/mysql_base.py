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

import abc
import uuid

from oslo_log import log as logging
from oslo_utils import netutils

from trove.common import cfg
from trove.common.db.mysql import models
from trove.common.i18n import _
from trove.common import utils
from trove.guestagent.backup.backupagent import BackupAgent
from trove.guestagent.datastore.mysql.service import MySqlAdmin
from trove.guestagent.strategies import backup
from trove.guestagent.strategies.replication import base

AGENT = BackupAgent()
CONF = cfg.CONF

REPL_BACKUP_NAMESPACE = 'trove.guestagent.strategies.backup.mysql_impl'

LOG = logging.getLogger(__name__)


class MysqlReplicationBase(base.Replication):
    """Base class for MySql Replication strategies."""

    @property
    def repl_backup_runner(self):
        return backup.get_backup_strategy('InnoBackupEx',
                                          REPL_BACKUP_NAMESPACE)

    @property
    def repl_incr_backup_runner(self):
        return backup.get_backup_strategy('InnoBackupExIncremental',
                                          REPL_BACKUP_NAMESPACE)

    @property
    def repl_backup_extra_opts(self):
        return CONF.backup_runner_options.get('InnoBackupEx', '')

    def get_master_ref(self, service, snapshot_info):
        master_ref = {
            'host': netutils.get_my_ipv4(),
            'port': service.get_port()
        }
        return master_ref

    def _create_replication_user(self):
        replication_user = None
        replication_password = utils.generate_random_password(16)

        mysql_user = None  # cache the model as we just want name validation

        retry_count = 0

        while replication_user is None:
            try:
                name = 'slave_' + str(uuid.uuid4())[:8]
                if mysql_user:
                    mysql_user.name = name
                else:
                    mysql_user = models.MySQLUser(
                        name=name, password=replication_password
                    )
                    mysql_user.check_create()
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
        replica_number = snapshot_info.get('replica_number', 1)

        LOG.debug("Acquiring backup for replica number %d.", replica_number)
        # Only create a backup if it's the first replica
        if replica_number == 1:
            AGENT.execute_backup(
                context, snapshot_info, runner=self.repl_backup_runner,
                extra_opts=self.repl_backup_extra_opts,
                incremental_runner=self.repl_incr_backup_runner)
        else:
            LOG.debug("Using existing backup created for previous replica.")
        LOG.debug("Replication snapshot %(snapshot_id)s used for replica "
                  "number %(replica_number)d.",
                  {'snapshot_id': snapshot_id,
                   'replica_number': replica_number})

        replication_user = self._create_replication_user()
        service.grant_replication_privilege(replication_user)

        # With streamed InnobackupEx, the log position is in
        # the stream and will be decoded by the slave
        log_position = {
            'replication_user': replication_user
        }
        return snapshot_id, log_position

    def enable_as_master(self, service, master_config):
        if not service.exists_replication_source_overrides():
            service.write_replication_source_overrides(master_config)
            service.restart()

    @abc.abstractmethod
    def connect_to_master(self, service, snapshot):
        """Connects a slave to a master"""

    def enable_as_slave(self, service, snapshot, slave_config):
        try:
            service.write_replication_replica_overrides(slave_config)
            service.restart()
            self.connect_to_master(service, snapshot)
        except Exception:
            LOG.exception(_("Exception enabling guest as replica"))
            raise

    def detach_slave(self, service, for_failover):
        replica_info = service.stop_slave(for_failover)
        service.remove_replication_replica_overrides()
        service.restart()
        return replica_info

    def get_replica_context(self, service):
        replication_user = self._create_replication_user()
        service.grant_replication_privilege(replication_user)
        return {
            'master': self.get_master_ref(service, None),
            'log_position': {
                'replication_user': replication_user
            }
        }

    def cleanup_source_on_replica_detach(self, admin_service, replica_info):
        admin_service.delete_user_by_name(replica_info['replication_user'])

    def demote_master(self, service):
        service.remove_replication_source_overrides()
        service.restart()
