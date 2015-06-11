#   Copyright (c) 2014 Mirantis, Inc.
#   All Rights Reserved.
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

import json
import os
import re
import tempfile

from oslo_utils import netutils
import pymongo

from trove.common import cfg
from trove.common import exception
from trove.common.exception import ProcessExecutionError
from trove.common.i18n import _
from trove.common import instance as ds_instance
from trove.common import pagination
from trove.common import utils as utils
from trove.guestagent.common import operating_system
from trove.guestagent.datastore.experimental.mongodb import system
from trove.guestagent.datastore import service
from trove.guestagent.db import models
from trove.openstack.common import log as logging


LOG = logging.getLogger(__name__)
CONF = cfg.CONF
CONFIG_FILE = (operating_system.
               file_discovery(system.CONFIG_CANDIDATES))
MONGODB_PORT = CONF.mongodb.mongodb_port
CONFIGSVR_PORT = CONF.mongodb.configsvr_port
IGNORED_DBS = CONF.mongodb.ignore_dbs


class MongoDBApp(object):
    """Prepares DBaaS on a Guest container."""

    def __init__(self, status):
        self.state_change_wait_time = CONF.state_change_wait_time
        self.status = status

    def install_if_needed(self, packages):
        """Prepare the guest machine with a MongoDB installation."""
        LOG.info(_("Preparing Guest as MongoDB."))
        if not system.PACKAGER.pkg_is_installed(packages):
            LOG.debug("Installing packages: %s." % str(packages))
            system.PACKAGER.pkg_install(packages, {}, system.TIME_OUT)
        LOG.info(_("Finished installing MongoDB server."))

    def _get_service(self):
        if self.status._is_query_router() is True:
            return (operating_system.
                    service_discovery(system.MONGOS_SERVICE_CANDIDATES))
        else:
            return (operating_system.
                    service_discovery(system.MONGOD_SERVICE_CANDIDATES))

    def _enable_db_on_boot(self):
        LOG.info(_("Enabling MongoDB on boot."))
        try:
            mongo_service = self._get_service()
            utils.execute_with_timeout(mongo_service['cmd_enable'],
                                       shell=True)
        except KeyError:
            raise RuntimeError(_("MongoDB service is not discovered."))

    def _disable_db_on_boot(self):
        LOG.info(_("Disabling MongoDB on boot."))
        try:
            mongo_service = self._get_service()
            utils.execute_with_timeout(mongo_service['cmd_disable'],
                                       shell=True)
        except KeyError:
            raise RuntimeError("MongoDB service is not discovered.")

    def stop_db(self, update_db=False, do_not_start_on_reboot=False):
        LOG.info(_("Stopping MongoDB."))
        if do_not_start_on_reboot:
            self._disable_db_on_boot()

        try:
            mongo_service = self._get_service()
            # TODO(ramashri) see if hardcoded values can be removed
            utils.execute_with_timeout(mongo_service['cmd_stop'],
                                       shell=True, timeout=100)
        except KeyError:
            raise RuntimeError(_("MongoDB service is not discovered."))

        if not self.status.wait_for_real_status_to_change_to(
                ds_instance.ServiceStatuses.SHUTDOWN,
                self.state_change_wait_time, update_db):
            LOG.error(_("Could not stop MongoDB."))
            self.status.end_install_or_restart()
            raise RuntimeError(_("Could not stop MongoDB"))

    def restart(self):
        LOG.info(_("Restarting MongoDB."))
        try:
            self.status.begin_restart()
            self.stop_db()
            self.start_db()
        finally:
            self.status.end_install_or_restart()

    def start_db(self, update_db=False):
        LOG.info(_("Starting MongoDB."))

        self._enable_db_on_boot()

        try:
            mongo_service = self._get_service()
            utils.execute_with_timeout(mongo_service['cmd_start'],
                                       shell=True)
        except ProcessExecutionError:
            pass
        except KeyError:
            raise RuntimeError("MongoDB service is not discovered.")
        self.wait_for_start(update_db=update_db)

    def wait_for_start(self, update_db=False):
        LOG.debug('Waiting for MongoDB to start.')
        if not self.status.wait_for_real_status_to_change_to(
                ds_instance.ServiceStatuses.RUNNING,
                self.state_change_wait_time, update_db):
            LOG.error(_("Start up of MongoDB failed."))
            # If it won't start, but won't die either, kill it by hand so we
            # don't let a rouge process wander around.
            try:
                out, err = utils.execute_with_timeout(
                    system.FIND_PID, shell=True)
                pid = "".join(out.split(" ")[1:2])
                utils.execute_with_timeout(
                    system.MONGODB_KILL % pid, shell=True)
            except exception.ProcessExecutionError:
                LOG.exception(_("Error killing MongoDB start command."))
                # There's nothing more we can do...
            self.status.end_install_or_restart()
            raise RuntimeError("Could not start MongoDB.")
        LOG.debug('MongoDB started successfully.')

    def start_db_with_conf_changes(self, config_contents):
        LOG.info(_("Starting MongoDB with configuration changes."))
        LOG.info(_("Configuration contents:\n %s.") % config_contents)
        if self.status.is_running:
            LOG.error(_("Cannot start MongoDB with configuration changes. "
                        "MongoDB state == %s.") % self.status)
            raise RuntimeError("MongoDB is not stopped.")
        self._write_config(config_contents)
        self.start_db(True)

    def reset_configuration(self, configuration):
        config_contents = configuration['config_contents']
        LOG.info(_("Resetting configuration."))
        self._write_config(config_contents)

    def update_config_contents(self, config_contents, parameters):
        LOG.info(_("Updating configuration contents."))
        if not config_contents:
            config_contents = self._read_config()

        contents = self._delete_config_parameters(config_contents,
                                                  parameters.keys())
        for param, value in parameters.items():
            if param and value:
                contents = self._add_config_parameter(contents,
                                                      param, value)
        return contents

    def _write_config(self, config_contents):
        """
        Update contents of MongoDB configuration file
        """
        LOG.info(_("Updating MongoDB config."))
        if config_contents:
            LOG.info(_("Writing %s.") % system.TMP_CONFIG)
            try:
                with open(system.TMP_CONFIG, 'w') as t:
                    t.write(config_contents)

                LOG.info(_("Moving %(a)s to %(b)s.")
                         % {'a': system.TMP_CONFIG, 'b': CONFIG_FILE})
                operating_system.move(system.TMP_CONFIG, CONFIG_FILE,
                                      as_root=True)
            except Exception:
                os.unlink(system.TMP_CONFIG)
                raise
        else:
            LOG.debug("Empty config_contents. Do nothing.")

    def _read_config(self):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return f.read()
        except IOError:
            LOG.info(_("Config file %s not found.") % CONFIG_FILE)
            return ''

    def _delete_config_parameters(self, config_contents, parameters):
        if not config_contents:
            return None

        params_as_string = '|'.join(parameters)
        p = re.compile("\\s*#?\\s*(%s)\\s*=" % params_as_string)
        contents_as_list = config_contents.splitlines()
        filtered = filter(lambda line: not p.match(line), contents_as_list)
        return '\n'.join(filtered)

    def _add_config_parameter(self, config_contents, parameter, value):
        return (config_contents or '') + "\n%s = %s" % (parameter, value)

    def clear_storage(self):
        mount_point = "/var/lib/mongodb/*"
        LOG.debug("Clearing storage at %s." % mount_point)
        try:
            operating_system.remove(mount_point, force=True, as_root=True)
        except exception.ProcessExecutionError:
            LOG.exception(_("Error clearing storage."))

    def add_config_servers(self, config_server_hosts):
        """
        This method is used by query router (mongos) instances.
        """
        config_contents = self._read_config()
        configdb_contents = ','.join(['%(host)s:%(port)s'
                                      % {'host': host, 'port': CONFIGSVR_PORT}
                                      for host in config_server_hosts])
        LOG.debug("Config server list %s." % configdb_contents)
        # remove db path from config and update configdb
        contents = self._delete_config_parameters(config_contents,
                                                  ["dbpath", "nojournal",
                                                   "smallfiles", "journal",
                                                   "noprealloc", "configdb"])
        contents = self._add_config_parameter(contents,
                                              "configdb", configdb_contents)
        LOG.info(_("Rewriting configuration."))
        self.start_db_with_conf_changes(contents)

    def write_mongos_upstart(self):
        upstart_contents = (system.MONGOS_UPSTART_CONTENTS.
                            format(config_file_placeholder=CONFIG_FILE))

        LOG.info(_("Writing %s.") % system.TMP_MONGOS_UPSTART)

        with open(system.TMP_MONGOS_UPSTART, 'w') as t:
            t.write(upstart_contents)

        LOG.info(_("Moving %(a)s to %(b)s.")
                 % {'a': system.TMP_MONGOS_UPSTART,
                    'b': system.MONGOS_UPSTART})
        operating_system.move(system.TMP_MONGOS_UPSTART, system.MONGOS_UPSTART,
                              as_root=True)
        operating_system.remove('/etc/init/mongodb.conf', force=True,
                                as_root=True)

    def add_shard(self, replica_set_name, replica_set_member):
        """
        This method is used by query router (mongos) instances.
        """
        url = "%(rs)s/%(host)s:%(port)s"\
              % {'rs': replica_set_name,
                 'host': replica_set_member,
                 'port': MONGODB_PORT}
        MongoDBAdmin().add_shard(url)

    def add_members(self, members):
        """
        This method is used by a replica-set member instance.
        """
        def check_initiate_status():
            """
            This method is used to verify replica-set status.
            """
            status = MongoDBAdmin().get_repl_status()

            if((status["ok"] == 1) and
               (status["members"][0]["stateStr"] == "PRIMARY") and
               (status["myState"] == 1)):
                    return True
            else:
                return False

        def check_rs_status():
            """
            This method is used to verify replica-set status.
            """
            status = MongoDBAdmin().get_repl_status()
            primary_count = 0

            if status["ok"] != 1:
                return False
            if len(status["members"]) != (len(members) + 1):
                return False
            for rs_member in status["members"]:
                if rs_member["state"] not in [1, 2, 7]:
                    return False
                if rs_member["health"] != 1:
                    return False
                if rs_member["state"] == 1:
                    primary_count += 1

            return primary_count == 1

        # Create the admin user on this member.
        # This is only necessary for setting up the replica set.
        # The query router will handle requests once this set
        # is added as a shard.
        password = utils.generate_random_password()
        self.create_admin_user(password)

        # initiate replica-set
        MongoDBAdmin().rs_initiate()
        # TODO(ramashri) see if hardcoded values can be removed
        utils.poll_until(check_initiate_status, sleep_time=60, time_out=100)

        # add replica-set members
        MongoDBAdmin().rs_add_members(members)
        # TODO(ramashri) see if hardcoded values can be removed
        utils.poll_until(check_rs_status, sleep_time=60, time_out=100)

    def list_all_dbs(self):
        return MongoDBAdmin().list_database_names()

    def db_data_size(self, db_name):
        schema = models.MongoDBSchema(db_name)
        return MongoDBAdmin().db_stats(schema.serialize())['dataSize']

    def admin_cmd_auth_params(self):
        return MongoDBAdmin().cmd_admin_auth_params

    def get_key_file(self):
        return system.MONGO_KEY_FILE

    def get_key(self):
        return open(system.MONGO_KEY_FILE).read().rstrip()

    def store_key(self, key):
        """Store the cluster key."""
        LOG.debug('Storing key for MongoDB cluster.')
        with tempfile.NamedTemporaryFile() as f:
            f.write(key)
            f.flush()
            operating_system.copy(f.name, system.MONGO_KEY_FILE,
                                  force=True, as_root=True)
        operating_system.chmod(system.MONGO_KEY_FILE,
                               operating_system.FileMode.SET_USR_RO,
                               as_root=True)
        operating_system.chown(system.MONGO_KEY_FILE,
                               system.MONGO_USER, system.MONGO_USER,
                               as_root=True)

    def store_admin_password(self, password):
        LOG.debug('Storing admin password.')
        creds = MongoDBCredentials(username=system.MONGO_ADMIN_NAME,
                                   password=password)
        creds.write(system.MONGO_ADMIN_CREDS_FILE)
        return creds

    def create_admin_user(self, password):
        """Create the admin user while the localhost exception is active."""
        LOG.debug('Creating the admin user.')
        creds = self.store_admin_password(password)
        user = models.MongoDBUser(name='admin.%s' % creds.username,
                                  password=creds.password)
        user.roles = system.MONGO_ADMIN_ROLES
        user.databases = 'admin'
        with MongoDBClient(user, auth=False) as client:
            MongoDBAdmin().create_user(user, client=client)
        LOG.debug('Created admin user.')

    def secure(self, cluster_config=None):
        # Secure the server by storing the cluster key  if this is a cluster
        # or creating the admin user if this is a single instance.
        LOG.debug('Securing MongoDB instance.')
        if cluster_config:
            self.store_key(cluster_config['key'])
        else:
            LOG.debug('Generating admin password.')
            password = utils.generate_random_password()
            self.start_db()
            self.create_admin_user(password)
            self.stop_db()
        LOG.debug('MongoDB secure complete.')


class MongoDBAppStatus(service.BaseDbStatus):

    is_config_server = None
    is_query_router = None

    def _is_config_server(self):
        if self.is_config_server is None:
            try:
                cmd = ("grep '^configsvr[ \t]*=[ \t]*true$' %s"
                       % CONFIG_FILE)
                utils.execute_with_timeout(cmd, shell=True)
                self.is_config_server = True
            except exception.ProcessExecutionError:
                self.is_config_server = False
        return self.is_config_server

    def _is_query_router(self):
        if self.is_query_router is None:
            try:
                cmd = ("grep '^configdb[ \t]*=.*$' %s"
                       % CONFIG_FILE)
                utils.execute_with_timeout(cmd, shell=True)
                self.is_query_router = True
            except exception.ProcessExecutionError:
                self.is_query_router = False
        return self.is_query_router

    def _get_actual_db_status(self):
        try:
            port = CONFIGSVR_PORT if self._is_config_server() else MONGODB_PORT
            out, err = utils.execute_with_timeout(
                'mongostat', '--host', str(netutils.get_my_ipv4()),
                '--port', str(port), '-n', str(1), check_exit_code=[0, 1]
            )
            if not err:
                return ds_instance.ServiceStatuses.RUNNING
            else:
                return ds_instance.ServiceStatuses.SHUTDOWN
        except exception.ProcessExecutionError as e:
            LOG.exception(_("Process execution %s.") % e)
            return ds_instance.ServiceStatuses.SHUTDOWN
        except OSError as e:
            LOG.exception(_("OS Error %s.") % e)
            return ds_instance.ServiceStatuses.SHUTDOWN


class MongoDBAdmin(object):
    """Handles administrative tasks on MongoDB."""

    # user is cached by making it a class attribute
    admin_user = None

    def _admin_user(self):
        if not type(self).admin_user:
            creds = MongoDBCredentials()
            creds.read(system.MONGO_ADMIN_CREDS_FILE)
            user = models.MongoDBUser(
                'admin.%s' % creds.username,
                creds.password
            )
            user.databases = 'admin'
            type(self).admin_user = user
        return type(self).admin_user

    @property
    def cmd_admin_auth_params(self):
        """Returns a list of strings that constitute MongoDB command line
        authentication parameters.
        """
        user = self._admin_user()
        return ['--username', user.username,
                '--password', user.password,
                '--authenticationDatabase', user.database.name]

    def _create_user_with_client(self, user, client):
        """Run the add user command."""
        client[user.database.name].add_user(
            user.username, password=user.password, roles=user.roles
        )

    def create_user(self, user, client=None):
        """Creates a user on their database."""
        LOG.debug('Creating user %s on database %s with roles %s.'
                  % (user.username, user.database.name, str(user.roles)))

        if not user.password:
            raise exception.BadRequest(_("User's password is empty."))

        if client:
            self._create_user_with_client(user, client)
        else:
            with MongoDBClient(self._admin_user()) as admin_client:
                self._create_user_with_client(user, admin_client)

    def create_users(self, users):
        """Create the given user(s)."""
        with MongoDBClient(self._admin_user()) as client:
            for user in users:
                self.create_user(models.MongoDBUser.deserialize_user(user),
                                 client)

    def delete_user(self, user):
        """Delete the given user."""
        user = models.MongoDBUser.deserialize_user(user)
        username = user.username
        db_name = user.database.name
        LOG.debug('Deleting user %s from database %s.' % (username, db_name))
        with MongoDBClient(self._admin_user()) as admin_client:
            admin_client[db_name].remove_user(username)

    def _get_user_record(self, client, user):
        """Get the user's record."""
        return client.admin.system.users.find_one(
            {'user': user.username, 'db': user.database.name}
        )

    def get_user(self, name):
        """Get information for the given user."""
        LOG.debug('Getting user %s.' % name)
        user = models.MongoDBUser(name)
        with MongoDBClient(self._admin_user()) as admin_client:
            user_info = self._get_user_record(admin_client, user)
            if not user_info:
                return None
            user.roles = user_info['roles']
        return user.serialize()

    def list_users(self, limit=None, marker=None, include_marker=False):
        """Get a list of all users."""
        users = []
        with MongoDBClient(self._admin_user()) as admin_client:
            for user_info in admin_client.admin.system.users.find():
                user = models.MongoDBUser(name=user_info['_id'])
                if user.name == 'admin.os_admin':
                    continue
                users.append(user.serialize())
        LOG.debug('users = ' + str(users))
        return pagination.paginate_list(users, limit, marker,
                                        include_marker)

    def enable_root(self, password=None):
        """Create a user 'root' with role 'root'."""
        if not password:
            LOG.debug('Generating root user password.')
            password = utils.generate_random_password()
        root_user = models.MongoDBUser(name='admin.root', password=password)
        root_user.roles = 'root'
        self.create_user(root_user)
        return root_user.serialize()

    def is_root_enabled(self):
        """Check if user 'admin.root' exists."""
        with MongoDBClient(self._admin_user()) as admin_client:
            return bool(admin_client.admin.system.users.find_one(
                {'roles.role': 'root'}
            ))

    def create_database(self, databases):
        """Forces creation of databases.
        For each new database creates a dummy document in a dummy collection,
        then drops the collection.
        """
        tmp = 'dummy'
        with MongoDBClient(self._admin_user()) as admin_client:
            for item in databases:
                db_name = models.MongoDBSchema.deserialize_schema(item).name
                LOG.debug('Creating MongoDB database %s' % db_name)
                db = admin_client[db_name]
                db[tmp].insert({'dummy': True})
                db.drop_collection(tmp)

    def delete_database(self, database):
        """Deletes the database."""
        with MongoDBClient(self._admin_user()) as admin_client:
            db_name = models.MongoDBSchema.deserialize_schema(database).name
            admin_client.drop_database(db_name)

    def list_database_names(self):
        """Get the list of database names."""
        with MongoDBClient(self._admin_user()) as admin_client:
            return admin_client.database_names()

    def list_databases(self, limit=None, marker=None, include_marker=False):
        """Lists the databases."""
        db_names = self.list_database_names()
        for hidden in IGNORED_DBS:
            if hidden in db_names:
                db_names.remove(hidden)
        databases = [models.MongoDBSchema(db_name).serialize()
                     for db_name in db_names]
        LOG.debug('databases = ' + str(databases))
        return pagination.paginate_list(databases, limit, marker,
                                        include_marker)

    def add_shard(self, url):
        """Runs the addShard command."""
        with MongoDBClient(self._admin_user()) as admin_client:
            admin_client.admin.command({'addShard': url})

    def get_repl_status(self):
        """Runs the replSetGetStatus command."""
        with MongoDBClient(self._admin_user()) as admin_client:
            return admin_client.admin.command('replSetGetStatus')

    def rs_initiate(self):
        """Runs the replSetInitiate command."""
        with MongoDBClient(self._admin_user()) as admin_client:
            return admin_client.admin.command('replSetInitiate')

    def rs_add_members(self, members):
        """Adds the given members to the replication set."""
        with MongoDBClient(self._admin_user()) as admin_client:
            # get the current config, add the new members, then save it
            config = admin_client.admin.command('replSetGetConfig')['config']
            config['version'] += 1
            next_id = max([m['_id'] for m in config['members']]) + 1
            for member in members:
                config['members'].append({'_id': next_id, 'host': member})
                next_id += 1
            admin_client.admin.command('replSetReconfig', config)

    def db_stats(self, database, scale=1):
        """Gets the stats for the given database."""
        with MongoDBClient(self._admin_user()) as admin_client:
            db_name = models.MongoDBSchema.deserialize_schema(database).name
            return admin_client[db_name].command('dbStats', scale=scale)


class MongoDBClient(object):
    """A wrapper to manage a MongoDB connection."""

    # engine information is cached by making it a class attribute
    engine = {}

    def __init__(self, user, host=None, port=None,
                 auth=True):
        """Get the client. Specifying host and/or port updates cached values.
        :param user: (required) MongoDBUser instance
        :param host: server address, defaults to localhost
        :param port: server port, defaults to 27017
        :param auth: set to False to disable authentication, default True
        :return:
        """
        new_client = False
        self._logged_in = False
        if not type(self).engine:
            # no engine cached
            type(self).engine['host'] = (host if host else 'localhost')
            type(self).engine['port'] = (port if port else MONGODB_PORT)
            new_client = True
        elif host or port:
            LOG.debug("Updating MongoDB client.")
            if host:
                type(self).engine['host'] = host
            if port:
                type(self).engine['host'] = port
            new_client = True
        if new_client:
            host = type(self).engine['host']
            port = type(self).engine['port']
            LOG.debug("Creating MongoDB client to %(host)s:%(port)s."
                      % {'host': host, 'port': port})
            type(self).engine['client'] = pymongo.MongoClient(host=host,
                                                              port=port,
                                                              connect=False)
        self.session = type(self).engine['client']
        if auth:
            db_name = user.database.name
            LOG.debug("Authentication MongoDB client on %s." % db_name)
            self._db = self.session[db_name]
            self._db.authenticate(user.username, password=user.password)
            self._logged_in = True

    def __enter__(self):
        return self.session

    def __exit__(self, exc_type, exc_value, traceback):
        LOG.debug("Disconnecting from MongoDB.")
        if self._logged_in:
            self._db.logout()
        self.session.close()


class MongoDBCredentials(object):
    """Handles storing/retrieving credentials. Stored as json in files."""

    def __init__(self, username=None, password=None):
        self.username = username
        self.password = password

    def read(self, filename):
        with open(filename) as f:
            credentials = json.load(f)
            self.username = credentials['username']
            self.password = credentials['password']

    def write(self, filename):
        self.clear_file(filename)
        with open(filename, 'w') as f:
            credentials = {'username': self.username,
                           'password': self.password}
            json.dump(credentials, f)

    @staticmethod
    def clear_file(filename):
        LOG.debug("Creating clean file %s" % filename)
        if operating_system.file_discovery([filename]):
            operating_system.remove(filename)
        # force file creation by just opening it
        open(filename, 'wb')
        operating_system.chmod(filename,
                               operating_system.FileMode.SET_USR_RW,
                               as_root=True)
