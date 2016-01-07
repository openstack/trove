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

from oslo_log import log as logging

from trove.common import cfg
from trove.guestagent.common import operating_system
from trove.guestagent.datastore.experimental.postgresql.service.status import (
    PgSqlAppStatus)

LOG = logging.getLogger(__name__)
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

    def start_db(self, context, enable_on_boot=True, update_db=False):
        PgSqlAppStatus.get().start_db_service(
            self.SERVICE_CANDIDATES, CONF.state_change_wait_time,
            enable_on_boot=enable_on_boot, update_db=update_db)

    def stop_db(self, context, do_not_start_on_reboot=False, update_db=False):
        PgSqlAppStatus.get().stop_db_service(
            self.SERVICE_CANDIDATES, CONF.state_change_wait_time,
            disable_on_boot=do_not_start_on_reboot, update_db=update_db)
