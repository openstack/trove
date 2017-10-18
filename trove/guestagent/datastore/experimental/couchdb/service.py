# Copyright 2015 IBM Corp.
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

import ast
import getpass
import json
from oslo_log import log as logging

from trove.common import cfg
from trove.common.db.couchdb import models
from trove.common import exception
from trove.common.i18n import _
from trove.common import instance as rd_instance
from trove.common import pagination
from trove.common.stream_codecs import JsonCodec
from trove.common import utils
from trove.guestagent.common import operating_system
from trove.guestagent.common.operating_system import FileMode
from trove.guestagent.datastore.experimental.couchdb import system
from trove.guestagent.datastore import service
from trove.guestagent import pkg

CONF = cfg.CONF
LOG = logging.getLogger(__name__)
packager = pkg.Package()

COUCHDB_LIB_DIR = "/var/lib/couchdb"
COUCHDB_LOG_DIR = "/var/log/couchdb"
COUCHDB_CONFIG_DIR = "/etc/couchdb"
COUCHDB_BIN_DIR = "/var/run/couchdb"


class CouchDBApp(object):
    """
    Handles installation and configuration of CouchDB
    on a Trove instance.
    """

    def __init__(self, status, state_change_wait_time=None):
        """
        Sets default status and state_change_wait_time.
        """
        self.state_change_wait_time = (
            state_change_wait_time if state_change_wait_time else
            CONF.state_change_wait_time
        )
        LOG.debug("state_change_wait_time = %s.", self.state_change_wait_time)
        self.status = status

    def install_if_needed(self, packages):
        """
        Install CouchDB if needed, do nothing if it is already installed.
        """
        LOG.info(_('Preparing guest as a CouchDB server.'))
        if not packager.pkg_is_installed(packages):
            LOG.debug("Installing packages: %s.", str(packages))
            packager.pkg_install(packages, {}, system.TIME_OUT)
        LOG.info(_("Finished installing CouchDB server."))

    def change_permissions(self):
        """
        When CouchDB is installed, a default user 'couchdb' is created.
        Inorder to start/stop/restart CouchDB service as the current
        OS user, add the current OS user to the 'couchdb' group and provide
        read/write access to the 'couchdb' group.
        """
        try:
            LOG.debug("Changing permissions.")
            for dir in [COUCHDB_LIB_DIR, COUCHDB_LOG_DIR,
                        COUCHDB_BIN_DIR, COUCHDB_CONFIG_DIR]:
                operating_system.chown(dir, 'couchdb', 'couchdb', as_root=True)
                operating_system.chmod(dir, FileMode.ADD_GRP_RW, as_root=True)

            operating_system.change_user_group(getpass.getuser(), 'couchdb',
                                               as_root=True)
            LOG.debug("Successfully changed permissions.")
        except exception.ProcessExecutionError:
            LOG.exception(_("Error changing permissions."))

    def stop_db(self, update_db=False, do_not_start_on_reboot=False):
        self.status.stop_db_service(
            system.SERVICE_CANDIDATES, self.state_change_wait_time,
            disable_on_boot=do_not_start_on_reboot, update_db=update_db)

    def start_db(self, update_db=False):
        self.status.start_db_service(
            system.SERVICE_CANDIDATES, self.state_change_wait_time,
            enable_on_boot=True, update_db=update_db)

    def restart(self):
        self.status.restart_db_service(
            system.SERVICE_CANDIDATES, self.state_change_wait_time)

    def make_host_reachable(self):
        try:
            LOG.debug("Changing bind address to 0.0.0.0 .")
            self.stop_db()
            out, err = utils.execute_with_timeout(
                system.UPDATE_BIND_ADDRESS, shell=True
            )
            self.start_db()
        except exception.ProcessExecutionError:
            LOG.exception(_("Error while trying to update bind address of"
                            " CouchDB server."))

    def start_db_with_conf_changes(self, config_contents):
        '''
         Will not be implementing configuration change API for CouchDB in
         the Kilo release. Currently all that this method does is to start
         the CouchDB server without any configuration changes. Looks like
         this needs to be implemented to enable volume resize on the guest
         agent side.
        '''
        LOG.info(_("Starting CouchDB with configuration changes."))
        self.start_db(True)

    def store_admin_password(self, password):
        LOG.debug('Storing the admin password.')
        creds = CouchDBCredentials(username=system.COUCHDB_ADMIN_NAME,
                                   password=password)
        creds.write(system.COUCHDB_ADMIN_CREDS_FILE)
        return creds

    def create_admin_user(self, password):
        '''
        Creating the admin user, os_admin, for the couchdb instance
        '''
        LOG.debug('Creating the admin user.')
        creds = self.store_admin_password(password)
        out, err = utils.execute_with_timeout(
            system.COUCHDB_CREATE_ADMIN % {'password': creds.password},
            shell=True)
        LOG.debug('Created admin user.')

    def secure(self):
        '''
        Create the Trove admin user.
        The service should not be running at this point.
        '''
        self.start_db(update_db=False)
        password = utils.generate_random_password()
        self.create_admin_user(password)
        LOG.debug("CouchDB secure complete.")

    @property
    def admin_password(self):
        creds = CouchDBCredentials()
        creds.read(system.COUCHDB_ADMIN_CREDS_FILE)
        return creds.password


class CouchDBAppStatus(service.BaseDbStatus):
    """
        Handles all of the status updating for the CouchDB guest agent.
        We can verify that CouchDB is running by running the command:
          curl http://127.0.0.1:5984/
        The response will be similar to:
          {"couchdb":"Welcome","version":"1.6.0"}
    """

    def _get_actual_db_status(self):
        try:
            out, err = utils.execute_with_timeout(
                system.COUCHDB_SERVER_STATUS, shell=True
            )
            LOG.debug("CouchDB status = %r", out)
            server_status = json.loads(out)
            status = server_status["couchdb"]
            if status == 'Welcome':
                LOG.debug("Status of CouchDB is active.")
                return rd_instance.ServiceStatuses.RUNNING
            else:
                LOG.debug("Status of CouchDB is not active.")
                return rd_instance.ServiceStatuses.SHUTDOWN
        except exception.ProcessExecutionError:
            LOG.exception(_("Error getting CouchDB status."))
            return rd_instance.ServiceStatuses.SHUTDOWN


class CouchDBAdmin(object):
    '''Handles administrative functions on CouchDB.'''

    # user is cached by making it a class attribute
    admin_user = None

    def _admin_user(self):
        if not type(self).admin_user:
            creds = CouchDBCredentials()
            creds.read(system.COUCHDB_ADMIN_CREDS_FILE)
            user = models.CouchDBUser(creds.username, creds.password)
            type(self).admin_user = user
        return type(self).admin_user

    def _is_modifiable_user(self, name):
        if name in cfg.get_ignored_users():
            return False
        elif name == system.COUCHDB_ADMIN_NAME:
            return False
        return True

    def _is_modifiable_database(self, name):
        return name not in cfg.get_ignored_dbs()

    def create_user(self, users):
        LOG.debug("Creating user(s) for accessing CouchDB database(s).")
        self._admin_user()
        try:
            for item in users:
                user = models.CouchDBUser.deserialize(item)
                try:
                    LOG.debug("Creating user: %s.", user.name)
                    utils.execute_with_timeout(
                        system.CREATE_USER_COMMAND %
                        {'admin_name': self._admin_user().name,
                         'admin_password': self._admin_user().password,
                         'username': user.name,
                         'username': user.name,
                         'password': user.password},
                        shell=True)
                except exception.ProcessExecutionError as pe:
                    LOG.exception(_("Error creating user: %s."), user.name)
                    pass

                for database in user.databases:
                    mydb = models.CouchDBSchema.deserialize(database)
                    try:
                        LOG.debug("Granting user: %(user)s access to "
                                  "database: %(db)s.",
                                  {'user': user.name, 'db': mydb.name})
                        out, err = utils.execute_with_timeout(
                            system.GRANT_ACCESS_COMMAND %
                            {'admin_name': self._admin_user().name,
                             'admin_password': self._admin_user().password,
                             'dbname': mydb.name,
                             'username': user.name},
                            shell=True)
                    except exception.ProcessExecutionError as pe:
                        LOG.debug("Error granting user: %(user)s access to"
                                  "database: %(db)s.",
                                  {'user': user.name, 'db': mydb.name})
                        LOG.debug(pe)
                        pass
        except exception.ProcessExecutionError as pe:
            LOG.exception(_("An error occurred creating users: %s."),
                          pe.message)
            pass

    def delete_user(self, user):
        LOG.debug("Delete a given CouchDB user.")
        couchdb_user = models.CouchDBUser.deserialize(user)
        db_names = self.list_database_names()

        for db in db_names:
            userlist = []
            try:
                out, err = utils.execute_with_timeout(
                    system.DB_ACCESS_COMMAND %
                    {'admin_name': self._admin_user().name,
                     'admin_password': self._admin_user().password,
                     'dbname': db},
                    shell=True)
            except exception.ProcessExecutionError:
                LOG.debug(
                    "Error while trying to get the users for database: %s.",
                    db)
                continue

            evalout = ast.literal_eval(out)
            if evalout:
                members = evalout['members']
                names = members['names']
                for i in range(0, len(names)):
                    couchdb_user.databases = db
                    userlist.append(names[i])
                if couchdb_user.name in userlist:
                    userlist.remove(couchdb_user.name)
            out2, err2 = utils.execute_with_timeout(
                system.REVOKE_ACCESS_COMMAND % {
                    'admin_name': self._admin_user().name,
                    'admin_password': self._admin_user().password,
                    'dbname': db,
                    'username': userlist},
                shell=True)

        try:
            out2, err = utils.execute_with_timeout(
                system.DELETE_REV_ID %
                {'admin_name': self._admin_user().name,
                 'admin_password': self._admin_user().password},
                shell=True)
            evalout2 = ast.literal_eval(out2)
            rows = evalout2['rows']
            userlist = []

            for i in range(0, len(rows)):
                row = rows[i]
                username = "org.couchdb.user:" + couchdb_user.name
                if row['key'] == username:
                    rev = row['value']
                    revid = rev['rev']
            utils.execute_with_timeout(
                system.DELETE_USER_COMMAND % {
                    'admin_name': self._admin_user().name,
                    'admin_password': self._admin_user().password,
                    'username': couchdb_user.name,
                    'revid': revid},
                shell=True)
        except exception.ProcessExecutionError as pe:
            LOG.exception(_(
                "There was an error while deleting user: %s."), pe)
            raise exception.GuestError(original_message=_(
                "Unable to delete user: %s.") % couchdb_user.name)

    def list_users(self, limit=None, marker=None, include_marker=False):
        '''List all users and the databases they have access to.'''
        users = []
        db_names = self.list_database_names()
        try:
            out, err = utils.execute_with_timeout(
                system.ALL_USERS_COMMAND %
                {'admin_name': self._admin_user().name,
                 'admin_password': self._admin_user().password},
                shell=True)
        except exception.ProcessExecutionError:
            LOG.debug("Error while trying to get list of all couchdb users")
        evalout = ast.literal_eval(out)
        rows = evalout['rows']
        userlist = []
        for i in range(0, len(rows)):
            row = rows[i]
            uname = row['key']
            if not self._is_modifiable_user(uname):
                break
            elif uname[17:]:
                userlist.append(uname[17:])
        for i in range(len(userlist)):
            user = models.CouchDBUser(userlist[i])
            for db in db_names:
                try:
                    out2, err = utils.execute_with_timeout(
                        system.DB_ACCESS_COMMAND %
                        {'admin_name': self._admin_user().name,
                         'admin_password': self._admin_user().password,
                         'dbname': db},
                        shell=True)
                except exception.ProcessExecutionError:
                    LOG.debug(
                        "Error while trying to get users for database: %s.",
                        db)
                    continue
                evalout2 = ast.literal_eval(out2)
                if evalout2:
                    members = evalout2['members']
                    names = members['names']
                    for i in range(0, len(names)):
                        if user.name == names[i]:
                            user.databases = db
            users.append(user.serialize())
        next_marker = None
        return users, next_marker

    def get_user(self, username, hostname):
        '''Get Information about the given user.'''
        LOG.debug('Getting user %s.', username)
        user = self._get_user(username, hostname)
        if not user:
            return None
        return user.serialize()

    def _get_user(self, username, hostname):
        user = models.CouchDBUser(username)
        db_names = self.list_database_names()
        for db in db_names:
            try:
                out, err = utils.execute_with_timeout(
                    system.DB_ACCESS_COMMAND %
                    {'admin_name': self._admin_user().name,
                     'admin_password': self._admin_user().password,
                     'dbname': db},
                    shell=True)
            except exception.ProcessExecutionError:
                LOG.debug(
                    "Error while trying to get the users for database: %s.",
                    db)
                continue

            evalout = ast.literal_eval(out)
            if evalout:
                members = evalout['members']
                names = members['names']
                for i in range(0, len(names)):
                    if user.name == names[i]:
                        user.databases = db
        return user

    def grant_access(self, username, databases):
        if self._get_user(username, None).name != username:
            raise exception.BadRequest(_(
                'Cannot grant access for non-existant user: '
                '%(user)s') % {'user': username})
        else:
            user = models.CouchDBUser(username)
            if not self._is_modifiable_user(user.name):
                LOG.warning(_('Cannot grant access for reserved user '
                              '%(user)s'), {'user': username})
            if not user:
                raise exception.BadRequest(_(
                    'Cannot grant access for reserved or non-existant user '
                    '%(user)s') % {'user': username})
            for db_name in databases:
                out, err = utils.execute_with_timeout(
                    system.GRANT_ACCESS_COMMAND %
                    {'admin_name': self._admin_user().name,
                     'admin_password': self._admin_user().password,
                     'dbname': db_name,
                     'username': username},
                    shell=True)

    def revoke_access(self, username, database):
        userlist = []
        if self._is_modifiable_user(username):
            out, err = utils.execute_with_timeout(
                system.DB_ACCESS_COMMAND %
                {'admin_name': self._admin_user().name,
                 'admin_password': self._admin_user().password,
                 'dbname': database},
                shell=True)
            evalout = ast.literal_eval(out)
            members = evalout['members']
            names = members['names']
            for i in range(0, len(names)):
                userlist.append(names[i])
            if username in userlist:
                userlist.remove(username)
        out2, err2 = utils.execute_with_timeout(
            system.REVOKE_ACCESS_COMMAND %
            {'admin_name': self._admin_user().name,
             'admin_password': self._admin_user().password,
             'dbname': database,
             'username': userlist},
            shell=True)

    def list_access(self, username, hostname):
        '''Returns a list of all databases which the user has access to'''
        user = self._get_user(username, hostname)
        return user.databases

    def enable_root(self, root_pwd=None):
        '''Create admin user root'''
        root_user = models.CouchDBUser.root(password=root_pwd)
        out, err = utils.execute_with_timeout(
            system.ENABLE_ROOT %
            {'admin_name': self._admin_user().name,
             'admin_password': self._admin_user().password,
             'password': root_pwd},
            shell=True)
        return root_user.serialize()

    def is_root_enabled(self):
        '''Check if user root exists'''
        out, err = utils.execute_with_timeout(
            system.IS_ROOT_ENABLED %
            {'admin_name': self._admin_user().name,
             'admin_password': self._admin_user().password},
            shell=True)
        evalout = ast.literal_eval(out)
        if evalout['root']:
            return True
        else:
            return False

    def create_database(self, databases):
        '''Create the given database(s).'''
        dbName = None
        db_create_failed = []
        LOG.debug("Creating CouchDB databases.")

        for database in databases:
            dbName = models.CouchDBSchema.deserialize(database).name
            if self._is_modifiable_database(dbName):
                LOG.debug('Creating CouchDB database %s', dbName)
                try:
                    utils.execute_with_timeout(
                        system.CREATE_DB_COMMAND %
                        {'admin_name': self._admin_user().name,
                         'admin_password': self._admin_user().password,
                         'dbname': dbName},
                        shell=True)
                except exception.ProcessExecutionError:
                    LOG.exception(_(
                        "There was an error creating database: %s."), dbName)
                    db_create_failed.append(dbName)
                    pass
            else:
                LOG.warning(_('Cannot create database with a reserved name '
                              '%(db)s'), {'db': dbName})
                db_create_failed.append(dbName)
        if len(db_create_failed) > 0:
            LOG.exception(_("Creating the following databases failed: %s."),
                          db_create_failed)

    def list_database_names(self):
        '''Get the list of database names.'''
        out, err = utils.execute_with_timeout(
            system.LIST_DB_COMMAND %
            {'admin_name': self._admin_user().name,
             'admin_password': self._admin_user().password},
            shell=True)
        dbnames_list = eval(out)
        for hidden in cfg.get_ignored_dbs():
            if hidden in dbnames_list:
                dbnames_list.remove(hidden)
        return dbnames_list

    def list_databases(self, limit=None, marker=None, include_marker=False):
        '''Lists all the CouchDB databases.'''
        databases = []
        db_names = self.list_database_names()
        pag_dblist, marker = pagination.paginate_list(db_names, limit, marker,
                                                      include_marker)
        databases = [models.CouchDBSchema(db_name).serialize()
                     for db_name in pag_dblist]
        LOG.debug('databases = ' + str(databases))
        return databases, marker

    def delete_database(self, database):
        '''Delete the specified database.'''
        dbName = models.CouchDBSchema.deserialize(database).name
        if self._is_modifiable_database(dbName):
            try:
                LOG.debug("Deleting CouchDB database: %s.", dbName)
                utils.execute_with_timeout(
                    system.DELETE_DB_COMMAND %
                    {'admin_name': self._admin_user().name,
                     'admin_password': self._admin_user().password,
                     'dbname': dbName},
                    shell=True)
            except exception.ProcessExecutionError:
                LOG.exception(_(
                    "There was an error while deleting database:%s."), dbName)
                raise exception.GuestError(original_message=_(
                    "Unable to delete database: %s.") % dbName)
        else:
            LOG.warning(_('Cannot delete a reserved database '
                          '%(db)s'), {'db': dbName})


class CouchDBCredentials(object):
    """Handles storing/retrieving credentials. Stored as json in files"""

    def __init__(self, username=None, password=None):
        self.username = username
        self.password = password

    def read(self, filename):
        credentials = operating_system.read_file(filename, codec=JsonCodec())
        self.username = credentials['username']
        self.password = credentials['password']

    def write(self, filename):
        self.clear_file(filename)
        credentials = {'username': self.username,
                       'password': self.password}
        operating_system.write_file(filename, credentials, codec=JsonCodec())
        operating_system.chmod(filename, operating_system.FileMode.SET_USR_RW)

    @staticmethod
    def clear_file(filename):
        LOG.debug("Creating clean file %s", filename)
        if operating_system.file_discovery([filename]):
            operating_system.remove(filename)
        # force file creation by just opening it
        open(filename, 'wb')
        operating_system.chmod(filename,
                               operating_system.FileMode.SET_USR_RW,
                               as_root=True)
