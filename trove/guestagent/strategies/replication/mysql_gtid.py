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
import semantic_version

from trove.common import cfg
from trove.guestagent.strategies.replication import mysql_base

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class MysqlGTIDReplication(mysql_base.MysqlReplicationBase):
    """MySql Replication coordinated by GTIDs."""

    def connect_to_master(self, service, master_info):
        cur_ver = semantic_version.Version.coerce(CONF.datastore_version)
        mysql_84 = semantic_version.Version('8.4.0')
        if 'dataset' in master_info:
            # pull the last executed GTID from the master via
            # the xtrabackup metadata file. If that value is
            # provided we need to set the gtid_purged variable
            # before executing the CHANGE MASTER TO command
            if master_info.get('dataset', {}).get('log_executed_gtid_set'):
                last_gtid = master_info['dataset']['log_executed_gtid_set']
            else:
                last_gtid = self.read_last_master_gtid(service)
            LOG.info("last_gtid value is %s", last_gtid)
            if '-' in last_gtid:
                # Also, FLUSH PRIVILEGES will restore gtid_executed.
                if cur_ver >= mysql_84:
                    service.execute_sql('RESET BINARY LOGS AND GTIDS')
                else:
                    # for mysql 8.0
                    service.execute_sql('RESET MASTER')
                set_gtid_cmd = "SET GLOBAL gtid_purged='%s'" % last_gtid
                service.execute_sql(set_gtid_cmd)

        replica_conf = master_info['replica_conf']
        LOG.info(
            "Configure the slave, master: %s:%s, replication user: %s",
            master_info['master']['host'],
            master_info['master']['port'],
            replica_conf['replication_user']['name']
        )
        if cur_ver >= mysql_84:
            change_master_cmd = (
                "CHANGE REPLICATION SOURCE TO "
                "SOURCE_HOST='%(host)s', "
                "SOURCE_PORT=%(port)s, "
                "SOURCE_USER='%(user)s', "
                "SOURCE_PASSWORD='%(password)s', "
                "SOURCE_AUTO_POSITION=1, "
                "GET_SOURCE_PUBLIC_KEY=1, "
                "SOURCE_CONNECT_RETRY=15" %
                {
                    'host': master_info['master']['host'],
                    'port': master_info['master']['port'],
                    'user': replica_conf['replication_user']['name'],
                    'password': replica_conf['replication_user']['password']
                })
        else:
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
                    'user': replica_conf['replication_user']['name'],
                    'password': replica_conf['replication_user']['password']
                })

        service.execute_sql(change_master_cmd)
        service.start_slave()
