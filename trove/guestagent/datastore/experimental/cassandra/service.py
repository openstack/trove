#  Copyright 2013 Mirantis Inc.
#  All Rights Reserved.
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
import re
import stat

from cassandra.auth import PlainTextAuthProvider
from cassandra.cluster import Cluster
from cassandra.cluster import NoHostAvailable
from cassandra import OperationTimedOut
from oslo_log import log as logging
from oslo_utils import netutils

from trove.common import cfg
from trove.common import exception
from trove.common.i18n import _
from trove.common import instance as rd_instance
from trove.common import pagination
from trove.common.stream_codecs import IniCodec
from trove.common.stream_codecs import SafeYamlCodec
from trove.common import utils
from trove.guestagent.common import guestagent_utils
from trove.guestagent.common import operating_system
from trove.guestagent.common.operating_system import FileMode
from trove.guestagent.datastore import service
from trove.guestagent.db import models
from trove.guestagent import pkg


LOG = logging.getLogger(__name__)
CONF = cfg.CONF
MANAGER = CONF.datastore_manager if CONF.datastore_manager else 'cassandra'

packager = pkg.Package()


class CassandraApp(object):
    """Prepares DBaaS on a Guest container."""

    _ADMIN_USER = 'os_admin'

    _CONF_AUTH_SEC = 'authentication'
    _CONF_USR_KEY = 'username'
    _CONF_PWD_KEY = 'password'
    _CONF_DIR_MODS = stat.S_IRWXU
    _CONF_FILE_MODS = stat.S_IRUSR

    CASSANDRA_KILL_CMD = "sudo killall java  || true"

    def __init__(self):
        """By default login with root no password for initial setup."""
        self.state_change_wait_time = CONF.state_change_wait_time
        self.status = CassandraAppStatus(self.get_current_superuser())

    @property
    def service_candidates(self):
        return ['cassandra']

    @property
    def cassandra_conf(self):
        return {
            operating_system.REDHAT:
                "/etc/cassandra/default.conf/cassandra.yaml",
            operating_system.DEBIAN:
                "/etc/cassandra/cassandra.yaml",
            operating_system.SUSE:
                "/etc/cassandra/default.conf/cassandra.yaml"
        }[operating_system.get_os()]

    @property
    def cassandra_owner(self):
        return 'cassandra'

    @property
    def cassandra_data_dir(self):
        return guestagent_utils.build_file_path(
            self.cassandra_working_dir, 'data')

    @property
    def cassandra_working_dir(self):
        return "/var/lib/cassandra"

    @property
    def default_superuser_name(self):
        return "cassandra"

    @property
    def default_superuser_password(self):
        return "cassandra"

    @property
    def default_superuser_pwd_hash(self):
        # Default 'salted_hash' value for 'cassandra' user on Cassandra 2.1.
        return "$2a$10$wPEVuXBU7WE2Uwzqq3t19ObRJyoKztzC/Doyfr0VtDmVXC4GDAV3e"

    @property
    def cqlsh_conf_path(self):
        return "~/.cassandra/cqlshrc"

    def install_if_needed(self, packages):
        """Prepare the guest machine with a cassandra server installation."""
        LOG.info(_("Preparing Guest as a Cassandra Server"))
        if not packager.pkg_is_installed(packages):
            self._install_db(packages)
        LOG.debug("Cassandra install_if_needed complete")

    def init_storage_structure(self, mount_point):
        try:
            operating_system.create_directory(mount_point, as_root=True)
        except exception.ProcessExecutionError:
            LOG.exception(_("Error while initiating storage structure."))

    def start_db(self, update_db=False):
        self.status.start_db_service(
            self.service_candidates, self.state_change_wait_time,
            enable_on_boot=True, update_db=update_db)

    def stop_db(self, update_db=False, do_not_start_on_reboot=False):
        self.status.stop_db_service(
            self.service_candidates, self.state_change_wait_time,
            disable_on_boot=do_not_start_on_reboot, update_db=update_db)

    def restart(self):
        self.status.restart_db_service(
            self.service_candidates, self.state_change_wait_time)

    def _install_db(self, packages):
        """Install cassandra server"""
        LOG.debug("Installing cassandra server.")
        packager.pkg_install(packages, None, 10000)
        LOG.debug("Finished installing Cassandra server")

    def secure(self, update_user=None):
        """Configure the Trove administrative user.
        Update an existing user if given.
        Create a new one using the default database credentials
        otherwise and drop the built-in user when finished.
        """
        LOG.info(_('Configuring Trove superuser.'))

        current_superuser = update_user or models.CassandraUser(
            self.default_superuser_name,
            self.default_superuser_password)

        if update_user:
            os_admin = models.CassandraUser(update_user.name,
                                            utils.generate_random_password())
            CassandraAdmin(current_superuser).alter_user_password(os_admin)
        else:
            os_admin = models.CassandraUser(self._ADMIN_USER,
                                            utils.generate_random_password())
            CassandraAdmin(current_superuser)._create_superuser(os_admin)
            CassandraAdmin(os_admin).drop_user(current_superuser)

        self.__create_cqlsh_config({self._CONF_AUTH_SEC:
                                    {self._CONF_USR_KEY: os_admin.name,
                                     self._CONF_PWD_KEY: os_admin.password}})

        # Update the internal status with the new user.
        self.status = CassandraAppStatus(os_admin)

        return os_admin

    def __create_cqlsh_config(self, sections):
        config_path = self._get_cqlsh_conf_path()
        config_dir = os.path.dirname(config_path)
        if not os.path.exists(config_dir):
            os.mkdir(config_dir, self._CONF_DIR_MODS)
        else:
            os.chmod(config_dir, self._CONF_DIR_MODS)
        operating_system.write_file(config_path, sections, codec=IniCodec())
        os.chmod(config_path, self._CONF_FILE_MODS)

    def get_current_superuser(self):
        """
        Build the Trove superuser.
        Use the stored credentials.
        If not available fall back to the defaults.
        """
        if self.has_user_config():
            return self._load_current_superuser()

        LOG.warn(_("Trove administrative user has not been configured yet. "
                   "Using the built-in default: %s")
                 % self.default_superuser_name)
        return models.CassandraUser(self.default_superuser_name,
                                    self.default_superuser_password)

    def has_user_config(self):
        """
        Return TRUE if there is a client configuration file available
        on the guest.
        """
        return os.path.exists(self._get_cqlsh_conf_path())

    def _load_current_superuser(self):
        config = operating_system.read_file(self._get_cqlsh_conf_path(),
                                            codec=IniCodec())
        return models.CassandraUser(
            config[self._CONF_AUTH_SEC][self._CONF_USR_KEY],
            config[self._CONF_AUTH_SEC][self._CONF_PWD_KEY]
        )

    def write_config(self, config_contents):

        operating_system.write_file(
            self.cassandra_conf, config_contents, codec=SafeYamlCodec(),
            as_root=True)
        operating_system.chown(self.cassandra_conf,
                               self.cassandra_owner,
                               self.cassandra_owner,
                               recursive=False, as_root=True)
        operating_system.chmod(self.cassandra_conf,
                               FileMode.ADD_READ_ALL, as_root=True)

        LOG.info(_('Wrote new Cassandra configuration.'))

    def update_config_with_single(self, key, value):
        """Updates single key:value in 'cassandra.yaml'."""

        yamled = operating_system.read_file(self.cassandra_conf,
                                            codec=SafeYamlCodec())
        yamled.update({key: value})
        LOG.debug("Updating cassandra.yaml with %(key)s: %(value)s."
                  % {'key': key, 'value': value})
        LOG.debug("Dumping YAML to stream.")
        self.write_config(yamled)

    def update_conf_with_group(self, group):
        """Updates group of key:value in 'cassandra.yaml'."""

        yamled = operating_system.read_file(self.cassandra_conf,
                                            codec=SafeYamlCodec())
        for key, value in group.iteritems():
            if key == 'seed':
                (yamled.get('seed_provider')[0].
                 get('parameters')[0].
                 update({'seeds': value}))
            else:
                yamled.update({key: value})
            LOG.debug("Updating cassandra.yaml with %(key)s: %(value)s."
                      % {'key': key, 'value': value})
        LOG.debug("Dumping YAML to stream")
        self.write_config(yamled)

    def make_host_reachable(self):
        updates = {
            'rpc_address': "0.0.0.0",
            'broadcast_rpc_address': netutils.get_my_ipv4(),
            'listen_address': netutils.get_my_ipv4(),
            'seed': netutils.get_my_ipv4()
        }
        self.update_conf_with_group(updates)

    def start_db_with_conf_changes(self, config_contents):
        LOG.info(_("Starting Cassandra with configuration changes."))
        LOG.debug("Inside the guest - Cassandra is running %s."
                  % self.status.is_running)
        if self.status.is_running:
            LOG.error(_("Cannot execute start_db_with_conf_changes because "
                        "Cassandra state == %s.") % self.status)
            raise RuntimeError("Cassandra not stopped.")
        LOG.debug("Initiating config.")
        self.write_config(config_contents)
        self.start_db(True)

    def reset_configuration(self, configuration):
        config_contents = configuration['config_contents']
        LOG.debug("Resetting configuration")
        self.write_config(config_contents)

    def _get_cqlsh_conf_path(self):
        return os.path.expanduser(self.cqlsh_conf_path)


class CassandraAppStatus(service.BaseDbStatus):

    def __init__(self, superuser):
        """
        :param superuser:        User account the Status uses for connecting
                                 to the database.
        :type superuser:         CassandraUser
        """
        super(CassandraAppStatus, self).__init__()
        self.__user = superuser

    def set_superuser(self, user):
        self.__user = user

    def _get_actual_db_status(self):
        try:
            with CassandraLocalhostConnection(self.__user):
                return rd_instance.ServiceStatuses.RUNNING
        except NoHostAvailable:
            return rd_instance.ServiceStatuses.SHUTDOWN
        except Exception:
            LOG.exception(_("Error getting Cassandra status."))

        return rd_instance.ServiceStatuses.SHUTDOWN

    def cleanup_stalled_db_services(self):
        utils.execute_with_timeout(CassandraApp.CASSANDRA_KILL_CMD, shell=True)


class CassandraAdmin(object):
    """Handles administrative tasks on the Cassandra database.

    In Cassandra only SUPERUSERS can create other users and grant permissions
    to database resources. Trove uses the 'cassandra' superuser to perform its
    administrative tasks.

    The users it creates are all 'normal' (NOSUPERUSER) accounts.
    The permissions it can grant are also limited to non-superuser operations.
    This is to prevent anybody from creating a new superuser via the Trove API.
    """

    # Non-superuser grant modifiers.
    __NO_SUPERUSER_MODIFIERS = ('ALTER', 'CREATE', 'DROP', 'MODIFY', 'SELECT')

    _KS_NAME_REGEX = re.compile('^<keyspace (.+)>$')

    def __init__(self, user):
        self.__admin_user = user

    def create_user(self, context, users):
        """
        Create new non-superuser accounts.
        New users are by default granted full access to all database resources.
        """
        with CassandraLocalhostConnection(self.__admin_user) as client:
            for item in users:
                self._create_user_and_grant(client,
                                            self._deserialize_user(item))

    def _create_user_and_grant(self, client, user):
        """
        Create new non-superuser account and grant it full access to its
        databases.
        """
        self._create_user(client, user)
        for db in user.databases:
            self._grant_full_access_on_keyspace(
                client, self._deserialize_keyspace(db), user)

    def _create_user(self, client, user):
        # Create only NOSUPERUSER accounts here.
        LOG.debug("Creating a new user '%s'." % user.name)
        client.execute("CREATE USER '{}' WITH PASSWORD %s NOSUPERUSER;",
                       (user.name,), (user.password,))

    def _create_superuser(self, user):
        """Create a new superuser account and grant it full superuser-level
        access to all keyspaces.
        """
        LOG.debug("Creating a new superuser '%s'." % user.name)
        with CassandraLocalhostConnection(self.__admin_user) as client:
            client.execute("CREATE USER '{}' WITH PASSWORD %s SUPERUSER;",
                           (user.name,), (user.password,))
            client.execute("GRANT ALL PERMISSIONS ON ALL KEYSPACES TO '{}';",
                           (user.name,))

    def delete_user(self, context, user):
        self.drop_user(self._deserialize_user(user))

    def drop_user(self, user):
        with CassandraLocalhostConnection(self.__admin_user) as client:
            self._drop_user(client, user)

    def _drop_user(self, client, user):
        LOG.debug("Deleting user '%s'." % user.name)
        client.execute("DROP USER '{}';", (user.name, ))

    def get_user(self, context, username, hostname):
        with CassandraLocalhostConnection(self.__admin_user) as client:
            user = self._find_user(client, username)
            return user.serialize() if user is not None else None

    def _find_user(self, client, username):
        """
        Lookup a user with a given username.
        Omit user names on the ignore list.
        Return a new Cassandra user instance or None if no match is found.
        """
        return next((user for user in self._get_listed_users(client)
                     if user.name == username), None)

    def list_users(self, context, limit=None, marker=None,
                   include_marker=False):
        """
        List all non-superuser accounts. Omit names on the ignored list.
        Return an empty set if None.
        """
        with CassandraLocalhostConnection(self.__admin_user) as client:
            users = [user.serialize() for user in
                     self._get_listed_users(client)]
            return pagination.paginate_list(users, limit, marker,
                                            include_marker)

    def _get_listed_users(self, client):
        """
        Return a set of unique user instances.
        Omit user names on the ignore list.
        """
        return self._get_users(
            client, lambda user: user.name not in self.ignore_users)

    def _get_users(self, client, matcher=None):
        """
        :param matcher                Filter expression.
        :type matcher                 callable
        """
        acl = self._get_acl(client)
        return {self._build_user(user.name, acl)
                for user in client.execute("LIST USERS;")
                if not matcher or matcher(user)}

    def _load_user(self, client, username, check_reserved=True):
        if check_reserved:
            self._check_reserved_user_name(username)

        acl = self._get_acl(client, username=username)
        return self._build_user(username, acl)

    def _build_user(self, username, acl):
        user = models.CassandraUser(username)
        for ks, permissions in acl.get(username, {}).items():
            if permissions:
                user.databases.append(models.CassandraSchema(ks).serialize())
        return user

    def _get_acl(self, client, username=None):
        """Return the ACL for a database user.
        Return ACLs for all users if no particular username is specified.

        The ACL has the following format:
        {username #1:
            {keyspace #1: {access mod(s)...},
             keyspace #2: {...}},
         username #2:
            {keyspace #1: {...},
             keyspace #3: {...}}
        }
        """

        def build_list_query(username):
            query_tokens = ["LIST ALL PERMISSIONS"]
            if username:
                query_tokens.extend(["OF", "'%s'" % username])
            query_tokens.append("NORECURSIVE;")
            return ' '.join(query_tokens)

        def parse_keyspace_name(resource):
            """Parse a keyspace name from a resource string.
            The resource string has the following form:
                <object name>
            where 'object' is one of the database objects (keyspace, table...).
            Return the name as a singleton set. Return an empty set if no match
            is found.
            """
            match = self._KS_NAME_REGEX.match(resource)
            if match:
                return {match.group(1)}
            return {}

        def update_acl(username, keyspace, permission, acl):
            permissions = acl.get(username, {}).get(keyspace)
            if permissions is None:
                guestagent_utils.update_dict({user: {keyspace: {permission}}},
                                             acl)
            else:
                permissions.add(permission)

        all_keyspace_names = None
        acl = dict()
        for item in client.execute(build_list_query(username)):
            user = item.username
            resource = item.resource
            permission = item.permission
            if user and resource and permission:
                if resource == '<all keyspaces>':
                    # Cache the full keyspace list to improve performance and
                    # ensure consistent results for all users.
                    if all_keyspace_names is None:
                        all_keyspace_names = {
                            item.name
                            for item in self._get_available_keyspaces(client)
                        }
                    keyspaces = all_keyspace_names
                else:
                    keyspaces = parse_keyspace_name(resource)

                for keyspace in keyspaces:
                    update_acl(user, keyspace, permission, acl)

        return acl

    def list_superusers(self):
        """List all system users existing in the database."""
        with CassandraLocalhostConnection(self.__admin_user) as client:
            return self._get_users(client, lambda user: user.super)

    def grant_access(self, context, username, hostname, databases):
        """
        Grant full access on keyspaces to a given username.
        """
        user = models.CassandraUser(username)
        with CassandraLocalhostConnection(self.__admin_user) as client:
            for db in databases:
                self._grant_full_access_on_keyspace(
                    client, models.CassandraSchema(db), user)

    def revoke_access(self, context, username, hostname, database):
        """
        Revoke all permissions on any database resources from a given username.
        """
        user = models.CassandraUser(username)
        with CassandraLocalhostConnection(self.__admin_user) as client:
            self._revoke_all_access_on_keyspace(
                client, models.CassandraSchema(database), user)

    def _grant_full_access_on_keyspace(self, client, keyspace, user,
                                       check_reserved=True):
        """
        Grant all non-superuser permissions on a keyspace to a given user.
        """
        if check_reserved:
            self._check_reserved_user_name(user.name)
            self._check_reserved_keyspace_name(keyspace.name)

        for access in self.__NO_SUPERUSER_MODIFIERS:
            self._grant_permission_on_keyspace(client, access, keyspace, user)

    def _grant_permission_on_keyspace(self, client, modifier, keyspace, user):
        """
        Grant a non-superuser permission on a keyspace to a given user.
        Raise an exception if the caller attempts to grant a superuser access.
        """
        LOG.debug("Granting '%s' access on '%s' to user '%s'."
                  % (modifier, keyspace.name, user.name))
        if modifier in self.__NO_SUPERUSER_MODIFIERS:
            client.execute("GRANT {} ON KEYSPACE \"{}\" TO '{}';",
                           (modifier, keyspace.name, user.name))
        else:
            raise exception.UnprocessableEntity(
                "Invalid permission modifier (%s). Allowed values are: '%s'"
                % (modifier, ', '.join(self.__NO_SUPERUSER_MODIFIERS)))

    def _revoke_all_access_on_keyspace(self, client, keyspace, user,
                                       check_reserved=True):
        if check_reserved:
            self._check_reserved_user_name(user.name)
            self._check_reserved_keyspace_name(keyspace.name)

        LOG.debug("Revoking all permissions on '%s' from user '%s'."
                  % (keyspace.name, user.name))
        client.execute("REVOKE ALL PERMISSIONS ON KEYSPACE \"{}\" FROM '{}';",
                       (keyspace.name, user.name))

    def update_attributes(self, context, username, hostname, user_attrs):
        with CassandraLocalhostConnection(self.__admin_user) as client:
            user = self._load_user(client, username)
            new_name = user_attrs.get('name')
            new_password = user_attrs.get('password')
            self._update_user(client, user, new_name, new_password)

    def _update_user(self, client, user, new_username, new_password):
        """
        Update a user of a given username.
        Updatable attributes include username and password.
        If a new username and password are given a new user with those
        attributes is created and all permissions from the original
        user get transfered to it. The original user is then dropped
        therefore revoking its permissions.
        If only new password is specified the existing user gets altered
        with that password.
        """
        if new_username is not None and user.name != new_username:
            if new_password is not None:
                self._rename_user(client, user, new_username, new_password)
            else:
                raise exception.UnprocessableEntity(
                    _("Updating username requires specifying a password "
                      "as well."))
        elif new_password is not None and user.password != new_password:
            user.password = new_password
            self._alter_user_password(client, user)

    def _rename_user(self, client, user, new_username, new_password):
        """
        Rename a given user also updating its password.
        Transfer the current permissions to the new username.
        Drop the old username therefore revoking its permissions.
        """
        LOG.debug("Renaming user '%s' to '%s'" % (user.name, new_username))
        new_user = models.CassandraUser(new_username, new_password)
        new_user.databases.extend(user.databases)
        self._create_user_and_grant(client, new_user)
        self._drop_user(client, user)

    def alter_user_password(self, user):
        with CassandraLocalhostConnection(self.__admin_user) as client:
            self._alter_user_password(client, user)

    def change_passwords(self, context, users):
        with CassandraLocalhostConnection(self.__admin_user) as client:
            for user in users:
                self._alter_user_password(client, self._deserialize_user(user))

    def _alter_user_password(self, client, user):
        LOG.debug("Changing password of user '%s'." % user.name)
        client.execute("ALTER USER '{}' "
                       "WITH PASSWORD %s;", (user.name,), (user.password,))

    def create_database(self, context, databases):
        with CassandraLocalhostConnection(self.__admin_user) as client:
            for item in databases:
                self._create_single_node_keyspace(
                    client, self._deserialize_keyspace(item))

    def _create_single_node_keyspace(self, client, keyspace):
        """
        Create a single-replica keyspace.

        Cassandra stores replicas on multiple nodes to ensure reliability and
        fault tolerance. All replicas are equally important;
        there is no primary or master.
        A replication strategy determines the nodes where
        replicas are placed. SimpleStrategy is for a single data center only.
        The total number of replicas across the cluster is referred to as the
        replication factor.

        Replication Strategy:
        'SimpleStrategy' is not optimized for multiple data centers.
        'replication_factor' The number of replicas of data on multiple nodes.
                             Required for SimpleStrategy; otherwise, not used.

        Keyspace names are case-insensitive by default.
        To make a name case-sensitive, enclose it in double quotation marks.
        """
        client.execute("CREATE KEYSPACE \"{}\" WITH REPLICATION = "
                       "{{ 'class' : 'SimpleStrategy', "
                       "'replication_factor' : 1 }};", (keyspace.name,))

    def delete_database(self, context, database):
        with CassandraLocalhostConnection(self.__admin_user) as client:
            self._drop_keyspace(client, self._deserialize_keyspace(database))

    def _drop_keyspace(self, client, keyspace):
        LOG.debug("Dropping keyspace '%s'." % keyspace.name)
        client.execute("DROP KEYSPACE \"{}\";", (keyspace.name,))

    def list_databases(self, context, limit=None, marker=None,
                       include_marker=False):
        with CassandraLocalhostConnection(self.__admin_user) as client:
            databases = [keyspace.serialize() for keyspace
                         in self._get_available_keyspaces(client)]
            return pagination.paginate_list(databases, limit, marker,
                                            include_marker)

    def _get_available_keyspaces(self, client):
        """
        Return a set of unique keyspace instances.
        Omit keyspace names on the ignore list.
        """
        return {models.CassandraSchema(db.keyspace_name)
                for db in client.execute("SELECT * FROM "
                                         "system.schema_keyspaces;")
                if db.keyspace_name not in self.ignore_dbs}

    def list_access(self, context, username, hostname):
        with CassandraLocalhostConnection(self.__admin_user) as client:
            user = self._find_user(client, username)
            if user:
                return user.databases

        raise exception.UserNotFound(username)

    def _deserialize_keyspace(self, keyspace_dict, check_reserved=True):
        if keyspace_dict:
            db = models.CassandraSchema.deserialize_schema(keyspace_dict)
            if check_reserved:
                self._check_reserved_keyspace_name(db.name)

            return db

        return None

    def _check_reserved_keyspace_name(self, name):
        if name in self.ignore_dbs:
            raise ValueError(_("This keyspace-name is reserved: %s") % name)

    def _deserialize_user(self, user_dict, check_reserved=True):
        if user_dict:
            user = models.CassandraUser.deserialize_user(user_dict)
            if check_reserved:
                self._check_reserved_user_name(user.name)

            return user

        return None

    def _check_reserved_user_name(self, name):
        if name in self.ignore_users:
            raise ValueError(_("This user-name is reserved: %s") % name)

    @property
    def ignore_users(self):
        return cfg.get_ignored_users(manager=MANAGER)

    @property
    def ignore_dbs(self):
        return cfg.get_ignored_dbs(manager=MANAGER)


class CassandraConnection(object):
    """A wrapper to manage a Cassandra connection."""

    # Cassandra 2.1 only supports protocol versions 3 and lower.
    NATIVE_PROTOCOL_VERSION = 3

    def __init__(self, contact_points, user):
        self.__user = user
        # A Cluster is initialized with a set of initial contact points.
        # After the driver connects to one of the nodes it will automatically
        # discover the rest.
        # Will connect to '127.0.0.1' if None contact points are given.
        self._cluster = Cluster(
            contact_points=contact_points,
            auth_provider=PlainTextAuthProvider(user.name, user.password),
            protocol_version=self.NATIVE_PROTOCOL_VERSION)
        self.__session = None

    def __enter__(self):
        self.__connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.__disconnect()

    def execute(self, query, identifiers=None, data_values=None, timeout=None):
        """
        Execute a query with a given sequence or dict of data values to bind.
        If a sequence is used, '%s' should be used the placeholder for each
        argument. If a dict is used, '%(name)s' style placeholders must
        be used.
        Only data values should be supplied this way. Other items,
        such as keyspaces, table names, and column names should be set
        ahead of time. Use the '{}' style placeholders and
        'identifiers' parameter for those.
        Raise an exception if the operation exceeds the given timeout (sec).
        There is no timeout if set to None.
        Return a set of rows or an empty list if None.
        """
        if self.__is_active():
            try:
                rows = self.__session.execute(self.__bind(query, identifiers),
                                              data_values, timeout)
                return rows or []
            except OperationTimedOut:
                LOG.error(_("Query execution timed out."))
                raise

        LOG.debug("Cannot perform this operation on a closed connection.")
        raise exception.UnprocessableEntity()

    def __bind(self, query, identifiers):
        if identifiers:
            return query.format(*identifiers)
        return query

    def __connect(self):
        if not self._cluster.is_shutdown:
            LOG.debug("Connecting to a Cassandra cluster as '%s'."
                      % self.__user.name)
            if not self.__is_active():
                self.__session = self._cluster.connect()
            else:
                LOG.debug("Connection already open.")
            LOG.debug("Connected to cluster: '%s'"
                      % self._cluster.metadata.cluster_name)
            for host in self._cluster.metadata.all_hosts():
                LOG.debug("Connected to node: '%s' in rack '%s' at datacenter "
                          "'%s'" % (host.address, host.rack, host.datacenter))
        else:
            LOG.debug("Cannot perform this operation on a terminated cluster.")
            raise exception.UnprocessableEntity()

    def __disconnect(self):
        if self.__is_active():
            try:
                LOG.debug("Disconnecting from cluster: '%s'"
                          % self._cluster.metadata.cluster_name)
                self._cluster.shutdown()
                self.__session.shutdown()
            except Exception:
                LOG.debug("Failed to disconnect from a Cassandra cluster.")

    def __is_active(self):
        return self.__session and not self.__session.is_shutdown


class CassandraLocalhostConnection(CassandraConnection):
    """
    A connection to the localhost Cassandra server.
    """

    def __init__(self, user):
        super(CassandraLocalhostConnection, self).__init__(None, user)
