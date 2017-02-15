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
from cassandra.policies import ConstantReconnectionPolicy
from oslo_log import log as logging
from oslo_utils import netutils

from trove.common import cfg
from trove.common.db.cassandra import models
from trove.common import exception
from trove.common.i18n import _
from trove.common import instance as rd_instance
from trove.common.stream_codecs import IniCodec
from trove.common.stream_codecs import PropertiesCodec
from trove.common.stream_codecs import SafeYamlCodec
from trove.common.stream_codecs import XmlCodec
from trove.common import utils
from trove.guestagent.common.configuration import ConfigurationManager
from trove.guestagent.common.configuration import OneFileOverrideStrategy
from trove.guestagent.common import guestagent_utils
from trove.guestagent.common import operating_system
from trove.guestagent.common.operating_system import FileMode
from trove.guestagent.datastore import service
from trove.guestagent import pkg


LOG = logging.getLogger(__name__)
CONF = cfg.CONF

packager = pkg.Package()


class CassandraApp(object):
    """Prepares DBaaS on a Guest container."""

    _ADMIN_USER = 'os_admin'

    _CONF_AUTH_SEC = 'authentication'
    _CONF_USR_KEY = 'username'
    _CONF_PWD_KEY = 'password'
    _CONF_DIR_MODS = stat.S_IRWXU
    _CONF_FILE_MODS = stat.S_IRUSR

    CASSANDRA_CONF_FILE = "cassandra.yaml"
    CASSANDRA_TOPOLOGY_FILE = 'cassandra-rackdc.properties'
    CASSANDRA_LOGBACK_FILE = "logback.xml"

    _TOPOLOGY_CODEC = PropertiesCodec(
        delimiter='=', unpack_singletons=True, string_mappings={
            'true': True, 'false': False})

    CASSANDRA_KILL_CMD = "sudo killall java  || true"

    def __init__(self):
        self.state_change_wait_time = CONF.state_change_wait_time
        self.status = CassandraAppStatus(self.get_current_superuser())

        revision_dir = guestagent_utils.build_file_path(
            os.path.dirname(self.cassandra_conf),
            ConfigurationManager.DEFAULT_STRATEGY_OVERRIDES_SUB_DIR)
        self.configuration_manager = ConfigurationManager(
            self.cassandra_conf,
            self.cassandra_owner, self.cassandra_owner,
            SafeYamlCodec(default_flow_style=False), requires_root=True,
            override_strategy=OneFileOverrideStrategy(revision_dir))

        lb_revision_dir = guestagent_utils.build_file_path(
            os.path.dirname(self.cassandra_logback), 'logback-overrides')
        self.logback_conf_manager = ConfigurationManager(
            self.cassandra_logback,
            self.cassandra_owner, self.cassandra_owner,
            XmlCodec(), requires_root=True,
            override_strategy=OneFileOverrideStrategy(lb_revision_dir))

    @property
    def service_candidates(self):
        return ['cassandra']

    @property
    def cassandra_conf_dir(self):
        return {
            operating_system.REDHAT: "/etc/cassandra/default.conf/",
            operating_system.DEBIAN: "/etc/cassandra/",
            operating_system.SUSE: "/etc/cassandra/default.conf/"
        }[operating_system.get_os()]

    @property
    def cassandra_conf(self):
        return guestagent_utils.build_file_path(self.cassandra_conf_dir,
                                                self.CASSANDRA_CONF_FILE)

    @property
    def cassandra_topology(self):
        return guestagent_utils.build_file_path(self.cassandra_conf_dir,
                                                self.CASSANDRA_TOPOLOGY_FILE)

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
    def cassandra_system_log_file(self):
        return guestagent_utils.build_file_path(
            self.cassandra_log_dir, 'system', 'log')

    @property
    def cassandra_log_dir(self):
        return "/var/log/cassandra"

    @property
    def cassandra_logback(self):
        return guestagent_utils.build_file_path(self.cassandra_conf_dir,
                                                self.CASSANDRA_LOGBACK_FILE)

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

    def build_admin(self):
        return CassandraAdmin(self.get_current_superuser())

    def install_if_needed(self, packages):
        """Prepare the guest machine with a Cassandra server installation."""
        LOG.info(_("Preparing Guest as a Cassandra Server"))
        if not packager.pkg_is_installed(packages):
            self._install_db(packages)
        LOG.debug("Cassandra install_if_needed complete")

    def init_storage_structure(self, mount_point):
        try:
            operating_system.create_directory(mount_point, as_root=True)
        except exception.ProcessExecutionError:
            LOG.exception(_("Error while initiating storage structure."))

    def start_db(self, update_db=False, enable_on_boot=True):
        self.status.start_db_service(
            self.service_candidates, self.state_change_wait_time,
            enable_on_boot=enable_on_boot, update_db=update_db)

    def stop_db(self, update_db=False, do_not_start_on_reboot=False):
        self.status.stop_db_service(
            self.service_candidates, self.state_change_wait_time,
            disable_on_boot=do_not_start_on_reboot, update_db=update_db)

    def restart(self):
        self.status.restart_db_service(
            self.service_candidates, self.state_change_wait_time)

    def _install_db(self, packages):
        """Install Cassandra server"""
        LOG.debug("Installing Cassandra server.")
        packager.pkg_install(packages, None, 10000)
        LOG.debug("Finished installing Cassandra server")

    def _remove_system_tables(self):
        """
        Clean up the system keyspace.

        System tables are initialized on the first boot.
        They store certain properties, such as 'cluster_name',
        that cannot be easily changed once afterwards.
        The system keyspace needs to be cleaned up first. The
        tables will be regenerated on the next startup.
        Make sure to also cleanup the commitlog and caches to avoid
        startup errors due to inconsistencies.

        The service should not be running at this point.
        """
        if self.status.is_running:
            raise RuntimeError(_("Cannot remove system tables. "
                                 "The service is still running."))

        LOG.info(_('Removing existing system tables.'))
        system_keyspace_dir = guestagent_utils.build_file_path(
            self.cassandra_data_dir, 'system')
        commitlog_file = guestagent_utils.build_file_path(
            self.cassandra_working_dir, 'commitlog')
        chaches_dir = guestagent_utils.build_file_path(
            self.cassandra_working_dir, 'saved_caches')

        operating_system.remove(system_keyspace_dir,
                                force=True, recursive=True, as_root=True)
        operating_system.remove(commitlog_file,
                                force=True, recursive=True, as_root=True)
        operating_system.remove(chaches_dir,
                                force=True, recursive=True, as_root=True)

        operating_system.create_directory(
            system_keyspace_dir,
            user=self.cassandra_owner, group=self.cassandra_owner,
            force=True, as_root=True)
        operating_system.create_directory(
            commitlog_file,
            user=self.cassandra_owner, group=self.cassandra_owner,
            force=True, as_root=True)
        operating_system.create_directory(
            chaches_dir,
            user=self.cassandra_owner, group=self.cassandra_owner,
            force=True, as_root=True)

    def _apply_post_restore_updates(self, backup_info):
        """The service should not be running at this point.

        The restored database files carry some properties over from the
        original instance that need to be updated with appropriate
        values for the new instance.
        These include:

            - Reset the 'cluster_name' property to match the new unique
              ID of this instance.
              This is to ensure that the restored instance is a part of a new
              single-node cluster rather than forming a one with the
              original node.
            - Reset the administrator's password.
              The original password from the parent instance may be
              compromised or long lost.

        A general procedure is:
            - update the configuration property with the current value
              so that the service can start up
            - reset the superuser password
            - restart the service
            - change the cluster name
            - restart the service

        :seealso: _reset_admin_password
        :seealso: change_cluster_name
        """

        if self.status.is_running:
            raise RuntimeError(_("Cannot reset the cluster name. "
                                 "The service is still running."))

        LOG.debug("Applying post-restore updates to the database.")

        try:
            # Change the 'cluster_name' property to the current in-database
            # value so that the database can start up.
            self._update_cluster_name_property(backup_info['instance_id'])

            # Reset the superuser password so that we can log-in.
            self._reset_admin_password()

            # Start the database and update the 'cluster_name' to the
            # new value.
            self.start_db(update_db=False)
            self.change_cluster_name(CONF.guest_id)
        finally:
            self.stop_db()  # Always restore the initial state of the service.

    def cluster_secure(self, password):
        return self.secure(password=password).serialize()

    def secure(self, update_user=None, password=None):
        """Configure the Trove administrative user.
        Update an existing user if given.
        Create a new one using the default database credentials
        otherwise and drop the built-in user when finished.
        """
        LOG.info(_('Configuring Trove superuser.'))

        if password is None:
            password = utils.generate_random_password()

        admin_username = update_user.name if update_user else self._ADMIN_USER
        os_admin = models.CassandraUser(admin_username, password)

        if update_user:
            CassandraAdmin(update_user).alter_user_password(os_admin)
        else:
            cassandra = models.CassandraUser(
                models.CassandraUser.root_username,
                self.default_superuser_password)
            CassandraAdmin(cassandra)._create_superuser(os_admin)
            CassandraAdmin(os_admin).drop_user(cassandra)

        self._update_admin_credentials(os_admin)

        return os_admin

    def _update_admin_credentials(self, user):
        self.__create_cqlsh_config({self._CONF_AUTH_SEC:
                                    {self._CONF_USR_KEY: user.name,
                                     self._CONF_PWD_KEY: user.password}})

        # Update the internal status with the new user.
        self.status = CassandraAppStatus(user)

    def store_admin_credentials(self, admin_credentials):
        user = models.CassandraUser.deserialize(admin_credentials)
        self._update_admin_credentials(user)

    def get_admin_credentials(self):
        return self.get_current_superuser().serialize()

    def _reset_admin_password(self):
        """
        Reset the password of the Trove's administrative superuser.

        The service should not be running at this point.

        A general password reset procedure is:
            - disable user authentication and remote access
            - restart the service
            - update the password in the 'system_auth.credentials' table
            - re-enable authentication and make the host reachable
            - restart the service
        """
        if self.status.is_running:
            raise RuntimeError(_("Cannot reset the administrative password. "
                                 "The service is still running."))

        try:
            # Disable automatic startup in case the node goes down before
            # we have the superuser secured.
            operating_system.disable_service_on_boot(self.service_candidates)

            self.__disable_remote_access()
            self.__disable_authentication()

            # We now start up the service and immediately re-enable
            # authentication in the configuration file (takes effect after
            # restart).
            # Then we reset the superuser password to its default value
            # and restart the service to get user functions back.
            self.start_db(update_db=False, enable_on_boot=False)
            self.__enable_authentication()
            os_admin = self.__reset_user_password_to_default(self._ADMIN_USER)
            self.status = CassandraAppStatus(os_admin)
            self.restart()

            # Now change the administrative password to a new secret value.
            self.secure(update_user=os_admin)
        finally:
            self.stop_db()  # Always restore the initial state of the service.

        # At this point, we should have a secured database with new Trove-only
        # superuser password.
        # Proceed to re-enable remote access and automatic startup.
        self.__enable_remote_access()
        operating_system.enable_service_on_boot(self.service_candidates)

    def __reset_user_password_to_default(self, username):
        LOG.debug("Resetting the password of user '%(user)s' to '%(pw)s'.",
                  {'user': username, 'pw': self.default_superuser_password})

        user = models.CassandraUser(username, self.default_superuser_password)
        with CassandraLocalhostConnection(user) as client:
            client.execute(
                "UPDATE system_auth.credentials SET salted_hash=%s "
                "WHERE username='{}';", (user.name,),
                (self.default_superuser_pwd_hash,))

            return user

    def change_cluster_name(self, cluster_name):
        """Change the 'cluster_name' property of an exesting running instance.
        Cluster name is stored in the database and is required to match the
        configuration value. Cassandra fails to start otherwise.
        """

        if not self.status.is_running:
            raise RuntimeError(_("Cannot change the cluster name. "
                                 "The service is not running."))

        LOG.debug("Changing the cluster name to '%s'.", cluster_name)

        # Update the in-database value.
        self.__reset_cluster_name(cluster_name)

        # Update the configuration property.
        self._update_cluster_name_property(cluster_name)

        self.restart()

    def __reset_cluster_name(self, cluster_name):
        # Reset the in-database value stored locally on this node.
        current_superuser = self.get_current_superuser()
        with CassandraLocalhostConnection(current_superuser) as client:
            client.execute(
                "UPDATE system.local SET cluster_name = '{}' "
                "WHERE key='local';", (cluster_name,))

        # Newer version of Cassandra require a flush to ensure the changes
        # to the local system keyspace persist.
        self.flush_tables('system', 'local')

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

        LOG.warning(
            _("Trove administrative user has not been configured yet. "
              "Using the built-in default: %s"),
            models.CassandraUser.root_username)
        return models.CassandraUser(models.CassandraUser.root_username,
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

    def apply_initial_guestagent_configuration(self, cluster_name=None):
        """Update guestagent-controlled configuration properties.
        These changes to the default template are necessary in order to make
        the database service bootable and accessible in the guestagent context.

        :param cluster_name:  The 'cluster_name' configuration property.
                              Use the unique guest id by default.
        :type cluster_name:   string
        """
        self.configuration_manager.apply_system_override(
            {'data_file_directories': [self.cassandra_data_dir]})
        self._make_host_reachable()
        self._update_cluster_name_property(cluster_name or CONF.guest_id)
        # A single-node instance may use the SimpleSnitch
        # (keyspaces use SimpleStrategy).
        # A network-aware snitch has to be used otherwise.
        if cluster_name is None:
            updates = {'endpoint_snitch': 'SimpleSnitch'}
        else:
            updates = {'endpoint_snitch': 'GossipingPropertyFileSnitch'}
        self.configuration_manager.apply_system_override(updates)

    def _make_host_reachable(self):
        """
        Some of these settings may be overridden by user defined
        configuration groups.

        authenticator and authorizer
            - Necessary to enable users and permissions.
        rpc_address - Enable remote connections on all interfaces.
        broadcast_rpc_address - RPC address to broadcast to drivers and
                                other clients. Must be set if
                                rpc_address = 0.0.0.0 and can never be
                                0.0.0.0 itself.
        listen_address - The address on which the node communicates with
                         other nodes. Can never be 0.0.0.0.
        seed_provider - A list of discovery contact points.
        """
        self.__enable_authentication()
        self.__enable_remote_access()

    def __enable_remote_access(self):
        updates = {
            'rpc_address': "0.0.0.0",
            'broadcast_rpc_address': netutils.get_my_ipv4(),
            'listen_address': netutils.get_my_ipv4(),
            'seed_provider': {'parameters':
                              [{'seeds': netutils.get_my_ipv4()}]
                              }
        }

        self.configuration_manager.apply_system_override(updates)

    def __disable_remote_access(self):
        updates = {
            'rpc_address': "127.0.0.1",
            'listen_address': '127.0.0.1',
            'seed_provider': {'parameters':
                              [{'seeds': '127.0.0.1'}]
                              }
        }

        self.configuration_manager.apply_system_override(updates)

    def __enable_authentication(self):
        updates = {
            'authenticator': 'org.apache.cassandra.auth.PasswordAuthenticator',
            'authorizer': 'org.apache.cassandra.auth.CassandraAuthorizer'
        }

        self.configuration_manager.apply_system_override(updates)

    def __disable_authentication(self):
        updates = {
            'authenticator': 'org.apache.cassandra.auth.AllowAllAuthenticator',
            'authorizer': 'org.apache.cassandra.auth.AllowAllAuthorizer'
        }

        self.configuration_manager.apply_system_override(updates)

    def _update_cluster_name_property(self, name):
        """This 'cluster_name' property prevents nodes from one
        logical cluster from talking to another.
        All nodes in a cluster must have the same value.
        """
        self.configuration_manager.apply_system_override({'cluster_name':
                                                          name})

    def update_overrides(self, context, overrides, remove=False):
        if overrides:
            self.configuration_manager.apply_user_override(overrides)

    def remove_overrides(self):
        self.configuration_manager.remove_user_override()

    def write_cluster_topology(self, data_center, rack, prefer_local=True):
        LOG.info(_('Saving Cassandra cluster topology configuration.'))

        config = {'dc': data_center,
                  'rack': rack,
                  'prefer_local': prefer_local}

        operating_system.write_file(self.cassandra_topology, config,
                                    codec=self._TOPOLOGY_CODEC, as_root=True)
        operating_system.chown(
            self.cassandra_topology,
            self.cassandra_owner, self.cassandra_owner, as_root=True)
        operating_system.chmod(
            self.cassandra_topology, FileMode.ADD_READ_ALL, as_root=True)

    def start_db_with_conf_changes(self, config_contents):
        LOG.debug("Starting database with configuration changes.")
        if self.status.is_running:
            raise RuntimeError(_("The service is still running."))

        self.configuration_manager.save_configuration(config_contents)
        # The configuration template has to be updated with
        # guestagent-controlled settings.
        self.apply_initial_guestagent_configuration()
        self.start_db(True)

    def reset_configuration(self, configuration):
        LOG.debug("Resetting configuration.")
        config_contents = configuration['config_contents']
        self.configuration_manager.save_configuration(config_contents)

    def _get_cqlsh_conf_path(self):
        return os.path.expanduser(self.cqlsh_conf_path)

    def get_data_center(self):
        config = operating_system.read_file(self.cassandra_topology,
                                            codec=self._TOPOLOGY_CODEC)
        return config['dc']

    def get_rack(self):
        config = operating_system.read_file(self.cassandra_topology,
                                            codec=self._TOPOLOGY_CODEC)
        return config['rack']

    def set_seeds(self, seeds):
        LOG.debug("Setting seed nodes: %s", seeds)
        updates = {
            'seed_provider': {'parameters':
                              [{'seeds': ','.join(seeds)}]
                              }
        }

        self.configuration_manager.apply_system_override(updates)

    def get_seeds(self):
        """Return a list of seed node IPs if any.

        The seed IPs are stored as a comma-separated string in the
        seed-provider parameters:
        [{'class_name': '<name>', 'parameters': [{'seeds': '<ip>,<ip>'}, ...]}]
        """

        def find_first(key, dict_list):
            for item in dict_list:
                if key in item:
                    return item[key]
            return []

        sp_property = self.configuration_manager.get_value('seed_provider', [])
        seeds_str = find_first('seeds', find_first('parameters', sp_property))
        return seeds_str.split(',') if seeds_str else []

    def set_auto_bootstrap(self, enabled):
        """Auto-bootstrap makes new (non-seed) nodes automatically migrate the
        right data to themselves.
        The feature has to be turned OFF when initializing a fresh cluster
        without data.
        It must be turned back ON once the cluster is initialized.
        """
        LOG.debug("Setting auto-bootstrapping: %s", enabled)
        updates = {'auto_bootstrap': enabled}
        self.configuration_manager.apply_system_override(updates)

    def node_cleanup_begin(self):
        """Suspend periodic status updates and mark the instance busy
        throughout the operation.
        """
        self.status.begin_restart()
        self.status.set_status(rd_instance.ServiceStatuses.BLOCKED)

    def node_cleanup(self):
        """Cassandra does not automatically remove data from nodes that
        lose part of their partition range to a newly added node.
        Cleans up keyspaces and partition keys no longer belonging to the node.

        Do not treat cleanup failures as fatal. Resume the heartbeat after
        finishing and let it signal the true state of the instance to the
        caller.
        """
        LOG.debug("Running node cleanup.")
        # nodetool -h <HOST> -p <PORT> -u <USER> -pw <PASSWORD> cleanup
        try:
            self._run_nodetool_command('cleanup')
            self.status.set_status(rd_instance.ServiceStatuses.RUNNING)
        except Exception:
            LOG.exception(_("The node failed to complete its cleanup."))
        finally:
            self.status.end_restart()

    def node_decommission(self):
        """Causes a live node to decommission itself,
        streaming its data to the next node on the ring.

        Shutdown the database after successfully finishing the operation,
        or leave the node in a failed state otherwise.

        Suspend periodic status updates, so that the caller can poll for the
        database shutdown.
        """
        LOG.debug("Decommissioning the node.")
        # nodetool -h <HOST> -p <PORT> -u <USER> -pw <PASSWORD> decommission
        self.status.begin_restart()
        try:
            self._run_nodetool_command('decommission')
        except Exception:
            LOG.exception(_("The node failed to decommission itself."))
            self.status.set_status(rd_instance.ServiceStatuses.FAILED)
            return
        finally:
            # Cassandra connections have ability to automatically discover and
            # fallback to other cluster nodes whenever a node goes down.
            # Reset the status after decomissioning to ensure the heartbeat
            # connection talks to this node only.
            self.status = CassandraAppStatus(self.get_current_superuser())

        try:
            self.stop_db(update_db=True, do_not_start_on_reboot=True)
        finally:
            self.status.end_restart()

    def flush_tables(self, keyspace, *tables):
        """Flushes one or more tables from the memtable.
        """
        LOG.debug("Flushing tables.")
        # nodetool -h <HOST> -p <PORT> -u <USER> -pw <PASSWORD> flush --
        # <keyspace> ( <table> ... )
        self._run_nodetool_command('flush', keyspace, *tables)

    def set_logging_level(self, log_level):
        """Set the log Cassandra's system log verbosity level.
        """
        # Apply the change at runtime.
        self._run_nodetool_command('setlogginglevel', 'root', log_level)

        # Persist the change.
        self.logback_conf_manager.apply_system_override(
            {'configuration': {'root': {'@level': log_level}}})

    def _run_nodetool_command(self, cmd, *args, **kwargs):
        """Execute a nodetool command on this node.
        """
        return utils.execute('nodetool', '-h', 'localhost',
                             cmd, *args, **kwargs)

    def enable_root(self, root_password=None):
        """Cassandra's 'root' user is called 'cassandra'.
        Create a new superuser if it does not exist and grant it full
        superuser-level access to all keyspaces.
        """
        cassandra = models.CassandraUser.root(password=root_password)
        admin = self.build_admin()
        if self.is_root_enabled():
            admin.alter_user_password(cassandra)
        else:
            admin._create_superuser(cassandra)

        return cassandra.serialize()

    def is_root_enabled(self):
        """The Trove administrative user ('os_admin') should normally be the
        only superuser in the system.
        """
        found = self.build_admin().list_superusers()
        return len([user for user in found
                    if user.name != self._ADMIN_USER]) > 0


class CassandraAppStatus(service.BaseDbStatus):

    def __init__(self, superuser):
        """
        :param superuser:        User account the Status uses for connecting
                                 to the database.
        :type superuser:         CassandraUser
        """
        super(CassandraAppStatus, self).__init__()
        self.__user = superuser
        self.__client = None

    @property
    def client(self):
        if self.__client is None:
            self.__client = CassandraLocalhostConnection(self.__user)
        return self.__client

    def _get_actual_db_status(self):
        try:
            self.client.execute('SELECT now() FROM system.local;')
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
        self.__client = None

    @property
    def client(self):
        if self.__client is None:
            self.__client = CassandraLocalhostConnection(self.__admin_user)
        return self.__client

    def create_user(self, context, users):
        """
        Create new non-superuser accounts.
        New users are by default granted full access to all database resources.
        """
        for item in users:
            self._create_user_and_grant(self.client,
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
        LOG.debug("Creating a new user '%s'.", user.name)
        client.execute("CREATE USER '{}' WITH PASSWORD %s NOSUPERUSER;",
                       (user.name,), (user.password,))

    def _create_superuser(self, user):
        """Create a new superuser account and grant it full superuser-level
        access to all keyspaces.
        """
        LOG.debug("Creating a new superuser '%s'.", user.name)
        self.client.execute("CREATE USER '{}' WITH PASSWORD %s SUPERUSER;",
                            (user.name,), (user.password,))
        self.client.execute(
            "GRANT ALL PERMISSIONS ON ALL KEYSPACES TO '{}';", (user.name,))

    def delete_user(self, context, user):
        self.drop_user(self._deserialize_user(user))

    def drop_user(self, user):
        self._drop_user(self.client, user)

    def _drop_user(self, client, user):
        LOG.debug("Deleting user '%s'.", user.name)
        client.execute("DROP USER '{}';", (user.name, ))

    def get_user(self, context, username, hostname):
        user = self._find_user(self.client, username)
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
        return guestagent_utils.serialize_list(
            self._get_listed_users(self.client),
            limit=limit, marker=marker, include_marker=include_marker)

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
            models.CassandraUser(username).check_reserved()

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
        return self._get_users(self.client, lambda user: user.super)

    def grant_access(self, context, username, hostname, databases):
        """
        Grant full access on keyspaces to a given username.
        """
        user = models.CassandraUser(username)
        for db in databases:
            self._grant_full_access_on_keyspace(
                self.client, models.CassandraSchema(db), user)

    def revoke_access(self, context, username, hostname, database):
        """
        Revoke all permissions on any database resources from a given username.
        """
        user = models.CassandraUser(username)
        self._revoke_all_access_on_keyspace(
            self.client, models.CassandraSchema(database), user)

    def _grant_full_access_on_keyspace(self, client, keyspace, user,
                                       check_reserved=True):
        """
        Grant all non-superuser permissions on a keyspace to a given user.
        """
        if check_reserved:
            user.check_reserved()
            keyspace.check_reserved()

        for access in self.__NO_SUPERUSER_MODIFIERS:
            self._grant_permission_on_keyspace(client, access, keyspace, user)

    def _grant_permission_on_keyspace(self, client, modifier, keyspace, user):
        """
        Grant a non-superuser permission on a keyspace to a given user.
        Raise an exception if the caller attempts to grant a superuser access.
        """
        LOG.debug("Granting '%(mod)s' access on '%(keyspace_name)s' to "
                  "user '%(user)s'.",
                  {'mod': modifier, 'keyspace_name': keyspace.name,
                   'user': user.name})
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
            user.check_reserved()
            keyspace.check_reserved()

        LOG.debug("Revoking all permissions on '%(keyspace_name)s' "
                  "from user '%(user)s'.", {'keyspace_name': keyspace.name,
                                            'user': user.name})
        client.execute("REVOKE ALL PERMISSIONS ON KEYSPACE \"{}\" FROM '{}';",
                       (keyspace.name, user.name))

    def update_attributes(self, context, username, hostname, user_attrs):
        user = self._load_user(self.client, username)
        new_name = user_attrs.get('name')
        new_password = user_attrs.get('password')
        self._update_user(self.client, user, new_name, new_password)

    def _update_user(self, client, user, new_username, new_password):
        """
        Update a user of a given username.
        Updatable attributes include username and password.
        If a new username and password are given a new user with those
        attributes is created and all permissions from the original
        user get transferred to it. The original user is then dropped
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
        LOG.debug("Renaming user '%(old)s' to '%(new)s'",
                  {'old': user.name, 'new': new_username})
        new_user = models.CassandraUser(new_username, new_password)
        new_user.databases.extend(user.databases)
        self._create_user_and_grant(client, new_user)
        self._drop_user(client, user)

    def alter_user_password(self, user):
        self._alter_user_password(self.client, user)

    def change_passwords(self, context, users):
        for user in users:
            self._alter_user_password(self.client,
                                      self._deserialize_user(user))

    def _alter_user_password(self, client, user):
        LOG.debug("Changing password of user '%s'.", user.name)
        client.execute("ALTER USER '{}' "
                       "WITH PASSWORD %s;", (user.name,), (user.password,))

    def create_database(self, context, databases):
        for item in databases:
            self._create_single_node_keyspace(
                self.client, self._deserialize_keyspace(item))

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
        self._drop_keyspace(self.client,
                            self._deserialize_keyspace(database))

    def _drop_keyspace(self, client, keyspace):
        LOG.debug("Dropping keyspace '%s'.", keyspace.name)
        client.execute("DROP KEYSPACE \"{}\";", (keyspace.name,))

    def list_databases(self, context, limit=None, marker=None,
                       include_marker=False):
        return guestagent_utils.serialize_list(
            self._get_available_keyspaces(self.client),
            limit=limit, marker=marker, include_marker=include_marker)

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
        user = self._find_user(self.client, username)
        if user:
            return user.databases

        raise exception.UserNotFound(username)

    def _deserialize_keyspace(self, keyspace_dict, check_reserved=True):
        if keyspace_dict:
            db = models.CassandraSchema.deserialize(keyspace_dict)
            if check_reserved:
                db.check_reserved()

            return db

        return None

    def _deserialize_user(self, user_dict, check_reserved=True):
        if user_dict:
            user = models.CassandraUser.deserialize(user_dict)
            if check_reserved:
                user.check_reserved()

            return user

        return None

    @property
    def ignore_users(self):
        return cfg.get_ignored_users()

    @property
    def ignore_dbs(self):
        return cfg.get_ignored_dbs()


class CassandraConnection(object):
    """A wrapper to manage a Cassandra connection."""

    # Cassandra 2.1 only supports protocol versions 3 and lower.
    NATIVE_PROTOCOL_VERSION = 3
    CONNECTION_TIMEOUT_SEC = CONF.agent_call_high_timeout
    RECONNECT_DELAY_SEC = 3

    def __init__(self, contact_points, user):
        self.__user = user
        # A Cluster is initialized with a set of initial contact points.
        # After the driver connects to one of the nodes it will automatically
        # discover the rest.
        # Will connect to '127.0.0.1' if None contact points are given.
        #
        # Set the 'reconnection_policy' so that dead connections recover fast.
        self._cluster = Cluster(
            contact_points=contact_points,
            auth_provider=PlainTextAuthProvider(user.name, user.password),
            protocol_version=self.NATIVE_PROTOCOL_VERSION,
            connect_timeout=self.CONNECTION_TIMEOUT_SEC,
            control_connection_timeout=self.CONNECTION_TIMEOUT_SEC,
            reconnection_policy=ConstantReconnectionPolicy(
                self.RECONNECT_DELAY_SEC, max_attempts=None))
        self.__session = None

        self._connect()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self._disconnect()

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
        if self.is_active():
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

    def _connect(self):
        if not self._cluster.is_shutdown:
            LOG.debug("Connecting to a Cassandra cluster as '%s'.",
                      self.__user.name)
            if not self.is_active():
                self.__session = self._cluster.connect()
            else:
                LOG.debug("Connection already open.")
            LOG.debug("Connected to cluster: '%s'",
                      self._cluster.metadata.cluster_name)
            for host in self._cluster.metadata.all_hosts():
                LOG.debug("Connected to node: '%(address)s' in rack "
                          "'%(rack)s' at datacenter '%(datacenter)s'",
                          {'address': host.address, 'rack': host.rack,
                           'datacenter': host.datacenter})
        else:
            LOG.debug("Cannot perform this operation on a terminated cluster.")
            raise exception.UnprocessableEntity()

    def _disconnect(self):
        if self.is_active():
            try:
                LOG.debug("Disconnecting from cluster: '%s'",
                          self._cluster.metadata.cluster_name)
                self._cluster.shutdown()
            except Exception:
                LOG.debug("Failed to disconnect from a Cassandra cluster.")

    def is_active(self):
        return self.__session and not self.__session.is_shutdown

    def __del__(self):
        # The connections would survive the parent object's GC.
        # We need to close it explicitly.
        self._disconnect()


class CassandraLocalhostConnection(CassandraConnection):
    """
    A connection to the localhost Cassandra server.
    """

    def __init__(self, user):
        super(CassandraLocalhostConnection, self).__init__(None, user)
