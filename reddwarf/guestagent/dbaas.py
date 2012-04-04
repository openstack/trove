# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2011 OpenStack, LLC.
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

"""
Handles all processes within the Guest VM, considering it as a Platform

The :py:class:`GuestManager` class is a :py:class:`nova.manager.Manager` that
handles RPC calls relating to Platform specific operations.

**Related Flags**

"""


import logging
import os
import re
import sys
import uuid

from datetime import date
from sqlalchemy import create_engine
from sqlalchemy import exc
from sqlalchemy import interfaces
from sqlalchemy.sql.expression import text

from reddwarf import db
from reddwarf.common.exception import ProcessExecutionError
from reddwarf.common import config
from reddwarf.common import utils
from reddwarf.guestagent.db import models
from reddwarf.instance import models as rd_models

ADMIN_USER_NAME = "os_admin"
LOG = logging.getLogger(__name__)
FLUSH = text("""FLUSH PRIVILEGES;""")

ENGINE = None
MYSQLD_ARGS = None
PREPARING = False
UUID = False


def generate_random_password():
    return str(uuid.uuid4())


def get_engine():
        """Create the default engine with the updated admin user"""
        #TODO(rnirmal):Based on permissions issues being resolved we may revert
        #url = URL(drivername='mysql', host='localhost',
        #          query={'read_default_file': '/etc/mysql/my.cnf'})
        global ENGINE
        if ENGINE:
            return ENGINE
        #ENGINE = create_engine(name_or_url=url)
        pwd, err = utils.execute("sudo", "awk", "/password\\t=/{print $3}",
                                 "/etc/mysql/my.cnf")
        if not err:
            ENGINE = create_engine("mysql://%s:%s@localhost:3306" %
                                   (ADMIN_USER_NAME, pwd.strip()),
                                   pool_recycle=7200, echo=True,
                                   listeners=[KeepAliveConnection()])
        else:
            LOG.error(err)
        return ENGINE


def load_mysqld_options():
    try:
        out, err = utils.execute("/usr/sbin/mysqld", "--print-defaults",
                                 run_as_root=True)
        arglist = re.split("\n", out)[1].split()
        args = {}
        for item in arglist:
            if "=" in item:
                key, value = item.split("=")
                args[key.lstrip("--")] = value
            else:
                args[item.lstrip("--")] = None
        return args
    except ProcessExecutionError as e:
        return None


class DBaaSAgent(object):
    """ Database as a Service Agent Controller """

    def create_user(self, users):
        """Create users and grant them privileges for the
           specified databases"""
        host = "%"
        client = LocalSqlClient(get_engine())
        with client:
            for item in users:
                user = models.MySQLUser()
                user.deserialize(item)
                # TODO(cp16net):Should users be allowed to create users
                # 'os_admin' or 'debian-sys-maint'
                t = text("""CREATE USER `%s`@:host IDENTIFIED BY '%s';"""
                         % (user.name, user.password))
                client.execute(t, host=host)
                for database in user.databases:
                    mydb = models.MySQLDatabase()
                    mydb.deserialize(database)
                    t = text("""
                            GRANT ALL PRIVILEGES ON `%s`.* TO `%s`@:host;"""
                            % (mydb.name, user.name))
                    client.execute(t, host=host)

    def list_users(self):
        """List users that have access to the database"""
        LOG.debug(_("---Listing Users---"))
        users = []
        client = LocalSqlClient(get_engine())
        with client:
            mysql_user = models.MySQLUser()
            t = text("""select User from mysql.user where host !=
                     'localhost';""")
            result = client.execute(t)
            LOG.debug(_("result = %s") % str(result))
            for row in result:
                LOG.debug(_("user = %s" % str(row))
                mysql_user = models.MySQLUser()
                mysql_user.name = row['User']
                # Now get the databases
                t = text("""SELECT grantee, table_schema
                            from information_schema.SCHEMA_PRIVILEGES
                            group by grantee, table_schema;""")
                db_result = client.execute(t)
                for db in db_result:
                    matches = re.match("^'(.+)'@", db['grantee'])
                    if matches is not None and \
                       matches.group(1) == mysql_user.name:
                        mysql_db = models.MySQLDatabase()
                        mysql_db.name = db['table_schema']
                        mysql_user.databases.append(mysql_db.serialize())
                users.append(mysql_user.serialize())
        LOG.debug(_("users = %s") str(users))
        return users

    def delete_user(self, user):
        """Delete the specified users"""
        client = LocalSqlClient(get_engine())
        with client:
            mysql_user = models.MySQLUser()
            mysql_user.deserialize(user)
            t = text("""DROP USER `%s`""" % mysql_user.name)
            client.execute(t)

    def create_database(self, databases):
        """Create the list of specified databases"""
        client = LocalSqlClient(get_engine())
        with client:
            for item in databases:
                mydb = models.MySQLDatabase()
                mydb.deserialize(item)
                t = text("""CREATE DATABASE IF NOT EXISTS
                            `%s` CHARACTER SET = %s COLLATE = %s;"""
                         % (mydb.name, mydb.character_set, mydb.collate))
                client.execute(t)

    def list_databases(self):
        """List databases the user created on this mysql instance"""
        LOG.debug(_("---Listing Databases---"))
        databases = []
        client = LocalSqlClient(get_engine())
        with client:
            # If you have an external volume mounted at /var/lib/mysql
            # the lost+found directory will show up in mysql as a database
            # which will create errors if you try to do any database ops
            # on it.  So we remove it here if it exists.
            t = text('''
            SELECT
                schema_name as name,
                default_character_set_name as charset,
                default_collation_name as collation
            FROM
                information_schema.schemata
            WHERE
                schema_name not in
                ('mysql', 'information_schema', 'lost+found')
            ORDER BY
                schema_name ASC;
            ''')
            database_names = client.execute(t)
            LOG.debug(_("database_names = %r") % database_names)
            for database in database_names:
                LOG.debug(_("database = %s ") % str(database))
                mysql_db = models.MySQLDatabase()
                mysql_db.name = database[0]
                mysql_db.character_set = database[1]
                mysql_db.collate = database[2]
                databases.append(mysql_db.serialize())
        LOG.debug(_("databases = ") + str(databases))
        return databases

    def delete_database(self, database):
        """Delete the specified database"""
        client = LocalSqlClient(get_engine())
        with client:
            mydb = models.MySQLDatabase()
            mydb.deserialize(database)
            t = text("""DROP DATABASE `%s`;""" % mydb.name)
            client.execute(t)

    def enable_root(self):
        """Enable the root user global access and/or reset the root password"""
        host = "%"
        user = models.MySQLUser()
        user.name = "root"
        user.password = generate_random_password()
        client = LocalSqlClient(get_engine())
        with client:
            try:
                t = text("""CREATE USER :user@:host;""")
                client.execute(t, user=user.name, host=host, pwd=user.password)
            except exc.OperationalError as err:
                # Ignore, user is already created, just reset the password
                # TODO(rnirmal): More fine grained error checking later on
                LOG.debug(err)
        with client:
            t = text("""UPDATE mysql.user SET Password=PASSWORD(:pwd)
                           WHERE User=:user;""")
            client.execute(t, user=user.name, pwd=user.password)
            t = text("""GRANT ALL PRIVILEGES ON *.* TO :user@:host
                        WITH GRANT OPTION;""")
            client.execute(t, user=user.name, host=host)
            return user.serialize()

    def disable_root(self):
        """Disable root access apart from localhost"""
        host = "localhost"
        pwd = generate_random_password()
        user = "root"
        client = LocalSqlClient(get_engine())
        with client:
            t = text("""DELETE FROM mysql.user where User=:user
                        and Host!=:host""")
            client.execute(t, user=user, host=host)
            t = text("""UPDATE mysql.user SET Password=PASSWORD(:pwd)
                        WHERE User=:user;""")
            client.execute(t, pwd=pwd, user=user)
        return True

    def is_root_enabled(self):
        """Return True if root access is enabled; False otherwise."""
        client = LocalSqlClient(get_engine())
        with client:
            mysql_user = models.MySQLUser()
            t = text("""SELECT User FROM mysql.user where User = 'root'
                        and host != 'localhost';""")
            result = client.execute(t)
            LOG.debug(_("result = ") + str(result))
            return result.rowcount != 0

    def prepare(self, databases, memory_mb):
        """Makes ready DBAAS on a Guest container."""
        global PREPARING
        PREPARING = True
        from reddwarf.guestagent.pkg import PkgAgent
        if not isinstance(self, PkgAgent):
            raise TypeError("This must also be an instance of Pkg agent.")
        preparer = DBaaSPreparer(self)
        preparer.prepare()
        self.create_database(databases)
        PREPARING = False

    def update_status(self):
        """Update the status of the MySQL service"""
        global MYSQLD_ARGS
        global PREPARING
        id = config.Config.get('guest_id')
        status = rd_models.InstanceServiceStatus.find_by(instance_id=id)

        if PREPARING:
            status.set_status(rd_models.ServiceStatuses.BUILDING)
            status.save()
            return

        try:
            out, err = utils.execute("/usr/bin/mysqladmin", "ping",
                                     run_as_root=True)
            status.set_status(rd_models.ServiceStatuses.RUNNING)
            status.save()
        except ProcessExecutionError as e:
            try:
                out, err = utils.execute("ps", "-C", "mysqld", "h")
                pid = out.split()[0]
                # TODO(rnirmal): Need to create new statuses for instances
                # where the mysql service is up, but unresponsive
                status.set_status(rd_models.ServiceStatuses.BLOCKED)
                status.save()
            except ProcessExecutionError as e:
                if not MYSQLD_ARGS:
                    MYSQLD_ARGS = load_mysqld_options()
                pid_file = MYSQLD_ARGS.get('pid-file',
                                           '/var/run/mysqld/mysqld.pid')
                if os.path.exists(pid_file):
                    status.set_status(rd_models.ServiceStatuses.CRASHED)
                    status.save()
                else:
                    status.set_status(rd_models.ServiceStatuses.SHUTDOWN)
                    status.save()


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


class KeepAliveConnection(interfaces.PoolListener):
    """
    A connection pool listener that ensures live connections are returned
    from the connecction pool at checkout. This alleviates the problem of
    MySQL connections timeing out.
    """

    def checkout(self, dbapi_con, con_record, con_proxy):
        """Event triggered when a connection is checked out from the pool"""
        try:
            try:
                dbapi_con.ping(False)
            except TypeError:
                dbapi_con.ping()
        except dbapi_con.OperationalError, ex:
            if ex.args[0] in (2006, 2013, 2014, 2045, 2055):
                raise exc.DisconnectionError()
            else:
                raise


class DBaaSPreparer(object):
    """Prepares DBaaS on a Guest container."""

    TIME_OUT = 1000

    def __init__(self, pkg_agent):
        """ By default login with root no password for initial setup. """
        self.engine = create_engine("mysql://root:@localhost:3306", echo=True)
        self.pkg = pkg_agent

    def _generate_root_password(self, client):
        """ Generate and set a random root password and forget about it. """
        t = text("""UPDATE mysql.user SET Password=PASSWORD(:pwd)
                           WHERE User='root';""")
        client.execute(t, pwd=generate_random_password())

    def _init_mycnf(self, password):
        """
        Install the set of mysql my.cnf templates from dbaas-mycnf package.
        The package generates a template suited for the current
        container flavor. Update the os_admin user and password
        to the my.cnf file for direct login from localhost
        """
        orig_mycnf = "/etc/mysql/my.cnf"
        final_mycnf = "/var/lib/mysql/my.cnf"
        tmp_mycnf = "/tmp/my.cnf.tmp"
        dbaas_mycnf = "/etc/dbaas/my.cnf/my.cnf.default"

        LOG.debug(_("Installing my.cnf templates"))
        self.pkg.pkg_install("dbaas-mycnf", self.TIME_OUT)

        if os.path.isfile(dbaas_mycnf):
            utils.execute("sudo", "mv", orig_mycnf,
                          "%(name)s.%(date)s"
                          % {'name': orig_mycnf,
                             'date': date.today().isoformat()})
            utils.execute("sudo", "cp", dbaas_mycnf, orig_mycnf)

        mycnf_file = open(orig_mycnf, 'r')
        tmp_file = open(tmp_mycnf, 'w')

        for line in mycnf_file:
            tmp_file.write(line)
            if "[client]" in line:
                tmp_file.write("user\t\t= %s\n" % ADMIN_USER_NAME)
                tmp_file.write("password\t= %s\n" % password)

        mycnf_file.close()
        tmp_file.close()
        utils.execute("sudo", "mv", tmp_mycnf, final_mycnf)
        utils.execute("sudo", "rm", orig_mycnf)
        utils.execute("sudo", "ln", "-s", final_mycnf, orig_mycnf)

    def _remove_anonymous_user(self, client):
        t = text("""DELETE FROM mysql.user WHERE User='';""")
        client.execute(t)

    def _remove_remote_root_access(self, client):
        t = text("""DELETE FROM mysql.user
                           WHERE User='root'
                           AND Host!='localhost';""")
        client.execute(t)

    def _create_admin_user(self, client, password):
        """
        Create a os_admin user with a random password
        with all privileges similar to the root user
        """
        t = text("CREATE USER :user@'localhost';")
        client.execute(t, user=ADMIN_USER_NAME)
        t = text("""
                 UPDATE mysql.user SET Password=PASSWORD(:pwd)
                     WHERE User=:user;
                 """)
        client.execute(t, pwd=password, user=ADMIN_USER_NAME)
        t = text("""
                 GRANT ALL PRIVILEGES ON *.* TO :user@'localhost'
                       WITH GRANT OPTION;
                 """)
        client.execute(t, user=ADMIN_USER_NAME)

    def _install_mysql(self):
        """Install mysql server. The current version is 5.1"""
        LOG.debug(_("Installing mysql server"))
        self.pkg.pkg_install("mysql-server-5.1", self.TIME_OUT)
        #TODO(rnirmal): Add checks to make sure the package got installed

    def _restart_mysql(self):
        """
        Restart mysql after all the modifications are completed.
        List of modifications:
        - Remove existing ib_logfile*
        """
        # TODO(rnirmal): To be replaced by the mounted volume location
        # FIXME once we have volumes in place, use default till then
        mysql_base_dir = "/var/lib/mysql"
        try:
            LOG.debug(_("Restarting mysql..."))
            utils.execute("sudo", "service", "mysql", "stop")

            # Remove the ib_logfile, if not mysql won't start.
            # For some reason wildcards don't seem to work, so
            # deleting both the files separately
            utils.execute("sudo", "rm", "%s/ib_logfile0" % mysql_base_dir)
            utils.execute("sudo", "rm", "%s/ib_logfile1" % mysql_base_dir)

            utils.execute("sudo", "service", "mysql", "start")
        except ProcessExecutionError:
            LOG.error(_("Unable to restart mysql server."))

    def prepare(self):
        """Prepare the guest machine with a secure mysql server installation"""
        LOG.info(_("Preparing Guest as MySQL Server"))
        try:
            utils.execute("apt-get", "update", run_as_root=True)
        except ProcessExecutionError as e:
            LOG.error(_("Error updating the apt sources"))

        self._install_mysql()

        admin_password = generate_random_password()

        client = LocalSqlClient(self.engine)
        with client:
            self._generate_root_password(client)
            self._remove_anonymous_user(client)
            self._remove_remote_root_access(client)
            self._create_admin_user(client, admin_password)

        self._init_mycnf(admin_password)
        self._restart_mysql()
        LOG.info(_("Dbaas preparation complete."))
