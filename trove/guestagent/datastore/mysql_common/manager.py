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
import tempfile

from oslo_log import log as logging

from trove.common import cfg
from trove.common import configurations
from trove.common import exception
from trove.common import utils
from trove.common.notification import EndNotification
from trove.guestagent import guest_log
from trove.guestagent.common import operating_system
from trove.guestagent.datastore import manager
from trove.guestagent.strategies import replication as repl_strategy
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

    @property
    def replication(self):
        """If the datastore supports replication, return an instance of
        the strategy.
        """
        try:
            return repl_strategy.get_instance(self.manager)
        except Exception as ex:
            LOG.warning("Cannot get replication instance for '%(manager)s': "
                        "%(msg)s", {'manager': self.manager, 'msg': str(ex)})

        return None

    def get_service_status(self):
        try:
            with mysql_util.SqlClient(self.app.get_engine()) as client:
                cmd = "SELECT 1;"
                client.execute(cmd)

            LOG.debug("Database service check: database query is responsive")
            return service_status.ServiceStatuses.HEALTHY
        except Exception:
            return super(MySqlManager, self).get_service_status()

    def create_database(self, context, databases):
        with EndNotification(context):
            return self.adm.create_database(databases)

    def create_user(self, context, users):
        with EndNotification(context):
            self.adm.create_user(users)

    def delete_database(self, context, database):
        with EndNotification(context):
            return self.adm.delete_database(database)

    def delete_user(self, context, user):
        with EndNotification(context):
            self.adm.delete_user(user)

    def list_databases(self, context, limit=None, marker=None,
                       include_marker=False):
        return self.adm.list_databases(limit, marker, include_marker)

    def list_users(self, context, limit=None, marker=None,
                   include_marker=False):
        return self.adm.list_users(limit, marker, include_marker)

    def get_user(self, context, username, hostname):
        return self.adm.get_user(username, hostname)

    def update_attributes(self, context, username, hostname, user_attrs):
        with EndNotification(context):
            self.adm.update_attributes(username, hostname, user_attrs)

    def grant_access(self, context, username, hostname, databases):
        return self.adm.grant_access(username, hostname, databases)

    def revoke_access(self, context, username, hostname, database):
        return self.adm.revoke_access(username, hostname, database)

    def list_access(self, context, username, hostname):
        return self.adm.list_access(username, hostname)

    def enable_root(self, context):
        return self.adm.enable_root()

    def enable_root_with_password(self, context, root_password=None):
        return self.adm.enable_root(root_password)

    def is_root_enabled(self, context):
        return self.adm.is_root_enabled()

    def disable_root(self, context):
        return self.adm.disable_root()

    def change_passwords(self, context, users):
        with EndNotification(context):
            self.adm.change_passwords(users)

    def do_prepare(self, context, packages, databases, memory_mb, users,
                   device_path, mount_point, backup_info,
                   config_contents, root_password, overrides,
                   cluster_config, snapshot, ds_version=None):
        """This is called from prepare in the base class."""
        data_dir = mount_point + '/data'
        self.app.stop_db()
        operating_system.create_directory(data_dir,
                                          user=CONF.database_service_uid,
                                          group=CONF.database_service_uid,
                                          as_root=True)
        # This makes sure the include dir is created.
        self.app.set_data_dir(data_dir)

        # Prepare mysql configuration
        LOG.info('Preparing database configuration')
        self.app.configuration_manager.save_configuration(config_contents)
        self.app.update_overrides(overrides)

        # Restore data from backup and reset root password
        if backup_info:
            self.perform_restore(context, data_dir, backup_info)
            self.reset_password_for_restore(ds_version=ds_version,
                                            data_dir=data_dir)

        # Start database service.
        # Cinder volume initialization(after formatted) may leave a
        # lost+found folder
        # The --ignore-db-dir option is deprecated in MySQL 5.7. With the
        # introduction of the data dictionary in MySQL 8.0, it became
        # superfluous and was removed in that version.
        command = (f'--ignore-db-dir=lost+found --ignore-db-dir=conf.d '
                   f'--datadir={data_dir}')
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

    def stop_db(self, context):
        self.app.stop_db()

    def restart(self, context):
        self.app.restart()

    def start_db_with_conf_changes(self, context, config_contents, ds_version):
        self.app.start_db_with_conf_changes(config_contents, ds_version)

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

    def apply_overrides(self, context, overrides):
        LOG.info("Applying overrides (%s).", overrides)
        self.app.apply_overrides(overrides)

    def update_overrides(self, context, overrides, remove=False):
        if remove:
            self.app.remove_overrides()
        self.app.update_overrides(overrides)

    def create_backup(self, context, backup_info):
        """
        Entry point for initiating a backup for this guest agents db instance.
        The call currently blocks until the backup is complete or errors. If
        device_path is specified, it will be mounted based to a point specified
        in configuration.

        :param context: User context object.
        :param backup_info: a dictionary containing the db instance id of the
                            backup task, location, type, and other data.
        """
        with EndNotification(context):
            self.app.create_backup(context, backup_info)

    def perform_restore(self, context, restore_location, backup_info):
        LOG.info("Starting to restore database from backup %s, "
                 "backup_info: %s", backup_info['id'], backup_info)

        try:
            self.app.restore_backup(context, backup_info, restore_location)
        except Exception:
            LOG.error("Failed to restore from backup %s.", backup_info['id'])
            self.status.set_status(service_status.ServiceStatuses.FAILED)
            raise

        LOG.info("Finished restore data from backup %s", backup_info['id'])

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

        with tempfile.NamedTemporaryFile(mode='w') as init_file, \
            tempfile.NamedTemporaryFile(suffix='.err') as err_file:
            operating_system.write_file(
                init_file.name,
                f"ALTER USER 'root'@'localhost' IDENTIFIED BY '{root_pass}';"
            )
            command = (
                f'mysqld_safe --init-file={init_file.name} '
                f'--log-error={err_file.name} '
                f'--datadir={data_dir}'
            )
            extra_volumes = {
                init_file.name: {"bind": init_file.name, "mode": "rw"},
                err_file.name: {"bind": err_file.name, "mode": "rw"},
            }

            # Allow database service user to access the temporary files.
            for file in [init_file.name, err_file.name]:
                operating_system.chmod(file,
                                       operating_system.FileMode.SET_ALL_RWX(),
                                       force=True, as_root=True)

            try:
                self.app.start_db(ds_version=ds_version, command=command,
                                  extra_volumes=extra_volumes)
            except Exception as err:
                LOG.error('Failed to reset password for restore, error: %s',
                          str(err))
                LOG.debug('Content in init error log file: %s',
                          err_file.read())
                raise err
            finally:
                LOG.debug(
                    'The init container log: %s',
                    docker_util.get_container_logs(self.app.docker_client)
                )
                docker_util.remove_container(self.app.docker_client)

        LOG.info('Finished to reset password for restore')

    def attach_replica(self, context, replica_info, slave_config):
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

    def detach_replica(self, context, for_failover=False):
        LOG.info("Detaching replica.")
        replica_info = self.replication.detach_slave(self.app, for_failover)
        return replica_info

    def backup_required_for_replication(self, context):
        return self.replication.backup_required_for_replication()

    def get_replication_snapshot(self, context, snapshot_info,
                                 replica_source_config=None):
        LOG.info("Getting replication snapshot, snapshot_info: %s",
                 snapshot_info)

        self.replication.enable_as_master(self.app, replica_source_config)
        LOG.info('Enabled as replication master')

        snapshot_id, log_position = self.replication.snapshot_for_replication(
            context, self.app, self.adm, None, snapshot_info)

        volume_stats = self.get_filesystem_stats(context, None)

        replication_snapshot = {
            'dataset': {
                'datastore_manager': self.manager,
                'dataset_size': volume_stats.get('used', 0.0),
                'volume_size': volume_stats.get('total', 0.0),
                'snapshot_id': snapshot_id
            },
            'replication_strategy': self.replication_strategy,
            'master': self.replication.get_master_ref(self.app, snapshot_info),
            'log_position': log_position
        }

        return replication_snapshot

    def enable_as_master(self, context, replica_source_config):
        LOG.info("Enable as master")
        self.replication.enable_as_master(self.app, replica_source_config)

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

    def get_replica_context(self, context):
        LOG.info("Getting replica context.")
        replica_info = self.replication.get_replica_context(self.app, self.adm)
        return replica_info

    def demote_replication_master(self, context):
        LOG.info("Demoting replication master.")
        self.replication.demote_master(self.app)

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
        operating_system.create_directory(data_dir,
                                          user=CONF.database_service_uid,
                                          group=CONF.database_service_uid,
                                          as_root=True)
        # This makes sure the include dir is created.
        self.app.set_data_dir(data_dir)

        try:
            # Prepare mysql configuration
            LOG.debug('Preparing database configuration')
            self.app.configuration_manager.save_configuration(config_contents)
            self.app.update_overrides(config_overrides)

            # Start database service.
            # Cinder volume initialization(after formatted) may leave a
            # lost+found folder
            # The --ignore-db-dir option is deprecated in MySQL 5.7. With the
            # introduction of the data dictionary in MySQL 8.0, it became
            # superfluous and was removed in that version.
            command = (f'--ignore-db-dir=lost+found --ignore-db-dir=conf.d '
                       f'--datadir={data_dir}')
            self.app.start_db(ds_version=ds_version, command=command)
        except Exception as e:
            LOG.error(f"Failed to restore database service after rebuild, "
                      f"error: {str(e)}")
            self.prepare_error = True
            raise
        finally:
            self.status.end_install(error_occurred=self.prepare_error)
