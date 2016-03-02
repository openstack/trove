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

from oslo_log import log as logging

from trove.common.i18n import _
from trove.common import instance as rd_instance
from trove.guestagent.datastore.mysql_common import manager


LOG = logging.getLogger(__name__)


class GaleraManager(manager.MySqlManager):

    def __init__(self, mysql_app, mysql_app_status, mysql_admin,
                 manager_name='galera'):

        super(GaleraManager, self).__init__(
            mysql_app, mysql_app_status, mysql_admin, manager_name)
        self._mysql_app = mysql_app
        self._mysql_app_status = mysql_app_status
        self._mysql_admin = mysql_admin

        self.volume_do_not_start_on_reboot = False

    def do_prepare(self, context, packages, databases, memory_mb, users,
                   device_path, mount_point, backup_info,
                   config_contents, root_password, overrides,
                   cluster_config, snapshot):
        self.volume_do_not_start_on_reboot = True
        super(GaleraManager, self).do_prepare(
            context, packages, databases, memory_mb, users,
            device_path, mount_point, backup_info,
            config_contents, root_password, overrides,
            cluster_config, snapshot)

    def install_cluster(self, context, replication_user, cluster_configuration,
                        bootstrap):
        app = self.mysql_app(self.mysql_app_status.get())
        try:
            app.install_cluster(
                replication_user, cluster_configuration, bootstrap)
            LOG.debug("install_cluster call has finished.")
        except Exception:
            LOG.exception(_('Cluster installation failed.'))
            app.status.set_status(
                rd_instance.ServiceStatuses.FAILED)
            raise

    def reset_admin_password(self, context, admin_password):
        LOG.debug("Storing the admin password on the instance.")
        app = self.mysql_app(self.mysql_app_status.get())
        app.reset_admin_password(admin_password)

    def get_cluster_context(self, context):
        LOG.debug("Getting the cluster context.")
        app = self.mysql_app(self.mysql_app_status.get())
        return app.get_cluster_context()

    def write_cluster_configuration_overrides(self, context,
                                              cluster_configuration):
        LOG.debug("Apply the updated cluster configuration.")
        app = self.mysql_app(self.mysql_app_status.get())
        app.write_cluster_configuration_overrides(cluster_configuration)

    def enable_root_with_password(self, context, root_password=None):
        return self.mysql_admin().enable_root(root_password)
