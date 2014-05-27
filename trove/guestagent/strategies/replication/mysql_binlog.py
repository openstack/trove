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

from trove.guestagent.strategies.replication import base
from trove.guestagent.common import operating_system
from trove.openstack.common import log as logging

MASTER_CONFIG = """
[mysqld]
log_bin = /var/lib/mysql/mysql-bin.log
"""
SLAVE_CONFIG = """
[mysqld]
log_bin = /var/lib/mysql/mysql-bin.log
relay_log = /var/lib/mysql/mysql-relay-bin.log
"""

LOG = logging.getLogger(__name__)


class MysqlBinlogReplication(base.Replication):
    """MySql Replication coordinated by binlog position."""

    def get_master_ref(self, mysql_service, master_config):
        master_ref = {
            'host': operating_system.get_ip_address(),
            'port': mysql_service.get_port()
        }
        return master_ref

    def snapshot_for_replication(self, mysql_service, location, master_config):
        # TODO(mwj): snapshot_id = master_config['snapshot_id']
        # Check to see if the snapshot_id exists as a backup. If so, and
        # it is suitable for restoring the slave, just use it
        # Otherwise, create a new backup of the master site.
        snapshot_id = None
        log_position = mysql_service.get_binlog_position()
        return snapshot_id, log_position

    def enable_as_master(self, mysql_service, master_config):
        mysql_service.write_replication_overrides(MASTER_CONFIG)
        mysql_service.restart()
        mysql_service.grant_replication_privilege()

    def enable_as_slave(self, mysql_service, snapshot):
        mysql_service.write_replication_overrides(SLAVE_CONFIG)
        mysql_service.restart()
        mysql_service.change_master_for_binlog(
            snapshot['master']['host'],
            snapshot['master']['port'],
            snapshot['log_position'])
        mysql_service.start_slave()

    def detach_slave(self, mysql_service):
        mysql_service.stop_slave()
        mysql_service.remove_replication_overrides()
        mysql_service.restart()

    def demote_master(self, mysql_service):
        mysql_service.revoke_replication_privilege()
        mysql_service.remove_replication_overrides()
        mysql_service.restart()
