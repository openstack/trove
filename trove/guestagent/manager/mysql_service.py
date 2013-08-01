import os
import re
import time
import uuid
import sqlalchemy

from datetime import date
from sqlalchemy import exc
from sqlalchemy import interfaces
from sqlalchemy.sql.expression import text

from trove.common import cfg
from trove.common import utils as utils
from trove.common import exception
from trove.guestagent import query
from trove.guestagent.db import models
from trove.guestagent.pkg import Package
from trove.instance import models as rd_models
from trove.openstack.common import log as logging
from trove.openstack.common.gettextutils import _
from trove.extensions.mysql.models import RootHistory

ADMIN_USER_NAME = "os_admin"
LOG = logging.getLogger(__name__)
FLUSH = text(query.FLUSH)

ENGINE = None
MYSQLD_ARGS = None
PREPARING = False
UUID = False

TMP_MYCNF = "/tmp/my.cnf.tmp"
MYSQL_BASE_DIR = "/var/lib/mysql"

CONF = cfg.CONF
INCLUDE_MARKER_OPERATORS = {
    True: ">=",
    False: ">"
}

# Create a package impl
pkg = Package()


def generate_random_password():
    return str(uuid.uuid4())


def get_auth_password():
    pwd, err = utils.execute_with_timeout(
        "sudo",
        "awk",
        "/password\\t=/{print $3; exit}",
        "/etc/mysql/my.cnf")
    if err:
        LOG.error(err)
        raise RuntimeError("Problem reading my.cnf! : %s" % err)
    return pwd.strip()


def get_engine():
        """Create the default engine with the updated admin user"""
        #TODO(rnirmal):Based on permissions issues being resolved we may revert
        #url = URL(drivername='mysql', host='localhost',
        #          query={'read_default_file': '/etc/mysql/my.cnf'})
        global ENGINE
        if ENGINE:
            return ENGINE
        #ENGINE = create_engine(name_or_url=url)
        pwd = get_auth_password()
        ENGINE = sqlalchemy.create_engine("mysql://%s:%s@localhost:3306" %
                                          (ADMIN_USER_NAME, pwd.strip()),
                                          pool_recycle=7200, echo=True,
                                          listeners=[KeepAliveConnection()])
        return ENGINE


def load_mysqld_options():
    try:
        out, err = utils.execute("/usr/sbin/mysqld", "--print-defaults",
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
    except exception.ProcessExecutionError as e:
        return None


class MySqlAppStatus(object):
    """
    Answers the question "what is the status of the MySQL application on
    this box?" The answer can be that the application is not installed, or
    the state of the application is determined by calling a series of
    commands.

    This class also handles saving and load the status of the MySQL application
    in the database.
    The status is updated whenever the update() method is called, except
    if the state is changed to building or restart mode using the
     "begin_mysql_install" and "begin_mysql_restart" methods.
    The building mode persists in the database while restarting mode does
    not (so if there is a Python Pete crash update() will set the status to
    show a failure).
    These modes are exited and functionality to update() returns when
    end_install_or_restart() is called, at which point the status again
    reflects the actual status of the MySQL app.
    """

    _instance = None

    def __init__(self):
        if self._instance is not None:
            raise RuntimeError("Cannot instantiate twice.")
        self.status = self._load_status().status
        self.restart_mode = False

    def begin_mysql_install(self):
        """Called right before MySQL is prepared."""
        self.set_status(rd_models.ServiceStatuses.BUILDING)

    def begin_mysql_restart(self):
        """Called before restarting MySQL."""
        self.restart_mode = True

    def end_install_or_restart(self):
        """Called after MySQL is installed or restarted.

        Updates the database with the actual MySQL status.
        """
        LOG.info("Ending install_if_needed or restart.")
        self.restart_mode = False
        real_status = self._get_actual_db_status()
        LOG.info("Updating status to %s" % real_status)
        self.set_status(real_status)

    @classmethod
    def get(cls):
        if not cls._instance:
            cls._instance = MySqlAppStatus()
        return cls._instance

    def _get_actual_db_status(self):
        global MYSQLD_ARGS
        try:
            out, err = utils.execute_with_timeout(
                "/usr/bin/mysqladmin",
                "ping", run_as_root=True, root_helper="sudo")
            LOG.info("Service Status is RUNNING.")
            return rd_models.ServiceStatuses.RUNNING
        except exception.ProcessExecutionError as e:
            LOG.error("Process execution ")
            try:
                out, err = utils.execute_with_timeout("/bin/ps", "-C",
                                                      "mysqld", "h")
                pid = out.split()[0]
                # TODO(rnirmal): Need to create new statuses for instances
                # where the mysql service is up, but unresponsive
                LOG.info("Service Status is BLOCKED.")
                return rd_models.ServiceStatuses.BLOCKED
            except exception.ProcessExecutionError as e:
                if not MYSQLD_ARGS:
                    MYSQLD_ARGS = load_mysqld_options()
                pid_file = MYSQLD_ARGS.get('pid_file',
                                           '/var/run/mysqld/mysqld.pid')
                if os.path.exists(pid_file):
                    LOG.info("Service Status is CRASHED.")
                    return rd_models.ServiceStatuses.CRASHED
                else:
                    LOG.info("Service Status is SHUTDOWN.")
                    return rd_models.ServiceStatuses.SHUTDOWN

    @property
    def is_mysql_installed(self):
        """
        True if MySQL app should be installed and attempts to ascertain
        its status won't result in nonsense.
        """
        return (self.status is not None and
                self.status != rd_models.ServiceStatuses.NEW and
                self.status != rd_models.ServiceStatuses.BUILDING and
                self.status != rd_models.ServiceStatuses.FAILED)

    @property
    def _is_mysql_restarting(self):
        return self.restart_mode

    @property
    def is_mysql_running(self):
        """True if MySQL is running."""
        return (self.status is not None and
                self.status == rd_models.ServiceStatuses.RUNNING)

    @staticmethod
    def _load_status():
        """Loads the status from the database."""
        inst_id = CONF.guest_id
        return rd_models.InstanceServiceStatus.find_by(instance_id=inst_id)

    def set_status(self, status):
        """Changes the status of the MySQL app in the database."""
        db_status = self._load_status()
        db_status.status = status
        db_status.save()
        self.status = status

    def update(self):
        """Find and report status of MySQL on this machine.

        The database is update and the status is also returned.
        """
        if self.is_mysql_installed and not self._is_mysql_restarting:
            LOG.info("Determining status of MySQL app...")
            status = self._get_actual_db_status()
            self.set_status(status)
        else:
            LOG.info("MySQL is not installed or is in restart mode, so for "
                     "now we'll skip determining the status of MySQL on this "
                     "box.")

    def wait_for_real_status_to_change_to(self, status, max_time,
                                          update_db=False):
        """
        Waits the given time for the real status to change to the one
        specified. Does not update the publicly viewable status Unless
        "update_db" is True.
        """
        WAIT_TIME = 3
        waited_time = 0
        while waited_time < max_time:
            time.sleep(WAIT_TIME)
            waited_time += WAIT_TIME
            LOG.info("Waiting for MySQL status to change to %s..." % status)
            actual_status = self._get_actual_db_status()
            LOG.info("MySQL status was %s after %d seconds."
                     % (actual_status, waited_time))
            if actual_status == status:
                if update_db:
                    self.set_status(actual_status)
                return True
        LOG.error("Time out while waiting for MySQL app status to change!")
        return False


class LocalSqlClient(object):
    """A sqlalchemy wrapper to manage transactions"""

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
        except:
            self.trans.rollback()
            self.trans = None
            raise


class MySqlAdmin(object):
    """Handles administrative tasks on the MySQL database."""

    def _associate_dbs(self, user):
        """Internal. Given a MySQLUser, populate its databases attribute."""
        LOG.debug("Associating dbs to user %s at %s" % (user.name, user.host))
        with LocalSqlClient(get_engine()) as client:
            q = query.Query()
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
                             '_password': item['password'],
                             }
                user = models.MySQLUser()
                user.deserialize(user_dict)
                LOG.debug("\tDeserialized: %s" % user.__dict__)
                uu = query.UpdateUser(user.name, host=user.host,
                                      clear=user.password)
                t = text(str(uu))
                client.execute(t)

    def update_attributes(self, username, hostname, user_attrs):
        """Change the attributes of one existing user."""
        LOG.debug("Changing the user attributes")
        LOG.debug("User is %s" % username)
        user = self._get_user(username, hostname)
        db_access = set()
        grantee = set()
        with LocalSqlClient(get_engine()) as client:
            q = query.Query()
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
            uu = query.UpdateUser(user.name, host=user.host,
                                  clear=user_attrs.get('password'),
                                  new_user=user_attrs.get('name'),
                                  new_host=user_attrs.get('host'))
            t = text(str(uu))
            client.execute(t)
            if user_attrs.get('name') is not None:
                if user_attrs['name'] not in grantee:
                    if user_attrs.get('host') is None:
                        host = user.host
                    else:
                        host = user_attrs.get('host')
                    self.grant_access(user_attrs['name'], host, db_access)

    def create_database(self, databases):
        """Create the list of specified databases"""
        with LocalSqlClient(get_engine()) as client:
            for item in databases:
                mydb = models.ValidatedMySQLDatabase()
                mydb.deserialize(item)
                cd = query.CreateDatabase(mydb.name,
                                          mydb.character_set,
                                          mydb.collate)
                t = text(str(cd))
                client.execute(t)

    def create_user(self, users):
        """Create users and grant them privileges for the
           specified databases"""
        with LocalSqlClient(get_engine()) as client:
            for item in users:
                user = models.MySQLUser()
                user.deserialize(item)
                # TODO(cp16net):Should users be allowed to create users
                # 'os_admin' or 'debian-sys-maint'
                g = query.Grant(user=user.name, host=user.host,
                                clear=user.password)
                t = text(str(g))
                client.execute(t)
                for database in user.databases:
                    mydb = models.ValidatedMySQLDatabase()
                    mydb.deserialize(database)
                    g = query.Grant(permissions='ALL', database=mydb.name,
                                    user=user.name, host=user.host,
                                    clear=user.password)
                    t = text(str(g))
                    client.execute(t)

    def delete_database(self, database):
        """Delete the specified database"""
        with LocalSqlClient(get_engine()) as client:
            mydb = models.ValidatedMySQLDatabase()
            mydb.deserialize(database)
            dd = query.DropDatabase(mydb.name)
            t = text(str(dd))
            client.execute(t)

    def delete_user(self, user):
        """Delete the specified users"""
        with LocalSqlClient(get_engine()) as client:
            mysql_user = models.MySQLUser()
            mysql_user.deserialize(user)
            du = query.DropUser(mysql_user.name, host=mysql_user.host)
            t = text(str(du))
            client.execute(t)

    def get_user(self, username, hostname):
        user = self._get_user(username, hostname)
        if not user:
            return None
        return user.serialize()

    def _get_user(self, username, hostname):
        """Return a single user matching the criteria"""
        user = models.MySQLUser()
        try:
            user.name = username  # Could possibly throw a BadRequest here.
        except exceptions.ValueError as ve:
            raise exception.BadRequest("Username %s is not valid: %s"
                                       % (username, ve.message))
        with LocalSqlClient(get_engine()) as client:
            q = query.Query()
            q.columns = ['User', 'Host', 'Password']
            q.tables = ['mysql.user']
            q.where = ["Host != 'localhost'",
                       "User = '%s'" % username,
                       "Host = '%s'" % hostname,
                       ]
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
        """Give a user permission to use a given database."""
        user = self._get_user(username, hostname)
        with LocalSqlClient(get_engine()) as client:
            for database in databases:
                g = query.Grant(permissions='ALL', database=database,
                                user=user.name, host=user.host,
                                hashed=user.password)
                t = text(str(g))
                client.execute(t)

    def is_root_enabled(self):
        """Return True if root access is enabled; False otherwise."""
        return MySqlRootAccess.is_root_enabled()

    def enable_root(self):
        """Enable the root user global access and/or reset the root password"""
        return MySqlRootAccess.enable_root()

    def report_root_enabled(self, context=None):
        """Records in the Root History that the root is enabled"""
        return MySqlRootAccess.report_root_enabled(context)

    def list_databases(self, limit=None, marker=None, include_marker=False):
        """List databases the user created on this mysql instance"""
        LOG.debug(_("---Listing Databases---"))
        databases = []
        with LocalSqlClient(get_engine()) as client:
            # If you have an external volume mounted at /var/lib/mysql
            # the lost+found directory will show up in mysql as a database
            # which will create errors if you try to do any database ops
            # on it.  So we remove it here if it exists.
            q = query.Query()
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
        """List users that have access to the database"""
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
            iq = query.Query()  # Inner query.
            iq.columns = ['User', 'Host', "CONCAT(User, '@', Host) as Marker"]
            iq.tables = ['mysql.user']
            iq.order = ['User', 'Host']
            innerquery = str(iq).rstrip(';')

            oq = query.Query()  # Outer query.
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
        """Give a user permission to use a given database."""
        user = self._get_user(username, hostname)
        with LocalSqlClient(get_engine()) as client:
            r = query.Revoke(database=database, user=user.name, host=user.host,
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
        """Event triggered when a connection is checked out from the pool"""
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
    if CONF.service_type == "mysql":
        MYSQL_PACKAGE_VERSION = CONF.mysql_pkg
    elif CONF.service_type == "percona":
        MYSQL_PACKAGE_VERSION = CONF.percona_pkg

    def __init__(self, status):
        """ By default login with root no password for initial setup. """
        self.state_change_wait_time = CONF.state_change_wait_time
        self.status = status

    def _create_admin_user(self, client, password):
        """
        Create a os_admin user with a random password
        with all privileges similar to the root user
        """
        localhost = "localhost"
        g = query.Grant(permissions='ALL', user=ADMIN_USER_NAME,
                        host=localhost, grant_option=True, clear=password)
        t = text(str(g))
        client.execute(t)

    @staticmethod
    def _generate_root_password(client):
        """ Generate and set a random root password and forget about it. """
        localhost = "localhost"
        uu = query.UpdateUser("root", host=localhost,
                              clear=generate_random_password())
        t = text(str(uu))
        client.execute(t)

    def install_if_needed(self):
        """Prepare the guest machine with a secure mysql server installation"""
        LOG.info(_("Preparing Guest as MySQL Server"))
        if not self.is_installed():
            self._install_mysql()
        LOG.info(_("Dbaas install_if_needed complete"))

    def complete_install_or_restart(self):
        self.status.end_install_or_restart()

    def secure(self, config_location, config_contents):
        LOG.info(_("Generating admin password..."))
        admin_password = generate_random_password()

        engine = sqlalchemy.create_engine("mysql://root:@localhost:3306",
                                          echo=True)
        with LocalSqlClient(engine) as client:
            self._remove_anonymous_user(client)
            self._create_admin_user(client, admin_password)

        self.stop_db()
        self._write_mycnf(admin_password, config_location, config_contents)
        self.start_mysql()

        LOG.info(_("Dbaas secure complete."))

    def secure_root(self):
        engine = sqlalchemy.create_engine("mysql://root:@localhost:3306",
                                          echo=True)
        with LocalSqlClient(engine) as client:
            LOG.info(_("Preserving root access from restore"))
            self._generate_root_password(client)
            self._remove_remote_root_access(client)

    def _install_mysql(self):
        """Install mysql server. The current version is 5.5"""
        LOG.debug(_("Installing mysql server"))
        pkg.pkg_install(self.MYSQL_PACKAGE_VERSION, self.TIME_OUT)
        LOG.debug(_("Finished installing mysql server"))
        #TODO(rnirmal): Add checks to make sure the package got installed

    def _enable_mysql_on_boot(self):
        """
        There is a difference between the init.d mechanism and the upstart
        The stock mysql uses the upstart mechanism, therefore, there is a
        mysql.conf file responsible for the job. to toggle enable/disable
        on boot one needs to modify this file. Percona uses the init.d
        mechanism and there is no mysql.conf file. Instead, the update-rc.d
        command needs to be used to modify the /etc/rc#.d/[S/K]##mysql links
        """
        LOG.info("Enabling mysql on boot.")
        conf = "/etc/init/mysql.conf"
        if os.path.isfile(conf):
            command = "sudo sed -i '/^manual$/d' %(conf)s"
            command = command % locals()
        else:
            command = "sudo update-rc.d mysql enable"
        utils.execute_with_timeout(command, shell=True)

    def _disable_mysql_on_boot(self):
        """
        There is a difference between the init.d mechanism and the upstart
        The stock mysql uses the upstart mechanism, therefore, there is a
        mysql.conf file responsible for the job. to toggle enable/disable
        on boot one needs to modify this file. Percona uses the init.d
        mechanism and there is no mysql.conf file. Instead, the update-rc.d
        command needs to be used to modify the /etc/rc#.d/[S/K]##mysql links
        """
        LOG.info("Disabling mysql on boot.")
        conf = "/etc/init/mysql.conf"
        if os.path.isfile(conf):
            command = '''sudo sh -c "echo manual >> %(conf)s"'''
            command = command % locals()
        else:
            command = "sudo update-rc.d mysql disable"
        utils.execute_with_timeout(command, shell=True)

    def stop_db(self, update_db=False, do_not_start_on_reboot=False):
        LOG.info(_("Stopping mysql..."))
        if do_not_start_on_reboot:
            self._disable_mysql_on_boot()
        utils.execute_with_timeout("sudo", "/etc/init.d/mysql", "stop")
        if not self.status.wait_for_real_status_to_change_to(
                rd_models.ServiceStatuses.SHUTDOWN,
                self.state_change_wait_time, update_db):
            LOG.error(_("Could not stop MySQL!"))
            self.status.end_install_or_restart()
            raise RuntimeError("Could not stop MySQL!")

    def _remove_anonymous_user(self, client):
        t = text(query.REMOVE_ANON)
        client.execute(t)

    def _remove_remote_root_access(self, client):
        t = text(query.REMOVE_ROOT)
        client.execute(t)

    def restart(self):
        try:
            self.status.begin_mysql_restart()
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
                utils.execute_with_timeout("sudo", "rm", "%s/ib_logfile%d"
                                           % (MYSQL_BASE_DIR, index))
            except exception.ProcessExecutionError as pe:
                # On restarts, sometimes these are wiped. So it can be a race
                # to have MySQL start up before it's restarted and these have
                # to be deleted. That's why its ok if they aren't found.
                LOG.error("Could not delete logfile!")
                LOG.error(pe)
                if "No such file or directory" not in str(pe):
                    raise

    def _write_mycnf(self, admin_password, config_location, config_contents):
        """
        Install the set of mysql my.cnf templates.
        Update the os_admin user and password to the my.cnf
        file for direct login from localhost
        """
        LOG.info(_("Writing my.cnf templates."))
        if admin_password is None:
            admin_password = get_auth_password()

        with open(TMP_MYCNF, 'w') as t:
            t.write(config_contents)
        utils.execute_with_timeout("sudo", "mv", TMP_MYCNF,
                                   config_location)

        self._write_temp_mycnf_with_admin_account(config_location,
                                                  TMP_MYCNF,
                                                  admin_password)
        utils.execute_with_timeout("sudo", "mv", TMP_MYCNF,
                                   config_location)

        self.wipe_ib_logfiles()

    def start_mysql(self, update_db=False):
        LOG.info(_("Starting mysql..."))
        # This is the site of all the trouble in the restart tests.
        # Essentially what happens is that mysql start fails, but does not
        # die. It is then impossible to kill the original, so

        self._enable_mysql_on_boot()

        try:
            utils.execute_with_timeout("sudo", "/etc/init.d/mysql", "start")
        except exception.ProcessExecutionError:
            # it seems mysql (percona, at least) might come back with [Fail]
            # but actually come up ok. we're looking into the timing issue on
            # parallel, but for now, we'd like to give it one more chance to
            # come up. so regardless of the execute_with_timeout() respose,
            # we'll assume mysql comes up and check it's status for a while.
            pass
        if not self.status.wait_for_real_status_to_change_to(
                rd_models.ServiceStatuses.RUNNING,
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

    def start_db_with_conf_changes(self, config_location, config_contents):
        LOG.info(_("Starting mysql with conf changes..."))
        LOG.info(_("inside the guest - self.status.is_mysql_running(%s)...")
                 % self.status.is_mysql_running)
        if self.status.is_mysql_running:
            LOG.error(_("Cannot execute start_db_with_conf_changes because "
                        "MySQL state == %s!") % self.status)
            raise RuntimeError("MySQL not stopped.")
        LOG.info(_("Initiating config."))
        self._write_mycnf(None, config_location, config_contents)
        self.start_mysql(True)

    def reset_configuration(self, configuration):
        config_location = configuration['config_location']
        config_contents = configuration['config_contents']
        LOG.info(_("Resetting configuration"))
        self._write_mycnf(None, config_location, config_contents)

    def is_installed(self):
        #(cp16net) could raise an exception, does it need to be handled here?
        version = pkg.pkg_version(self.MYSQL_PACKAGE_VERSION)
        return not version is None


class MySqlRootAccess(object):

    @classmethod
    def is_root_enabled(cls):
        """Return True if root access is enabled; False otherwise."""
        with LocalSqlClient(get_engine()) as client:
            t = text(query.ROOT_ENABLED)
            result = client.execute(t)
            LOG.debug("Found %s with remote root access" % result.rowcount)
            return result.rowcount != 0

    @classmethod
    def enable_root(cls):
        """Enable the root user global access and/or reset the root password"""
        user = models.MySQLUser()
        user.name = "root"
        user.host = "%"
        user.password = generate_random_password()
        with LocalSqlClient(get_engine()) as client:
            print(client)
            try:
                cu = query.CreateUser(user.name, host=user.host)
                t = text(str(cu))
                client.execute(t, **cu.keyArgs)
            except exc.OperationalError as err:
                # Ignore, user is already created, just reset the password
                # TODO(rnirmal): More fine grained error checking later on
                LOG.debug(err)
        with LocalSqlClient(get_engine()) as client:
            print(client)
            uu = query.UpdateUser(user.name, host=user.host,
                                  clear=user.password)
            t = text(str(uu))
            client.execute(t)

            LOG.debug("CONF.root_grant: %s CONF.root_grant_option: %s" %
                      (CONF.root_grant, CONF.root_grant_option))

            g = query.Grant(permissions=CONF.root_grant,
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
