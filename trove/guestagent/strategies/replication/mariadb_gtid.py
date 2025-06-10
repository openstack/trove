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

import os

from oslo_log import log as logging

from trove.common import cfg
from trove.common import exception
from trove.guestagent.common import operating_system
from trove.guestagent.strategies.replication import mysql_base

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class MariaDBGTIDReplication(mysql_base.MysqlReplicationBase):
    """MariaDB Replication coordinated by GTIDs."""

    def get_replica_context(self, service, adm):
        """Get replication information as master."""
        master_info = super(MariaDBGTIDReplication, self).get_replica_context(
            service, adm)

        replica_conf = master_info['replica_conf']
        get_pos_cmd = 'SELECT @@global.gtid_binlog_pos;'
        gtid_pos = service.execute_sql(get_pos_cmd).first()[0]
        LOG.debug('gtid_binlog_pos: %s', gtid_pos)
        replica_conf['log_position']['gtid_pos'] = gtid_pos

        return master_info

    def read_last_master_gtid(self, service):
        # mariadb > 10.5  uses mariadb_backup_binlog_info instead.
        xtrabackup_info_file = ('%s/xtrabackup_binlog_info'
                                % service.get_data_dir())
        mariabackup_info_file = ('%s/mariadb_backup_binlog_info'
                                 % service.get_data_dir())

        if os.path.exists(mariabackup_info_file):
            INFO_FILE = mariabackup_info_file
            LOG.info("Using mariabackup_info_file")
        elif os.path.exists(xtrabackup_info_file):
            INFO_FILE = xtrabackup_info_file
            LOG.info("Using xtrabackup_binlog_info")
        else:
            # Handle the case where neither file exists
            LOG.error("Neither xtrabackup_binlog_info nor "
                      "mariadb_backup_binlog_info found.")
            raise exception.UnableToDetermineLastMasterGTID(
                binlog_file="xtrabackup_binlog_info or"
                            "mariadb_backup_binlog_info")

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
                binlog_file=INFO_FILE) from ex

    def connect_to_master(self, service, master_info):
        replica_conf = master_info['replica_conf']
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
                'user': replica_conf['replication_user']['name'],
                'password': replica_conf['replication_user']['password']
            })
        service.execute_sql(change_master_cmd)

        service.start_slave()
