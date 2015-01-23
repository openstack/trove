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
from trove.common import cfg
from trove.guestagent import dbaas
from trove.guestagent import backup
from trove.guestagent import volume
from .service.config import PgSqlConfig
from .service.database import PgSqlDatabase
from .service.install import PgSqlInstall
from .service.root import PgSqlRoot
from .service.users import PgSqlUsers
from .service.status import PgSqlAppStatus
from trove.openstack.common import log as logging
from trove.openstack.common import periodic_task


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class Manager(
        periodic_task.PeriodicTasks,
        PgSqlUsers,
        PgSqlDatabase,
        PgSqlRoot,
        PgSqlConfig,
        PgSqlInstall,
):

    def __init__(self, *args, **kwargs):
        super(Manager, self).__init__(*args, **kwargs)

    @periodic_task.periodic_task(ticks_between_runs=3)
    def update_status(self, context):
        PgSqlAppStatus.get().update()

    def prepare(
            self,
            context,
            packages,
            databases,
            memory_mb,
            users,
            device_path=None,
            mount_point=None,
            backup_info=None,
            config_contents=None,
            root_password=None,
            overrides=None,
            cluster_config=None
    ):
        self.install(context, packages)
        PgSqlAppStatus.get().begin_restart()
        self.stop_db(context)
        if device_path:
            device = volume.VolumeDevice(device_path)
            device.format()
            if os.path.exists(mount_point):
                if not backup_info:
                    device.migrate_data(mount_point)
            device.mount(mount_point)
        self.reset_configuration(context, config_contents)
        self.set_db_to_listen(context)
        self.start_db(context)

        if backup_info:
            backup.restore(context, backup_info, '/tmp')

        if root_password and not backup_info:
            self.enable_root(context, root_password)

        PgSqlAppStatus.get().end_install_or_restart()

        if databases:
            self.create_database(context, databases)

        if users:
            self.create_user(context, users)

    def get_filesystem_stats(self, context, fs_path):
        mount_point = CONF.get(CONF.datastore_manager).mount_point
        return dbaas.get_filesystem_volume_stats(mount_point)

    def create_backup(self, context, backup_info):
        backup.backup(context, backup_info)

    def mount_volume(self, context, device_path=None, mount_point=None):
        """Mount the volume as specified by device_path to mount_point."""
        device = volume.VolumeDevice(device_path)
        device.mount(mount_point, write_to_fstab=False)
        LOG.debug(
            "Mounted device {device} at mount point {mount}.".format(
                device=device_path, mount=mount_point))

    def unmount_volume(self, context, device_path=None, mount_point=None):
        """Unmount the volume as specified by device_path from mount_point."""
        device = volume.VolumeDevice(device_path)
        device.unmount(mount_point)
        LOG.debug(
            "Unmounted device {device} from mount point {mount}.".format(
                device=device_path, mount=mount_point))

    def resize_fs(self, context, device_path=None, mount_point=None):
        """Resize the filesystem as specified by device_path at mount_point."""
        device = volume.VolumeDevice(device_path)
        device.resize_fs(mount_point)
        LOG.debug(
            "Resized the filesystem at {mount}.".format(
                mount=mount_point))
