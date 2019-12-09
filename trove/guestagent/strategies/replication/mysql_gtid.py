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
from oslo_utils import encodeutils

from trove.common import exception
from trove.common.i18n import _
from trove.guestagent.backup.backupagent import BackupAgent
from trove.guestagent.common import operating_system
from trove.guestagent.common.operating_system import FileMode
from trove.guestagent.datastore.mysql.service import MySqlApp
from trove.guestagent.strategies.replication import mysql_base

AGENT = BackupAgent()

LOG = logging.getLogger(__name__)


class MysqlGTIDReplication(mysql_base.MysqlReplicationBase):
    """MySql Replication coordinated by GTIDs."""

    class UnableToDetermineLastMasterGTID(exception.TroveError):
        message = _("Unable to determine last GTID executed on master "
                    "(from file %(binlog_file)s).")

    def connect_to_master(self, service, snapshot):
        if 'dataset' in snapshot:
            # pull the last executed GTID from the master via
            # the xtrabackup metadata file. If that value is
            # provided we need to set the gtid_purged variable
            # before executing the CHANGE MASTER TO command
            last_gtid = self._read_last_master_gtid()
            LOG.debug("last_gtid value is %s", last_gtid)
            # fix ['mysql-bin.000001', '154', '\n'] still existed last_gtid
            # with '\n' value
            if last_gtid and len(last_gtid) != 1:
                set_gtid_cmd = "SET GLOBAL gtid_purged='%s'" % last_gtid
                LOG.debug("set gtid_purged with %s", set_gtid_cmd)
                service.execute_on_client(set_gtid_cmd)

        logging_config = snapshot['log_position']
        LOG.debug("connect_to_master %s", logging_config['replication_user'])
        change_master_cmd = (
            "CHANGE MASTER TO MASTER_HOST='%(host)s', "
            "MASTER_PORT=%(port)s, "
            "MASTER_USER='%(user)s', "
            "MASTER_PASSWORD='%(password)s', "
            "MASTER_AUTO_POSITION=1, "
            "MASTER_CONNECT_RETRY=15" %
            {
                'host': snapshot['master']['host'],
                'port': snapshot['master']['port'],
                'user': logging_config['replication_user']['name'],
                'password': logging_config['replication_user']['password']
            })
        service.execute_on_client(change_master_cmd)
        service.start_slave()

    def _read_last_master_gtid(self):
        INFO_FILE = ('%s/xtrabackup_binlog_info' % MySqlApp.get_data_dir())
        LOG.info("Setting read permissions on %s", INFO_FILE)
        operating_system.chmod(INFO_FILE, FileMode.ADD_READ_ALL, as_root=True)
        LOG.info("Reading last master GTID from %s", INFO_FILE)
        try:
            with open(INFO_FILE, 'rb') as f:
                row = f.read().split(b'\t')
                return encodeutils.safe_decode(row[2])
        except (IOError, IndexError) as ex:
            LOG.exception(ex)
            raise self.UnableToDetermineLastMasterGTID(
                {'binlog_file': INFO_FILE})
