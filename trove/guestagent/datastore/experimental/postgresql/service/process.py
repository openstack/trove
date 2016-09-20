# Copyright (c) 2013 OpenStack Foundation
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

import os
import re

from trove.common import cfg
from trove.guestagent.common import operating_system
from trove.guestagent.datastore.experimental.postgresql import pgutil
from trove.guestagent.datastore.experimental.postgresql.service.status import (
    PgSqlAppStatus)
from trove.guestagent import guest_log


CONF = cfg.CONF


class PgSqlProcess(object):
    """Mixin that manages the PgSql process."""

    SERVICE_CANDIDATES = ["postgresql"]
    PGSQL_OWNER = 'postgres'
    DATA_BASE = '/var/lib/postgresql/'
    PID_FILE = '/var/run/postgresql/postgresql.pid'
    UNIX_SOCKET_DIR = '/var/run/postgresql/'

    @property
    def pgsql_data_dir(self):
        return os.path.dirname(self.pg_version[0])

    @property
    def pgsql_recovery_config(self):
        return os.path.join(self.pgsql_data_dir, "recovery.conf")

    @property
    def pg_version(self):
        """Find the database version file stored in the data directory.

        :returns: A tuple with the path to the version file
                  (in the root of the data directory) and the version string.
        """
        version_files = operating_system.list_files_in_directory(
            self.DATA_BASE, recursive=True, pattern='PG_VERSION', as_root=True)
        version_file = sorted(version_files, key=len)[0]
        version = operating_system.read_file(version_file, as_root=True)
        return version_file, version.strip()

    def restart(self, context):
        PgSqlAppStatus.get().restart_db_service(
            self.SERVICE_CANDIDATES, CONF.state_change_wait_time)
        self.set_guest_log_status(guest_log.LogStatus.Restart_Completed)

    def start_db(self, context, enable_on_boot=True, update_db=False):
        PgSqlAppStatus.get().start_db_service(
            self.SERVICE_CANDIDATES, CONF.state_change_wait_time,
            enable_on_boot=enable_on_boot, update_db=update_db)

    def stop_db(self, context, do_not_start_on_reboot=False, update_db=False):
        PgSqlAppStatus.get().stop_db_service(
            self.SERVICE_CANDIDATES, CONF.state_change_wait_time,
            disable_on_boot=do_not_start_on_reboot, update_db=update_db)

    def pg_checkpoint(self):
        """Wrapper for CHECKPOINT call"""
        pgutil.psql("CHECKPOINT")

    def pg_current_xlog_location(self):
        """Wrapper for pg_current_xlog_location()
        Cannot be used against a running slave
        """
        r = pgutil.query("SELECT pg_current_xlog_location()")
        return r[0][0]

    def pg_last_xlog_replay_location(self):
        """Wrapper for pg_last_xlog_replay_location()
         For use on standby servers
         """
        r = pgutil.query("SELECT pg_last_xlog_replay_location()")
        return r[0][0]

    def pg_is_in_recovery(self):
        """Wrapper for pg_is_in_recovery() for detecting a server in
        standby mode
        """
        r = pgutil.query("SELECT pg_is_in_recovery()")
        return r[0][0]

    def pg_primary_host(self):
        """There seems to be no way to programmatically  determine this
        on a hot standby, so grab what we have written to the recovery
        file
        """
        r = operating_system.read_file(self.pgsql_recovery_config,
                                       as_root=True)
        regexp = re.compile("host=(\d+.\d+.\d+.\d+) ")
        m = regexp.search(r)
        return m.group(1)

    @classmethod
    def recreate_wal_archive_dir(cls):
        wal_archive_dir = CONF.postgresql.wal_archive_location
        operating_system.remove(wal_archive_dir, force=True, recursive=True,
                                as_root=True)
        operating_system.create_directory(wal_archive_dir,
                                          user=cls.PGSQL_OWNER,
                                          group=cls.PGSQL_OWNER,
                                          force=True, as_root=True)

    @classmethod
    def remove_wal_archive_dir(cls):
        wal_archive_dir = CONF.postgresql.wal_archive_location
        operating_system.remove(wal_archive_dir, force=True, recursive=True,
                                as_root=True)
