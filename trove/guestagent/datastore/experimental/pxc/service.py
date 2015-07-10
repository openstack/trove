# Copyright 2015 Tesora, Inc.
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
import sqlalchemy
from sqlalchemy.sql.expression import text

from trove.common.i18n import _
from trove.common import utils
from trove.guestagent.common import sql_query
from trove.guestagent.datastore.experimental.pxc import system
from trove.guestagent.datastore.mysql import service_base


LOG = logging.getLogger(__name__)
CONF = service_base.CONF

CNF_CLUSTER = "cluster"


class KeepAliveConnection(service_base.BaseKeepAliveConnection):
    pass


class PXCAppStatus(service_base.BaseMySqlAppStatus):
    pass


class LocalSqlClient(service_base.BaseLocalSqlClient):
    pass


class PXCApp(service_base.BaseMySqlApp):
    def __init__(self, status):
        super(PXCApp, self).__init__(status, LocalSqlClient,
                                     KeepAliveConnection)

    def _test_mysql(self):
        engine = sqlalchemy.create_engine("mysql://root:@localhost:3306",
                                          echo=True)
        try:
            with LocalSqlClient(engine) as client:
                out = client.execute(text("select 1;"))
                for line in out:
                    LOG.debug("line: %s" % line)
                return True
        except Exception:
            return False

    def _wait_for_mysql_to_be_really_alive(self, max_time):
        utils.poll_until(self._test_mysql, sleep_time=3, time_out=max_time)

    def secure(self, config_contents, overrides):
        LOG.info(_("Generating admin password."))
        admin_password = utils.generate_random_password()
        service_base.clear_expired_password()
        engine = sqlalchemy.create_engine("mysql://root:@localhost:3306",
                                          echo=True)
        with LocalSqlClient(engine) as client:
            self._remove_anonymous_user(client)
            self._create_admin_user(client, admin_password)
        self.stop_db()
        self._reset_configuration(config_contents, admin_password)
        self._apply_user_overrides(overrides)
        self.start_mysql()
        # TODO(cp16net) figure out reason for PXC not updating the password
        try:
            with LocalSqlClient(engine) as client:
                query = text("select Host, User from mysql.user;")
                client.execute(query)
        except Exception:
            LOG.debug('failed to query mysql')
        # creating the admin user after the config files are written because
        # percona pxc was not commiting the grant for the admin user after
        # removing the annon users.
        self._wait_for_mysql_to_be_really_alive(
            CONF.timeout_wait_for_service)
        with LocalSqlClient(engine) as client:
            self._create_admin_user(client, admin_password)
        self.stop_db()

        self._reset_configuration(config_contents, admin_password)
        self._apply_user_overrides(overrides)
        self.start_mysql()
        self._wait_for_mysql_to_be_really_alive(
            CONF.timeout_wait_for_service)
        LOG.debug("MySQL secure complete.")

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
            mysql_service = system.service_discovery(
                service_base.MYSQL_SERVICE_CANDIDATES)
            utils.execute_with_timeout(
                mysql_service['cmd_bootstrap_pxc_cluster'],
                shell=True, timeout=timeout)
        except KeyError:
            LOG.exception(_("Error bootstrapping cluster."))
            raise RuntimeError(_("Service is not discovered."))

    def install_cluster(self, replication_user, cluster_configuration,
                        bootstrap=False):
        LOG.info(_("Installing cluster configuration."))
        self._grant_cluster_replication_privilege(replication_user)
        self.stop_db()
        self.configuration_manager.apply_system_override(cluster_configuration,
                                                         CNF_CLUSTER)
        self.wipe_ib_logfiles()
        LOG.debug("bootstrap the instance? : %s" % bootstrap)
        # Have to wait to sync up the joiner instances with the donor instance.
        if bootstrap:
            self._bootstrap_cluster(timeout=CONF.restore_usage_timeout)
        else:
            self.start_mysql(timeout=CONF.restore_usage_timeout)


class PXCRootAccess(service_base.BaseMySqlRootAccess):
    def __init__(self):
        super(PXCRootAccess, self).__init__(LocalSqlClient,
                                            PXCApp(PXCAppStatus.get()))


class PXCAdmin(service_base.BaseMySqlAdmin):
    def __init__(self):
        super(PXCAdmin, self).__init__(LocalSqlClient, PXCRootAccess(),
                                       PXCApp)
