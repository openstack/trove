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

import os

from oslo_log import log as logging
from oslo_utils import netutils
import pymongo

from trove.common import cfg
from trove.common import exception
from trove.common.i18n import _
from trove.common import instance as ds_instance
from trove.common import pagination
from trove.common.stream_codecs import JsonCodec, SafeYamlCodec
from trove.common import utils as utils
from trove.guestagent.common.configuration import ConfigurationManager
from trove.guestagent.common.configuration import OneFileOverrideStrategy
from trove.guestagent.common import guestagent_utils
from trove.guestagent.common import operating_system
from trove.guestagent.datastore.experimental.mongodb import system
from trove.guestagent.datastore import service
from trove.guestagent.db import models


LOG = logging.getLogger(__name__)
CONF = cfg.CONF
CONFIG_FILE = operating_system.file_discovery(system.CONFIG_CANDIDATES)
MANAGER = CONF.datastore_manager if CONF.datastore_manager else 'mongodb'

# Configuration group for clustering-related settings.
CNF_CLUSTER = 'clustering'

MONGODB_PORT = CONF.mongodb.mongodb_port
CONFIGSVR_PORT = CONF.mongodb.configsvr_port


class MongoDBApp(object):
    """Prepares DBaaS on a Guest container."""

    def __init__(self):
        self.state_change_wait_time = CONF.state_change_wait_time

        revision_dir = guestagent_utils.build_file_path(
            os.path.dirname(CONFIG_FILE),
            ConfigurationManager.DEFAULT_STRATEGY_OVERRIDES_SUB_DIR)
        self.configuration_manager = ConfigurationManager(
            CONFIG_FILE, system.MONGO_USER, system.MONGO_USER,
            SafeYamlCodec(default_flow_style=False),
            requires_root=True,
            override_strategy=OneFileOverrideStrategy(revision_dir))

        self.is_query_router = False
        self.is_cluster_member = False
        self.status = MongoDBAppStatus()

    def install_if_needed(self, packages):
        """Prepare the guest machine with a MongoDB installation."""
        LOG.info(_("Preparing Guest as MongoDB."))
        if not system.PACKAGER.pkg_is_installed(packages):
            LOG.debug("Installing packages: %s." % str(packages))
            system.PACKAGER.pkg_install(packages, {}, system.TIME_OUT)
        LOG.info(_("Finished installing MongoDB server."))

    def _get_service_candidates(self):
        if self.is_query_router:
            return system.MONGOS_SERVICE_CANDIDATES
        return system.MONGOD_SERVICE_CANDIDATES

    def stop_db(self, update_db=False, do_not_start_on_reboot=False):
        self.status.stop_db_service(
            self._get_service_candidates(), self.state_change_wait_time,
            disable_on_boot=do_not_start_on_reboot, update_db=update_db)

    def restart(self):
        self.status.restart_db_service(
            self._get_service_candidates(), self.state_change_wait_time)

    def start_db(self, update_db=False):
        self.status.start_db_service(
            self._get_service_candidates(), self.state_change_wait_time,
            enable_on_boot=True, update_db=update_db)

    def update_overrides(self, context, overrides, remove=False):
        if overrides:
            self.configuration_manager.apply_user_override(overrides)

    def remove_overrides(self):
        self.configuration_manager.remove_user_override()

    def start_db_with_conf_changes(self, config_contents):
        LOG.info(_('Starting MongoDB with configuration changes.'))
        if self.status.is_running:
            format = 'Cannot start_db_with_conf_changes because status is %s.'
            LOG.debug(format, self.status)
            raise RuntimeError(format % self.status)
        LOG.info(_("Initiating config."))
        self.configuration_manager.save_configuration(config_contents)
        # The configuration template has to be updated with
        # guestagent-controlled settings.
        self.apply_initial_guestagent_configuration(
            None, mount_point=system.MONGODB_MOUNT_POINT)
        self.start_db(True)

    def apply_initial_guestagent_configuration(
            self, cluster_config, mount_point=None):
        LOG.debug("Applying initial configuration.")

        # Mongodb init scripts assume the PID-file path is writable by the
        # database service.
        # See: https://jira.mongodb.org/browse/SERVER-20075
        self._initialize_writable_run_dir()

        self.configuration_manager.apply_system_override(
            {'processManagement.fork': False,
             'processManagement.pidFilePath': system.MONGO_PID_FILE,
             'systemLog.destination': 'file',
             'systemLog.path': system.MONGO_LOG_FILE,
             'systemLog.logAppend': True
             })

        if mount_point:
            self.configuration_manager.apply_system_override(
                {'storage.dbPath': mount_point})

        if cluster_config is not None:
            self._configure_as_cluster_instance(cluster_config)
        else:
            self._configure_network(MONGODB_PORT)

    def _initialize_writable_run_dir(self):
        """Create a writable directory for Mongodb's runtime data
        (e.g. PID-file).
        """
        mongodb_run_dir = os.path.dirname(system.MONGO_PID_FILE)
        LOG.debug("Initializing a runtime directory: %s" % mongodb_run_dir)
        operating_system.create_directory(
            mongodb_run_dir, user=system.MONGO_USER, group=system.MONGO_USER,
            force=True, as_root=True)

    def _configure_as_cluster_instance(self, cluster_config):
        """Configure this guest as a cluster instance and return its
        new status.
        """
        if cluster_config['instance_type'] == "query_router":
            self._configure_as_query_router()
        elif cluster_config["instance_type"] == "config_server":
            self._configure_as_config_server()
        elif cluster_config["instance_type"] == "member":
            self._configure_as_cluster_member(
                cluster_config['replica_set_name'])
        else:
            LOG.error(_("Bad cluster configuration; instance type "
                        "given as %s.") % cluster_config['instance_type'])
            return ds_instance.ServiceStatuses.FAILED

        if 'key' in cluster_config:
            self._configure_cluster_security(cluster_config['key'])

    def _configure_as_query_router(self):
        LOG.info(_("Configuring instance as a cluster query router."))
        self.is_query_router = True

        # FIXME(pmalik): We should really have a separate configuration
        # template for the 'mongos' process.
        # Remove all storage configurations from the template.
        # They apply only to 'mongod' processes.
        # Already applied overrides will be integrated into the base file and
        # their current groups removed.
        config = guestagent_utils.expand_dict(
            self.configuration_manager.parse_configuration())
        if 'storage' in config:
            LOG.debug("Removing 'storage' directives from the configuration "
                      "template.")
            del config['storage']
            self.configuration_manager.save_configuration(
                guestagent_utils.flatten_dict(config))

        # Apply 'mongos' configuration.
        self._configure_network(MONGODB_PORT)
        self.configuration_manager.apply_system_override(
            {'sharding.configDB': ''}, CNF_CLUSTER)

    def _configure_as_config_server(self):
        LOG.info(_("Configuring instance as a cluster config server."))
        self._configure_network(CONFIGSVR_PORT)
        self.configuration_manager.apply_system_override(
            {'sharding.clusterRole': 'configsvr'}, CNF_CLUSTER)

    def _configure_as_cluster_member(self, replica_set_name):
        LOG.info(_("Configuring instance as a cluster member."))
        self.is_cluster_member = True
        self._configure_network(MONGODB_PORT)
        # we don't want these thinking they are in a replica set yet
        # as that would prevent us from creating the admin user,
        # so start mongo before updating the config.
        # mongo will be started by the cluster taskmanager
        self.start_db()
        self.configuration_manager.apply_system_override(
            {'replication.replSetName': replica_set_name}, CNF_CLUSTER)

    def _configure_cluster_security(self, key_value):
        """Force cluster key-file-based authentication.

        This will enabled RBAC.
        """
        # Store the cluster member authentication key.
        self.store_key(key_value)

        self.configuration_manager.apply_system_override(
            {'security.clusterAuthMode': 'keyFile',
             'security.keyFile': self.get_key_file()}, CNF_CLUSTER)

    def _configure_network(self, port=None):
        """Make the service accessible at a given (or default if not) port.
        """
        instance_ip = netutils.get_my_ipv4()
        bind_interfaces_string = ','.join([instance_ip, '127.0.0.1'])
        options = {'net.bindIp': bind_interfaces_string}
        if port is not None:
            guestagent_utils.update_dict({'net.port': port}, options)

        self.configuration_manager.apply_system_override(options)
        self.status.set_host(instance_ip, port=port)

    def clear_storage(self):
        mount_point = "/var/lib/mongodb/*"
        LOG.debug("Clearing storage at %s." % mount_point)
        try:
            operating_system.remove(mount_point, force=True, as_root=True)
        except exception.ProcessExecutionError:
            LOG.exception(_("Error clearing storage."))

    def _has_config_db(self):
        value_string = self.configuration_manager.get_value(
            'sharding', {}).get('configDB')

        return value_string is not None

    # FIXME(pmalik): This method should really be called 'set_config_servers'.
    # The current name suggests it adds more config servers, but it
    # rather replaces the existing ones.
    def add_config_servers(self, config_server_hosts):
        """Set config servers on a query router (mongos) instance.
        """
        config_servers_string = ','.join(['%s:27019' % host
                                          for host in config_server_hosts])
        LOG.info(_("Setting config servers: %s") % config_servers_string)
        self.configuration_manager.apply_system_override(
            {'sharding.configDB': config_servers_string}, CNF_CLUSTER)
        self.start_db(True)

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

        MongoDBAdmin().rs_initiate()
        # TODO(ramashri) see if hardcoded values can be removed
        utils.poll_until(check_initiate_status, sleep_time=30, time_out=100)

        # add replica-set members
        MongoDBAdmin().rs_add_members(members)
        # TODO(ramashri) see if hardcoded values can be removed
        utils.poll_until(check_rs_status, sleep_time=10, time_out=100)

    def _set_localhost_auth_bypass(self, enabled):
        """When active, the localhost exception allows connections from the
        localhost interface to create the first user on the admin database.
        The exception applies only when there are no users created in the
        MongoDB instance.
        """
        self.configuration_manager.apply_system_override(
            {'setParameter': {'enableLocalhostAuthBypass': enabled}})

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
        return operating_system.read_file(
            system.MONGO_KEY_FILE, as_root=True).rstrip()

    def store_key(self, key):
        """Store the cluster key."""
        LOG.debug('Storing key for MongoDB cluster.')
        operating_system.write_file(system.MONGO_KEY_FILE, key, as_root=True)
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
        # the driver engine is already cached, but we need to change it it
        with MongoDBClient(None, host='localhost',
                           port=MONGODB_PORT) as client:
            MongoDBAdmin().create_validated_user(user, client=client)
        # now revert to the normal engine
        self.status.set_host(host=netutils.get_my_ipv4(),
                             port=MONGODB_PORT)
        LOG.debug('Created admin user.')

    def secure(self):
        """Create the Trove admin user.

        The service should not be running at this point.
        This will enable role-based access control (RBAC) by default.
        """
        if self.status.is_running:
            raise RuntimeError(_("Cannot secure the instance. "
                                 "The service is still running."))

        try:
            self.configuration_manager.apply_system_override(
                {'security.authorization': 'enabled'})
            self._set_localhost_auth_bypass(True)
            self.start_db(update_db=False)
            password = utils.generate_random_password()
            self.create_admin_user(password)
            LOG.debug("MongoDB secure complete.")
        finally:
            self._set_localhost_auth_bypass(False)
            self.stop_db()

    def get_configuration_property(self, name, default=None):
        """Return the value of a MongoDB configuration property.
        """
        return self.configuration_manager.get_value(name, default)

    def prep_primary(self):
        # Prepare the primary member of a replica set.
        password = utils.generate_random_password()
        self.create_admin_user(password)
        self.restart()

    @property
    def replica_set_name(self):
        return MongoDBAdmin().get_repl_status()['set']

    @property
    def admin_password(self):
        creds = MongoDBCredentials()
        creds.read(system.MONGO_ADMIN_CREDS_FILE)
        return creds.password

    def is_shard_active(self, replica_set_name):
        shards = MongoDBAdmin().list_active_shards()
        if replica_set_name in [shard['_id'] for shard in shards]:
            LOG.debug('Replica set %s is active.' % replica_set_name)
            return True
        else:
            LOG.debug('Replica set %s is not active.' % replica_set_name)
            return False


class MongoDBAppStatus(service.BaseDbStatus):

    def __init__(self, host='localhost', port=None):
        super(MongoDBAppStatus, self).__init__()
        self.set_host(host, port=port)

    def set_host(self, host, port=None):
        # This forces refresh of the 'pymongo' engine cached in the
        # MongoDBClient class.
        # Authentication is not required to check the server status.
        MongoDBClient(None, host=host, port=port)

    def _get_actual_db_status(self):
        try:
            with MongoDBClient(None) as client:
                client.server_info()
            return ds_instance.ServiceStatuses.RUNNING
        except (pymongo.errors.ServerSelectionTimeoutError,
                pymongo.errors.AutoReconnect):
            return ds_instance.ServiceStatuses.SHUTDOWN
        except Exception:
            LOG.exception(_("Error getting MongoDB status."))

        return ds_instance.ServiceStatuses.SHUTDOWN

    def cleanup_stalled_db_services(self):
        pid, err = utils.execute_with_timeout(system.FIND_PID, shell=True)
        utils.execute_with_timeout(system.MONGODB_KILL % pid, shell=True)


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
            type(self).admin_user = user
        return type(self).admin_user

    def _is_modifiable_user(self, name):
        if ((name in cfg.get_ignored_users(manager=MANAGER)) or
                name == system.MONGO_ADMIN_NAME):
            return False
        return True

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

    def create_validated_user(self, user, client=None):
        """Creates a user on their database. The caller should ensure that
        this action is valid.
        :param user:   a MongoDBUser object
        """
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
        """Create the given user(s).
        :param users:   list of serialized user objects
        """
        with MongoDBClient(self._admin_user()) as client:
            for item in users:
                user = models.MongoDBUser.deserialize_user(item)
                if not self._is_modifiable_user(user.name):
                    LOG.warning('Skipping creation of user with reserved '
                                'name %(user)s' % {'user': user.name})
                elif self._get_user_record(user.name, client=client):
                    LOG.warning('Skipping creation of user with pre-existing '
                                'name %(user)s' % {'user': user.name})
                else:
                    self.create_validated_user(user, client=client)

    def delete_validated_user(self, user):
        """Deletes a user from their database. The caller should ensure that
        this action is valid.
        :param user:   a MongoDBUser object
        """
        LOG.debug('Deleting user %s from database %s.'
                  % (user.username, user.database.name))
        with MongoDBClient(self._admin_user()) as admin_client:
            admin_client[user.database.name].remove_user(user.username)

    def delete_user(self, user):
        """Delete the given user.
        :param user:   a serialized user object
        """
        user = models.MongoDBUser.deserialize_user(user)
        if not self._is_modifiable_user(user.name):
            raise exception.BadRequest(_(
                'Cannot delete user with reserved name %(user)s')
                % {'user': user.name})
        else:
            self.delete_validated_user(user)

    def _get_user_record(self, name, client=None):
        """Get the user's record."""
        user = models.MongoDBUser(name)
        if not self._is_modifiable_user(user.name):
            LOG.warning('Skipping retrieval of user with reserved '
                        'name %(user)s' % {'user': user.name})
            return None
        if client:
            user_info = client.admin.system.users.find_one(
                {'user': user.username, 'db': user.database.name})
        else:
            with MongoDBClient(self._admin_user()) as admin_client:
                user_info = admin_client.admin.system.users.find_one(
                    {'user': user.username, 'db': user.database.name})
        if not user_info:
            return None
        user.roles = user_info['roles']
        return user

    def get_user(self, name):
        """Get information for the given user."""
        LOG.debug('Getting user %s.' % name)
        user = self._get_user_record(name)
        if not user:
            return None
        return user.serialize()

    def list_users(self, limit=None, marker=None, include_marker=False):
        """Get a list of all users."""
        users = []
        with MongoDBClient(self._admin_user()) as admin_client:
            for user_info in admin_client.admin.system.users.find():
                user = models.MongoDBUser(name=user_info['_id'])
                user.roles = user_info['roles']
                if self._is_modifiable_user(user.name):
                    users.append(user.serialize())
        LOG.debug('users = ' + str(users))
        return pagination.paginate_list(users, limit, marker,
                                        include_marker)

    def change_passwords(self, users):
        with MongoDBClient(self._admin_user()) as admin_client:
            for item in users:
                user = models.MongoDBUser.deserialize_user(item)
                if not self._is_modifiable_user(user.name):
                    LOG.warning('Skipping password change for user with '
                                'reserved name %(user)s.'
                                % {'user': user.name})
                    return None
                LOG.debug('Changing password for user %(user)s'
                          % {'user': user.name})
                self._create_user_with_client(user, admin_client)

    def update_attributes(self, name, user_attrs):
        """Update user attributes."""
        user = self._get_user_record(name)
        if not user:
            raise exception.BadRequest(_(
                'Cannot update attributes for user %(user)s as it either does '
                'not exist or is a reserved user.') % {'user': name})
        password = user_attrs.get('password')
        if password:
            user.password = password
            self.change_passwords([user.serialize()])
        if user_attrs.get('name'):
            LOG.warning('Changing user name is not supported.')
        if user_attrs.get('host'):
            LOG.warning('Changing user host is not supported.')

    def enable_root(self, password=None):
        """Create a user 'root' with role 'root'."""
        if not password:
            LOG.debug('Generating root user password.')
            password = utils.generate_random_password()
        root_user = models.MongoDBUser(name='admin.root', password=password)
        root_user.roles = {'db': 'admin', 'role': 'root'}
        self.create_validated_user(root_user)
        return root_user.serialize()

    def is_root_enabled(self):
        """Check if user 'admin.root' exists."""
        with MongoDBClient(self._admin_user()) as admin_client:
            return bool(admin_client.admin.system.users.find_one(
                {'roles.role': 'root'}
            ))

    def _update_user_roles(self, user):
        with MongoDBClient(self._admin_user()) as admin_client:
            admin_client[user.database.name].add_user(
                user.username, roles=user.roles
            )

    def grant_access(self, username, databases):
        """Adds the RW role to the user for each specified database."""
        user = self._get_user_record(username)
        if not user:
            raise exception.BadRequest(_(
                'Cannot grant access for reserved or non-existant user '
                '%(user)s') % {'user': username})
        for db_name in databases:
            # verify the database name
            models.MongoDBSchema(db_name)
            role = {'db': db_name, 'role': 'readWrite'}
            if role not in user.roles:
                LOG.debug('Adding role %s to user %s.'
                          % (str(role), username))
                user.roles = role
            else:
                LOG.debug('User %s already has role %s.'
                          % (username, str(role)))
        LOG.debug('Updating user %s.' % username)
        self._update_user_roles(user)

    def revoke_access(self, username, database):
        """Removes the RW role from the user for the specified database."""
        user = self._get_user_record(username)
        if not user:
            raise exception.BadRequest(_(
                'Cannot revoke access for reserved or non-existant user '
                '%(user)s') % {'user': username})
        # verify the database name
        models.MongoDBSchema(database)
        role = {'db': database, 'role': 'readWrite'}
        LOG.debug('Removing role %s from user %s.'
                  % (str(role), username))
        user.revoke_role(role)
        LOG.debug('Updating user %s.' % username)
        self._update_user_roles(user)

    def list_access(self, username):
        """Returns a list of all databases for which the user has the RW role.
        """
        user = self._get_user_record(username)
        if not user:
            raise exception.BadRequest(_(
                'Cannot list access for reserved or non-existant user '
                '%(user)s') % {'user': username})
        return user.databases

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
        for hidden in cfg.get_ignored_dbs(manager=MANAGER):
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
            status = admin_client.admin.command('replSetGetStatus')
            LOG.debug('Replica set status: %s' % status)
            return status

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

    def list_active_shards(self):
        """Get a list of shards active in this cluster."""
        with MongoDBClient(self._admin_user()) as admin_client:
            return [shard for shard in admin_client.config.shards.find()]


class MongoDBClient(object):
    """A wrapper to manage a MongoDB connection."""

    # engine information is cached by making it a class attribute
    engine = {}

    def __init__(self, user, host=None, port=None):
        """Get the client. Specifying host and/or port updates cached values.
        :param user: MongoDBUser instance used to authenticate
        :param host: server address, defaults to localhost
        :param port: server port, defaults to 27017
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
                type(self).engine['port'] = port
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
        if user:
            db_name = user.database.name
            LOG.debug("Authenticating MongoDB client on %s." % db_name)
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
        credentials = operating_system.read_file(filename, codec=JsonCodec())
        self.username = credentials['username']
        self.password = credentials['password']

    def write(self, filename):
        credentials = {'username': self.username,
                       'password': self.password}

        operating_system.write_file(filename, credentials, codec=JsonCodec())
        operating_system.chmod(filename, operating_system.FileMode.SET_USR_RW)
