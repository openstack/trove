# Copyright 2013 OpenStack Foundation
# Copyright 2013 Rackspace Hosting
# Copyright 2013 Hewlett-Packard Development Company, L.P.
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
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
import os.path

from oslo_log import log as logging

from trove.common import cfg
from trove.common import configurations
from trove.common import constants
from trove.common import exception
from trove.common.notification import EndNotification
from trove.common import utils
from trove.guestagent.common import operating_system
from trove.guestagent.datastore import manager
from trove.guestagent import guest_log
from trove.guestagent.utils import docker as docker_util
from trove.guestagent.utils import mysql as mysql_util
from trove.instance import service_status

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class MySqlManager(manager.Manager):
    def __init__(self, mysql_app, mysql_app_status, mysql_admin,
                 manager_name='mysql'):
        super(MySqlManager, self).__init__(manager_name)

        self.app = mysql_app
        self.status = mysql_app_status
        self.adm = mysql_admin
        self.volume_do_not_start_on_reboot = False

    @property
    def configuration_manager(self):
        return self.app.configuration_manager

    def get_service_status(self):
        try:
            with mysql_util.SqlClient(self.app.get_engine()) as client:
                cmd = "SELECT 1;"
                client.execute(cmd)

            LOG.debug("Database service check: database query is responsive")
            return service_status.ServiceStatuses.HEALTHY
        except Exception:
            return super(MySqlManager, self).get_service_status()

    def get_start_db_params(self, data_dir):
        return f'--datadir={data_dir}'

    def do_prepare(self, context, packages, databases, memory_mb, users,
                   device_path, mount_point, backup_info,
                   config_contents, root_password, overrides,
                   cluster_config, snapshot, ds_version=None):
        """This is called from prepare in the base class."""
        data_dir = mount_point + '/data'
        self.app.stop_db()
        operating_system.ensure_directory(
            data_dir,
            user=self.app.database_service_uid,
            group=self.app.database_service_gid,
            as_root=True)
        # This makes sure the include dir is created.
        self.app.set_data_dir(data_dir)

        # Prepare mysql configuration
        LOG.info('Preparing database configuration')
        self.app.configuration_manager.reset_configuration(config_contents)
        self.app.update_overrides(overrides)

        # Restore data from backup and reset root password
        if backup_info:
            self.perform_restore(context, data_dir, backup_info)
            self.reset_password_for_restore(ds_version=ds_version,
                                            data_dir=data_dir)

        # Start database service.
        command = self.get_start_db_params(data_dir)
        self.app.start_db(ds_version=ds_version, command=command)

        self.app.secure()
        enable_remote_root = (backup_info and self.adm.is_root_enabled())
        if enable_remote_root:
            self.status.report_root(context)
        else:
            self.app.secure_root()

        if snapshot:
            # This instance is a replication slave
            self.attach_replica(context, snapshot, snapshot['config'])

    def create_backup(self, context, backup_info):
        """Create backup for the database.

        :param context: User context object.
        :param backup_info: a dictionary containing the db instance id of the
                            backup task, location, type, and other data.
        """
        LOG.info(f"Creating backup {backup_info['id']}")
        with EndNotification(context):
            # Set /var/run/mysqld to allow localhost access.
            volumes_mapping = {
                '/var/lib/mysql': {'bind': '/var/lib/mysql', 'mode': 'rw'},
                constants.MYSQL_HOST_SOCKET_PATH: {"bind": "/var/run/mysqld",
                                                   "mode": "ro"},
                '/tmp': {'bind': '/tmp', 'mode': 'rw'}
            }
            self.app.create_backup(context, backup_info,
                                   volumes_mapping=volumes_mapping,
                                   need_dbuser=True)

    def get_datastore_log_defs(self):
        owner = cfg.get_configuration_property('database_service_uid')
        datastore_dir = self.app.get_data_dir()
        server_section = configurations.MySQLConfParser.SERVER_CONF_SECTION
        long_query_time = CONF.get(self.manager).get(
            'guest_log_long_query_time') / 1000
        general_log_file = self.build_log_file_name(
            self.GUEST_LOG_DEFS_GENERAL_LABEL, owner,
            datastore_dir=datastore_dir)
        error_log_file = self.validate_log_file('/var/log/mysqld.log', owner)
        slow_query_log_file = self.build_log_file_name(
            self.GUEST_LOG_DEFS_SLOW_QUERY_LABEL, owner,
            datastore_dir=datastore_dir)
        return {
            self.GUEST_LOG_DEFS_GENERAL_LABEL: {
                self.GUEST_LOG_TYPE_LABEL: guest_log.LogType.USER,
                self.GUEST_LOG_USER_LABEL: owner,
                self.GUEST_LOG_FILE_LABEL: general_log_file,
                self.GUEST_LOG_SECTION_LABEL: server_section,
                self.GUEST_LOG_ENABLE_LABEL: {
                    'general_log': 'on',
                    'general_log_file': general_log_file,
                    'log_output': 'file',
                },
                self.GUEST_LOG_DISABLE_LABEL: {
                    'general_log': 'off',
                },
            },
            self.GUEST_LOG_DEFS_SLOW_QUERY_LABEL: {
                self.GUEST_LOG_TYPE_LABEL: guest_log.LogType.USER,
                self.GUEST_LOG_USER_LABEL: owner,
                self.GUEST_LOG_FILE_LABEL: slow_query_log_file,
                self.GUEST_LOG_SECTION_LABEL: server_section,
                self.GUEST_LOG_ENABLE_LABEL: {
                    'slow_query_log': 'on',
                    'slow_query_log_file': slow_query_log_file,
                    'long_query_time': long_query_time,
                },
                self.GUEST_LOG_DISABLE_LABEL: {
                    'slow_query_log': 'off',
                },
            },
            self.GUEST_LOG_DEFS_ERROR_LABEL: {
                self.GUEST_LOG_TYPE_LABEL: guest_log.LogType.SYS,
                self.GUEST_LOG_USER_LABEL: owner,
                self.GUEST_LOG_FILE_LABEL: error_log_file,
            },
        }

    def is_log_enabled(self, logname):
        if logname == self.GUEST_LOG_DEFS_GENERAL_LABEL:
            value = self.configuration_manager.get_value(
                'general_log', section='mysqld', default='off')
            LOG.debug(f"The config value of general_log is {value}")
            return value == 'on'
        elif logname == self.GUEST_LOG_DEFS_SLOW_QUERY_LABEL:
            value = self.configuration_manager.get_value(
                'slow_query_log', section='mysqld', default='off')
            LOG.debug(f"The config value of slow_query_log is {value}")
            return value == 'on'

        return False

    def apply_overrides(self, context, overrides):
        LOG.info("Applying database config.")
        self.app.apply_overrides(overrides)
        LOG.info("Finished applying database config.")

    def reset_password_for_restore(self, ds_version=None,
                                   data_dir='/var/lib/mysql/data'):
        """Reset the root password after restore the db data.

        We create a temporary database container by running mysqld_safe to
        reset the root password.
        """
        LOG.info('Starting to reset password for restore')

        try:
            root_pass = self.app.get_auth_password(file="root.cnf")
        except exception.UnprocessableEntity:
            root_pass = utils.generate_random_password()
            self.app.save_password('root', root_pass)

        init_file = os.path.join(data_dir, "init.sql")
        operating_system.write_file(
            init_file,
            f"ALTER USER 'root'@'localhost' IDENTIFIED BY '{root_pass}';",
            as_root=True
        )
        # Change ownership so the database service user
        # can read it in the container
        operating_system.chown(
            init_file,
            user=self.app.database_service_uid,
            group=self.app.database_service_gid,
            as_root=True
        )

        command = (
            f'mysqld --init-file={init_file} '
            f'--datadir={data_dir} '
        )

        # Start the database container process.
        try:
            self.app.start_db(ds_version=ds_version, command=command)
        except Exception as err:
            LOG.error('Failed to reset password for restore, error: %s',
                      str(err))
            raise err  # re-raised at the end of the finally clause
        finally:
            try:
                LOG.debug(
                    'The init container log: %s',
                    docker_util.get_container_logs(self.app.docker_client)
                )
                docker_util.remove_container(self.app.docker_client)
                # Remove init.sql file after password reset
                operating_system.remove(init_file, force=True, as_root=True)
            except Exception as err:
                LOG.error('Failed to remove container or init file. error: %s',
                          str(err))
                pass
        LOG.info('Finished to reset password for restore')

    def _validate_slave_for_replication(self, context, replica_info):
        if replica_info['replication_strategy'] != self.replication_strategy:
            raise exception.IncompatibleReplicationStrategy(
                replica_info.update({
                    'guest_strategy': self.replication_strategy
                }))

        volume_stats = self.get_filesystem_stats(context, None)
        if (volume_stats.get('total', 0.0) <
                replica_info['dataset']['dataset_size']):
            raise exception.InsufficientSpaceForReplica(
                replica_info.update({
                    'slave_volume_size': volume_stats.get('total', 0.0)
                }))

    def attach_replica(self, context, replica_info, slave_config, **kwargs):
        LOG.info("Attaching replica, replica_info: %s", replica_info)
        try:
            if 'replication_strategy' in replica_info:
                self._validate_slave_for_replication(context, replica_info)

            self.replication.enable_as_slave(self.app, replica_info,
                                             slave_config)
        except Exception as err:
            LOG.error("Error enabling replication, error: %s", str(err))
            self.status.set_status(service_status.ServiceStatuses.FAILED)
            raise

    def make_read_only(self, context, read_only):
        LOG.info("Executing make_read_only(%s)", read_only)
        self.app.make_read_only(read_only)

    def get_latest_txn_id(self, context):
        LOG.info("Calling get_latest_txn_id.")
        return self.app.get_latest_txn_id()

    def get_last_txn(self, context):
        LOG.info("Calling get_last_txn")
        return self.app.get_last_txn()

    def wait_for_txn(self, context, txn):
        LOG.info("Calling wait_for_txn.")
        self.app.wait_for_txn(txn)

    def upgrade(self, context, upgrade_info):
        """Upgrade the database."""
        LOG.info('Starting to upgrade database, upgrade_info: %s',
                 upgrade_info)
        self.app.upgrade(upgrade_info)

    def rebuild(self, context, ds_version, config_contents=None,
                config_overrides=None):
        """Restore datastore service after instance rebuild."""
        LOG.info("Starting to restore database service")
        self.status.begin_install()

        mount_point = CONF.get(CONF.datastore_manager).mount_point
        data_dir = mount_point + '/data'
        operating_system.ensure_directory(data_dir,
                                          user=self.app.database_service_uid,
                                          group=self.app.database_service_gid,
                                          as_root=True)
        # This makes sure the include dir is created.
        self.app.set_data_dir(data_dir)

        try:
            # Prepare mysql configuration
            LOG.debug('Preparing database configuration')
            self.app.configuration_manager.reset_configuration(config_contents)
            self.app.update_overrides(config_overrides)

            # Start database service.
            command = self.get_start_db_params(data_dir)
            self.app.start_db(ds_version=ds_version, command=command)
        except Exception as e:
            LOG.error(f"Failed to restore database service after rebuild, "
                      f"error: {str(e)}")
            self.prepare_error = True
            raise
        finally:
            self.status.end_install(error_occurred=self.prepare_error)

    def post_create_backup(self, context, **kwargs):
        LOG.info("Running post_create_backup")
        try:
            self.app.execute_sql("UNLOCK TABLES;")

            mount_point = CONF.get(CONF.datastore_manager).mount_point
            operating_system.fsunfreeze(mount_point)
        except Exception as e:
            LOG.error("Run post_create_backup failed, error: %s" % str(e))

        return {}
