import os
import passlib.utils
import re
import uuid
from datetime import date
import sqlalchemy
from sqlalchemy import exc
from sqlalchemy import interfaces
from sqlalchemy.sql.expression import text

from trove.common import cfg
from trove.common import utils as utils
from trove.common import exception
from trove.common import instance as rd_instance
from trove.guestagent.common import operating_system
from trove.guestagent.common import sql_query
from trove.guestagent.db import models
from trove.guestagent import pkg
from trove.guestagent.datastore import service
from trove.openstack.common import log as logging
from trove.openstack.common.gettextutils import _
from trove.extensions.mysql.models import RootHistory

ADMIN_USER_NAME = "os_admin"
LOG = logging.getLogger(__name__)
FLUSH = text(sql_query.FLUSH)
ENGINE = None
PREPARING = False
UUID = False

TMP_MYCNF = "/tmp/my.cnf.tmp"
MYSQL_BASE_DIR = "/var/lib/mysql"

CONF = cfg.CONF
INCLUDE_MARKER_OPERATORS = {
    True: ">=",
    False: ">"
}

MYSQL_CONFIG = "/etc/mysql/my.cnf"
MYSQL_SERVICE_CANDIDATES = ["mysql", "mysqld", "mysql-server"]
MYSQL_BIN_CANDIDATES = ["/usr/sbin/mysqld", "/usr/libexec/mysqld"]


# Create a package impl
packager = pkg.Package()


def generate_random_password():
    return passlib.utils.generate_password(size=CONF.default_password_length)


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
        LOG.debug("/root/.mysql_secret is not exists.")
        return
    m = re.match('# The random password set for the root user at .*: (.*)',
                 out)
    if m:
        try:
            out, err = utils.execute("mysqladmin", "-p%s" % m.group(1),
                                     "password", "", run_as_root=True,
                                     root_helper="sudo")
        except exception.ProcessExecutionError:
            LOG.error("Cannot change mysql password.")
            return
        utils.execute("rm", "-f", secret_file, run_as_root=True,
                      root_helper="sudo")
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
    #TODO(rnirmal):Based on permissions issues being resolved we may revert
    #url = URL(drivername='mysql', host='localhost',
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
    #find mysqld bin
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
        args = {}
        for item in arglist:
            if "=" in item:
                key, value = item.split("=")
                args[key.lstrip("--")] = value
            else:
                args[item.lstrip("--")] = None
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
                "ping", run_as_root=True, root_helper="sudo")
            LOG.info("Service Status is RUNNING.")
            return rd_instance.ServiceStatuses.RUNNING
        except exception.ProcessExecutionError:
            LOG.error("Process execution ")
            try:
                out, err = utils.execute_with_timeout("/bin/ps", "-C",
                                                      "mysqld", "h")
                pid = out.split()[0]
                # TODO(rnirmal): Need to create new statuses for instances
                # where the mysql service is up, but unresponsive
                LOG.info('MySQL pid: %(pid)s' % {'pid': pid})
                LOG.info("Service Status is BLOCKED.")
                return rd_instance.ServiceStatuses.BLOCKED
            except exception.ProcessExecutionError:
                mysql_args = load_mysqld_options()
                pid_file = mysql_args.get('pid_file',
                                          '/var/run/mysqld/mysqld.pid')
                if os.path.exists(pid_file):
                    LOG.info("Service Status is CRASHED.")
                    return rd_instance.ServiceStatuses.CRASHED
                else:
                    LOG.info("Service Status is SHUTDOWN.")
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
        LOG.debug("Associating dbs to user %s at %s" % (user.name, user.host))
        with LocalSqlClient(get_engine()) as client:
            q = sql_query.Query()
            q.columns = ["grantee", "table_schema"]
            q.tables = ["information_schema.SCHEMA_PRIVILEGES"]
            q.group = ["grantee", "table_schema"]
            q.where = ["privilege_type != 'USAGE'"]
            t = text(str(q))
            db_result = client.execute(t)
            for db in db_result:
                LOG.debug("\t db: %s" % db)
                if db['grantee'] == "'%s'@'%s'" % (user.name, user.host):
                    mysql_db = models.MySQLDatabase()
                    mysql_db.name = db['table_schema']
                    user.databases.append(mysql_db.serialize())

    def change_passwords(self, users):
        """Change the passwords of one or more existing users."""
        LOG.debug("Changing the password of some users.")
        LOG.debug("Users is %s" % users)
        with LocalSqlClient(get_engine()) as client:
            for item in users:
                LOG.debug("\tUser: %s" % item)
                user_dict = {'_name': item['name'],
                             '_host': item['host'],
                             '_password': item['password']}
                user = models.MySQLUser()
                user.deserialize(user_dict)
                LOG.debug("\tDeserialized: %s" % user.__dict__)
                uu = sql_query.UpdateUser(user.name, host=user.host,
                                          clear=user.password)
                t = text(str(uu))
                client.execute(t)

    def update_attributes(self, username, hostname, user_attrs):
        """Change the attributes of an existing user."""
        LOG.debug("Changing the user attributes")
        LOG.debug("User is %s" % username)
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
           specified databases."""
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
        with LocalSqlClient(get_engine()) as client:
            mysql_user = models.MySQLUser()
            mysql_user.deserialize(user)
            du = sql_query.DropUser(mysql_user.name, host=mysql_user.host)
            t = text(str(du))
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
        except exceptions.ValueError as ve:
            raise exception.BadRequest("Username %s is not valid: %s"
                                       % (username, ve.message))
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
            LOG.debug("Result: %s" % result)
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
        with LocalSqlClient(get_engine()) as client:
            for database in databases:
                g = sql_query.Grant(permissions='ALL', database=database,
                                    user=user.name, host=user.host,
                                    hashed=user.password)
                t = text(str(g))
                client.execute(t)

    def is_root_enabled(self):
        """Return True if root access is enabled; False otherwise."""
        return MySqlRootAccess.is_root_enabled()

    def enable_root(self, root_password=None):
        """Enable the root user global access and/or
           reset the root password."""
        return MySqlRootAccess.enable_root(root_password)

    def report_root_enabled(self, context=None):
        """Records in the Root History that the root is enabled."""
        return MySqlRootAccess.report_root_enabled(context)

    def list_databases(self, limit=None, marker=None, include_marker=False):
        """List databases the user created on this mysql instance."""
        LOG.debug(_("---Listing Databases---"))
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
            q.where = ["schema_name NOT IN ("
                       "'mysql', 'information_schema', "
                       "'lost+found', '#mysql50#lost+found'"
                       ")"]
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
            LOG.debug(_("database_names = %r") % database_names)
            for count, database in enumerate(database_names):
                if count >= limit:
                    break
                LOG.debug(_("database = %s ") % str(database))
                mysql_db = models.MySQLDatabase()
                mysql_db.name = database[0]
                next_marker = mysql_db.name
                mysql_db.character_set = database[1]
                mysql_db.collate = database[2]
                databases.append(mysql_db.serialize())
        LOG.debug(_("databases = ") + str(databases))
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
        LOG.debug(_("---Listing Users---"))
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
                                 host=user.host,
                                 hashed=user.password)
            t = text(str(r))
            client.execute(t)

    def list_access(self, username, hostname):
        """Show all the databases to which the user has more than
           USAGE granted."""
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
                                  clear=generate_random_password())
        t = text(str(uu))
        client.execute(t)

    def install_if_needed(self, packages):
        """Prepare the guest machine with a secure
           mysql server installation."""
        LOG.info(_("Preparing Guest as MySQL Server"))
        if not packager.pkg_is_installed(packages):
            LOG.debug(_("Installing mysql server"))
            self._clear_mysql_config()
            # set blank password on pkg configuration stage
            pkg_opts = {'root_password': '',
                        'root_password_again': ''}
            packager.pkg_install(packages, pkg_opts, self.TIME_OUT)
            self._create_mysql_confd_dir()
            LOG.debug(_("Finished installing mysql server"))
        self.start_mysql()
        LOG.info(_("Dbaas install_if_needed complete"))

    def complete_install_or_restart(self):
        self.status.end_install_or_restart()

    def secure(self, config_contents):
        LOG.info(_("Generating admin password..."))
        admin_password = generate_random_password()
        clear_expired_password()
        engine = sqlalchemy.create_engine("mysql://root:@localhost:3306",
                                          echo=True)
        with LocalSqlClient(engine) as client:
            self._remove_anonymous_user(client)
            self._create_admin_user(client, admin_password)

        self.stop_db()
        self._write_mycnf(admin_password, config_contents)
        self.start_mysql()

        LOG.info(_("Dbaas secure complete."))

    def secure_root(self, secure_remote_root=True):
        with LocalSqlClient(get_engine()) as client:
            LOG.info(_("Preserving root access from restore"))
            self._generate_root_password(client)
            if secure_remote_root:
                self._remove_remote_root_access(client)

    def _clear_mysql_config(self):
        """Clear old configs, which can be incompatible with new version."""
        LOG.debug("Clearing old mysql config")
        random_uuid = str(uuid.uuid4())
        configs = ["/etc/my.cnf", "/etc/mysql/conf.d", "/etc/mysql/my.cnf"]
        for config in configs:
            command = "mv %s %s_%s" % (config, config, random_uuid)
            try:
                utils.execute_with_timeout(command, shell=True,
                                           root_helper="sudo")
                LOG.debug("%s saved to %s_%s" % (config, config, random_uuid))
            except exception.ProcessExecutionError:
                pass

    def _create_mysql_confd_dir(self):
        conf_dir = "/etc/mysql/conf.d"
        LOG.debug("Creating %s" % conf_dir)
        command = "sudo mkdir -p %s" % conf_dir
        utils.execute_with_timeout(command, shell=True)

    def _enable_mysql_on_boot(self):
        LOG.info("Enabling mysql on boot.")
        try:
            mysql_service = operating_system.service_discovery(
                MYSQL_SERVICE_CANDIDATES)
            utils.execute_with_timeout(mysql_service['cmd_enable'], shell=True)
        except KeyError:
            raise RuntimeError("Service is not discovered.")

    def _disable_mysql_on_boot(self):
        try:
            mysql_service = operating_system.service_discovery(
                MYSQL_SERVICE_CANDIDATES)
            utils.execute_with_timeout(mysql_service['cmd_disable'],
                                       shell=True)
        except KeyError:
            raise RuntimeError("Service is not discovered.")

    def stop_db(self, update_db=False, do_not_start_on_reboot=False):
        LOG.info(_("Stopping mysql..."))
        if do_not_start_on_reboot:
            self._disable_mysql_on_boot()
        try:
            mysql_service = operating_system.service_discovery(
                MYSQL_SERVICE_CANDIDATES)
            utils.execute_with_timeout(mysql_service['cmd_stop'], shell=True)
        except KeyError:
            raise RuntimeError("Service is not discovered.")
        if not self.status.wait_for_real_status_to_change_to(
                rd_instance.ServiceStatuses.SHUTDOWN,
                self.state_change_wait_time, update_db):
            LOG.error(_("Could not stop MySQL!"))
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

    def _replace_mycnf_with_template(self, template_path, original_path):
        LOG.debug("replacing the mycnf with template")
        LOG.debug("template_path(%s) original_path(%s)"
                  % (template_path, original_path))
        if os.path.isfile(template_path):
            if os.path.isfile(original_path):
                utils.execute_with_timeout(
                    "sudo", "mv", original_path,
                    "%(name)s.%(date)s" %
                    {'name': original_path, 'date':
                        date.today().isoformat()})
            utils.execute_with_timeout("sudo", "cp", template_path,
                                       original_path)

    def _write_temp_mycnf_with_admin_account(self, original_file_path,
                                             temp_file_path, password):
        utils.execute_with_timeout("sudo", "chmod", "0711", MYSQL_BASE_DIR)
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
        LOG.info(_("Wiping ib_logfiles..."))
        for index in range(2):
            try:
                (utils.
                 execute_with_timeout("sudo", "rm", "%s/ib_logfile%d"
                                                    % (MYSQL_BASE_DIR, index)))
            except exception.ProcessExecutionError as pe:
                # On restarts, sometimes these are wiped. So it can be a race
                # to have MySQL start up before it's restarted and these have
                # to be deleted. That's why its ok if they aren't found.
                LOG.error("Could not delete logfile!")
                LOG.error(pe)
                if "No such file or directory" not in str(pe):
                    raise

    def _write_mycnf(self, admin_password, config_contents):
        """
        Install the set of mysql my.cnf templates.
        Update the os_admin user and password to the my.cnf
        file for direct login from localhost.
        """
        LOG.info(_("Writing my.cnf templates."))
        if admin_password is None:
            admin_password = get_auth_password()

        with open(TMP_MYCNF, 'w') as t:
            t.write(config_contents)
        utils.execute_with_timeout("sudo", "mv", TMP_MYCNF,
                                   MYSQL_CONFIG)

        self._write_temp_mycnf_with_admin_account(MYSQL_CONFIG,
                                                  TMP_MYCNF,
                                                  admin_password)
        utils.execute_with_timeout("sudo", "mv", TMP_MYCNF,
                                   MYSQL_CONFIG)

        self.wipe_ib_logfiles()

    def start_mysql(self, update_db=False):
        LOG.info(_("Starting mysql..."))
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
            LOG.error(_("Start up of MySQL failed!"))
            # If it won't start, but won't die either, kill it by hand so we
            # don't let a rouge process wander around.
            try:
                utils.execute_with_timeout("sudo", "pkill", "-9", "mysql")
            except exception.ProcessExecutionError as p:
                LOG.error("Error killing stalled mysql start command.")
                LOG.error(p)
                # There's nothing more we can do...
            self.status.end_install_or_restart()
            raise RuntimeError("Could not start MySQL!")

    def start_db_with_conf_changes(self, config_contents):
        LOG.info(_("Starting mysql with conf changes..."))
        LOG.info(_("inside the guest - self.status.is_mysql_running(%s)...")
                 % self.status.is_running)
        if self.status.is_running:
            LOG.error(_("Cannot execute start_db_with_conf_changes because "
                        "MySQL state == %s!") % self.status)
            raise RuntimeError("MySQL not stopped.")
        LOG.info(_("Initiating config."))
        self._write_mycnf(None, config_contents)
        self.start_mysql(True)

    def reset_configuration(self, configuration):
        config_contents = configuration['config_contents']
        LOG.info(_("Resetting configuration"))
        self._write_mycnf(None, config_contents)


class MySqlRootAccess(object):
    @classmethod
    def is_root_enabled(cls):
        """Return True if root access is enabled; False otherwise."""
        with LocalSqlClient(get_engine()) as client:
            t = text(sql_query.ROOT_ENABLED)
            result = client.execute(t)
            LOG.debug("Found %s with remote root access" % result.rowcount)
            return result.rowcount != 0

    @classmethod
    def enable_root(cls, root_password=None):
        """Enable the root user global access and/or
           reset the root password."""
        user = models.RootUser()
        user.name = "root"
        user.host = "%"
        user.password = root_password or generate_random_password()
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

            LOG.debug("CONF.root_grant: %s CONF.root_grant_option: %s" %
                      (CONF.root_grant, CONF.root_grant_option))

            g = sql_query.Grant(permissions=CONF.root_grant,
                                user=user.name,
                                host=user.host,
                                grant_option=CONF.root_grant_option,
                                clear=user.password)

            t = text(str(g))
            client.execute(t)
            return user.serialize()

    @classmethod
    def report_root_enabled(cls, context):
        return RootHistory.create(context, CONF.guest_id, 'root')
