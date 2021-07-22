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
from collections import OrderedDict

from oslo_log import log as logging
import psycopg2

from trove.common import cfg
from trove.common import exception
from trove.common import stream_codecs
from trove.common import utils
from trove.common.db.postgresql import models
from trove.guestagent.common import configuration
from trove.guestagent.common import guestagent_utils
from trove.guestagent.common import operating_system
from trove.guestagent.datastore import service
from trove.guestagent.datastore.postgres import query
from trove.guestagent.utils import docker as docker_util
from trove.instance import service_status

LOG = logging.getLogger(__name__)
CONF = cfg.CONF

SUPER_USER_NAME = "postgres"
CONFIG_FILE = "/etc/postgresql/postgresql.conf"
CNF_EXT = 'conf'
# The same with include_dir config option
CNF_INCLUDE_DIR = '/etc/postgresql/conf.d'
HBA_CONFIG_FILE = '/etc/postgresql/pg_hba.conf'
# The same with the path in archive_command config option.
WAL_ARCHIVE_DIR = '/var/lib/postgresql/data/wal_archive'


class PgSqlAppStatus(service.BaseDbStatus):
    def __init__(self, docker_client):
        super(PgSqlAppStatus, self).__init__(docker_client)

    def get_actual_db_status(self):
        """Check database service status."""
        status = docker_util.get_container_status(self.docker_client)
        if status == "running":
            cmd = "psql -U postgres -c 'select 1;'"
            try:
                docker_util.run_command(self.docker_client, cmd)
                return service_status.ServiceStatuses.HEALTHY
            except Exception as exc:
                LOG.warning('Failed to run docker command, error: %s',
                            str(exc))
                container_log = docker_util.get_container_logs(
                    self.docker_client, tail='all')
                LOG.debug('container log: \n%s', '\n'.join(container_log))
                return service_status.ServiceStatuses.RUNNING
        elif status == "not running":
            return service_status.ServiceStatuses.SHUTDOWN
        elif status == "paused":
            return service_status.ServiceStatuses.PAUSED
        elif status == "exited":
            return service_status.ServiceStatuses.SHUTDOWN
        elif status == "dead":
            return service_status.ServiceStatuses.CRASHED
        else:
            return service_status.ServiceStatuses.UNKNOWN


class PgSqlApp(service.BaseDbApp):
    _configuration_manager = None

    @property
    def configuration_manager(self):
        if self._configuration_manager:
            return self._configuration_manager

        self._configuration_manager = configuration.ConfigurationManager(
            CONFIG_FILE,
            CONF.database_service_uid,
            CONF.database_service_uid,
            stream_codecs.KeyValueCodec(
                value_quoting=True,
                bool_case=stream_codecs.KeyValueCodec.BOOL_LOWER,
                big_ints=True),
            requires_root=True,
            override_strategy=configuration.ImportOverrideStrategy(
                CNF_INCLUDE_DIR, CNF_EXT)
        )
        return self._configuration_manager

    def __init__(self, status, docker_client):
        super(PgSqlApp, self).__init__(status, docker_client)

        # See
        # https://github.com/docker-library/docs/blob/master/postgres/README.md#pgdata
        mount_point = cfg.get_configuration_property('mount_point')
        self.datadir = f"{mount_point}/data/pgdata"
        self.adm = PgSqlAdmin(SUPER_USER_NAME)

    def get_data_dir(self):
        return self.configuration_manager.get_value('data_directory')

    def set_data_dir(self, value):
        self.configuration_manager.apply_system_override(
            {'data_directory': value})

    def reload(self):
        cmd = f"pg_ctl reload -D {self.datadir}"
        docker_util.run_command(self.docker_client, cmd)

    def apply_access_rules(self):
        """PostgreSQL Client authentication settings

        The order of entries is important. The first failure to authenticate
        stops the lookup. That is why the 'local' connections validate first.
        The OrderedDict is necessary to guarantee the iteration order.
        """
        LOG.debug("Applying client authentication access rules.")

        access_rules = OrderedDict(
            [('local', [['all', SUPER_USER_NAME, None, 'trust'],
                        ['replication', SUPER_USER_NAME, None, 'trust'],
                        ['all', 'all', None, 'md5']]),
             ('host', [['all', SUPER_USER_NAME, '127.0.0.1/32', 'trust'],
                       ['all', SUPER_USER_NAME, '::1/128', 'trust'],
                       ['all', SUPER_USER_NAME, 'localhost', 'trust'],
                       ['all', SUPER_USER_NAME, '0.0.0.0/0', 'reject'],
                       ['all', SUPER_USER_NAME, '::/0', 'reject'],
                       ['all', 'all', '0.0.0.0/0', 'md5'],
                       ['all', 'all', '::/0', 'md5']])
             ])
        operating_system.write_file(
            HBA_CONFIG_FILE, access_rules,
            stream_codecs.PropertiesCodec(string_mappings={'\t': None}),
            as_root=True)
        operating_system.chown(HBA_CONFIG_FILE,
                               CONF.database_service_uid,
                               CONF.database_service_uid,
                               as_root=True)
        operating_system.chmod(HBA_CONFIG_FILE,
                               operating_system.FileMode.SET_USR_RO,
                               as_root=True)

    def update_overrides(self, overrides):
        """Update config options in the include directory."""
        if overrides:
            self.configuration_manager.apply_user_override(overrides)

    def apply_overrides(self, overrides):
        """Reload config."""
        cmd = "pg_ctl reload"
        docker_util.run_command(self.docker_client, cmd)

    def start_db(self, update_db=False, ds_version=None, command=None,
                 extra_volumes=None):
        """Start and wait for database service."""
        docker_image = CONF.get(CONF.datastore_manager).docker_image
        image = (f'{docker_image}:latest' if not ds_version else
                 f'{docker_image}:{ds_version}')
        command = command if command else ''

        try:
            postgres_pass = self.get_auth_password(file="postgres.cnf")
        except exception.UnprocessableEntity:
            postgres_pass = utils.generate_random_password()

        # Get uid and gid
        user = "%s:%s" % (CONF.database_service_uid, CONF.database_service_uid)

        # Create folders for postgres on localhost
        for folder in ['/etc/postgresql', '/var/run/postgresql']:
            operating_system.ensure_directory(
                folder, user=CONF.database_service_uid,
                group=CONF.database_service_uid, force=True,
                as_root=True)

        volumes = {
            "/etc/postgresql": {"bind": "/etc/postgresql", "mode": "rw"},
            "/var/run/postgresql": {"bind": "/var/run/postgresql",
                                    "mode": "rw"},
            "/var/lib/postgresql": {"bind": "/var/lib/postgresql",
                                    "mode": "rw"},
            "/var/lib/postgresql/data": {"bind": "/var/lib/postgresql/data",
                                         "mode": "rw"},
        }
        if extra_volumes:
            volumes.update(extra_volumes)

        # Expose ports
        ports = {}
        tcp_ports = cfg.get_configuration_property('tcp_ports')
        for port_range in tcp_ports:
            for port in port_range:
                ports[f'{port}/tcp'] = port

        try:
            docker_util.start_container(
                self.docker_client,
                image,
                volumes=volumes,
                network_mode="bridge",
                ports=ports,
                user=user,
                environment={
                    "POSTGRES_PASSWORD": postgres_pass,
                    "PGDATA": self.datadir,
                },
                command=command
            )

            # Save root password
            LOG.debug("Saving root credentials to local host.")
            self.save_password('postgres', postgres_pass)
        except Exception:
            LOG.exception("Failed to start database service")
            raise exception.TroveError("Failed to start database service")

        if not self.status.wait_for_status(
            service_status.ServiceStatuses.HEALTHY,
            CONF.state_change_wait_time, update_db
        ):
            raise exception.TroveError("Failed to start database service")

    def restart(self):
        LOG.info("Restarting database")

        # Ensure folders permission for database.
        for folder in ['/etc/postgresql', '/var/run/postgresql']:
            operating_system.ensure_directory(
                folder, user=CONF.database_service_uid,
                group=CONF.database_service_uid, force=True,
                as_root=True)

        try:
            docker_util.restart_container(self.docker_client)
        except Exception:
            LOG.exception("Failed to restart database")
            raise exception.TroveError("Failed to restart database")

        if not self.status.wait_for_status(
            service_status.ServiceStatuses.HEALTHY,
            CONF.state_change_wait_time, update_db=True
        ):
            raise exception.TroveError("Failed to start database")

        LOG.info("Finished restarting database")

    def restore_backup(self, context, backup_info, restore_location):
        backup_id = backup_info['id']
        storage_driver = CONF.storage_strategy
        backup_driver = cfg.get_configuration_property('backup_strategy')
        image = cfg.get_configuration_property('backup_docker_image')
        name = 'db_restore'
        volumes = {
            '/var/lib/postgresql/data': {
                'bind': '/var/lib/postgresql/data',
                'mode': 'rw'
            }
        }

        os_cred = (f"--os-token={context.auth_token} "
                   f"--os-auth-url={CONF.service_credentials.auth_url} "
                   f"--os-tenant-id={context.project_id}")

        command = (
            f'/usr/bin/python3 main.py --nobackup '
            f'--storage-driver={storage_driver} --driver={backup_driver} '
            f'{os_cred} '
            f'--restore-from={backup_info["location"]} '
            f'--restore-checksum={backup_info["checksum"]} '
            f'--pg-wal-archive-dir {WAL_ARCHIVE_DIR}'
        )
        if CONF.backup_aes_cbc_key:
            command = (f"{command} "
                       f"--backup-encryption-key={CONF.backup_aes_cbc_key}")

        LOG.debug('Stop the database and clean up the data before restore '
                  'from %s', backup_id)
        self.stop_db()
        for dir in [WAL_ARCHIVE_DIR, self.datadir]:
            operating_system.remove_dir_contents(dir)

        # Start to run restore inside a separate docker container
        LOG.info('Starting to restore backup %s, command: %s', backup_id,
                 command)
        output, ret = docker_util.run_container(
            self.docker_client, image, name,
            volumes=volumes, command=command)
        result = output[-1]
        if not ret:
            msg = f'Failed to run restore container, error: {result}'
            LOG.error(msg)
            raise Exception(msg)

        for dir in [WAL_ARCHIVE_DIR, self.datadir]:
            operating_system.chown(dir, CONF.database_service_uid,
                                   CONF.database_service_uid, force=True,
                                   as_root=True)

    def is_replica(self):
        """Wrapper for pg_is_in_recovery() for detecting a server in
        standby mode
        """
        r = self.adm.query("SELECT pg_is_in_recovery()")
        return r[0][0]

    def get_current_wal_lsn(self):
        """Wrapper for pg_current_wal_lsn()

        Cannot be used against a running replica
        """
        r = self.adm.query("SELECT pg_current_wal_lsn()")
        return r[0][0]

    def get_last_wal_replay_lsn(self):
        """Wrapper for pg_last_wal_replay_lsn()

         For use on replica servers
         """
        r = self.adm.query("SELECT pg_last_wal_replay_lsn()")
        return r[0][0]

    def pg_rewind(self, conn_info):
        docker_image = CONF.get(CONF.datastore_manager).docker_image
        image = f'{docker_image}:{CONF.datastore_version}'
        user = "%s:%s" % (CONF.database_service_uid, CONF.database_service_uid)
        volumes = {
            "/var/run/postgresql": {"bind": "/var/run/postgresql",
                                    "mode": "rw"},
            "/var/lib/postgresql": {"bind": "/var/lib/postgresql",
                                    "mode": "rw"},
            "/var/lib/postgresql/data": {"bind": "/var/lib/postgresql/data",
                                         "mode": "rw"},
        }
        command = (f"pg_rewind --target-pgdata={self.datadir} "
                   f"--source-server='{conn_info}'")

        docker_util.remove_container(self.docker_client, name='pg_rewind')

        LOG.info('Running pg_rewind in container')
        output, ret = docker_util.run_container(
            self.docker_client, image, 'pg_rewind',
            volumes=volumes, command=command, user=user)
        result = output[-1]
        LOG.debug(f"Finished running pg_rewind, last output: {result}")
        if not ret:
            msg = f'Failed to run pg_rewind in container, error: {result}'
            LOG.error(msg)
            raise Exception(msg)


class PgSqlAdmin(object):
    # Default set of options of an administrative account.
    ADMIN_OPTIONS = (
        'SUPERUSER', 'CREATEDB', 'CREATEROLE', 'INHERIT', 'REPLICATION',
        'BYPASSRLS', 'LOGIN'
    )

    def __init__(self, username):
        port = cfg.get_configuration_property('postgresql_port')
        self.connection = PostgresConnection(username, port=port)

    def build_root_user(self, password=None):
        return models.PostgreSQLUser.root(name='root', password=password)

    def enable_root(self, root_password=None):
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
        """
        root = self.build_root_user(root_password)
        results = self.query(query.UserQuery.list_root(self.ignore_users))
        cur_roots = [row[0] for row in results]
        if 'root' not in cur_roots:
            self.create_user(root)

        self.alter_user(root, None, *PgSqlAdmin.ADMIN_OPTIONS)
        return root.serialize()

    def disable_root(self):
        """Generate a new random password for the public superuser account.

        Do not disable its access rights. Once enabled the account should
        stay that way.
        """
        self.enable_root()

    def list_root(self, ignore=()):
        """Query to list all superuser accounts."""
        statement = (
            "SELECT usename FROM pg_catalog.pg_user WHERE usesuper = true"
        )

        for name in ignore:
            statement += " AND usename != '{name}'".format(name=name)

        return statement

    def grant_access(self, username, hostname, databases):
        """Give a user permission to use a given database.

        The username and hostname parameters are strings.
        The databases parameter is a list of strings representing the names of
        the databases to grant permission on.
        """
        for database in databases:
            LOG.info(f"Granting user {username} access to database {database}")
            self.psql(
                query.AccessQuery.grant(
                    user=username,
                    database=database,
                )
            )

    def revoke_access(self, username, hostname, database):
        """Revoke a user's permission to use a given database.

        The username and hostname parameters are strings.
        The database parameter is a string representing the name of the
        database.
        """
        LOG.info(f"Revoking user ({username}) access to database {database}")
        self.psql(
            query.AccessQuery.revoke(
                user=username,
                database=database,
            )
        )

    def list_access(self, username, hostname):
        """List database for which the given user as access.
        Return a list of serialized Postgres databases.
        """
        user = self._find_user(username)
        return user.databases if user is not None else []

    def create_databases(self, databases):
        """Create the list of specified databases.

        The databases parameter is a list of serialized Postgres databases.
        """
        for database in databases:
            self.create_database(models.PostgreSQLSchema.deserialize(database))

    def create_database(self, database):
        """Create a database.

        :param database:          Database to be created.
        :type database:           PostgreSQLSchema
        """
        LOG.info(f"Creating database {database.name}")
        self.psql(
            query.DatabaseQuery.create(
                name=database.name,
                encoding=database.character_set,
                collation=database.collate,
            )
        )

    def delete_database(self, database):
        """Delete the specified database.
        """
        self._drop_database(
            models.PostgreSQLSchema.deserialize(database))

    def _drop_database(self, database):
        """Drop a given Postgres database.

        :param database:          Database to be dropped.
        :type database:           PostgreSQLSchema
        """
        LOG.info(f"Dropping database {database.name}")
        self.psql(query.DatabaseQuery.drop(name=database.name))

    def list_databases(self, limit=None, marker=None, include_marker=False):
        return guestagent_utils.serialize_list(
            self._get_databases(),
            limit=limit, marker=marker, include_marker=include_marker)

    def _get_databases(self):
        """Return all non-system Postgres databases on the instance."""
        results = self.query(
            query.DatabaseQuery.list(ignore=self.ignore_dbs)
        )
        return [models.PostgreSQLSchema(
            row[0].strip(), character_set=row[1], collate=row[2])
            for row in results]

    def create_users(self, users):
        """Create users and grant privileges for the specified databases.

        The users parameter is a list of serialized Postgres users.
        """
        for user in users:
            self.create_user(models.PostgreSQLUser.deserialize(user), None)

    def create_user(self, user, encrypt_password=None, *options):
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
        with_clause = query.UserQuery._build_with_clause(
            '<SANITIZED>',
            encrypt_password,
            *options
        )
        LOG.info(f"Creating user {user.name} {with_clause}")

        self.psql(
            query.UserQuery.create(
                user.name,
                user.password,
                encrypt_password,
                *options
            )
        )
        self._grant_access(
            user.name,
            [models.PostgreSQLSchema.deserialize(db) for db in user.databases])

    def create_admin_user(self, user, encrypt_password=None):
        self.create_user(user, encrypt_password, *self.ADMIN_OPTIONS)

    def _grant_access(self, username, databases):
        self.grant_access(
            username,
            None,
            [db.name for db in databases],
        )

    def list_users(self, limit=None, marker=None, include_marker=False):
        """List all users on the instance along with their access permissions.
        Return a paginated list of serialized Postgres users.
        """
        return guestagent_utils.serialize_list(
            self._get_users(),
            limit=limit, marker=marker, include_marker=include_marker)

    def _get_users(self):
        """Return all non-system Postgres users on the instance."""
        results = self.query(
            query.UserQuery.list(ignore=self.ignore_users)
        )

        names = set([row[0].strip() for row in results])
        return [self._build_user(name, results) for name in names]

    def _build_user(self, username, acl=None):
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

    def delete_user(self, user):
        """Delete the specified user.
        """
        self._drop_user(models.PostgreSQLUser.deserialize(user))

    def _drop_user(self, user):
        """Drop a given Postgres user.

        :param user:              User to be dropped.
        :type user:               PostgreSQLUser
        """
        # Postgresql requires that you revoke grants before dropping the user
        databases = list(self.list_access(user.name, None))
        for db in databases:
            db_schema = models.PostgreSQLSchema.deserialize(db)
            self.revoke_access(user.name, None, db_schema.name)

        LOG.info(f"Dropping user {user.name}")
        self.psql(query.UserQuery.drop(name=user.name))

    def get_user(self, username, hostname):
        """Return a serialized representation of a user with a given name.
        """
        user = self._find_user(username)
        return user.serialize() if user is not None else None

    def _find_user(self, username):
        """Lookup a user with a given username.

        Return a new Postgres user instance or None if no match is found.
        """
        results = self.query(query.UserQuery.get(name=username))

        if results:
            return self._build_user(username, results)

        return None

    def user_exists(self, username):
        """Return whether a given user exists on the instance."""
        results = self.query(query.UserQuery.get(name=username))

        return bool(results)

    def change_passwords(self, users):
        """Change the passwords of one or more existing users.

        The users parameter is a list of serialized Postgres users.
        """
        for user in users:
            self.alter_user(
                models.PostgreSQLUser.deserialize(user))

    def alter_user(self, user, encrypt_password=None, *options):
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
        with_clause = query.UserQuery._build_with_clause(
            '<SANITIZED>',
            encrypt_password,
            *options
        )
        LOG.info(f"Altering user {user.name} {with_clause}")

        self.psql(
            query.UserQuery.alter_user(
                user.name,
                user.password,
                encrypt_password,
                *options)
        )

    def update_attributes(self, username, hostname, user_attrs):
        """Change the attributes of one existing user.

        The username and hostname parameters are strings.
        The user_attrs parameter is a dictionary in the following form:

            {"password": "", "name": ""}

        Each key/value pair in user_attrs is optional.
        """
        user = self._build_user(username)
        new_username = user_attrs.get('name')
        new_password = user_attrs.get('password')

        if new_username is not None:
            self._rename_user(user, new_username)
            # Make sure we can retrieve the renamed user.
            user = self._find_user(new_username)
            if user is None:
                raise exception.TroveError(
                    "Renamed user %s could not be found on the instance."
                    % new_username)

        if new_password is not None:
            user.password = new_password
            self.alter_user(user)

    def _rename_user(self, user, new_username):
        """Rename a Postgres user and transfer all access to the new name.

        :param user:              User to be renamed.
        :type user:               PostgreSQLUser
        """
        LOG.info(f"Changing username for {user.name} to {new_username}")
        # PostgreSQL handles the permission transfer itself.
        self.psql(
            query.UserQuery.update_name(
                old=user.name,
                new=new_username,
            )
        )

    def psql(self, statement):
        """Execute a non-returning statement (usually DDL);
        Turn autocommit ON (this is necessary for statements that cannot run
        within an implicit transaction, like CREATE DATABASE).
        """
        return self.connection.execute(statement)

    def query(self, query):
        """Execute a query and return the result set.
        """
        return self.connection.query(query)

    @property
    def ignore_users(self):
        return cfg.get_ignored_users()

    @property
    def ignore_dbs(self):
        return cfg.get_ignored_dbs()


class PostgresConnection(object):
    def __init__(self, user, password=None, host='/var/run/postgresql',
                 port=5432):
        """Utility class to communicate with PostgreSQL.

        Connect with socket rather than IP or localhost address to avoid
        manipulation of pg_hba.conf when the database is running inside
        container with bridge network.

        This class is consistent with PostgresConnection in
        backup/utils/postgresql.py
        """
        self.user = user
        self.password = password
        self.host = host
        self.port = port

        self.connect_str = (f"user='{self.user}' password='{self.password}' "
                            f"host='{self.host}' port='{self.port}'")

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
        cmd = self._bind(statement, identifiers)
        with psycopg2.connect(self.connect_str) as connection:
            connection.autocommit = autocommit
            with connection.cursor() as cursor:
                cursor.execute(cmd, data_values)
                if fetch:
                    return cursor.fetchall()

    def _bind(self, statement, identifiers):
        if identifiers:
            return statement.format(*identifiers)
        return statement
