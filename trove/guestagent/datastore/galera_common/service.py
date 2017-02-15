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

import abc

from oslo_log import log as logging
from sqlalchemy.sql.expression import text

from trove.common.i18n import _
from trove.common import utils
from trove.guestagent.common import sql_query
from trove.guestagent.datastore.mysql_common import service


LOG = logging.getLogger(__name__)
CONF = service.CONF


class GaleraApp(service.BaseMySqlApp):

    def __init__(self, status, local_sql_client, keep_alive_connection_cls):
        super(GaleraApp, self).__init__(status, local_sql_client,
                                        keep_alive_connection_cls)

    def _grant_cluster_replication_privilege(self, replication_user):
        LOG.info(_("Granting Replication Slave privilege."))
        with self.local_sql_client(self.get_engine()) as client:
            perms = ['REPLICATION CLIENT', 'RELOAD', 'LOCK TABLES']
            g = sql_query.Grant(permissions=perms,
                                user=replication_user['name'],
                                clear=replication_user['password'])
            t = text(str(g))
            client.execute(t)

    def _bootstrap_cluster(self, timeout=120):
        LOG.info(_("Bootstraping cluster."))
        try:
            utils.execute_with_timeout(
                self.mysql_service['cmd_bootstrap_galera_cluster'],
                shell=True, timeout=timeout)
        except KeyError:
            LOG.exception(_("Error bootstrapping cluster."))
            raise RuntimeError(_("Service is not discovered."))

    def write_cluster_configuration_overrides(self, cluster_configuration):
        self.configuration_manager.apply_system_override(
            cluster_configuration, 'cluster')

    def install_cluster(self, replication_user, cluster_configuration,
                        bootstrap=False):
        LOG.info(_("Installing cluster configuration."))
        self._grant_cluster_replication_privilege(replication_user)
        self.stop_db()
        self.write_cluster_configuration_overrides(cluster_configuration)
        self.wipe_ib_logfiles()
        LOG.debug("bootstrap the instance? : %s", bootstrap)
        # Have to wait to sync up the joiner instances with the donor instance.
        if bootstrap:
            self._bootstrap_cluster(timeout=CONF.restore_usage_timeout)
        else:
            self.start_mysql(timeout=CONF.restore_usage_timeout)

    @abc.abstractproperty
    def cluster_configuration(self):
        """
        Returns the cluster section from the configuration manager.
        """

    def get_cluster_context(self):
        auth = self.cluster_configuration.get(
            "wsrep_sst_auth").replace('"', '')
        cluster_name = self.cluster_configuration.get("wsrep_cluster_name")
        return {
            'replication_user': {
                'name': auth.split(":")[0],
                'password': auth.split(":")[1],
            },
            'cluster_name': cluster_name,
            'admin_password': self.get_auth_password()
        }
