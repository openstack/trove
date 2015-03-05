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

from trove.common import cfg
from trove.common import utils
from trove.guestagent.common import operating_system
from trove.guestagent.datastore.experimental.postgresql.service.status import (
    PgSqlAppStatus)
from trove.openstack.common import log as logging

LOG = logging.getLogger(__name__)
CONF = cfg.CONF

PGSQL_SERVICE_CANDIDATES = ("postgresql",)


class PgSqlProcess(object):
    """Mixin that manages the PgSql process."""

    def start_db(self, context):
        self._enable_pgsql_on_boot()
        """Start the PgSql service."""
        cmd = operating_system.service_discovery(PGSQL_SERVICE_CANDIDATES)
        LOG.info(
            _("{guest_id}: Starting database engine with command ({command}).")
            .format(
                guest_id=CONF.guest_id,
                command=cmd['cmd_start'],
            )
        )
        utils.execute_with_timeout(
            *cmd['cmd_start'].split(),
            timeout=30
        )

    def _enable_pgsql_on_boot(self):
        try:
            pgsql_service = operating_system.service_discovery(
                PGSQL_SERVICE_CANDIDATES)
            utils.execute_with_timeout(pgsql_service['cmd_enable'],
                                       shell=True)
        except KeyError:
            LOG.exception(_("Error enabling PostgreSQL start on boot."))
            raise RuntimeError("Service is not discovered.")

    def _disable_pgsql_on_boot(self):
        try:
            pgsql_service = operating_system.service_discovery(
                PGSQL_SERVICE_CANDIDATES)
            utils.execute_with_timeout(pgsql_service['cmd_disable'],
                                       shell=True)
        except KeyError:
            LOG.exception(_("Error disabling PostgreSQL start on boot."))
            raise RuntimeError("Service is not discovered.")

    def stop_db(self, context, do_not_start_on_reboot=False):
        """Stop the PgSql service."""
        if do_not_start_on_reboot:
            self._disable_pgsql_on_boot()
        cmd = operating_system.service_discovery(PGSQL_SERVICE_CANDIDATES)
        LOG.info(
            _("{guest_id}: Stopping database engine with command ({command}).")
            .format(
                guest_id=CONF.guest_id,
                command=cmd['cmd_stop'],
            )
        )
        utils.execute_with_timeout(
            *cmd['cmd_stop'].split(),
            timeout=30
        )

    def restart(self, context):
        """Restart the PgSql service."""
        LOG.info(
            _("{guest_id}: Restarting database engine.").format(
                guest_id=CONF.guest_id,
            )
        )
        try:
            PgSqlAppStatus.get().begin_restart()
            self.stop_db(context)
            self.start_db(context)
        finally:
            PgSqlAppStatus.get().end_install_or_restart()
