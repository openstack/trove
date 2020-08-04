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

import abc
import re

from oslo_log import log as logging
from oslo_utils import encodeutils
from oslo_utils import timeutils
import six
from six.moves import urllib
import sqlalchemy
from sqlalchemy import exc
from sqlalchemy.sql.expression import text

from trove.backup.state import BackupState
from trove.common import cfg
from trove.common import exception
from trove.common import utils
from trove.common.configurations import MySQLConfParser
from trove.common.db.mysql import models
from trove.common.i18n import _
from trove.common.stream_codecs import IniCodec
from trove.conductor import api as conductor_api
from trove.guestagent.common import guestagent_utils
from trove.guestagent.common import operating_system
from trove.guestagent.common import sql_query
from trove.guestagent.common.configuration import ConfigurationManager
from trove.guestagent.common.configuration import ImportOverrideStrategy
from trove.guestagent.datastore import service
from trove.guestagent.datastore.mysql_common import service as commmon_service
from trove.guestagent.utils import docker as docker_util
from trove.guestagent.utils import mysql as mysql_util
from trove.instance import service_status

LOG = logging.getLogger(__name__)
CONF = cfg.CONF
ADMIN_USER_NAME = "os_admin"
CONNECTION_STR_FORMAT = ("mysql+pymysql://%s:%s@localhost/?"
                         "unix_socket=/var/run/mysqld/mysqld.sock")
ENGINE = None
INCLUDE_MARKER_OPERATORS = {
    True: ">=",
    False: ">"
}
MYSQL_CONFIG = "/etc/mysql/my.cnf"
CNF_EXT = 'cnf'
CNF_INCLUDE_DIR = '/etc/mysql/conf.d'
CNF_MASTER = 'master-replication'
CNF_SLAVE = 'slave-replication'

BACKUP_LOG = re.compile(r'.*Backup successfully, checksum: (?P<checksum>.*), '
                        r'location: (?P<location>.*)')


class BaseMySqlAppStatus(service.BaseDbStatus):
    def __init__(self, docker_client):
        super(BaseMySqlAppStatus, self).__init__(docker_client)

    def get_actual_db_status(self):
        """Check database service status."""
        status = docker_util.get_container_status(self.docker_client)
        if status == "running":
            root_pass = commmon_service.BaseMySqlApp.get_auth_password(
                file="root.cnf")
            cmd = 'mysql -uroot -p%s -e "select 1;"' % root_pass
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


@six.add_metaclass(abc.ABCMeta)
class BaseMySqlAdmin(object):
    """Handles administrative tasks on the MySQL database."""

    def __init__(self, mysql_root_access, mysql_app):
        self.mysql_root_access = mysql_root_access
        self.mysql_app = mysql_app

    def _associate_dbs(self, user):
        """Internal. Given a MySQLUser, populate its databases attribute."""
        LOG.debug("Associating dbs to user %(name)s at %(host)s.",
                  {'name': user.name, 'host': user.host})
        with mysql_util.SqlClient(self.mysql_app.get_engine()) as client:
            q = sql_query.Query()
            q.columns = ["grantee", "table_schema"]
            q.tables = ["information_schema.SCHEMA_PRIVILEGES"]
            q.group = ["grantee", "table_schema"]
            q.where = ["privilege_type != 'USAGE'"]
            t = text(str(q))
            db_result = client.execute(t)
            for db in db_result:
                LOG.debug("\t db: %s.", db)
                if db['grantee'] == "'%s'@'%s'" % (user.name, user.host):
                    user.databases = db['table_schema']

    def change_passwords(self, users):
        """Change the passwords of one or more existing users."""
        LOG.debug("Changing the password of some users.")
        with mysql_util.SqlClient(self.mysql_app.get_engine()) as client:
            for item in users:
                LOG.debug("Changing password for user %s.", item)
                user_dict = {'_name': item['name'],
                             '_host': item['host'],
                             '_password': item['password']}
                user = models.MySQLUser.deserialize(user_dict)
                LOG.debug("\tDeserialized: %s.", user.__dict__)
                uu = sql_query.SetPassword(user.name, host=user.host,
                                           new_password=user.password)
                t = text(str(uu))
                client.execute(t)

    def update_attributes(self, username, hostname, user_attrs):
        """Change the attributes of an existing user."""
        LOG.debug("Changing user attributes for user %s.", username)
        user = self._get_user(username, hostname)

        new_name = user_attrs.get('name')
        new_host = user_attrs.get('host')
        new_password = user_attrs.get('password')

        if new_name or new_host or new_password:

            with mysql_util.SqlClient(self.mysql_app.get_engine()) as client:

                if new_password is not None:
                    uu = sql_query.SetPassword(user.name, host=user.host,
                                               new_password=new_password)

                    t = text(str(uu))
                    client.execute(t)

                if new_name or new_host:
                    uu = sql_query.RenameUser(user.name, host=user.host,
                                              new_user=new_name,
                                              new_host=new_host)
                    t = text(str(uu))
                    client.execute(t)

    def create_database(self, databases):
        """Create the list of specified databases."""
        with mysql_util.SqlClient(self.mysql_app.get_engine()) as client:
            for item in databases:
                mydb = models.MySQLSchema.deserialize(item)
                mydb.check_create()
                cd = sql_query.CreateDatabase(mydb.name,
                                              mydb.character_set,
                                              mydb.collate)
                t = text(str(cd))
                LOG.debug('Creating database, command: %s', str(cd))
                client.execute(t)

    def create_user(self, users):
        """Create users and grant them privileges for the
           specified databases.
        """
        with mysql_util.SqlClient(self.mysql_app.get_engine()) as client:
            for item in users:
                user = models.MySQLUser.deserialize(item)
                user.check_create()

                cu = sql_query.CreateUser(user.name, host=user.host,
                                          clear=user.password)
                t = text(str(cu))
                client.execute(t, **cu.keyArgs)

                for database in user.databases:
                    mydb = models.MySQLSchema.deserialize(database)
                    g = sql_query.Grant(permissions='ALL', database=mydb.name,
                                        user=user.name, host=user.host)
                    t = text(str(g))
                    LOG.debug('Creating user, command: %s', str(g))
                    client.execute(t)

    def delete_database(self, database):
        """Delete the specified database."""
        with mysql_util.SqlClient(self.mysql_app.get_engine()) as client:
            mydb = models.MySQLSchema.deserialize(database)
            mydb.check_delete()
            dd = sql_query.DropDatabase(mydb.name)
            t = text(str(dd))
            client.execute(t)

    def delete_user(self, user):
        """Delete the specified user."""
        mysql_user = models.MySQLUser.deserialize(user)
        mysql_user.check_delete()
        self.delete_user_by_name(mysql_user.name, mysql_user.host)

    def delete_user_by_name(self, name, host='%'):
        with mysql_util.SqlClient(self.mysql_app.get_engine()) as client:
            du = sql_query.DropUser(name, host=host)
            t = text(str(du))
            LOG.debug("delete_user_by_name: %s", t)
            client.execute(t)

    def get_user(self, username, hostname):
        user = self._get_user(username, hostname)
        if not user:
            return None
        return user.serialize()

    def _get_user(self, username, hostname):
        """Return a single user matching the criteria."""
        user = None
        try:
            # Could possibly throw a ValueError here.
            user = models.MySQLUser(name=username)
            user.check_reserved()
        except ValueError as ve:
            LOG.exception("Error Getting user information")
            err_msg = encodeutils.exception_to_unicode(ve)
            raise exception.BadRequest(_("Username %(user)s is not valid"
                                         ": %(reason)s") %
                                       {'user': username, 'reason': err_msg}
                                       )
        with mysql_util.SqlClient(self.mysql_app.get_engine()) as client:
            q = sql_query.Query()
            q.columns = ['User', 'Host']
            q.tables = ['mysql.user']
            q.where = ["Host != 'localhost'",
                       "User = '%s'" % username,
                       "Host = '%s'" % hostname]
            q.order = ['User', 'Host']
            t = text(str(q))
            result = client.execute(t).fetchall()
            LOG.debug("Getting user information %s.", result)
            if len(result) != 1:
                return None
            found_user = result[0]
            user.host = found_user['Host']
            self._associate_dbs(user)
            return user

    def grant_access(self, username, hostname, databases):
        """Grant a user permission to use a given database."""
        user = self._get_user(username, hostname)
        mydb = None  # cache the model as we just want name validation
        with mysql_util.SqlClient(self.mysql_app.get_engine()) as client:
            for database in databases:
                try:
                    if mydb:
                        mydb.name = database
                    else:
                        mydb = models.MySQLSchema(name=database)
                        mydb.check_reserved()
                except ValueError:
                    LOG.exception("Error granting access")
                    raise exception.BadRequest(_(
                        "Grant access to %s is not allowed") % database)

                g = sql_query.Grant(permissions='ALL', database=mydb.name,
                                    user=user.name, host=user.host,
                                    hashed=user.password)
                t = text(str(g))
                client.execute(t)

    def is_root_enabled(self):
        """Return True if root access is enabled; False otherwise."""
        return self.mysql_root_access.is_root_enabled()

    def enable_root(self, root_password=None):
        """Enable the root user global access and/or
           reset the root password.
        """
        return self.mysql_root_access.enable_root(root_password)

    def disable_root(self):
        """Disable the root user global access
        """
        return self.mysql_root_access.disable_root()

    def list_databases(self, limit=None, marker=None, include_marker=False):
        """List databases on this mysql instance."""
        LOG.info("Listing Databases")
        ignored_database_names = "'%s'" % "', '".join(cfg.get_ignored_dbs())
        LOG.debug("The following database names are on ignore list and will "
                  "be omitted from the listing: %s", ignored_database_names)
        databases = []
        with mysql_util.SqlClient(self.mysql_app.get_engine()) as client:
            # If you have an external volume mounted at /var/lib/mysql
            # the lost+found directory will show up in mysql as a database
            # which will create errors if you try to do any database ops
            # on it.  So we remove it here if it exists.
            q = sql_query.Query()
            q.columns = [
                'schema_name as name',
                'default_character_set_name as charset',
                'default_collation_name as collation',
            ]
            q.tables = ['information_schema.schemata']
            q.where = ["schema_name NOT IN (" + ignored_database_names + ")"]
            q.order = ['schema_name ASC']
            if limit:
                q.limit = limit + 1
            if marker:
                q.where.append("schema_name %s '%s'" %
                               (INCLUDE_MARKER_OPERATORS[include_marker],
                                marker))
            t = text(str(q))
            database_names = client.execute(t)
            next_marker = None
            for count, database in enumerate(database_names):
                if limit is not None and count >= limit:
                    break
                mysql_db = models.MySQLSchema(name=database[0],
                                              character_set=database[1],
                                              collate=database[2])
                next_marker = mysql_db.name
                databases.append(mysql_db.serialize())

        LOG.info("databases = %s", str(databases))
        if limit is not None and database_names.rowcount <= limit:
            next_marker = None
        return databases, next_marker

    def list_users(self, limit=None, marker=None, include_marker=False):
        """List users that have access to the database."""
        '''
        SELECT
            User,
            Host,
            Marker
        FROM
            (SELECT
                User,
                Host,
                CONCAT(User, '@', Host) as Marker
            FROM mysql.user
            ORDER BY 1, 2) as innerquery
        WHERE
            Marker > :marker
        ORDER BY
            Marker
        LIMIT :limit;
        '''
        LOG.info("Listing Users")
        ignored_user_names = "'%s'" % "', '".join(cfg.get_ignored_users())
        LOG.debug("The following user names are on ignore list and will "
                  "be omitted from the listing: %s", ignored_user_names)
        users = []
        with mysql_util.SqlClient(self.mysql_app.get_engine()) as client:
            iq = sql_query.Query()  # Inner query.
            iq.columns = ['User', 'Host', "CONCAT(User, '@', Host) as Marker"]
            iq.tables = ['mysql.user']
            iq.order = ['User', 'Host']
            innerquery = str(iq).rstrip(';')

            oq = sql_query.Query()  # Outer query.
            oq.columns = ['User', 'Host', 'Marker']
            oq.tables = ['(%s) as innerquery' % innerquery]
            oq.where = [
                "Host != 'localhost'",
                "User NOT IN (" + ignored_user_names + ")"]
            oq.order = ['Marker']
            if marker:
                oq.where.append("Marker %s '%s'" %
                                (INCLUDE_MARKER_OPERATORS[include_marker],
                                 marker))
            if limit:
                oq.limit = limit + 1
            t = text(str(oq))
            result = client.execute(t)
            next_marker = None
            for count, row in enumerate(result):
                if limit is not None and count >= limit:
                    break
                LOG.debug("user = %s", str(row))
                mysql_user = models.MySQLUser(name=row['User'],
                                              host=row['Host'])
                mysql_user.check_reserved()
                self._associate_dbs(mysql_user)
                next_marker = row['Marker']
                users.append(mysql_user.serialize())
        if limit is not None and result.rowcount <= limit:
            next_marker = None
        LOG.info("users = %s", str(users))

        return users, next_marker

    def revoke_access(self, username, hostname, database):
        """Revoke a user's permission to use a given database."""
        user = self._get_user(username, hostname)
        with mysql_util.SqlClient(self.mysql_app.get_engine()) as client:
            r = sql_query.Revoke(database=database,
                                 user=user.name,
                                 host=user.host)
            t = text(str(r))
            client.execute(t)

    def list_access(self, username, hostname):
        """Show all the databases to which the user has more than
           USAGE granted.
        """
        user = self._get_user(username, hostname)
        return user.databases


@six.add_metaclass(abc.ABCMeta)
class BaseMySqlApp(object):
    """Prepares DBaaS on a Guest container."""

    CFG_CODEC = IniCodec()
    configuration_manager = ConfigurationManager(
        MYSQL_CONFIG, CONF.database_service_uid, CONF.database_service_uid,
        CFG_CODEC, requires_root=True,
        override_strategy=ImportOverrideStrategy(CNF_INCLUDE_DIR, CNF_EXT)
    )

    def __init__(self, status, docker_client):
        """By default login with root no password for initial setup."""
        self.status = status
        self.docker_client = docker_client

    def get_engine(self):
        """Create the default engine with the updated admin user.

        If admin user not created yet, use root instead.
        """
        global ENGINE
        if ENGINE:
            return ENGINE

        user = ADMIN_USER_NAME
        password = ""
        try:
            password = self.get_auth_password()
        except exception.UnprocessableEntity:
            # os_admin user not created yet
            user = 'root'

        ENGINE = sqlalchemy.create_engine(
            CONNECTION_STR_FORMAT % (user,
                                     urllib.parse.quote(password.strip())),
            pool_recycle=120, echo=CONF.sql_query_logging,
            listeners=[mysql_util.BaseKeepAliveConnection()])

        return ENGINE

    def execute_sql(self, sql_statement):
        LOG.debug("Executing SQL: %s", sql_statement)
        with mysql_util.SqlClient(self.get_engine()) as client:
            return client.execute(sql_statement)

    @classmethod
    def get_auth_password(cls, file="os_admin.cnf"):
        auth_config = operating_system.read_file(
            cls.get_client_auth_file(file), codec=cls.CFG_CODEC, as_root=True)
        return auth_config['client']['password']

    @classmethod
    def get_data_dir(cls):
        return cls.configuration_manager.get_value(
            MySQLConfParser.SERVER_CONF_SECTION).get('datadir')

    @classmethod
    def set_data_dir(cls, value):
        cls.configuration_manager.apply_system_override(
            {MySQLConfParser.SERVER_CONF_SECTION: {'datadir': value}})

    @classmethod
    def get_client_auth_file(cls, file="os_admin.cnf"):
        # Save the password inside the mount point directory so we could
        # restore everyting when rebuilding the instance.
        conf_dir = guestagent_utils.get_conf_dir()
        return guestagent_utils.build_file_path(conf_dir, file)

    def _create_admin_user(self, client, password):
        """
        Create a os_admin user with a random password
        with all privileges similar to the root user.
        """
        LOG.info("Creating Trove admin user '%s'.", ADMIN_USER_NAME)
        host = "localhost"
        try:
            cu = sql_query.CreateUser(ADMIN_USER_NAME, host=host,
                                      clear=password)
            t = text(str(cu))
            client.execute(t, **cu.keyArgs)
        except (exc.OperationalError, exc.InternalError) as err:
            # Ignore, user is already created, just reset the password
            # (user will already exist in a restore from backup)
            LOG.debug(err)
            uu = sql_query.SetPassword(ADMIN_USER_NAME, host=host,
                                       new_password=password)
            t = text(str(uu))
            client.execute(t)

        g = sql_query.Grant(permissions='ALL', user=ADMIN_USER_NAME,
                            host=host, grant_option=True)
        t = text(str(g))
        client.execute(t)
        LOG.info("Trove admin user '%s' created.", ADMIN_USER_NAME)

    @staticmethod
    def save_password(user, password):
        content = {'client': {'user': user,
                              'password': password,
                              'host': "localhost"}}

        conf_dir = guestagent_utils.get_conf_dir()
        operating_system.write_file(
            f'{conf_dir}/{user}.cnf', content, codec=IniCodec(), as_root=True)

    def secure(self):
        LOG.info("Securing MySQL now.")

        root_pass = self.get_auth_password(file="root.cnf")
        admin_password = utils.generate_random_password()

        engine = sqlalchemy.create_engine(
            CONNECTION_STR_FORMAT % ('root', root_pass), echo=True)
        with mysql_util.SqlClient(engine, use_flush=False) as client:
            self._create_admin_user(client, admin_password)

        engine = sqlalchemy.create_engine(
            CONNECTION_STR_FORMAT % (ADMIN_USER_NAME,
                                     urllib.parse.quote(admin_password)),
            echo=True)
        with mysql_util.SqlClient(engine) as client:
            self._remove_anonymous_user(client)

        self.save_password(ADMIN_USER_NAME, admin_password)
        LOG.info("MySQL secure complete.")

    def secure_root(self):
        with mysql_util.SqlClient(self.get_engine()) as client:
            self._remove_remote_root_access(client)

    def _remove_anonymous_user(self, client):
        LOG.debug("Removing anonymous user.")
        t = text(sql_query.REMOVE_ANON)
        client.execute(t)
        LOG.debug("Anonymous user removed.")

    def _remove_remote_root_access(self, client):
        LOG.debug("Removing remote root access.")
        t = text(sql_query.REMOVE_ROOT)
        client.execute(t)
        LOG.debug("Root remote access removed.")

    def update_overrides(self, overrides):
        if overrides:
            self.configuration_manager.apply_user_override(
                {MySQLConfParser.SERVER_CONF_SECTION: overrides})

    def remove_overrides(self):
        self.configuration_manager.remove_user_override()

    def apply_overrides(self, overrides):
        LOG.info("Applying overrides to running MySQL, overrides: %s",
                 overrides)
        with mysql_util.SqlClient(self.get_engine()) as client:
            for k, v in overrides.items():
                byte_value = guestagent_utils.to_bytes(v)
                q = sql_query.SetServerVariable(key=k, value=byte_value)
                t = text(str(q))
                try:
                    client.execute(t)
                except exc.OperationalError:
                    output = {'key': k, 'value': byte_value}
                    LOG.error("Unable to set %(key)s with value %(value)s.",
                              output)

    def start_db(self, update_db=False, ds_version=None, command=None,
                 extra_volumes=None):
        """Start and wait for database service."""
        docker_image = CONF.get(CONF.datastore_manager).docker_image
        image = (f'{docker_image}:latest' if not ds_version else
                 f'{docker_image}:{ds_version}')
        command = command if command else ''

        try:
            root_pass = self.get_auth_password(file="root.cnf")
        except exception.UnprocessableEntity:
            root_pass = utils.generate_random_password()

        # Get uid and gid
        user = "%s:%s" % (CONF.database_service_uid, CONF.database_service_uid)

        # Create folders for mysql on localhost
        for folder in ['/etc/mysql', '/var/run/mysqld']:
            operating_system.create_directory(
                folder, user=CONF.database_service_uid,
                group=CONF.database_service_uid, force=True,
                as_root=True)

        volumes = {
            "/etc/mysql": {"bind": "/etc/mysql", "mode": "rw"},
            "/var/run/mysqld": {"bind": "/var/run/mysqld",
                                "mode": "rw"},
            "/var/lib/mysql": {"bind": "/var/lib/mysql", "mode": "rw"},
        }
        if extra_volumes:
            volumes.update(extra_volumes)

        try:
            LOG.info("Starting docker container, image: %s", image)
            docker_util.start_container(
                self.docker_client,
                image,
                volumes=volumes,
                network_mode="host",
                user=user,
                environment={
                    "MYSQL_ROOT_PASSWORD": root_pass,
                    "MYSQL_INITDB_SKIP_TZINFO": 1,
                },
                command=command
            )

            # Save root password
            LOG.debug("Saving root credentials to local host.")
            self.save_password('root', root_pass)
        except Exception:
            LOG.exception("Failed to start mysql")
            raise exception.TroveError(_("Failed to start mysql"))

        if not self.status.wait_for_real_status_to_change_to(
            service_status.ServiceStatuses.HEALTHY,
            CONF.state_change_wait_time, update_db
        ):
            raise exception.TroveError(_("Failed to start mysql"))

    def start_db_with_conf_changes(self, config_contents, ds_version):
        LOG.info(f"Starting database service with new configuration and "
                 f"datastore version {ds_version}.")

        if self.status.is_running:
            LOG.info("Stopping MySQL before applying changes.")
            self.stop_db()

        self._reset_configuration(config_contents)
        self.start_db(update_db=True, ds_version=ds_version)

    def stop_db(self, update_db=False):
        LOG.info("Stopping MySQL.")

        try:
            docker_util.stop_container(self.docker_client)
        except Exception:
            LOG.exception("Failed to stop mysql")
            raise exception.TroveError("Failed to stop mysql")

        if not self.status.wait_for_real_status_to_change_to(
            service_status.ServiceStatuses.SHUTDOWN,
            CONF.state_change_wait_time, update_db):
            raise exception.TroveError("Failed to stop mysql")

    def wipe_ib_logfiles(self):
        """Destroys the iblogfiles.

        If for some reason the selected log size in the conf changes from the
        current size of the files MySQL will fail to start, so we delete the
        files to be safe.
        """
        for index in range(2):
            try:
                # On restarts, sometimes these are wiped. So it can be a race
                # to have MySQL start up before it's restarted and these have
                # to be deleted. That's why its ok if they aren't found and
                # that is why we use the "force" option to "remove".
                operating_system.remove("%s/ib_logfile%d"
                                        % (self.get_data_dir(), index),
                                        force=True, as_root=True)
            except exception.ProcessExecutionError:
                LOG.exception("Could not delete logfile.")
                raise

    def _reset_configuration(self, configuration, admin_password=None):
        self.configuration_manager.save_configuration(configuration)
        if admin_password:
            self.save_password(ADMIN_USER_NAME, admin_password)
        self.wipe_ib_logfiles()

    def reset_configuration(self, configuration):
        config_contents = configuration['config_contents']
        LOG.info("Resetting configuration.")
        self._reset_configuration(config_contents)

    def restart(self):
        LOG.info("Restarting mysql")

        # Ensure folders permission for database.
        for folder in ['/etc/mysql', '/var/run/mysqld']:
            operating_system.create_directory(
                folder, user=CONF.database_service_uid,
                group=CONF.database_service_uid, force=True,
                as_root=True)

        try:
            docker_util.restart_container(self.docker_client)
        except Exception:
            LOG.exception("Failed to restart mysql")
            raise exception.TroveError("Failed to restart mysql")

        if not self.status.wait_for_real_status_to_change_to(
            service_status.ServiceStatuses.HEALTHY,
            CONF.state_change_wait_time, update_db=False):
            raise exception.TroveError("Failed to start mysql")

        LOG.info("Finished restarting mysql")

    def create_backup(self, context, backup_info):
        storage_driver = CONF.storage_strategy
        backup_driver = cfg.get_configuration_property('backup_strategy')
        incremental = ''
        backup_type = 'full'
        if backup_info.get('parent'):
            incremental = (
                f'--incremental '
                f'--parent-location={backup_info["parent"]["location"]} '
                f'--parent-checksum={backup_info["parent"]["checksum"]}')
            backup_type = 'incremental'

        backup_id = backup_info["id"]
        image = CONF.backup_docker_image
        name = 'db_backup'
        volumes = {'/var/lib/mysql': {'bind': '/var/lib/mysql', 'mode': 'rw'}}
        admin_pass = self.get_auth_password()
        user_token = context.auth_token
        auth_url = CONF.service_credentials.auth_url
        user_tenant = context.project_id

        swift_metadata = (
            f'datastore:{backup_info["datastore"]},'
            f'datastore_version:{backup_info["datastore_version"]}'
        )
        swift_params = f'--swift-extra-metadata={swift_metadata}'
        swift_container = backup_info.get('swift_container',
                                          CONF.backup_swift_container)
        if backup_info.get('swift_container'):
            swift_params = (
                f'{swift_params} '
                f'--swift-container {swift_container}'
            )

        command = (
            f'/usr/bin/python3 main.py --backup --backup-id={backup_id} '
            f'--storage-driver={storage_driver} --driver={backup_driver} '
            f'--db-user=os_admin --db-password={admin_pass} '
            f'--db-host=127.0.0.1 '
            f'--os-token={user_token} --os-auth-url={auth_url} '
            f'--os-tenant-id={user_tenant} '
            f'{swift_params} '
            f'{incremental}'
        )

        # Update backup status in db
        conductor = conductor_api.API(context)
        mount_point = CONF.get(CONF.datastore_manager).mount_point
        stats = guestagent_utils.get_filesystem_volume_stats(mount_point)
        backup_state = {
            'backup_id': backup_id,
            'size': stats.get('used', 0.0),
            'state': BackupState.BUILDING,
            'backup_type': backup_type
        }
        conductor.update_backup(CONF.guest_id,
                                sent=timeutils.utcnow_ts(microsecond=True),
                                **backup_state)
        LOG.debug("Updated state for %s to %s.", backup_id, backup_state)

        # Start to run backup inside a separate docker container
        try:
            LOG.info('Starting to create backup %s, command: %s', backup_id,
                     command)
            output, ret = docker_util.run_container(
                self.docker_client, image, name,
                volumes=volumes, command=command)
            result = output[-1]
            if not ret:
                msg = f'Failed to run backup container, error: {result}'
                LOG.error(msg)
                raise Exception(msg)

            backup_result = BACKUP_LOG.match(result)
            if backup_result:
                backup_state.update({
                    'checksum': backup_result.group('checksum'),
                    'location': backup_result.group('location'),
                    'success': True,
                    'state': BackupState.COMPLETED,
                })
            else:
                LOG.error(f'Cannot parse backup output: {result}')
                backup_state.update({
                    'success': False,
                    'state': BackupState.FAILED,
                })
        except Exception as err:
            LOG.error("Failed to create backup %s", backup_id)
            backup_state.update({
                'success': False,
                'state': BackupState.FAILED,
            })
            raise exception.TroveError(
                "Failed to create backup %s, error: %s" %
                (backup_id, str(err))
            )
        finally:
            LOG.info("Completed backup %s.", backup_id)
            conductor.update_backup(CONF.guest_id,
                                    sent=timeutils.utcnow_ts(
                                        microsecond=True),
                                    **backup_state)
            LOG.debug("Updated state for %s to %s.", backup_id, backup_state)

    def restore_backup(self, context, backup_info, restore_location):
        backup_id = backup_info['id']
        storage_driver = CONF.storage_strategy
        backup_driver = cfg.get_configuration_property('backup_strategy')
        user_token = context.auth_token
        auth_url = CONF.service_credentials.auth_url
        user_tenant = context.project_id
        image = CONF.backup_docker_image
        name = 'db_restore'
        volumes = {'/var/lib/mysql': {'bind': '/var/lib/mysql', 'mode': 'rw'}}

        command = (
            f'/usr/bin/python3 main.py --nobackup '
            f'--storage-driver={storage_driver} --driver={backup_driver} '
            f'--os-token={user_token} --os-auth-url={auth_url} '
            f'--os-tenant-id={user_tenant} '
            f'--restore-from={backup_info["location"]} '
            f'--restore-checksum={backup_info["checksum"]}'
        )

        LOG.debug('Stop the database and clean up the data before restore '
                  'from %s', backup_id)
        self.stop_db()
        operating_system.chmod(restore_location,
                               operating_system.FileMode.SET_FULL,
                               as_root=True)
        utils.clean_out(restore_location)

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

        LOG.debug('Deleting ib_logfile files after restore from backup %s',
                  backup_id)
        operating_system.chown(restore_location, CONF.database_service_uid,
                               CONF.database_service_uid, force=True,
                               as_root=True)
        self.wipe_ib_logfiles()

    def exists_replication_source_overrides(self):
        return self.configuration_manager.has_system_override(CNF_MASTER)

    def write_replication_source_overrides(self, overrideValues):
        self.configuration_manager.apply_system_override(overrideValues,
                                                         CNF_MASTER)

    def write_replication_replica_overrides(self, overrideValues):
        self.configuration_manager.apply_system_override(overrideValues,
                                                         CNF_SLAVE)

    def remove_replication_source_overrides(self):
        self.configuration_manager.remove_system_override(CNF_MASTER)

    def remove_replication_replica_overrides(self):
        self.configuration_manager.remove_system_override(CNF_SLAVE)

    def grant_replication_privilege(self, replication_user):
        LOG.info("Granting replication slave privilege for %s",
                 replication_user['name'])

        with mysql_util.SqlClient(self.get_engine()) as client:
            g = sql_query.Grant(permissions=['REPLICATION SLAVE'],
                                user=replication_user['name'],
                                clear=replication_user['password'])

            t = text(str(g))
            client.execute(t)

    def get_port(self):
        with mysql_util.SqlClient(self.get_engine()) as client:
            result = client.execute('SELECT @@port').first()
            return result[0]

    def wait_for_slave_status(self, status, client, max_time):
        def verify_slave_status():
            ret = client.execute(
                "SELECT SERVICE_STATE FROM "
                "performance_schema.replication_connection_status").first()
            if not ret:
                actual_status = 'OFF'
            else:
                actual_status = ret[0]
            return actual_status.upper() == status.upper()

        LOG.debug("Waiting for slave status %s with timeout %s",
                  status, max_time)
        try:
            utils.poll_until(verify_slave_status, sleep_time=3,
                             time_out=max_time)
            LOG.info("Replication status: %s.", status)
        except exception.PollTimeOut:
            raise RuntimeError(
                _("Replication is not %(status)s after %(max)d seconds.") % {
                    'status': status.lower(), 'max': max_time})

    def start_slave(self):
        LOG.info("Starting slave replication.")
        with mysql_util.SqlClient(self.get_engine()) as client:
            client.execute('START SLAVE')
            self.wait_for_slave_status("ON", client, 180)

    def stop_slave(self, for_failover):
        LOG.info("Stopping slave replication.")

        replication_user = None
        with mysql_util.SqlClient(self.get_engine()) as client:
            result = client.execute('SHOW SLAVE STATUS')
            replication_user = result.first()['Master_User']
            client.execute('STOP SLAVE')
            client.execute('RESET SLAVE ALL')
            self.wait_for_slave_status('OFF', client, 180)
            if not for_failover:
                client.execute('DROP USER IF EXISTS ' + replication_user)

        return {
            'replication_user': replication_user
        }

    def stop_master(self):
        LOG.info("Stopping replication master.")
        with mysql_util.SqlClient(self.get_engine()) as client:
            client.execute('RESET MASTER')

    def make_read_only(self, read_only):
        with mysql_util.SqlClient(self.get_engine()) as client:
            q = "set global read_only = %s" % read_only
            client.execute(text(str(q)))

    def upgrade(self, upgrade_info):
        """Upgrade the database."""
        new_version = upgrade_info.get('datastore_version')

        LOG.info('Stopping db container for upgrade')
        self.stop_db()

        LOG.info('Deleting db container for upgrade')
        docker_util.remove_container(self.docker_client)

        LOG.info('Starting new db container with version %s for upgrade',
                 new_version)
        self.start_db(update_db=True, ds_version=new_version)


class BaseMySqlRootAccess(object):
    def __init__(self, mysql_app):
        self.mysql_app = mysql_app

    def is_root_enabled(self):
        """Return True if root access is enabled; False otherwise."""
        with mysql_util.SqlClient(self.mysql_app.get_engine()) as client:
            t = text(sql_query.ROOT_ENABLED)
            result = client.execute(t)
            LOG.debug("Found %s with remote root access.", result.rowcount)
            return result.rowcount != 0

    def enable_root(self, root_password=None):
        """Enable the root user global access and/or
           reset the root password.
        """
        user = models.MySQLUser.root(password=root_password)
        with mysql_util.SqlClient(self.mysql_app.get_engine()) as client:
            try:
                cu = sql_query.CreateUser(user.name, host=user.host)
                t = text(str(cu))
                client.execute(t, **cu.keyArgs)
            except (exc.OperationalError, exc.InternalError) as err:
                # Ignore, user is already created, just reset the password
                # TODO(rnirmal): More fine grained error checking later on
                LOG.debug(err)
        with mysql_util.SqlClient(self.mysql_app.get_engine()) as client:
            uu = sql_query.SetPassword(user.name, host=user.host,
                                       new_password=user.password)
            t = text(str(uu))
            client.execute(t)

            LOG.debug("CONF.root_grant: %(grant)s CONF.root_grant_option: "
                      "%(grant_option)s.",
                      {'grant': CONF.root_grant,
                       'grant_option': CONF.root_grant_option})

            g = sql_query.Grant(permissions=CONF.root_grant,
                                user=user.name,
                                host=user.host,
                                grant_option=CONF.root_grant_option)

            t = text(str(g))
            client.execute(t)
            return user.serialize()

    def disable_root(self):
        """Reset the root password to an unknown value.
        """
        self.enable_root(root_password=None)
