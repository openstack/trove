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
from oslo_utils import importutils

from trove.common.i18n import _
from trove.common import instance as rd_instance
from trove.guestagent.datastore.mysql_common import manager


MYSQL_APP = ("trove.guestagent.datastore.experimental.pxc.service."
             "PXCApp")
MYSQL_APP_STATUS = ("trove.guestagent.datastore.experimental.pxc.service."
                    "PXCAppStatus")
MYSQL_ADMIN = ("trove.guestagent.datastore.experimental.pxc.service."
               "PXCAdmin")

LOG = logging.getLogger(__name__)


class Manager(manager.MySqlManager):

    def __init__(self):
        mysql_app = importutils.import_class(MYSQL_APP)
        mysql_app_status = importutils.import_class(MYSQL_APP_STATUS)
        mysql_admin = importutils.import_class(MYSQL_ADMIN)

        super(Manager, self).__init__(mysql_app, mysql_app_status, mysql_admin)

    def do_prepare(self, context, packages, databases, memory_mb, users,
                   device_path, mount_point, backup_info,
                   config_contents, root_password, overrides,
                   cluster_config, snapshot):
        self.volume_do_not_start_on_reboot = True
        super(Manager, self).do_prepare(
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
