# Copyright 2013 OpenStack Foundation
# Copyright 2013 Rackspace Hosting
# Copyright 2013 Hewlett-Packard Development Company, L.P.
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

from collections import defaultdict
import os
import re
import uuid

import sqlalchemy
from sqlalchemy import exc
from sqlalchemy import interfaces
from sqlalchemy.sql.expression import text

from trove.common import cfg
from trove.common import exception
from trove.common.exception import PollTimeOut
from trove.common.i18n import _
from trove.common import instance as rd_instance
from trove.common import utils as utils
from trove.guestagent.common import operating_system
from trove.guestagent.common.operating_system import FileMode
from trove.guestagent.common import sql_query
from trove.guestagent.datastore import service
from trove.guestagent.db import models
from trove.guestagent import pkg
from trove.openstack.common import log as logging

ADMIN_USER_NAME = "os_admin"
LOG = logging.getLogger(__name__)
FLUSH = text(sql_query.FLUSH)
ENGINE = None
PREPARING = False
UUID = False

TMP_MYCNF = "/tmp/my.cnf.tmp"
MYSQL_BASE_DIR = "/var/lib/mysql"

CONF = cfg.CONF
MANAGER = CONF.datastore_manager if CONF.datastore_manager else 'mysql'

INCLUDE_MARKER_OPERATORS = {
    True: ">=",
    False: ">"
}

OS_NAME = operating_system.get_os()
MYSQL_CONFIG = {operating_system.REDHAT: "/etc/my.cnf",
                operating_system.DEBIAN: "/etc/mysql/my.cnf",
                operating_system.SUSE: "/etc/my.cnf"}[OS_NAME]
MYSQL_SERVICE_CANDIDATES = ["mysql", "mysqld", "mysql-server"]
MYSQL_BIN_CANDIDATES = ["/usr/sbin/mysqld", "/usr/libexec/mysqld"]
MYCNF_OVERRIDES = "/etc/mysql/conf.d/overrides.cnf"
MYCNF_OVERRIDES_TMP = "/tmp/overrides.cnf.tmp"
MYCNF_REPLMASTER = "/etc/mysql/conf.d/0replmaster.cnf"
MYCNF_REPLSLAVE = "/etc/mysql/conf.d/1replslave.cnf"
MYCNF_REPLCONFIG_TMP = "/tmp/replication.cnf.tmp"


# Create a package impl
packager = pkg.Package()


def clear_expired_password():
    """
    Some mysql installations generate random root password
    and save it in /root/.mysql_secret, this password is
    expired and should be changed by client that supports expired passwords.
    """
    LOG.debug("Removing expired password.")
    secret_file = "/root/.mysql_secret"
    try:
        out, err = utils.execute("cat", secret_file,
                                 run_as_root=True, root_helper="sudo")
    except exception.ProcessExecutionError:
        LOG.exception(_("/root/.mysql_secret does not exist."))
        return
    m = re.match('# The random password set for the root user at .*: (.*)',
                 out)
    if m:
        try:
            out, err = utils.execute("mysqladmin", "-p%s" % m.group(1),
                                     "password", "", run_as_root=True,
                                     root_helper="sudo")
        except exception.ProcessExecutionError:
            LOG.exception(_("Cannot change mysql password."))
            return
        operating_system.remove(secret_file, force=True, as_root=True)
        LOG.debug("Expired password removed.")


def get_auth_password():
    pwd, err = utils.execute_with_timeout(
        "sudo",
        "awk",
        "/password\\t=/{print $3; exit}",
        MYSQL_CONFIG)
    if err:
        LOG.error(err)
        raise RuntimeError("Problem reading my.cnf! : %s" % err)
    return pwd.strip()


def get_engine():
    """Create the default engine with the updated admin user."""
    # TODO(rnirmal):Based on permissions issues being resolved we may revert
    # url = URL(drivername='mysql', host='localhost',
    #          query={'read_default_file': '/etc/mysql/my.cnf'})
    global ENGINE
    if ENGINE:
        return ENGINE
    pwd = get_auth_password()
    ENGINE = sqlalchemy.create_engine("mysql://%s:%s@localhost:3306" %
                                      (ADMIN_USER_NAME, pwd.strip()),
                                      pool_recycle=7200,
                                      echo=CONF.sql_query_logging,
                                      listeners=[KeepAliveConnection()])
    return ENGINE


def load_mysqld_options():
    # find mysqld bin
    for bin in MYSQL_BIN_CANDIDATES:
        if os.path.isfile(bin):
            mysqld_bin = bin
            break
    else:
        return {}
    try:
        out, err = utils.execute(mysqld_bin, "--print-defaults",
                                 run_as_root=True, root_helper="sudo")
        arglist = re.split("\n", out)[1].split()
        args = defaultdict(list)
        for item in arglist:
            if "=" in item:
                key, value = item.split("=", 1)
                args[key.lstrip("--")].append(value)
            else:
                args[item.lstrip("--")].append(None)
        return args
    except exception.ProcessExecutionError:
        return {}


class MySqlAppStatus(service.BaseDbStatus):
    @classmethod
    def get(cls):
        if not cls._instance:
            cls._instance = MySqlAppStatus()
        return cls._instance

    def _get_actual_db_status(self):
        try:
            out, err = utils.execute_with_timeout(
                "/usr/bin/mysqladmin",
                "ping", run_as_root=True, root_helper="sudo",
                log_output_on_error=True)
            LOG.info(_("MySQL Service Status is RUNNING."))
            return rd_instance.ServiceStatuses.RUNNING
        except exception.ProcessExecutionError:
            LOG.exception(_("Failed to get database status."))
            try:
                out, err = utils.execute_with_timeout("/bin/ps", "-C",
                                                      "mysqld", "h")
                pid = out.split()[0]
                # TODO(rnirmal): Need to create new statuses for instances
                # where the mysql service is up, but unresponsive
                LOG.info(_('MySQL Service Status %(pid)s is BLOCKED.') %
                         {'pid': pid})
                return rd_instance.ServiceStatuses.BLOCKED
            except exception.ProcessExecutionError:
                LOG.exception(_("Process execution failed."))
                mysql_args = load_mysqld_options()
                pid_file = mysql_args.get('pid_file',
                                          ['/var/run/mysqld/mysqld.pid'])[0]
                if os.path.exists(pid_file):
                    LOG.info(_("MySQL Service Status is CRASHED."))
                    return rd_instance.ServiceStatuses.CRASHED
                else:
                    LOG.info(_("MySQL Service Status is SHUTDOWN."))
                    return rd_instance.ServiceStatuses.SHUTDOWN


class LocalSqlClient(object):
    """A sqlalchemy wrapper to manage transactions."""

    def __init__(self, engine, use_flush=True):
        self.engine = engine
        self.use_flush = use_flush

    def __enter__(self):
        self.conn = self.engine.connect()
        self.trans = self.conn.begin()
        return self.conn

    def __exit__(self, type, value, traceback):
        if self.trans:
            if type is not None:  # An error occurred
                self.trans.rollback()
            else:
                if self.use_flush:
                    self.conn.execute(FLUSH)
                self.trans.commit()
        self.conn.close()

    def execute(self, t, **kwargs):
        try:
            return self.conn.execute(t, kwargs)
        except Exception:
            self.trans.rollback()
            self.trans = None
            raise


class MySqlAdmin(object):
    """Handles administrative tasks on the MySQL database."""

    def _associate_dbs(self, user):
        """Internal. Given a MySQLUser, populate its databases attribute."""
        LOG.debug("Associating dbs to user %s at %s." %
                  (user.name, user.host))
        with LocalSqlClient(get_engine()) as client:
            q = sql_query.Query()
            q.columns = ["grantee", "table_schema"]
            q.tables = ["information_schema.SCHEMA_PRIVILEGES"]
            q.group = ["grantee", "table_schema"]
            q.where = ["privilege_type != 'USAGE'"]
            t = text(str(q))
            db_result = client.execute(t)
            for db in db_result:
                LOG.debug("\t db: %s." % db)
                if db['grantee'] == "'%s'@'%s'" % (user.name, user.host):
                    mysql_db = models.MySQLDatabase()
                    mysql_db.name = db['table_schema']
                    user.databases.append(mysql_db.serialize())

    def change_passwords(self, users):
        """Change the passwords of one or more existing users."""
        LOG.debug("Changing the password of some users.")
        with LocalSqlClient(get_engine()) as client:
            for item in users:
                LOG.debug("Changing password for user %s." % item)
                user_dict = {'_name': item['name'],
                             '_host': item['host'],
                             '_password': item['password']}
                user = models.MySQLUser()
                user.deserialize(user_dict)
                LOG.debug("\tDeserialized: %s." % user.__dict__)
                uu = sql_query.UpdateUser(user.name, host=user.host,
                                          clear=user.password)
                t = text(str(uu))
                client.execute(t)

    def update_attributes(self, username, hostname, user_attrs):
        """Change the attributes of an existing user."""
        LOG.debug("Changing user attributes for user %s." % username)
        user = self._get_user(username, hostname)
        db_access = set()
        grantee = set()
        with LocalSqlClient(get_engine()) as client:
            q = sql_query.Query()
            q.columns = ["grantee", "table_schema"]
            q.tables = ["information_schema.SCHEMA_PRIVILEGES"]
            q.group = ["grantee", "table_schema"]
            q.where = ["privilege_type != 'USAGE'"]
            t = text(str(q))
            db_result = client.execute(t)
            for db in db_result:
                grantee.add(db['grantee'])
                if db['grantee'] == "'%s'@'%s'" % (user.name, user.host):
                    db_name = db['table_schema']
                    db_access.add(db_name)
        with LocalSqlClient(get_engine()) as client:
            uu = sql_query.UpdateUser(user.name, host=user.host,
                                      clear=user_attrs.get('password'),
                                      new_user=user_attrs.get('name'),
                                      new_host=user_attrs.get('host'))
            t = text(str(uu))
            client.execute(t)
            uname = user_attrs.get('name') or username
            host = user_attrs.get('host') or hostname
            find_user = "'%s'@'%s'" % (uname, host)
            if find_user not in grantee:
                self.grant_access(uname, host, db_access)

    def create_database(self, databases):
        """Create the list of specified databases."""
        with LocalSqlClient(get_engine()) as client:
            for item in databases:
                mydb = models.ValidatedMySQLDatabase()
                mydb.deserialize(item)
                cd = sql_query.CreateDatabase(mydb.name,
                                              mydb.character_set,
                                              mydb.collate)
                t = text(str(cd))
                client.execute(t)

    def create_user(self, users):
        """Create users and grant them privileges for the
           specified databases.
        """
        with LocalSqlClient(get_engine()) as client:
            for item in users:
                user = models.MySQLUser()
                user.deserialize(item)
                # TODO(cp16net):Should users be allowed to create users
                # 'os_admin' or 'debian-sys-maint'
                g = sql_query.Grant(user=user.name, host=user.host,
                                    clear=user.password)
                t = text(str(g))
                client.execute(t)
                for database in user.databases:
                    mydb = models.ValidatedMySQLDatabase()
                    mydb.deserialize(database)
                    g = sql_query.Grant(permissions='ALL', database=mydb.name,
                                        user=user.name, host=user.host,
                                        clear=user.password)
                    t = text(str(g))
                    client.execute(t)

    def delete_database(self, database):
        """Delete the specified database."""
        with LocalSqlClient(get_engine()) as client:
            mydb = models.ValidatedMySQLDatabase()
            mydb.deserialize(database)
            dd = sql_query.DropDatabase(mydb.name)
            t = text(str(dd))
            client.execute(t)

    def delete_user(self, user):
        """Delete the specified user."""
        mysql_user = models.MySQLUser()
        mysql_user.deserialize(user)
        self.delete_user_by_name(mysql_user.name, mysql_user.host)

    def delete_user_by_name(self, name, host='%'):
        with LocalSqlClient(get_engine()) as client:
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
        user = models.MySQLUser()
        try:
            user.name = username  # Could possibly throw a BadRequest here.
        except ValueError as ve:
            LOG.exception(_("Error Getting user information"))
            raise exception.BadRequest(_("Username %(user)s is not valid"
                                         ": %(reason)s") %
                                       {'user': username, 'reason': ve.message}
                                       )
        with LocalSqlClient(get_engine()) as client:
            q = sql_query.Query()
            q.columns = ['User', 'Host', 'Password']
            q.tables = ['mysql.user']
            q.where = ["Host != 'localhost'",
                       "User = '%s'" % username,
                       "Host = '%s'" % hostname]
            q.order = ['User', 'Host']
            t = text(str(q))
            result = client.execute(t).fetchall()
            LOG.debug("Getting user information %s." % result)
            if len(result) != 1:
                return None
            found_user = result[0]
            user.password = found_user['Password']
            user.host = found_user['Host']
            self._associate_dbs(user)
            return user

    def grant_access(self, username, hostname, databases):
        """Grant a user permission to use a given database."""
        user = self._get_user(username, hostname)
        mydb = models.ValidatedMySQLDatabase()
        with LocalSqlClient(get_engine()) as client:
            for database in databases:
                    try:
                        mydb.name = database
                    except ValueError:
                        LOG.exception(_("Error granting access"))
                        raise exception.BadRequest(_(
                            "Grant access to %s is not allowed") % database)

                    g = sql_query.Grant(permissions='ALL', database=mydb.name,
                                        user=user.name, host=user.host,
                                        hashed=user.password)
                    t = text(str(g))
                    client.execute(t)

    def is_root_enabled(self):
        """Return True if root access is enabled; False otherwise."""
        return MySqlRootAccess.is_root_enabled()

    def enable_root(self, root_password=None):
        """Enable the root user global access and/or
           reset the root password.
        """
        return MySqlRootAccess.enable_root(root_password)

    def list_databases(self, limit=None, marker=None, include_marker=False):
        """List databases the user created on this mysql instance."""
        LOG.debug("---Listing Databases---")
        ignored_database_names = "'%s'" % "', '".join(CONF.ignore_dbs)
        LOG.debug("The following database names are on ignore list and will "
                  "be omitted from the listing: %s" % ignored_database_names)
        databases = []
        with LocalSqlClient(get_engine()) as client:
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
            LOG.debug("database_names = %r." % database_names)
            for count, database in enumerate(database_names):
                if count >= limit:
                    break
                LOG.debug("database = %s." % str(database))
                mysql_db = models.MySQLDatabase()
                mysql_db.name = database[0]
                next_marker = mysql_db.name
                mysql_db.character_set = database[1]
                mysql_db.collate = database[2]
                databases.append(mysql_db.serialize())
        LOG.debug("databases = " + str(databases))
        if database_names.rowcount <= limit:
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
        LOG.debug("---Listing Users---")
        users = []
        with LocalSqlClient(get_engine()) as client:
            mysql_user = models.MySQLUser()
            iq = sql_query.Query()  # Inner query.
            iq.columns = ['User', 'Host', "CONCAT(User, '@', Host) as Marker"]
            iq.tables = ['mysql.user']
            iq.order = ['User', 'Host']
            innerquery = str(iq).rstrip(';')

            oq = sql_query.Query()  # Outer query.
            oq.columns = ['User', 'Host', 'Marker']
            oq.tables = ['(%s) as innerquery' % innerquery]
            oq.where = ["Host != 'localhost'"]
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
            LOG.debug("result = " + str(result))
            for count, row in enumerate(result):
                if count >= limit:
                    break
                LOG.debug("user = " + str(row))
                mysql_user = models.MySQLUser()
                mysql_user.name = row['User']
                mysql_user.host = row['Host']
                self._associate_dbs(mysql_user)
                next_marker = row['Marker']
                users.append(mysql_user.serialize())
        if result.rowcount <= limit:
            next_marker = None
        LOG.debug("users = " + str(users))

        return users, next_marker

    def revoke_access(self, username, hostname, database):
        """Revoke a user's permission to use a given database."""
        user = self._get_user(username, hostname)
        with LocalSqlClient(get_engine()) as client:
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


class KeepAliveConnection(interfaces.PoolListener):
    """
    A connection pool listener that ensures live connections are returned
    from the connection pool at checkout. This alleviates the problem of
    MySQL connections timing out.
    """

    def checkout(self, dbapi_con, con_record, con_proxy):
        """Event triggered when a connection is checked out from the pool."""
        try:
            try:
                dbapi_con.ping(False)
            except TypeError:
                dbapi_con.ping()
        except dbapi_con.OperationalError as ex:
            if ex.args[0] in (2006, 2013, 2014, 2045, 2055):
                raise exc.DisconnectionError()
            else:
                raise


class MySqlApp(object):
    """Prepares DBaaS on a Guest container."""

    TIME_OUT = 1000

    def __init__(self, status):
        """By default login with root no password for initial setup."""
        self.state_change_wait_time = CONF.state_change_wait_time
        self.status = status

    def _create_admin_user(self, client, password):
        """
        Create a os_admin user with a random password
        with all privileges similar to the root user.
        """
        localhost = "localhost"
        g = sql_query.Grant(permissions='ALL', user=ADMIN_USER_NAME,
                            host=localhost, grant_option=True, clear=password)
        t = text(str(g))
        client.execute(t)

    @staticmethod
    def _generate_root_password(client):
        """Generate and set a random root password and forget about it."""
        localhost = "localhost"
        uu = sql_query.UpdateUser("root", host=localhost,
                                  clear=utils.generate_random_password())
        t = text(str(uu))
        client.execute(t)

    def install_if_needed(self, packages):
        """Prepare the guest machine with a secure
           mysql server installation.
        """
        LOG.info(_("Preparing Guest as MySQL Server."))
        if not packager.pkg_is_installed(packages):
            LOG.debug("Installing MySQL server.")
            self._clear_mysql_config()
            # set blank password on pkg configuration stage
            pkg_opts = {'root_password': '',
                        'root_password_again': ''}
            packager.pkg_install(packages, pkg_opts, self.TIME_OUT)
            self._create_mysql_confd_dir()
            LOG.info(_("Finished installing MySQL server."))
        self.start_mysql()

    def complete_install_or_restart(self):
        self.status.end_install_or_restart()

    def secure(self, config_contents, overrides):
        LOG.info(_("Generating admin password."))
        admin_password = utils.generate_random_password()
        clear_expired_password()
        engine = sqlalchemy.create_engine("mysql://root:@localhost:3306",
                                          echo=True)
        with LocalSqlClient(engine) as client:
            self._remove_anonymous_user(client)
            self._create_admin_user(client, admin_password)

        self.stop_db()
        self._write_mycnf(admin_password, config_contents, overrides)
        self.start_mysql()

        LOG.debug("MySQL secure complete.")

    def secure_root(self, secure_remote_root=True):
        with LocalSqlClient(get_engine()) as client:
            LOG.info(_("Preserving root access from restore."))
            self._generate_root_password(client)
            if secure_remote_root:
                self._remove_remote_root_access(client)

    def _clear_mysql_config(self):
        """Clear old configs, which can be incompatible with new version."""
        LOG.debug("Clearing old MySQL config.")
        random_uuid = str(uuid.uuid4())
        configs = ["/etc/my.cnf", "/etc/mysql/conf.d", "/etc/mysql/my.cnf"]
        for config in configs:
            try:
                old_conf_backup = "%s_%s" % (config, random_uuid)
                operating_system.move(config, old_conf_backup, as_root=True)
                LOG.debug("%s saved to %s_%s." %
                          (config, config, random_uuid))
            except exception.ProcessExecutionError:
                pass

    def _create_mysql_confd_dir(self):
        conf_dir = "/etc/mysql/conf.d"
        LOG.debug("Creating %s." % conf_dir)
        operating_system.create_directory(conf_dir, as_root=True)

    def _enable_mysql_on_boot(self):
        LOG.debug("Enabling MySQL on boot.")
        try:
            mysql_service = operating_system.service_discovery(
                MYSQL_SERVICE_CANDIDATES)
            utils.execute_with_timeout(mysql_service['cmd_enable'], shell=True)
        except KeyError:
            LOG.exception(_("Error enabling MySQL start on boot."))
            raise RuntimeError("Service is not discovered.")

    def _disable_mysql_on_boot(self):
        try:
            mysql_service = operating_system.service_discovery(
                MYSQL_SERVICE_CANDIDATES)
            utils.execute_with_timeout(mysql_service['cmd_disable'],
                                       shell=True)
        except KeyError:
            LOG.exception(_("Error disabling MySQL start on boot."))
            raise RuntimeError("Service is not discovered.")

    def stop_db(self, update_db=False, do_not_start_on_reboot=False):
        LOG.info(_("Stopping MySQL."))
        if do_not_start_on_reboot:
            self._disable_mysql_on_boot()
        try:
            mysql_service = operating_system.service_discovery(
                MYSQL_SERVICE_CANDIDATES)
            utils.execute_with_timeout(mysql_service['cmd_stop'], shell=True)
        except KeyError:
            LOG.exception(_("Error stopping MySQL."))
            raise RuntimeError("Service is not discovered.")
        if not self.status.wait_for_real_status_to_change_to(
                rd_instance.ServiceStatuses.SHUTDOWN,
                self.state_change_wait_time, update_db):
            LOG.error(_("Could not stop MySQL."))
            self.status.end_install_or_restart()
            raise RuntimeError("Could not stop MySQL!")

    def _remove_anonymous_user(self, client):
        t = text(sql_query.REMOVE_ANON)
        client.execute(t)

    def _remove_remote_root_access(self, client):
        t = text(sql_query.REMOVE_ROOT)
        client.execute(t)

    def restart(self):
        try:
            self.status.begin_restart()
            self.stop_db()
            self.start_mysql()
        finally:
            self.status.end_install_or_restart()

    def update_overrides(self, override_values):
        """
        This function will update the MySQL overrides.cnf file
        if there is content to write.

        :param override_values:
        :return:
        """

        if override_values:
            LOG.debug("Writing new overrides.cnf config file.")
            self._write_config_overrides(override_values)

    def apply_overrides(self, overrides):
        LOG.debug("Applying overrides to MySQL.")
        with LocalSqlClient(get_engine()) as client:
            LOG.debug("Updating override values in running MySQL.")
            for k, v in overrides.iteritems():
                q = sql_query.SetServerVariable(key=k, value=v)
                t = text(str(q))
                try:
                    client.execute(t)
                except exc.OperationalError:
                    output = {'key': k, 'value': v}
                    LOG.exception(_("Unable to set %(key)s with value "
                                    "%(value)s.") % output)

    def make_read_only(self, read_only):
        with LocalSqlClient(get_engine()) as client:
            q = "set global read_only = %s" % read_only
            client.execute(text(str(q)))

    def _write_temp_mycnf_with_admin_account(self, original_file_path,
                                             temp_file_path, password):
        mycnf_file = open(original_file_path, 'r')
        tmp_file = open(temp_file_path, 'w')
        for line in mycnf_file:
            tmp_file.write(line)
            if "[client]" in line:
                tmp_file.write("user\t\t= %s\n" % ADMIN_USER_NAME)
                tmp_file.write("password\t= %s\n" % password)
        mycnf_file.close()
        tmp_file.close()

    def wipe_ib_logfiles(self):
        """Destroys the iblogfiles.

        If for some reason the selected log size in the conf changes from the
        current size of the files MySQL will fail to start, so we delete the
        files to be safe.
        """
        LOG.info(_("Wiping ib_logfiles."))
        for index in range(2):
            try:
                # On restarts, sometimes these are wiped. So it can be a race
                # to have MySQL start up before it's restarted and these have
                # to be deleted. That's why its ok if they aren't found and
                # that is why we use the "force" option to "remove".
                operating_system.remove("%s/ib_logfile%d"
                                        % (MYSQL_BASE_DIR, index), force=True,
                                        as_root=True)
            except exception.ProcessExecutionError:
                LOG.exception("Could not delete logfile.")
                raise

    def _write_mycnf(self, admin_password, config_contents, overrides=None):
        """
        Install the set of mysql my.cnf templates.
        Update the os_admin user and password to the my.cnf
        file for direct login from localhost.
        """
        LOG.info(_("Writing my.cnf templates."))
        if admin_password is None:
            admin_password = get_auth_password()

        try:
            with open(TMP_MYCNF, 'w') as t:
                t.write(config_contents)

            operating_system.move(TMP_MYCNF, MYSQL_CONFIG, as_root=True)
            self._write_temp_mycnf_with_admin_account(MYSQL_CONFIG,
                                                      TMP_MYCNF,
                                                      admin_password)
            operating_system.move(TMP_MYCNF, MYSQL_CONFIG, as_root=True)
        except Exception:
            os.unlink(TMP_MYCNF)
            raise

        self.wipe_ib_logfiles()

        # write configuration file overrides
        if overrides:
            self._write_config_overrides(overrides)

    def _write_config_overrides(self, overrideValues):
        LOG.info(_("Writing new temp overrides.cnf file."))

        with open(MYCNF_OVERRIDES_TMP, 'w') as overrides:
            overrides.write(overrideValues)
        LOG.info(_("Moving overrides.cnf into correct location."))
        operating_system.move(MYCNF_OVERRIDES_TMP, MYCNF_OVERRIDES,
                              as_root=True)
        LOG.info(_("Setting permissions on overrides.cnf."))
        operating_system.chmod(MYCNF_OVERRIDES, FileMode.SET_GRP_RW_OTH_R,
                               as_root=True)

    def remove_overrides(self):
        LOG.info(_("Removing overrides configuration file."))
        if os.path.exists(MYCNF_OVERRIDES):
            operating_system.remove(MYCNF_OVERRIDES, as_root=True)

    def _write_replication_overrides(self, overrideValues, cnf_file):
        LOG.info(_("Writing replication.cnf file."))

        with open(MYCNF_REPLCONFIG_TMP, 'w') as overrides:
            overrides.write(overrideValues)
        LOG.debug("Moving temp replication.cnf into correct location.")
        operating_system.move(MYCNF_REPLCONFIG_TMP, cnf_file, as_root=True)
        LOG.debug("Setting permissions on replication.cnf.")
        operating_system.chmod(cnf_file, FileMode.SET_GRP_RW_OTH_R,
                               as_root=True)

    def _remove_replication_overrides(self, cnf_file):
        LOG.info(_("Removing replication configuration file."))
        if os.path.exists(cnf_file):
            operating_system.remove(cnf_file, as_root=True)

    def exists_replication_source_overrides(self):
        return os.path.exists(MYCNF_REPLMASTER)

    def write_replication_source_overrides(self, overrideValues):
        self._write_replication_overrides(overrideValues, MYCNF_REPLMASTER)

    def write_replication_replica_overrides(self, overrideValues):
        self._write_replication_overrides(overrideValues, MYCNF_REPLSLAVE)

    def remove_replication_source_overrides(self):
        self._remove_replication_overrides(MYCNF_REPLMASTER)

    def remove_replication_replica_overrides(self):
        self._remove_replication_overrides(MYCNF_REPLSLAVE)

    def grant_replication_privilege(self, replication_user):
        LOG.info(_("Granting Replication Slave privilege."))

        LOG.debug("grant_replication_privilege: %s" % replication_user)

        with LocalSqlClient(get_engine()) as client:
            g = sql_query.Grant(permissions=['REPLICATION SLAVE'],
                                user=replication_user['name'],
                                clear=replication_user['password'])

            t = text(str(g))
            client.execute(t)

    def get_port(self):
        with LocalSqlClient(get_engine()) as client:
            result = client.execute('SELECT @@port').first()
            return result[0]

    def get_binlog_position(self):
        with LocalSqlClient(get_engine()) as client:
            result = client.execute('SHOW MASTER STATUS').first()
            binlog_position = {
                'log_file': result['File'],
                'position': result['Position']
            }
            return binlog_position

    def execute_on_client(self, sql_statement):
        LOG.debug("Executing SQL: %s" % sql_statement)
        with LocalSqlClient(get_engine()) as client:
            return client.execute(sql_statement)

    def start_slave(self):
        LOG.info(_("Starting slave replication."))
        with LocalSqlClient(get_engine()) as client:
            client.execute('START SLAVE')
            self._wait_for_slave_status("ON", client, 60)

    def stop_slave(self, for_failover):
        replication_user = None
        LOG.info(_("Stopping slave replication."))
        with LocalSqlClient(get_engine()) as client:
            result = client.execute('SHOW SLAVE STATUS')
            replication_user = result.first()['Master_User']
            client.execute('STOP SLAVE')
            client.execute('RESET SLAVE ALL')
            self._wait_for_slave_status("OFF", client, 30)
            if not for_failover:
                client.execute('DROP USER ' + replication_user)
        return {
            'replication_user': replication_user
        }

    def stop_master(self):
        LOG.info(_("Stopping replication master."))
        with LocalSqlClient(get_engine()) as client:
            client.execute('RESET MASTER')

    def _wait_for_slave_status(self, status, client, max_time):

        def verify_slave_status():
            actual_status = client.execute(
                "SHOW GLOBAL STATUS like 'slave_running'").first()[1]
            return actual_status.upper() == status.upper()

        LOG.debug("Waiting for SLAVE_RUNNING to change to %s.", status)
        try:
            utils.poll_until(verify_slave_status, sleep_time=3,
                             time_out=max_time)
            LOG.info(_("Replication is now %s.") % status.lower())
        except PollTimeOut:
            raise RuntimeError(
                _("Replication is not %(status)s after %(max)d seconds.") % {
                    'status': status.lower(), 'max': max_time})

    def start_mysql(self, update_db=False):
        LOG.info(_("Starting MySQL."))
        # This is the site of all the trouble in the restart tests.
        # Essentially what happens is that mysql start fails, but does not
        # die. It is then impossible to kill the original, so

        self._enable_mysql_on_boot()

        try:
            mysql_service = operating_system.service_discovery(
                MYSQL_SERVICE_CANDIDATES)
            utils.execute_with_timeout(mysql_service['cmd_start'], shell=True)
        except KeyError:
            raise RuntimeError("Service is not discovered.")
        except exception.ProcessExecutionError:
            # it seems mysql (percona, at least) might come back with [Fail]
            # but actually come up ok. we're looking into the timing issue on
            # parallel, but for now, we'd like to give it one more chance to
            # come up. so regardless of the execute_with_timeout() response,
            # we'll assume mysql comes up and check it's status for a while.
            pass
        if not self.status.wait_for_real_status_to_change_to(
                rd_instance.ServiceStatuses.RUNNING,
                self.state_change_wait_time, update_db):
            LOG.error(_("Start up of MySQL failed."))
            # If it won't start, but won't die either, kill it by hand so we
            # don't let a rouge process wander around.
            try:
                utils.execute_with_timeout("sudo", "pkill", "-9", "mysql")
            except exception.ProcessExecutionError:
                LOG.exception(_("Error killing stalled MySQL start command."))
                # There's nothing more we can do...
            self.status.end_install_or_restart()
            raise RuntimeError("Could not start MySQL!")

    def start_db_with_conf_changes(self, config_contents):
        LOG.info(_("Starting MySQL with conf changes."))
        LOG.debug("Inside the guest - Status is_running = (%s)."
                  % self.status.is_running)
        if self.status.is_running:
            LOG.error(_("Cannot execute start_db_with_conf_changes because "
                        "MySQL state == %s.") % self.status)
            raise RuntimeError("MySQL not stopped.")
        LOG.info(_("Resetting configuration."))
        self._write_mycnf(None, config_contents)
        self.start_mysql(True)

    def reset_configuration(self, configuration):
        config_contents = configuration['config_contents']
        LOG.info(_("Resetting configuration."))
        self._write_mycnf(None, config_contents)

    # DEPRECATED: Mantain for API Compatibility
    def get_txn_count(self):
        LOG.info(_("Retrieving latest txn id."))
        txn_count = 0
        with LocalSqlClient(get_engine()) as client:
            result = client.execute('SELECT @@global.gtid_executed').first()
            for uuid_set in result[0].split(','):
                for interval in uuid_set.split(':')[1:]:
                    if '-' in interval:
                        iparts = interval.split('-')
                        txn_count += int(iparts[1]) - int(iparts[0])
                    else:
                        txn_count += 1
        return txn_count

    def _get_slave_status(self):
        with LocalSqlClient(get_engine()) as client:
            return client.execute('SHOW SLAVE STATUS').first()

    def _get_master_UUID(self):
        slave_status = self._get_slave_status()
        return slave_status and slave_status['Master_UUID'] or None

    def _get_gtid_executed(self):
        with LocalSqlClient(get_engine()) as client:
            return client.execute('SELECT @@global.gtid_executed').first()[0]

    def get_last_txn(self):
        master_UUID = self._get_master_UUID()
        last_txn_id = '0'
        gtid_executed = self._get_gtid_executed()
        for gtid_set in gtid_executed.split(','):
            uuid_set = gtid_set.split(':')
            if uuid_set[0] == master_UUID:
                last_txn_id = uuid_set[-1].split('-')[-1]
                break
        return master_UUID, int(last_txn_id)

    def get_latest_txn_id(self):
        LOG.info(_("Retrieving latest txn id."))
        return self._get_gtid_executed()

    def wait_for_txn(self, txn):
        LOG.info(_("Waiting on txn '%s'.") % txn)
        with LocalSqlClient(get_engine()) as client:
            client.execute("SELECT WAIT_UNTIL_SQL_THREAD_AFTER_GTIDS('%s')"
                           % txn)


class MySqlRootAccess(object):
    @classmethod
    def is_root_enabled(cls):
        """Return True if root access is enabled; False otherwise."""
        with LocalSqlClient(get_engine()) as client:
            t = text(sql_query.ROOT_ENABLED)
            result = client.execute(t)
            LOG.debug("Found %s with remote root access." % result.rowcount)
            return result.rowcount != 0

    @classmethod
    def enable_root(cls, root_password=None):
        """Enable the root user global access and/or
           reset the root password.
        """
        user = models.RootUser()
        user.name = "root"
        user.host = "%"
        user.password = root_password or utils.generate_random_password()
        with LocalSqlClient(get_engine()) as client:
            print(client)
            try:
                cu = sql_query.CreateUser(user.name, host=user.host)
                t = text(str(cu))
                client.execute(t, **cu.keyArgs)
            except exc.OperationalError as err:
                # Ignore, user is already created, just reset the password
                # TODO(rnirmal): More fine grained error checking later on
                LOG.debug(err)
        with LocalSqlClient(get_engine()) as client:
            print(client)
            uu = sql_query.UpdateUser(user.name, host=user.host,
                                      clear=user.password)
            t = text(str(uu))
            client.execute(t)

            LOG.debug("CONF.root_grant: %s CONF.root_grant_option: %s." %
                      (CONF.root_grant, CONF.root_grant_option))

            g = sql_query.Grant(permissions=CONF.root_grant,
                                user=user.name,
                                host=user.host,
                                grant_option=CONF.root_grant_option,
                                clear=user.password)

            t = text(str(g))
            client.execute(t)
            return user.serialize()
