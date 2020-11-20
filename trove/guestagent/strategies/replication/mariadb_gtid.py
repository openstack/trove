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
from trove.guestagent.strategies.replication import mysql_base

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class MariaDBGTIDReplication(mysql_base.MysqlReplicationBase):
    """MariaDB Replication coordinated by GTIDs."""

    def get_replica_context(self, service, adm):
        """Get replication information as master."""
        master_info = super(MariaDBGTIDReplication, self).get_replica_context(
            service, adm)

        get_pos_cmd = 'SELECT @@global.gtid_binlog_pos;'
        gtid_pos = service.execute_sql(get_pos_cmd).first()[0]
        LOG.debug('gtid_binlog_pos: %s', gtid_pos)
        master_info['log_position']['gtid_pos'] = gtid_pos

        return master_info

    def connect_to_master(self, service, master_info):
        logging_config = master_info['log_position']
        last_gtid = ''

        if 'dataset' in master_info:
            # This will happen when initial replication is set up.
            last_gtid = self.read_last_master_gtid(service)
            set_gtid_cmd = "SET GLOBAL gtid_slave_pos='%s';" % last_gtid
            service.execute_sql(set_gtid_cmd)

        change_master_cmd = (
            "CHANGE MASTER TO "
            "MASTER_HOST='%(host)s', "
            "MASTER_PORT=%(port)s, "
            "MASTER_USER='%(user)s', "
            "MASTER_PASSWORD='%(password)s', "
            "MASTER_CONNECT_RETRY=15, "
            "MASTER_USE_GTID=slave_pos" %
            {
                'host': master_info['master']['host'],
                'port': master_info['master']['port'],
                'user': logging_config['replication_user']['name'],
                'password': logging_config['replication_user']['password'],
            })
        service.execute_sql(change_master_cmd)

        service.start_slave()
