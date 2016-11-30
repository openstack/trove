# Copyright (c) 2013 OpenStack Foundation
# Copyright (c) 2016 Tesora, Inc.
#
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

from collections import OrderedDict
import os
import re

from oslo_log import log as logging
import psycopg2

from trove.common import cfg
from trove.common.db.postgresql import models
from trove.common import exception
from trove.common.i18n import _
from trove.common import instance
from trove.common.stream_codecs import PropertiesCodec
from trove.common import utils
from trove.guestagent.common.configuration import ConfigurationManager
from trove.guestagent.common.configuration import OneFileOverrideStrategy
from trove.guestagent.common import guestagent_utils
from trove.guestagent.common import operating_system
from trove.guestagent.common.operating_system import FileMode
from trove.guestagent.datastore.experimental.postgresql import pgsql_query
from trove.guestagent.datastore import service
from trove.guestagent import pkg

LOG = logging.getLogger(__name__)
CONF = cfg.CONF

BACKUP_CFG_OVERRIDE = 'PgBaseBackupConfig'
DEBUG_MODE_OVERRIDE = 'DebugLevelOverride'


class PgSqlApp(object):

    OS = operating_system.get_os()
    LISTEN_ADDRESSES = ['*']  # Listen on all available IP (v4/v6) interfaces.
    ADMIN_USER = 'os_admin'  # Trove's administrative user.

    def __init__(self):
        super(PgSqlApp, self).__init__()

        self._current_admin_user = None
        self.status = PgSqlAppStatus(self.pgsql_extra_bin_dir)

        revision_dir = guestagent_utils.build_file_path(
            os.path.dirname(self.pgsql_config),
            ConfigurationManager.DEFAULT_STRATEGY_OVERRIDES_SUB_DIR)
        self.configuration_manager = ConfigurationManager(
            self.pgsql_config, self.pgsql_owner, self.pgsql_owner,
            PropertiesCodec(
                delimiter='=',
                string_mappings={'on': True, 'off': False, "''": None}),
            requires_root=True,
            override_strategy=OneFileOverrideStrategy(revision_dir))

    @property
    def service_candidates(self):
        return ['postgresql']

    @property
    def pgsql_owner(self):
        return 'postgres'

    @property
    def default_superuser_name(self):
        return "postgres"

    @property
    def pgsql_base_data_dir(self):
        return '/var/lib/postgresql/'

    @property
    def pgsql_pid_file(self):
        return guestagent_utils.build_file_path(self.pgsql_run_dir,
                                                'postgresql.pid')

    @property
    def pgsql_run_dir(self):
        return '/var/run/postgresql/'

    @property
    def pgsql_extra_bin_dir(self):
        """Redhat and Ubuntu packages for PgSql do not place 'extra' important
        binaries in /usr/bin, but rather in a directory like /usr/pgsql-9.4/bin
        in the case of PostgreSQL 9.4 for RHEL/CentOS
        """
        return {
            operating_system.DEBIAN: '/usr/lib/postgresql/%s/bin/',
            operating_system.REDHAT: '/usr/pgsql-%s/bin/',
            operating_system.SUSE: '/usr/bin/'
        }[self.OS] % self.pg_version[1]

    @property
    def pgsql_config(self):
        return self._find_config_file('postgresql.conf')

    @property
    def pgsql_hba_config(self):
        return self._find_config_file('pg_hba.conf')

    @property
    def pgsql_ident_config(self):
        return self._find_config_file('pg_ident.conf')

    def _find_config_file(self, name_pattern):
        version_base = guestagent_utils.build_file_path(self.pgsql_config_dir,
                                                        self.pg_version[1])
        return sorted(operating_system.list_files_in_directory(
            version_base, recursive=True, pattern=name_pattern,
            as_root=True), key=len)[0]

    @property
    def pgsql_config_dir(self):
        return {
            operating_system.DEBIAN: '/etc/postgresql/',
            operating_system.REDHAT: '/var/lib/postgresql/',
            operating_system.SUSE: '/var/lib/pgsql/'
        }[self.OS]

    @property
    def pgsql_log_dir(self):
        return "/var/log/postgresql/"

    def build_admin(self):
        return PgSqlAdmin(self.get_current_admin_user())

    def update_overrides(self, context, overrides, remove=False):
        if remove:
            self.configuration_manager.remove_user_override()
        elif overrides:
            self.configuration_manager.apply_user_override(overrides)

    def set_current_admin_user(self, user):
        self._current_admin_user = user

    def get_current_admin_user(self):
        if self._current_admin_user is not None:
            return self._current_admin_user

        if self.status.is_installed:
            return models.PostgreSQLUser(self.ADMIN_USER)

        return models.PostgreSQLUser(self.default_superuser_name)

    def apply_overrides(self, context, overrides):
        self.reload_configuration()

    def reload_configuration(self):
        """Send a signal to the server, causing configuration files to be
        reloaded by all server processes.
        Active queries or connections to the database will not be
        interrupted.

        NOTE: Do not use the 'SET' command as it only affects the current
        session.
        """
        self.build_admin().psql(
            "SELECT pg_reload_conf()")

    def reset_configuration(self, context, configuration):
        """Reset the PgSql configuration to the one given.
        """
        config_contents = configuration['config_contents']
        self.configuration_manager.save_configuration(config_contents)

    def start_db_with_conf_changes(self, context, config_contents):
        """Starts the PgSql instance with a new configuration."""
        if self.status.is_running:
            raise RuntimeError(_("The service is still running."))

        self.configuration_manager.save_configuration(config_contents)
        # The configuration template has to be updated with
        # guestagent-controlled settings.
        self.apply_initial_guestagent_configuration()
        self.start_db()

    def apply_initial_guestagent_configuration(self):
        """Update guestagent-controlled configuration properties.
        """
        LOG.debug("Applying initial guestagent configuration.")
        file_locations = {
            'data_directory': self._quote(self.pgsql_data_dir),
            'hba_file': self._quote(self.pgsql_hba_config),
            'ident_file': self._quote(self.pgsql_ident_config),
            'external_pid_file': self._quote(self.pgsql_pid_file),
            'unix_socket_directories': self._quote(self.pgsql_run_dir),
            'listen_addresses': self._quote(','.join(self.LISTEN_ADDRESSES)),
            'port': cfg.get_configuration_property('postgresql_port')}
        self.configuration_manager.apply_system_override(file_locations)
        self._apply_access_rules()

    @staticmethod
    def _quote(value):
        return "'%s'" % value

    def _apply_access_rules(self):
        LOG.debug("Applying database access rules.")

        # Connections to all resources are granted.
        #
        # Local access from administrative users is implicitly trusted.
        #
        # Remote access from the Trove's account is always rejected as
        # it is not needed and could be used by malicious users to hijack the
        # instance.
        #
        # Connections from other accounts always require a double-MD5-hashed
        # password.
        #
        # Make the rules readable only by the Postgres service.
        #
        # NOTE: The order of entries is important.
        # The first failure to authenticate stops the lookup.
        # That is why the 'local' connections validate first.
        # The OrderedDict is necessary to guarantee the iteration order.
        local_admins = ','.join([self.default_superuser_name, self.ADMIN_USER])
        remote_admins = self.ADMIN_USER
        access_rules = OrderedDict(
            [('local', [['all', local_admins, None, 'trust'],
                        ['replication', local_admins, None, 'trust'],
                        ['all', 'all', None, 'md5']]),
             ('host', [['all', local_admins, '127.0.0.1/32', 'trust'],
                       ['all', local_admins, '::1/128', 'trust'],
                       ['all', local_admins, 'localhost', 'trust'],
                       ['all', remote_admins, '0.0.0.0/0', 'reject'],
                       ['all', remote_admins, '::/0', 'reject'],
                       ['all', 'all', '0.0.0.0/0', 'md5'],
                       ['all', 'all', '::/0', 'md5']])
             ])
        operating_system.write_file(self.pgsql_hba_config, access_rules,
                                    PropertiesCodec(
                                        string_mappings={'\t': None}),
                                    as_root=True)
        operating_system.chown(self.pgsql_hba_config,
                               self.pgsql_owner, self.pgsql_owner,
                               as_root=True)
        operating_system.chmod(self.pgsql_hba_config, FileMode.SET_USR_RO,
                               as_root=True)

    def disable_backups(self):
        """Reverse overrides applied by PgBaseBackup strategy"""
        if not self.configuration_manager.has_system_override(
                BACKUP_CFG_OVERRIDE):
            return
        LOG.info("Removing configuration changes for backups")
        self.configuration_manager.remove_system_override(BACKUP_CFG_OVERRIDE)
        self.remove_wal_archive_dir()
        self.restart()

    def enable_backups(self):
        """Apply necessary changes to config to enable WAL-based backups
        if we are using the PgBaseBackup strategy
        """
        LOG.info(_("Checking if we need to apply changes to WAL config"))
        if 'PgBaseBackup' not in self.backup_strategy:
            return
        if self.configuration_manager.has_system_override(BACKUP_CFG_OVERRIDE):
            return

        LOG.info("Applying changes to WAL config for use by base backups")
        wal_arch_loc = self.wal_archive_location
        if not os.path.isdir(wal_arch_loc):
            raise RuntimeError(_("Cannot enable backup as WAL dir '%s' does "
                                 "not exist.") % wal_arch_loc)
        arch_cmd = "'test ! -f {wal_arch}/%f && cp %p {wal_arch}/%f'".format(
            wal_arch=wal_arch_loc
        )
        opts = {
            'wal_level': 'hot_standby',
            'archive_mode': 'on',
            'max_wal_senders': 8,
            'checkpoint_segments': 8,
            'wal_keep_segments': 8,
            'archive_command': arch_cmd
        }
        if not self.pg_version[1] in ('9.3'):
            opts['wal_log_hints'] = 'on'

        self.configuration_manager.apply_system_override(
            opts, BACKUP_CFG_OVERRIDE)
        self.restart()

    def disable_debugging(self, level=1):
        """Disable debug-level logging in postgres"""
        self.configuration_manager.remove_system_override(DEBUG_MODE_OVERRIDE)

    def enable_debugging(self, level=1):
        """Enable debug-level logging in postgres"""
        opt = {'log_min_messages': 'DEBUG%s' % level}
        self.configuration_manager.apply_system_override(opt,
                                                         DEBUG_MODE_OVERRIDE)

    def install(self, context, packages):
        """Install one or more packages that postgresql needs to run.

        The packages parameter is a string representing the package names that
        should be given to the system's package manager.
        """

        LOG.debug(
            "{guest_id}: Beginning PgSql package installation.".format(
                guest_id=CONF.guest_id
            )
        )
        self.recreate_wal_archive_dir()

        packager = pkg.Package()
        if not packager.pkg_is_installed(packages):
            try:
                LOG.info(
                    _("{guest_id}: Installing ({packages}).").format(
                        guest_id=CONF.guest_id,
                        packages=packages,
                    )
                )
                packager.pkg_install(packages, {}, 1000)
            except (pkg.PkgAdminLockError, pkg.PkgPermissionError,
                    pkg.PkgPackageStateError, pkg.PkgNotFoundError,
                    pkg.PkgTimeout, pkg.PkgScriptletError,
                    pkg.PkgDownloadError, pkg.PkgSignError,
                    pkg.PkgBrokenError):
                LOG.exception(
                    "{guest_id}: There was a package manager error while "
                    "trying to install ({packages}).".format(
                        guest_id=CONF.guest_id,
                        packages=packages,
                    )
                )
                raise
            except Exception:
                LOG.exception(
                    "{guest_id}: The package manager encountered an unknown "
                    "error while trying to install ({packages}).".format(
                        guest_id=CONF.guest_id,
                        packages=packages,
                    )
                )
                raise
            else:
                self.start_db()
                LOG.debug(
                    "{guest_id}: Completed package installation.".format(
                        guest_id=CONF.guest_id,
                    )
                )

    @property
    def pgsql_recovery_config(self):
        return os.path.join(self.pgsql_data_dir, "recovery.conf")

    @property
    def pgsql_data_dir(self):
        return os.path.dirname(self.pg_version[0])

    @property
    def pg_version(self):
        """Find the database version file stored in the data directory.

        :returns: A tuple with the path to the version file
                  (in the root of the data directory) and the version string.
        """
        version_files = operating_system.list_files_in_directory(
            self.pgsql_base_data_dir, recursive=True, pattern='PG_VERSION',
            as_root=True)
        version_file = sorted(version_files, key=len)[0]
        version = operating_system.read_file(version_file, as_root=True)
        return version_file, version.strip()

    def restart(self):
        self.status.restart_db_service(
            self.service_candidates, CONF.state_change_wait_time)

    def start_db(self, enable_on_boot=True, update_db=False):
        self.status.start_db_service(
            self.service_candidates, CONF.state_change_wait_time,
            enable_on_boot=enable_on_boot, update_db=update_db)

    def stop_db(self, do_not_start_on_reboot=False, update_db=False):
        self.status.stop_db_service(
            self.service_candidates, CONF.state_change_wait_time,
            disable_on_boot=do_not_start_on_reboot, update_db=update_db)

    def secure(self, context):
        """Create an administrative user for Trove.
        Force password encryption.
        Also disable the built-in superuser
        """
        password = utils.generate_random_password()

        os_admin_db = models.PostgreSQLSchema(self.ADMIN_USER)
        os_admin = models.PostgreSQLUser(self.ADMIN_USER, password)
        os_admin.databases.append(os_admin_db.serialize())

        postgres = models.PostgreSQLUser(self.default_superuser_name)
        admin = PgSqlAdmin(postgres)
        admin._create_database(context, os_admin_db)
        admin._create_admin_user(context, os_admin,
                                 encrypt_password=True)

        PgSqlAdmin(os_admin).alter_user(context, postgres, None,
                                        'NOSUPERUSER', 'NOLOGIN')

        self.set_current_admin_user(os_admin)

    def pg_current_xlog_location(self):
        """Wrapper for pg_current_xlog_location()
        Cannot be used against a running slave
        """
        r = self.build_admin().query("SELECT pg_current_xlog_location()")
        return r[0][0]

    def pg_last_xlog_replay_location(self):
        """Wrapper for pg_last_xlog_replay_location()
         For use on standby servers
         """
        r = self.build_admin().query("SELECT pg_last_xlog_replay_location()")
        return r[0][0]

    def pg_is_in_recovery(self):
        """Wrapper for pg_is_in_recovery() for detecting a server in
        standby mode
        """
        r = self.build_admin().query("SELECT pg_is_in_recovery()")
        return r[0][0]

    def pg_primary_host(self):
        """There seems to be no way to programmatically determine this
        on a hot standby, so grab what we have written to the recovery
        file
        """
        r = operating_system.read_file(self.pgsql_recovery_config,
                                       as_root=True)
        regexp = re.compile("host=(\d+.\d+.\d+.\d+) ")
        m = regexp.search(r)
        return m.group(1)

    def recreate_wal_archive_dir(self):
        wal_archive_dir = self.wal_archive_location
        operating_system.remove(wal_archive_dir, force=True, recursive=True,
                                as_root=True)
        operating_system.create_directory(wal_archive_dir,
                                          user=self.pgsql_owner,
                                          group=self.pgsql_owner,
                                          force=True, as_root=True)

    def remove_wal_archive_dir(self):
        wal_archive_dir = self.wal_archive_location
        operating_system.remove(wal_archive_dir, force=True, recursive=True,
                                as_root=True)

    def is_root_enabled(self, context):
        """Return True if there is a superuser account enabled.
        """
        results = self.build_admin().query(
            pgsql_query.UserQuery.list_root(),
            timeout=30,
        )

        # There should be only one superuser (Trove's administrative account).
        return len(results) > 1 or (results[0][0] != self.ADMIN_USER)

    def enable_root(self, context, root_password=None):
        """Create a superuser user or reset the superuser password.

        The default PostgreSQL administration account is 'postgres'.
        This account always exists and cannot be removed.
        Its attributes and access can however be altered.

        Clients can connect from the localhost or remotely via TCP/IP:

        Local clients (e.g. psql) can connect from a preset *system* account
        called 'postgres'.
        This system account has no password and is *locked* by default,
        so that it can be used by *local* users only.
        It should *never* be enabled (or its password set)!!!
        That would just open up a new attack vector on the system account.

        Remote clients should use a build-in *database* account of the same
        name. It's password can be changed using the "ALTER USER" statement.

        Access to this account is disabled by Trove exposed only once the
        superuser access is requested.
        Trove itself creates its own administrative account.

            {"_name": "postgres", "_password": "<secret>"}
        """
        user = self.build_root_user(root_password)
        self.build_admin().alter_user(
            context, user, None, *PgSqlAdmin.ADMIN_OPTIONS)
        return user.serialize()

    def build_root_user(self, password=None):
        return models.PostgreSQLUser.root(password=password)

    def pg_start_backup(self, backup_label):
        r = self.build_admin().query(
            "SELECT pg_start_backup('%s', true)" % backup_label)
        return r[0][0]

    def pg_xlogfile_name(self, start_segment):
        r = self.build_admin().query(
            "SELECT pg_xlogfile_name('%s')" % start_segment)
        return r[0][0]

    def pg_stop_backup(self):
        r = self.build_admin().query("SELECT pg_stop_backup()")
        return r[0][0]

    def disable_root(self, context):
        """Generate a new random password for the public superuser account.
        Do not disable its access rights. Once enabled the account should
        stay that way.
        """
        self.enable_root(context)

    def enable_root_with_password(self, context, root_password=None):
        return self.enable_root(context, root_password)

    @property
    def wal_archive_location(self):
        return cfg.get_configuration_property('wal_archive_location')

    @property
    def backup_strategy(self):
        return cfg.get_configuration_property('backup_strategy')

    def save_files_pre_upgrade(self, mount_point):
        LOG.debug('Saving files pre-upgrade.')
        mnt_etc_dir = os.path.join(mount_point, 'save_etc')
        if self.OS not in [operating_system.REDHAT]:
            # No need to store the config files away for Redhat because
            # they are already stored in the data volume.
            operating_system.remove(mnt_etc_dir, force=True, as_root=True)
            operating_system.copy(self.pgsql_config_dir, mnt_etc_dir,
                                  preserve=True, recursive=True, as_root=True)
        return {'save_etc': mnt_etc_dir}

    def restore_files_post_upgrade(self, upgrade_info):
        LOG.debug('Restoring files post-upgrade.')
        if self.OS not in [operating_system.REDHAT]:
            # No need to restore the config files for Redhat because
            # they are already in the data volume.
            operating_system.copy('%s/.' % upgrade_info['save_etc'],
                                  self.pgsql_config_dir,
                                  preserve=True, recursive=True,
                                  force=True, as_root=True)
            operating_system.remove(upgrade_info['save_etc'], force=True,
                                    as_root=True)
        self.configuration_manager.refresh_cache()
        self.status.set_ready()


class PgSqlAppStatus(service.BaseDbStatus):

    HOST = 'localhost'

    def __init__(self, tools_dir):
        super(PgSqlAppStatus, self).__init__()
        self._cmd = guestagent_utils.build_file_path(tools_dir, 'pg_isready')

    def _get_actual_db_status(self):
        try:
            utils.execute_with_timeout(
                self._cmd, '-h', self.HOST, log_output_on_error=True)
            return instance.ServiceStatuses.RUNNING
        except exception.ProcessExecutionError:
            return instance.ServiceStatuses.SHUTDOWN
        except utils.Timeout:
            return instance.ServiceStatuses.BLOCKED
        except Exception:
            LOG.exception(_("Error getting Postgres status."))
            return instance.ServiceStatuses.CRASHED

        return instance.ServiceStatuses.SHUTDOWN


class PgSqlAdmin(object):

    # Default set of options of an administrative account.
    ADMIN_OPTIONS = (
        'SUPERUSER', 'CREATEDB', 'CREATEROLE', 'INHERIT', 'REPLICATION',
        'LOGIN'
    )

    def __init__(self, user):
        port = cfg.get_configuration_property('postgresql_port')
        self.__connection = PostgresLocalhostConnection(user.name, port=port)

    def grant_access(self, context, username, hostname, databases):
        """Give a user permission to use a given database.

        The username and hostname parameters are strings.
        The databases parameter is a list of strings representing the names of
        the databases to grant permission on.
        """
        for database in databases:
            LOG.info(
                _("{guest_id}: Granting user ({user}) access to database "
                    "({database}).").format(
                        guest_id=CONF.guest_id,
                        user=username,
                        database=database,)
            )
            self.psql(
                pgsql_query.AccessQuery.grant(
                    user=username,
                    database=database,
                ),
                timeout=30,
            )

    def revoke_access(self, context, username, hostname, database):
        """Revoke a user's permission to use a given database.

        The username and hostname parameters are strings.
        The database parameter is a string representing the name of the
        database.
        """
        LOG.info(
            _("{guest_id}: Revoking user ({user}) access to database"
                "({database}).").format(
                    guest_id=CONF.guest_id,
                    user=username,
                    database=database,)
        )
        self.psql(
            pgsql_query.AccessQuery.revoke(
                user=username,
                database=database,
            ),
            timeout=30,
        )

    def list_access(self, context, username, hostname):
        """List database for which the given user as access.
        Return a list of serialized Postgres databases.
        """
        user = self._find_user(context, username)
        if user is not None:
            return user.databases

        raise exception.UserNotFound(username)

    def create_database(self, context, databases):
        """Create the list of specified databases.

        The databases parameter is a list of serialized Postgres databases.
        """
        for database in databases:
            self._create_database(
                context,
                models.PostgreSQLSchema.deserialize(database))

    def _create_database(self, context, database):
        """Create a database.

        :param database:          Database to be created.
        :type database:           PostgreSQLSchema
        """
        LOG.info(
            _("{guest_id}: Creating database {name}.").format(
                guest_id=CONF.guest_id,
                name=database.name,
            )
        )
        self.psql(
            pgsql_query.DatabaseQuery.create(
                name=database.name,
                encoding=database.character_set,
                collation=database.collate,
            ),
            timeout=30,
        )

    def delete_database(self, context, database):
        """Delete the specified database.
        """
        self._drop_database(
            models.PostgreSQLSchema.deserialize(database))

    def _drop_database(self, database):
        """Drop a given Postgres database.

        :param database:          Database to be dropped.
        :type database:           PostgreSQLSchema
        """
        LOG.info(
            _("{guest_id}: Dropping database {name}.").format(
                guest_id=CONF.guest_id,
                name=database.name,
            )
        )
        self.psql(
            pgsql_query.DatabaseQuery.drop(name=database.name),
            timeout=30,
        )

    def list_databases(self, context, limit=None, marker=None,
                       include_marker=False):
        """List all databases on the instance.
        Return a paginated list of serialized Postgres databases.
        """

        return guestagent_utils.serialize_list(
            self._get_databases(),
            limit=limit, marker=marker, include_marker=include_marker)

    def _get_databases(self):
        """Return all non-system Postgres databases on the instance."""
        results = self.query(
            pgsql_query.DatabaseQuery.list(ignore=self.ignore_dbs),
            timeout=30,
        )
        return [models.PostgreSQLSchema(
            row[0].strip(), character_set=row[1], collate=row[2])
            for row in results]

    def create_user(self, context, users):
        """Create users and grant privileges for the specified databases.

        The users parameter is a list of serialized Postgres users.
        """
        for user in users:
            self._create_user(
                context,
                models.PostgreSQLUser.deserialize(user), None)

    def _create_user(self, context, user, encrypt_password=None, *options):
        """Create a user and grant privileges for the specified databases.

        :param user:              User to be created.
        :type user:               PostgreSQLUser

        :param encrypt_password:  Store passwords encrypted if True.
                                  Fallback to configured default
                                  behavior if None.
        :type encrypt_password:   boolean

        :param options:           Other user options.
        :type options:            list
        """
        LOG.info(
            _("{guest_id}: Creating user {user} {with_clause}.")
            .format(
                guest_id=CONF.guest_id,
                user=user.name,
                with_clause=pgsql_query.UserQuery._build_with_clause(
                    '<SANITIZED>',
                    encrypt_password,
                    *options
                ),
            )
        )
        self.psql(
            pgsql_query.UserQuery.create(
                user.name,
                user.password,
                encrypt_password,
                *options
            ),
            timeout=30,
        )
        self._grant_access(
            context, user.name,
            [models.PostgreSQLSchema.deserialize(db)
             for db in user.databases])

    def _create_admin_user(self, context, user, encrypt_password=None):
        self._create_user(context, user, encrypt_password, *self.ADMIN_OPTIONS)

    def _grant_access(self, context, username, databases):
        self.grant_access(
            context,
            username,
            None,
            [db.name for db in databases],
        )

    def list_users(
            self, context, limit=None, marker=None, include_marker=False):
        """List all users on the instance along with their access permissions.
        Return a paginated list of serialized Postgres users.
        """
        return guestagent_utils.serialize_list(
            self._get_users(context),
            limit=limit, marker=marker, include_marker=include_marker)

    def _get_users(self, context):
        """Return all non-system Postgres users on the instance."""
        results = self.query(
            pgsql_query.UserQuery.list(ignore=self.ignore_users),
            timeout=30,
        )

        names = set([row[0].strip() for row in results])
        return [self._build_user(context, name, results) for name in names]

    def _build_user(self, context, username, acl=None):
        """Build a model representation of a Postgres user.
        Include all databases it has access to.
        """
        user = models.PostgreSQLUser(username)
        if acl:
            dbs = [models.PostgreSQLSchema(row[1].strip(),
                                           character_set=row[2],
                                           collate=row[3])
                   for row in acl if row[0] == username and row[1] is not None]
            for d in dbs:
                user.databases.append(d.serialize())

        return user

    def delete_user(self, context, user):
        """Delete the specified user.
        """
        self._drop_user(
            context, models.PostgreSQLUser.deserialize(user))

    def _drop_user(self, context, user):
        """Drop a given Postgres user.

        :param user:              User to be dropped.
        :type user:               PostgreSQLUser
        """
        # Postgresql requires that you revoke grants before dropping the user
        dbs = self.list_access(context, user.name, None)
        for d in dbs:
            db = models.PostgreSQLSchema.deserialize(d)
            self.revoke_access(context, user.name, None, db.name)

        LOG.info(
            _("{guest_id}: Dropping user {name}.").format(
                guest_id=CONF.guest_id,
                name=user.name,
            )
        )
        self.psql(
            pgsql_query.UserQuery.drop(name=user.name),
            timeout=30,
        )

    def get_user(self, context, username, hostname):
        """Return a serialized representation of a user with a given name.
        """
        user = self._find_user(context, username)
        return user.serialize() if user is not None else None

    def _find_user(self, context, username):
        """Lookup a user with a given username.
        Return a new Postgres user instance or None if no match is found.
        """
        results = self.query(
            pgsql_query.UserQuery.get(name=username),
            timeout=30,
        )

        if results:
            return self._build_user(context, username, results)

        return None

    def user_exists(self, username):
        """Return whether a given user exists on the instance."""
        results = self.query(
            pgsql_query.UserQuery.get(name=username),
            timeout=30,
        )

        return bool(results)

    def change_passwords(self, context, users):
        """Change the passwords of one or more existing users.
        The users parameter is a list of serialized Postgres users.
        """
        for user in users:
            self.alter_user(
                context,
                models.PostgreSQLUser.deserialize(user), None)

    def alter_user(self, context, user, encrypt_password=None, *options):
        """Change the password and options of an existing users.

        :param user:              User to be altered.
        :type user:               PostgreSQLUser

        :param encrypt_password:  Store passwords encrypted if True.
                                  Fallback to configured default
                                  behavior if None.
        :type encrypt_password:   boolean

        :param options:           Other user options.
        :type options:            list
        """
        LOG.info(
            _("{guest_id}: Altering user {user} {with_clause}.")
            .format(
                guest_id=CONF.guest_id,
                user=user.name,
                with_clause=pgsql_query.UserQuery._build_with_clause(
                    '<SANITIZED>',
                    encrypt_password,
                    *options
                ),
            )
        )
        self.psql(
            pgsql_query.UserQuery.alter_user(
                user.name,
                user.password,
                encrypt_password,
                *options),
            timeout=30,
        )

    def update_attributes(self, context, username, hostname, user_attrs):
        """Change the attributes of one existing user.

        The username and hostname parameters are strings.
        The user_attrs parameter is a dictionary in the following form:

            {"password": "", "name": ""}

        Each key/value pair in user_attrs is optional.
        """
        user = self._build_user(context, username)
        new_username = user_attrs.get('name')
        new_password = user_attrs.get('password')

        if new_username is not None:
            self._rename_user(context, user, new_username)
            # Make sure we can retrieve the renamed user.
            user = self._find_user(context, new_username)
            if user is None:
                raise exception.TroveError(_(
                    "Renamed user %s could not be found on the instance.")
                    % new_username)

        if new_password is not None:
            user.password = new_password
            self.alter_user(context, user)

    def _rename_user(self, context, user, new_username):
        """Rename a given Postgres user and transfer all access to the
        new name.

        :param user:              User to be renamed.
        :type user:               PostgreSQLUser
        """
        LOG.info(
            _("{guest_id}: Changing username for {old} to {new}.").format(
                guest_id=CONF.guest_id,
                old=user.name,
                new=new_username,
            )
        )
        # PostgreSQL handles the permission transfer itself.
        self.psql(
            pgsql_query.UserQuery.update_name(
                old=user.name,
                new=new_username,
            ),
            timeout=30,
        )

    def psql(self, statement, timeout=30):
        """Execute a non-returning statement (usually DDL);
        Turn autocommit ON (this is necessary for statements that cannot run
        within an implicit transaction, like CREATE DATABASE).
        """
        return self.__connection.execute(statement)

    def query(self, query, timeout=30):
        """Execute a query and return the result set.
        """
        return self.__connection.query(query)

    @property
    def ignore_users(self):
        return cfg.get_ignored_users()

    @property
    def ignore_dbs(self):
        return cfg.get_ignored_dbs()


class PostgresConnection(object):

    def __init__(self, **connection_args):
        self._connection_args = connection_args

    def execute(self, statement, identifiers=None, data_values=None):
        """Execute a non-returning statement.
        """
        self._execute_stmt(statement, identifiers, data_values, False,
                           autocommit=True)

    def query(self, query, identifiers=None, data_values=None):
        """Execute a query and return the result set.
        """
        return self._execute_stmt(query, identifiers, data_values, True)

    def _execute_stmt(self, statement, identifiers, data_values, fetch,
                      autocommit=False):
        if statement:
            with psycopg2.connect(**self._connection_args) as connection:
                connection.autocommit = autocommit
                with connection.cursor() as cursor:
                    cursor.execute(
                        self._bind(statement, identifiers), data_values)
                    if fetch:
                        return cursor.fetchall()
        else:
            raise exception.UnprocessableEntity(_("Invalid SQL statement: %s")
                                                % statement)

    def _bind(self, statement, identifiers):
        if identifiers:
            return statement.format(*identifiers)
        return statement


class PostgresLocalhostConnection(PostgresConnection):

    HOST = 'localhost'

    def __init__(self, user, password=None, port=5432):
        super(PostgresLocalhostConnection, self).__init__(
            user=user, password=password,
            host=self.HOST, port=port)
