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

from oslo_log import log as logging

from .service.config import PgSqlConfig
from .service.database import PgSqlDatabase
from .service.install import PgSqlInstall
from .service.root import PgSqlRoot
from .service.status import PgSqlAppStatus

from trove.common import cfg
from trove.common.notification import EndNotification
from trove.guestagent import backup
from trove.guestagent.datastore.experimental.postgresql import pgutil
from trove.guestagent.datastore import manager
from trove.guestagent.db import models
from trove.guestagent import guest_log
from trove.guestagent import volume


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class Manager(
        PgSqlDatabase,
        PgSqlRoot,
        PgSqlConfig,
        PgSqlInstall,
        manager.Manager
):

    PG_BUILTIN_ADMIN = 'postgres'

    def __init__(self):
        super(Manager, self).__init__('postgresql')

    @property
    def status(self):
        return PgSqlAppStatus.get()

    @property
    def configuration_manager(self):
        return self._configuration_manager

    @property
    def datastore_log_defs(self):
        datastore_dir = '/var/log/postgresql/'
        long_query_time = CONF.get(self.manager).get(
            'guest_log_long_query_time')
        general_log_file = self.build_log_file_name(
            self.GUEST_LOG_DEFS_GENERAL_LABEL, self.PGSQL_OWNER,
            datastore_dir=datastore_dir)
        general_log_dir, general_log_filename = os.path.split(general_log_file)
        return {
            self.GUEST_LOG_DEFS_GENERAL_LABEL: {
                self.GUEST_LOG_TYPE_LABEL: guest_log.LogType.USER,
                self.GUEST_LOG_USER_LABEL: self.PGSQL_OWNER,
                self.GUEST_LOG_FILE_LABEL: general_log_file,
                self.GUEST_LOG_ENABLE_LABEL: {
                    'logging_collector': 'on',
                    'log_destination': self._quote('stderr'),
                    'log_directory': self._quote(general_log_dir),
                    'log_filename': self._quote(general_log_filename),
                    'log_statement': self._quote('all'),
                    'debug_print_plan': 'on',
                    'log_min_duration_statement': long_query_time,
                },
                self.GUEST_LOG_DISABLE_LABEL: {
                    'logging_collector': 'off',
                },
                self.GUEST_LOG_RESTART_LABEL: True,
            },
        }

    def do_prepare(self, context, packages, databases, memory_mb, users,
                   device_path, mount_point, backup_info, config_contents,
                   root_password, overrides, cluster_config, snapshot):
        pgutil.PG_ADMIN = self.PG_BUILTIN_ADMIN
        self.install(context, packages)
        self.stop_db(context)
        if device_path:
            device = volume.VolumeDevice(device_path)
            device.format()
            if os.path.exists(mount_point):
                device.migrate_data(mount_point)
            device.mount(mount_point)
        self.configuration_manager.save_configuration(config_contents)
        self.apply_initial_guestagent_configuration()

        if backup_info:
            pgutil.PG_ADMIN = self.ADMIN_USER
            backup.restore(context, backup_info, '/tmp')

        self.start_db(context)

        if not backup_info:
            self._secure(context)

    def _secure(self, context):
        # Create a new administrative user for Trove and also
        # disable the built-in superuser.
        os_admin_db = models.PostgreSQLSchema(self.ADMIN_USER)
        self._create_database(context, os_admin_db)
        self._create_admin_user(context, databases=[os_admin_db])
        pgutil.PG_ADMIN = self.ADMIN_USER
        postgres = models.PostgreSQLRootUser()
        self.alter_user(context, postgres, 'NOSUPERUSER', 'NOLOGIN')

    def create_backup(self, context, backup_info):
        with EndNotification(context):
            self.enable_backups()
            backup.backup(context, backup_info)
