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

from oslo_log import log as logging
import psycopg2

from trove.common.i18n import _
from trove.common import instance
from trove.common import utils
from trove.guestagent.datastore.experimental.postgresql import pgutil
from trove.guestagent.datastore import service

LOG = logging.getLogger(__name__)


class PgSqlAppStatus(service.BaseDbStatus):

    @classmethod
    def get(cls):
        if not cls._instance:
            cls._instance = PgSqlAppStatus()
        return cls._instance

    def _get_actual_db_status(self):
        try:
            # Any query will initiate a new database connection.
            pgutil.psql("SELECT 1")
            return instance.ServiceStatuses.RUNNING
        except psycopg2.OperationalError:
            return instance.ServiceStatuses.SHUTDOWN
        except utils.Timeout:
            return instance.ServiceStatuses.BLOCKED
        except Exception:
            LOG.exception(_("Error getting Postgres status."))
            return instance.ServiceStatuses.CRASHED

        return instance.ServiceStatuses.SHUTDOWN
