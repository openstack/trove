# Copyright 2020 Catalyst Cloud
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.
import os

from oslo_log import log as logging

from trove.common import cfg
from trove.common.notification import EndNotification
from trove.guestagent import guest_log
from trove.guestagent.common import operating_system
from trove.guestagent.datastore import manager
from trove.guestagent.datastore.postgres import service

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class PostgresManager(manager.Manager):
    def __init__(self):
        super(PostgresManager, self).__init__('postgres')

        self.status = service.PgSqlAppStatus(self.docker_client)
        self.app = service.PgSqlApp(self.status, self.docker_client)
        self.adm = service.PgSqlAdmin(service.SUPER_USER_NAME)

    @property
    def configuration_manager(self):
        return self.app.configuration_manager

    def do_prepare(self, context, packages, databases, memory_mb, users,
                   device_path, mount_point, backup_info,
                   config_contents, root_password, overrides,
                   cluster_config, snapshot, ds_version=None):
        operating_system.ensure_directory(self.app.datadir,
                                          user=CONF.database_service_uid,
                                          group=CONF.database_service_uid,
                                          as_root=True)
        operating_system.ensure_directory(service.WAL_ARCHIVE_DIR,
                                          user=CONF.database_service_uid,
                                          group=CONF.database_service_uid,
                                          as_root=True)

        LOG.info('Preparing database config files')
        self.app.configuration_manager.save_configuration(config_contents)
        self.app.set_data_dir(self.app.datadir)
        self.app.update_overrides(overrides)

        # Restore data from backup and reset root password
        if backup_info:
            self.perform_restore(context, self.app.datadir, backup_info)

            signal_file = f"{self.app.datadir}/recovery.signal"
            operating_system.execute_shell_cmd(
                f"touch {signal_file}", [], shell=True, as_root=True)
            operating_system.chown(signal_file, CONF.database_service_uid,
                                   CONF.database_service_uid, force=True,
                                   as_root=True)

        # config_file can only be set on the postgres command line
        command = f"postgres -c config_file={service.CONFIG_FILE}"
        self.app.start_db(ds_version=ds_version, command=command)
        self.app.secure()

        # if snapshot:
        #     # This instance is a replication slave
        #     self.attach_replica(context, snapshot, snapshot['config'])

    def apply_overrides(self, context, overrides):
        pass

    def get_datastore_log_defs(self):
        owner = cfg.get_configuration_property('database_service_uid')
        datastore_dir = self.app.get_data_dir()
        long_query_time = CONF.get(self.manager).get(
            'guest_log_long_query_time')
        general_log_file = self.build_log_file_name(
            self.GUEST_LOG_DEFS_GENERAL_LABEL, owner,
            datastore_dir=datastore_dir)
        general_log_dir, general_log_filename = os.path.split(general_log_file)
        return {
            self.GUEST_LOG_DEFS_GENERAL_LABEL: {
                self.GUEST_LOG_TYPE_LABEL: guest_log.LogType.USER,
                self.GUEST_LOG_USER_LABEL: owner,
                self.GUEST_LOG_FILE_LABEL: general_log_file,
                self.GUEST_LOG_ENABLE_LABEL: {
                    'logging_collector': True,
                    'log_destination': 'stderr',
                    'log_directory': general_log_dir,
                    'log_filename': general_log_filename,
                    'log_statement': 'all',
                    'debug_print_plan': True,
                    'log_min_duration_statement': long_query_time,
                },
                self.GUEST_LOG_DISABLE_LABEL: {
                    'logging_collector': False,
                },
                self.GUEST_LOG_RESTART_LABEL: True,
            },
        }

    def is_log_enabled(self, logname):
        return self.configuration_manager.get_value('logging_collector', False)

    def create_backup(self, context, backup_info):
        """Create backup for the database.

        :param context: User context object.
        :param backup_info: a dictionary containing the db instance id of the
                            backup task, location, type, and other data.
        """
        LOG.info(f"Creating backup {backup_info['id']}")
        with EndNotification(context):
            volumes_mapping = {
                '/var/lib/postgresql/data': {
                    'bind': '/var/lib/postgresql/data', 'mode': 'rw'
                },
                "/var/run/postgresql": {"bind": "/var/run/postgresql",
                                        "mode": "ro"},
            }
            extra_params = f"--pg-wal-archive-dir {service.WAL_ARCHIVE_DIR}"

            self.app.create_backup(context, backup_info,
                                   volumes_mapping=volumes_mapping,
                                   need_dbuser=False,
                                   extra_params=extra_params)
