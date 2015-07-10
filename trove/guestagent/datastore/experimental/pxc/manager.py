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

import os

from oslo_log import log as logging
from oslo_utils import importutils

from trove.common import cfg
from trove.common.i18n import _
from trove.common import instance as rd_instance
from trove.guestagent.common import operating_system
from trove.guestagent.datastore.mysql import manager_base
from trove.guestagent.datastore.mysql import service_base
from trove.guestagent.strategies.replication import get_replication_strategy
from trove.guestagent import volume

LOG = logging.getLogger(__name__)
CONF = cfg.CONF
MANAGER = CONF.datastore_manager if CONF.datastore_manager else 'mysql'
REPLICATION_STRATEGY = CONF.get(MANAGER).replication_strategy
REPLICATION_NAMESPACE = CONF.get(MANAGER).replication_namespace
REPLICATION_STRATEGY_CLASS = get_replication_strategy(REPLICATION_STRATEGY,
                                                      REPLICATION_NAMESPACE)

MYSQL_APP = "trove.guestagent.datastore.experimental.pxc." \
            "service.PXCApp"
MYSQL_APP_STATUS = "trove.guestagent.datastore.experimental.pxc." \
                   "service.PXCAppStatus"
MYSQL_ADMIN = "trove.guestagent.datastore.experimental.pxc." \
              "service.PXCAdmin"


class Manager(manager_base.BaseMySqlManager):

    def __init__(self):
        mysql_app = importutils.import_class(MYSQL_APP)
        mysql_app_status = importutils.import_class(MYSQL_APP_STATUS)
        mysql_admin = importutils.import_class(MYSQL_ADMIN)

        super(Manager, self).__init__(mysql_app, mysql_app_status,
                                      mysql_admin, REPLICATION_STRATEGY,
                                      REPLICATION_NAMESPACE,
                                      REPLICATION_STRATEGY_CLASS, MANAGER)

    def prepare(self, context, packages, databases, memory_mb, users,
                device_path=None, mount_point=None, backup_info=None,
                config_contents=None, root_password=None, overrides=None,
                cluster_config=None, snapshot=None):
        """Makes ready DBAAS on a Guest container."""
        self.mysql_app_status.get().begin_install()
        # status end_mysql_install set with secure()
        app = self.mysql_app(self.mysql_app_status.get())
        app.install_if_needed(packages)
        if device_path:
            # stop and do not update database
            app.stop_db(do_not_start_on_reboot=True)
            device = volume.VolumeDevice(device_path)
            # unmount if device is already mounted
            device.unmount_device(device_path)
            device.format()
            if os.path.exists(mount_point):
                # rsync existing data to a "data" sub-directory
                # on the new volume
                device.migrate_data(mount_point, target_subdir="data")
            # mount the volume
            device.mount(mount_point)
            operating_system.chown(
                mount_point, service_base.MYSQL_OWNER,
                service_base.MYSQL_OWNER,
                recursive=False, as_root=True)

            LOG.debug("Mounted the volume at %s." % mount_point)
            # We need to temporarily update the default my.cnf so that
            # mysql will start after the volume is mounted. Later on it
            # will be changed based on the config template
            # (see MySqlApp.secure()) and restart.
            app.set_data_dir(mount_point + '/data')
            app.start_mysql()
        if backup_info:
            self._perform_restore(backup_info, context,
                                  mount_point + "/data", app)
        LOG.debug("Securing MySQL now.")
        app.secure(config_contents, overrides)
        enable_root_on_restore = (backup_info and
                                  MySqlAdmin().is_root_enabled())
        if root_password and not backup_info:
            app.secure_root(secure_remote_root=True)
            MySqlAdmin().enable_root(root_password)
        elif enable_root_on_restore:
            app.secure_root(secure_remote_root=False)
            app.get().report_root(context, 'root')
        else:
            app.secure_root(secure_remote_root=True)

        if cluster_config is None:
            app.complete_install_or_restart()
        else:
            app.status.set_status(
                rd_instance.ServiceStatuses.BUILD_PENDING)

        if databases:
            self.create_database(context, databases)

        if users:
            self.create_user(context, users)

        if snapshot:
            self.attach_replica(context, snapshot, snapshot['config'])

        LOG.info(_('Completed setup of MySQL database instance.'))

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

    def cluster_complete(self, context):
        LOG.debug("Cluster creation complete, starting status checks.")
        app = self.mysql_app(self.mysql_app_status.get())
        status = app.status._get_actual_db_status()
        app.status.set_status(status)
