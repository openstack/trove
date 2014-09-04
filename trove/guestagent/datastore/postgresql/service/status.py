# Copyright (c) 2014 OpenStack Foundation
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
from trove.common import utils
from trove.common import exception
from trove.common import instance
from trove.guestagent.datastore import service
from trove.guestagent.datastore.postgresql import pgutil
from trove.openstack.common import log as logging

LOG = logging.getLogger(__name__)

PGSQL_PID = "'/var/run/postgresql/postgresql.pid'"


class PgSqlAppStatus(service.BaseDbStatus):
    @classmethod
    def get(cls):
        if not cls._instance:
            cls._instance = PgSqlAppStatus()
        return cls._instance

    def _get_actual_db_status(self):
        """Checks the acutal PgSql process to determine status.

        Status will be one of the following:

            -   RUNNING

                The process is running and responsive.

            -   BLOCKED

                The process is running but unresponsive.

            -   CRASHED

                The process is not running, but should be or the process
                is running and should not be.

            -   SHUTDOWN

                The process was gracefully shut down.
        """

        # Run a simple scalar query to make sure the process is responsive.
        try:
            pgutil.execute('psql', '-c', 'SELECT 1')
        except utils.Timeout:
            return instance.ServiceStatuses.BLOCKED
        except exception.ProcessExecutionError:
            try:
                utils.execute_with_timeout(
                    "/bin/ps", "-C", "postgres", "h"
                )
            except exception.ProcessExecutionError:
                if os.path.exists(PGSQL_PID):
                    return instance.ServiceStatuses.CRASHED
                return instance.ServiceStatuses.SHUTDOWN
            else:
                return instance.ServiceStatuses.BLOCKED
        else:
            return instance.ServiceStatuses.RUNNING
