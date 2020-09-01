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
from trove.common import exception
from trove.common import utils
from trove.common.db.mysql import models
from trove.guestagent.common import operating_system
from trove.guestagent.strategies.replication import base

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class MysqlReplicationBase(base.Replication):
    """Base class for MySql Replication strategies."""

    def get_master_ref(self, service, snapshot_info):
        master_ref = {
            'host': netutils.get_my_ipv4(),
            'port': service.get_port()
        }
        return master_ref

    def _create_replication_user(self, service, adm):
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

                LOG.debug("Trying to create replication user %s",
                          mysql_user.name)
                adm.create_users([mysql_user.serialize()])

                replication_user = {
                    'name': mysql_user.name,
                    'password': replication_password
                }
            except Exception:
                retry_count += 1
                if retry_count > 5:
                    LOG.error("Replication user retry count exceeded")
                    raise

        return replication_user

    def snapshot_for_replication(self, context, service, adm, location,
                                 snapshot_info):
        LOG.info("Creating backup for replication")
        service.create_backup(context, snapshot_info)

        LOG.info('Creating replication user')
        replication_user = self._create_replication_user(service, adm)
        service.grant_replication_privilege(replication_user)

        log_position = {
            'replication_user': replication_user
        }
        return snapshot_info['id'], log_position

    def enable_as_master(self, service, master_config):
        if not service.exists_replication_source_overrides():
            service.write_replication_source_overrides(master_config)
            service.restart()

    def read_last_master_gtid(self, service):
        INFO_FILE = ('%s/xtrabackup_binlog_info' % service.get_data_dir())
        operating_system.chmod(INFO_FILE,
                               operating_system.FileMode.ADD_READ_ALL,
                               as_root=True)

        LOG.info("Reading last master GTID from %s", INFO_FILE)
        try:
            with open(INFO_FILE, 'r') as f:
                content = f.read()
                LOG.debug('Content in %s: "%s"', INFO_FILE, content)
                ret = content.strip().split('\t')
                return ret[2] if len(ret) == 3 else ''
        except Exception as ex:
            LOG.error('Failed to read last master GTID, error: %s', str(ex))
            raise exception.UnableToDetermineLastMasterGTID(
                {'binlog_file': INFO_FILE})

    @abc.abstractmethod
    def connect_to_master(self, service, master_info):
        """Connects a slave to a master"""

    def enable_as_slave(self, service, master_info, slave_config):
        try:
            service.write_replication_replica_overrides(slave_config)
            service.restart()
            self.connect_to_master(service, master_info)
        except Exception as err:
            LOG.error("Exception enabling guest as replica, error: %s",
                      str(err))
            raise

    def detach_slave(self, service, for_failover):
        replica_info = service.stop_slave(for_failover)
        service.remove_replication_replica_overrides()
        service.restart()
        return replica_info

    def get_replica_context(self, service, adm):
        """Get replication information as master."""
        replication_user = self._create_replication_user(service, adm)
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
