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

import re

from oslo_log import log as logging

from trove.common import cfg
from trove.common.i18n import _
from trove.common import utils
from trove.guestagent.common import operating_system
from trove.guestagent.datastore.experimental.postgresql.service.process import(
    PgSqlProcess)
from trove.guestagent.datastore.experimental.postgresql.service.status import(
    PgSqlAppStatus)

LOG = logging.getLogger(__name__)
CONF = cfg.CONF

PGSQL_CONFIG = "/etc/postgresql/{version}/main/postgresql.conf"
PGSQL_HBA_CONFIG = "/etc/postgresql/{version}/main/pg_hba.conf"


class PgSqlConfig(PgSqlProcess):
    """Mixin that implements the config API.

    This mixin has a dependency on the PgSqlProcess mixin.
    """

    def _get_psql_version(self):
        """Poll PgSql for the version number.

        Return value is a string representing the version number.
        """
        LOG.debug(
            "{guest_id}: Polling for postgresql version.".format(
                guest_id=CONF.guest_id,
            )
        )
        out, err = utils.execute('psql', '--version')
        pattern = re.compile('\d\.\d')
        return pattern.search(out).group(0)

    def reset_configuration(self, context, configuration):
        """Reset the PgSql configuration file to the one given.

        The configuration parameter is a string containing the full
        configuration file that should be used.
        """
        config_location = PGSQL_CONFIG.format(
            version=self._get_psql_version(),
        )
        LOG.debug(
            "{guest_id}: Writing configuration file to /tmp/pgsql_config."
            .format(
                guest_id=CONF.guest_id,
            )
        )
        with open('/tmp/pgsql_config', 'w+') as config_file:
            config_file.write(configuration)
        operating_system.chown('/tmp/pgsql_config', 'postgres', None,
                               recursive=False, as_root=True)
        operating_system.move('/tmp/pgsql_config', config_location, timeout=30,
                              as_root=True)

    def set_db_to_listen(self, context):
        """Allow remote connections with encrypted passwords."""
        LOG.debug(
            "{guest_id}: Writing hba file to /tmp/pgsql_hba_config.".format(
                guest_id=CONF.guest_id,
            )
        )
        # Local access from administrative users is implicitly trusted.
        #
        # Remote access from the Trove's account is always rejected as
        # it is not needed and could be used by malicious users to hijack the
        # instance.
        #
        # Connections from other accounts always require a hashed password.
        with open('/tmp/pgsql_hba_config', 'w+') as config_file:
            config_file.write(
                "local  all  postgres,os_admin    trust\n")
            config_file.write(
                "local  all  all    md5\n")
            config_file.write(
                "host  all  postgres,os_admin  127.0.0.1/32  trust\n")
            config_file.write(
                "host  all  postgres,os_admin  ::1/128  trust\n")
            config_file.write(
                "host  all  postgres,os_admin  localhost  trust\n")
            config_file.write(
                "host  all  os_admin  0.0.0.0/0  reject\n")
            config_file.write(
                "host  all  os_admin  ::/0  reject\n")
            config_file.write(
                "host  all  all  0.0.0.0/0  md5\n")
            config_file.write(
                "host  all  all  ::/0  md5\n")

        operating_system.chown('/tmp/pgsql_hba_config',
                               'postgres', None, recursive=False, as_root=True)
        operating_system.move('/tmp/pgsql_hba_config', PGSQL_HBA_CONFIG.format(
            version=self._get_psql_version(),
        ), timeout=30, as_root=True)

    def start_db_with_conf_changes(self, context, config_contents):
        """Restarts the PgSql instance with a new configuration."""
        LOG.info(
            _("{guest_id}: Going into restart mode for config file changes.")
            .format(
                guest_id=CONF.guest_id,
            )
        )
        PgSqlAppStatus.get().begin_restart()
        self.stop_db(context)
        self.reset_configuration(context, config_contents)
        self.start_db(context)
        LOG.info(
            _("{guest_id}: Ending restart mode for config file changes.")
            .format(
                guest_id=CONF.guest_id,
            )
        )
        PgSqlAppStatus.get().end_restart()
