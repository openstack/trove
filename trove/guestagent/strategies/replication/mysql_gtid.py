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
from oslo_log import log as logging

from trove.guestagent.strategies.replication import mysql_base

LOG = logging.getLogger(__name__)


class MysqlGTIDReplication(mysql_base.MysqlReplicationBase):
    """MySql Replication coordinated by GTIDs."""
    def connect_to_master(self, service, master_info):
        if 'dataset' in master_info:
            # pull the last executed GTID from the master via
            # the xtrabackup metadata file. If that value is
            # provided we need to set the gtid_purged variable
            # before executing the CHANGE MASTER TO command
            last_gtid = self.read_last_master_gtid(service)
            LOG.info("last_gtid value is %s", last_gtid)
            if '-' in last_gtid:
                set_gtid_cmd = "SET GLOBAL gtid_purged='%s'" % last_gtid
                service.execute_sql(set_gtid_cmd)

        logging_config = master_info['log_position']
        LOG.info(
            "Configure the slave, master: %s:%s, replication user: %s",
            master_info['master']['host'],
            master_info['master']['port'],
            logging_config['replication_user']['name']
        )

        change_master_cmd = (
            "CHANGE MASTER TO "
            "MASTER_HOST='%(host)s', "
            "MASTER_PORT=%(port)s, "
            "MASTER_USER='%(user)s', "
            "MASTER_PASSWORD='%(password)s', "
            "MASTER_AUTO_POSITION=1, "
            "MASTER_CONNECT_RETRY=15" %
            {
                'host': master_info['master']['host'],
                'port': master_info['master']['port'],
                'user': logging_config['replication_user']['name'],
                'password': logging_config['replication_user']['password']
            })
        service.execute_sql(change_master_cmd)

        service.start_slave()
