# Copyright [2015] Hewlett-Packard Development Company, L.P.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import subprocess
import tempfile

from oslo_log import log as logging
from oslo_utils import netutils
from six.moves import configparser

from trove.common import cfg
from trove.common.db import models
from trove.common import exception
from trove.common.i18n import _
from trove.common.i18n import _LI
from trove.common import instance as rd_instance
from trove.common.stream_codecs import PropertiesCodec
from trove.common import utils as utils
from trove.guestagent.common.configuration import ConfigurationManager
from trove.guestagent.common.configuration import ImportOverrideStrategy
from trove.guestagent.common import guestagent_utils
from trove.guestagent.common import operating_system
from trove.guestagent.common.operating_system import FileMode
from trove.guestagent.datastore.experimental.vertica import system
from trove.guestagent.datastore import service
from trove.guestagent import pkg
from trove.guestagent import volume

LOG = logging.getLogger(__name__)
CONF = cfg.CONF
packager = pkg.Package()
DB_NAME = 'db_srvr'
MOUNT_POINT = CONF.vertica.mount_point
# We will use a fake configuration file for the options managed through
# configuration groups that we apply directly with ALTER DB ... SET ...
FAKE_CFG = os.path.join(MOUNT_POINT, "vertica.cfg.fake")


class VerticaAppStatus(service.BaseDbStatus):

    def _get_actual_db_status(self):
        """Get the status of dbaas and report it back."""
        try:
            out, err = system.shell_execute(system.STATUS_ACTIVE_DB,
                                            system.VERTICA_ADMIN)
            if out.strip() == DB_NAME:
                # UP status is confirmed
                LOG.info(_("Service Status is RUNNING."))
                return rd_instance.ServiceStatuses.RUNNING
            else:
                LOG.info(_("Service Status is SHUTDOWN."))
                return rd_instance.ServiceStatuses.SHUTDOWN
        except exception.ProcessExecutionError:
            LOG.exception(_("Failed to get database status."))
            return rd_instance.ServiceStatuses.CRASHED


class VerticaApp(object):
    """Prepares DBaaS on a Guest container."""

    def __init__(self, status):
        self.state_change_wait_time = CONF.state_change_wait_time
        self.status = status
        revision_dir = \
            guestagent_utils.build_file_path(
                os.path.join(MOUNT_POINT,
                             os.path.dirname(system.VERTICA_ADMIN)),
                ConfigurationManager.DEFAULT_STRATEGY_OVERRIDES_SUB_DIR)

        if not operating_system.exists(FAKE_CFG):
            operating_system.write_file(FAKE_CFG, '', as_root=True)
            operating_system.chown(FAKE_CFG, system.VERTICA_ADMIN,
                                   system.VERTICA_ADMIN_GRP, as_root=True)
            operating_system.chmod(FAKE_CFG, FileMode.ADD_GRP_RX_OTH_RX(),
                                   as_root=True)
        self.configuration_manager = \
            ConfigurationManager(FAKE_CFG, system.VERTICA_ADMIN,
                                 system.VERTICA_ADMIN_GRP,
                                 PropertiesCodec(delimiter='='),
                                 requires_root=True,
                                 override_strategy=ImportOverrideStrategy(
                                     revision_dir, "cnf"))

    def update_overrides(self, context, overrides, remove=False):
        if overrides:
            self.apply_overrides(overrides)

    def remove_overrides(self):
        config = self.configuration_manager.get_user_override()
        self._reset_config(config)
        self.configuration_manager.remove_user_override()

    def apply_overrides(self, overrides):
        self.configuration_manager.apply_user_override(overrides)
        self._apply_config(overrides)

    def _reset_config(self, config):
        try:
            db_password = self._get_database_password()
            for k, v in config.iteritems():
                alter_db_cmd = system.ALTER_DB_RESET_CFG % (DB_NAME, str(k))
                out, err = system.exec_vsql_command(db_password, alter_db_cmd)
                if err:
                    if err.is_warning():
                        LOG.warning(err)
                    else:
                        LOG.error(err)
                        raise RuntimeError(_("Failed to remove config %s") % k)

        except Exception:
            LOG.exception(_("Vertica configuration remove failed."))
            raise RuntimeError(_("Vertica configuration remove failed."))
        LOG.info(_("Vertica configuration reset completed."))

    def _apply_config(self, config):
        try:
            db_password = self._get_database_password()
            for k, v in config.iteritems():
                alter_db_cmd = system.ALTER_DB_CFG % (DB_NAME, str(k), str(v))
                out, err = system.exec_vsql_command(db_password, alter_db_cmd)
                if err:
                    if err.is_warning():
                        LOG.warning(err)
                    else:
                        LOG.error(err)
                        raise RuntimeError(_("Failed to apply config %s") % k)

        except Exception:
            LOG.exception(_("Vertica configuration apply failed"))
            raise RuntimeError(_("Vertica configuration apply failed"))
        LOG.info(_("Vertica config apply completed."))

    def _enable_db_on_boot(self):
        try:
            command = ["sudo", "su", "-", system.VERTICA_ADMIN, "-c",
                       (system.SET_RESTART_POLICY % (DB_NAME, "always"))]
            subprocess.Popen(command)
            command = ["sudo", "su", "-", "root", "-c",
                       (system.VERTICA_AGENT_SERVICE_COMMAND % "enable")]
            subprocess.Popen(command)
        except Exception:
            LOG.exception(_("Failed to enable database on boot."))
            raise RuntimeError(_("Could not enable database on boot."))

    def _disable_db_on_boot(self):
        try:
            command = (system.SET_RESTART_POLICY % (DB_NAME, "never"))
            system.shell_execute(command, system.VERTICA_ADMIN)
            command = (system.VERTICA_AGENT_SERVICE_COMMAND % "disable")
            system.shell_execute(command)
        except exception.ProcessExecutionError:
            LOG.exception(_("Failed to disable database on boot."))
            raise RuntimeError(_("Could not disable database on boot."))

    def stop_db(self, update_db=False, do_not_start_on_reboot=False):
        """Stop the database."""
        LOG.info(_("Stopping Vertica."))
        if do_not_start_on_reboot:
            self._disable_db_on_boot()

        try:
            # Stop vertica-agent service
            command = (system.VERTICA_AGENT_SERVICE_COMMAND % "stop")
            system.shell_execute(command)
            # Using Vertica adminTools to stop db.
            db_password = self._get_database_password()
            stop_db_command = (system.STOP_DB % (DB_NAME, db_password))
            out, err = system.shell_execute(system.STATUS_ACTIVE_DB,
                                            system.VERTICA_ADMIN)
            if out.strip() == DB_NAME:
                system.shell_execute(stop_db_command, system.VERTICA_ADMIN)
                if not self.status._is_restarting:
                    if not self.status.wait_for_real_status_to_change_to(
                            rd_instance.ServiceStatuses.SHUTDOWN,
                            self.state_change_wait_time, update_db):
                        LOG.error(_("Could not stop Vertica."))
                        self.status.end_restart()
                        raise RuntimeError(_("Could not stop Vertica!"))
                LOG.debug("Database stopped.")
            else:
                LOG.debug("Database is not running.")
        except exception.ProcessExecutionError:
            LOG.exception(_("Failed to stop database."))
            raise RuntimeError(_("Could not stop database."))

    def start_db(self, update_db=False):
        """Start the database."""
        LOG.info(_("Starting Vertica."))
        try:
            self._enable_db_on_boot()
            # Start vertica-agent service
            command = ["sudo", "su", "-", "root", "-c",
                       (system.VERTICA_AGENT_SERVICE_COMMAND % "start")]
            subprocess.Popen(command)
            # Using Vertica adminTools to start db.
            db_password = self._get_database_password()
            start_db_command = ["sudo", "su", "-", system.VERTICA_ADMIN, "-c",
                                (system.START_DB % (DB_NAME, db_password))]
            subprocess.Popen(start_db_command)
            if not self.status._is_restarting:
                self.status.end_restart()
            LOG.debug("Database started.")
        except Exception as e:
            raise RuntimeError(_("Could not start Vertica due to %s") % e)

    def start_db_with_conf_changes(self, config_contents):
        """
         Currently all that this method does is to start Vertica. This method
         needs to be implemented to enable volume resize on guestagent side.
        """
        LOG.info(_("Starting Vertica with configuration changes."))
        if self.status.is_running:
            format = 'Cannot start_db_with_conf_changes because status is %s.'
            LOG.debug(format, self.status)
            raise RuntimeError(format % self.status)
        LOG.info(_("Initiating config."))
        self.configuration_manager.save_configuration(config_contents)
        self.start_db(True)

    def restart(self):
        """Restart the database."""
        try:
            self.status.begin_restart()
            self.stop_db()
            self.start_db()
        finally:
            self.status.end_restart()

    def add_db_to_node(self, members=netutils.get_my_ipv4()):
        """Add db to host with admintools"""
        LOG.info(_("Calling admintools to add DB to host"))
        try:
            # Create db after install
            db_password = self._get_database_password()
            create_db_command = (system.ADD_DB_TO_NODE % (members,
                                                          DB_NAME,
                                                          db_password))
            system.shell_execute(create_db_command, "dbadmin")
        except exception.ProcessExecutionError:
            # Give vertica some time to get the node up, won't be available
            # by the time adminTools -t db_add_node completes
            LOG.info(_("adminTools failed as expected - wait for node"))
        self.wait_for_node_status()
        LOG.info(_("Vertica add db to host completed."))

    def remove_db_from_node(self, members=netutils.get_my_ipv4()):
        """Remove db from node with admintools"""
        LOG.info(_("Removing db from node"))
        try:
            # Create db after install
            db_password = self._get_database_password()
            create_db_command = (system.REMOVE_DB_FROM_NODE % (members,
                                                               DB_NAME,
                                                               db_password))
            system.shell_execute(create_db_command, "dbadmin")
        except exception.ProcessExecutionError:
            # Give vertica some time to get the node up, won't be available
            # by the time adminTools -t db_add_node completes
            LOG.info(_("adminTools failed as expected - wait for node"))

        # Give vertica some time to take the node down - it won't be available
        # by the time adminTools -t db_add_node completes
        self.wait_for_node_status()
        LOG.info(_("Vertica remove host from db completed."))

    def create_db(self, members=netutils.get_my_ipv4()):
        """Prepare the guest machine with a Vertica db creation."""
        LOG.info(_("Creating database on Vertica host."))
        try:
            # Create db after install
            db_password = self._get_database_password()
            create_db_command = (system.CREATE_DB % (members, DB_NAME,
                                                     MOUNT_POINT, MOUNT_POINT,
                                                     db_password))
            system.shell_execute(create_db_command, system.VERTICA_ADMIN)
        except Exception:
            LOG.exception(_("Vertica database create failed."))
            raise RuntimeError(_("Vertica database create failed."))
        LOG.info(_("Vertica database create completed."))

    def install_vertica(self, members=netutils.get_my_ipv4()):
        """Prepare the guest machine with a Vertica db creation."""
        LOG.info(_("Installing Vertica Server."))
        try:
            # Create db after install
            install_vertica_cmd = (system.INSTALL_VERTICA % (members,
                                                             MOUNT_POINT))
            system.shell_execute(install_vertica_cmd)
        except exception.ProcessExecutionError:
            LOG.exception(_("install_vertica failed."))
            raise RuntimeError(_("install_vertica failed."))
        self._generate_database_password()
        LOG.info(_("install_vertica completed."))

    def update_vertica(self, command, members=netutils.get_my_ipv4()):
        LOG.info(_("Calling update_vertica with command %s") % command)
        try:
            update_vertica_cmd = (system.UPDATE_VERTICA % (command, members,
                                                           MOUNT_POINT))
            system.shell_execute(update_vertica_cmd)
        except exception.ProcessExecutionError:
            LOG.exception(_("update_vertica failed."))
            raise RuntimeError(_("update_vertica failed."))
        # self._generate_database_password()
        LOG.info(_("update_vertica completed."))

    def add_udls(self):
        """Load the user defined load libraries into the database."""
        LOG.info(_("Adding configured user defined load libraries."))
        password = self._get_database_password()
        loaded_udls = []
        for lib in system.UDL_LIBS:
            func_name = lib['func_name']
            lib_name = lib['lib_name']
            language = lib['language']
            factory = lib['factory']
            path = lib['path']
            if os.path.isfile(path):
                LOG.debug("Adding the %s library as %s." %
                          (func_name, lib_name))
                out, err = system.exec_vsql_command(
                    password,
                    system.CREATE_LIBRARY % (lib_name, path)
                )
                if err:
                    if err.is_warning():
                        LOG.warning(err)
                    else:
                        LOG.error(err)
                        raise RuntimeError(_("Failed to create library %s.")
                                           % lib_name)
                out, err = system.exec_vsql_command(
                    password,
                    system.CREATE_SOURCE % (func_name, language,
                                            factory, lib_name)
                )
                if err:
                    if err.is_warning():
                        LOG.warning(err)
                    else:
                        LOG.error(err)
                        raise RuntimeError(_("Failed to create source %s.")
                                           % func_name)
                loaded_udls.append(func_name)
            else:
                LOG.warning(_("Skipping %(func)s as path %(path)s not "
                              "found.") % {"func": func_name, "path": path})
        LOG.info(_("The following UDL functions are available for use: %s")
                 % loaded_udls)

    def _generate_database_password(self):
        """Generate and write the password to vertica.cnf file."""
        config = configparser.ConfigParser()
        config.add_section('credentials')
        config.set('credentials', 'dbadmin_password',
                   utils.generate_random_password())
        self.write_config(config)

    def write_config(self, config,
                     unlink_function=os.unlink,
                     temp_function=tempfile.NamedTemporaryFile):
        """Write the configuration contents to vertica.cnf file."""
        LOG.debug('Defining config holder at %s.' % system.VERTICA_CONF)
        tempfile = temp_function('w', delete=False)
        try:
            config.write(tempfile)
            tempfile.close()
            command = (("install -o root -g root -m 644 %(source)s %(target)s"
                        ) % {'source': tempfile.name,
                             'target': system.VERTICA_CONF})
            system.shell_execute(command)
            unlink_function(tempfile.name)
        except Exception:
            unlink_function(tempfile.name)
            raise

    def read_config(self):
        """Reads and returns the Vertica config."""
        try:
            config = configparser.ConfigParser()
            config.read(system.VERTICA_CONF)
            return config
        except Exception:
            LOG.exception(_("Failed to read config %s.") % system.VERTICA_CONF)
            raise RuntimeError

    def _get_database_password(self):
        """Read the password from vertica.cnf file and return it."""
        return self.read_config().get('credentials', 'dbadmin_password')

    def install_if_needed(self, packages):
        """Install Vertica package if needed."""
        LOG.info(_("Preparing Guest as Vertica Server."))
        if not packager.pkg_is_installed(packages):
            LOG.debug("Installing Vertica Package.")
            packager.pkg_install(packages, None, system.INSTALL_TIMEOUT)

    def _set_readahead_for_disks(self):
        """This method sets readhead size for disks as needed by Vertica."""
        device = volume.VolumeDevice(CONF.device_path)
        device.set_readahead_size(CONF.vertica.readahead_size)
        LOG.debug("Set readhead size as required by Vertica.")

    def prepare_for_install_vertica(self):
        """This method executes preparatory methods before
        executing install_vertica.
        """
        command = ("VERT_DBA_USR=%s VERT_DBA_HOME=/home/dbadmin "
                   "VERT_DBA_GRP=%s /opt/vertica/oss/python/bin/python"
                   " -m vertica.local_coerce" %
                   (system.VERTICA_ADMIN, system.VERTICA_ADMIN_GRP))
        try:
            self._set_readahead_for_disks()
            system.shell_execute(command)
        except exception.ProcessExecutionError:
            LOG.exception(_("Failed to prepare for install_vertica."))
            raise

    def mark_design_ksafe(self, k):
        """Wrapper for mark_design_ksafe function for setting k-safety """
        LOG.info(_("Setting Vertica k-safety to %s") % str(k))
        out, err = system.exec_vsql_command(self._get_database_password(),
                                            system.MARK_DESIGN_KSAFE % k)
        # Only fail if we get an ERROR as opposed to a warning complaining
        # about setting k = 0
        if "ERROR" in err:
            LOG.error(err)
            raise RuntimeError(_("Failed to set k-safety level %s.") % k)

    def _create_user(self, username, password, role=None):
        """Creates a user, granting and enabling the given role for it."""
        LOG.info(_("Creating user in Vertica database."))
        out, err = system.exec_vsql_command(self._get_database_password(),
                                            system.CREATE_USER %
                                            (username, password))
        if err:
            if err.is_warning():
                LOG.warning(err)
            else:
                LOG.error(err)
                raise RuntimeError(_("Failed to create user %s.") % username)
        if role:
            self._grant_role(username, role)

    def _grant_role(self, username, role):
        """Grants a role to the user on the schema."""
        out, err = system.exec_vsql_command(self._get_database_password(),
                                            system.GRANT_TO_USER
                                            % (role, username))
        if err:
            if err.is_warning():
                LOG.warning(err)
            else:
                LOG.error(err)
                raise RuntimeError(_("Failed to grant role %(r)s to user "
                                     "%(u)s.")
                                   % {'r': role, 'u': username})
        out, err = system.exec_vsql_command(self._get_database_password(),
                                            system.ENABLE_FOR_USER
                                            % (username, role))
        if err:
            LOG.warning(err)

    def enable_root(self, root_password=None):
        """Resets the root password."""
        LOG.info(_LI("Enabling root."))
        user = models.DatastoreUser.root(password=root_password)
        if not self.is_root_enabled():
            self._create_user(user.name, user.password, 'pseudosuperuser')
        else:
            LOG.debug("Updating %s password." % user.name)
            try:
                out, err = system.exec_vsql_command(
                    self._get_database_password(),
                    system.ALTER_USER_PASSWORD % (user.name, user.password))
                if err:
                    if err.is_warning():
                        LOG.warning(err)
                    else:
                        LOG.error(err)
                        raise RuntimeError(_("Failed to update %s "
                                             "password.") % user.name)
            except exception.ProcessExecutionError:
                LOG.error(_("Failed to update %s password.") % user.name)
                raise RuntimeError(_("Failed to update %s password.")
                                   % user.name)
        return user.serialize()

    def is_root_enabled(self):
        """Return True if root access is enabled else False."""
        LOG.debug("Checking is root enabled.")
        try:
            out, err = system.shell_execute(system.USER_EXISTS %
                                            (self._get_database_password(),
                                             'root'), system.VERTICA_ADMIN)
            if err:
                LOG.error(err)
                raise RuntimeError(_("Failed to query for root user."))
        except exception.ProcessExecutionError:
            raise RuntimeError(_("Failed to query for root user."))
        return out.rstrip() == "1"

    def get_public_keys(self, user):
        """Generates key (if not found), and sends public key for user."""
        LOG.debug("Public keys requested for user: %s." % user)
        user_home_directory = os.path.expanduser('~' + user)
        public_key_file_name = user_home_directory + '/.ssh/id_rsa.pub'

        try:
            key_generate_command = (system.SSH_KEY_GEN % user_home_directory)
            system.shell_execute(key_generate_command, user)
        except exception.ProcessExecutionError:
            LOG.debug("Cannot generate key.")

        try:
            read_key_cmd = ("cat %(file)s" % {'file': public_key_file_name})
            out, err = system.shell_execute(read_key_cmd)
        except exception.ProcessExecutionError:
            LOG.exception(_("Cannot read public key."))
            raise
        return out.strip()

    def authorize_public_keys(self, user, public_keys):
        """Adds public key to authorized_keys for user."""
        LOG.debug("public keys to be added for user: %s." % (user))
        user_home_directory = os.path.expanduser('~' + user)
        authorized_file_name = user_home_directory + '/.ssh/authorized_keys'

        try:
            read_key_cmd = ("cat %(file)s" % {'file': authorized_file_name})
            out, err = system.shell_execute(read_key_cmd)
            public_keys.append(out.strip())
        except exception.ProcessExecutionError:
            LOG.debug("Cannot read authorized_keys.")
        all_keys = '\n'.join(public_keys) + "\n"

        try:
            with tempfile.NamedTemporaryFile("w", delete=False) as tempkeyfile:
                tempkeyfile.write(all_keys)
            copy_key_cmd = (("install -o %(user)s -m 600 %(source)s %(target)s"
                             ) % {'user': user, 'source': tempkeyfile.name,
                                  'target': authorized_file_name})
            system.shell_execute(copy_key_cmd)
            os.remove(tempkeyfile.name)
        except exception.ProcessExecutionError:
            LOG.exception(_("Cannot install public keys."))
            os.remove(tempkeyfile.name)
            raise

    def _export_conf_to_members(self, members):
        """This method exports conf files to other members."""
        try:
            for member in members:
                COPY_CMD = (system.SEND_CONF_TO_SERVER % (system.VERTICA_CONF,
                                                          member,
                                                          system.VERTICA_CONF))
                system.shell_execute(COPY_CMD)
        except exception.ProcessExecutionError:
            LOG.exception(_("Cannot export configuration."))
            raise

    def install_cluster(self, members):
        """Installs & configures cluster."""
        cluster_members = ','.join(members)
        LOG.debug("Installing cluster with members: %s." % cluster_members)
        self.install_vertica(cluster_members)
        self._export_conf_to_members(members)
        LOG.debug("Creating database with members: %s." % cluster_members)
        self.create_db(cluster_members)
        LOG.debug("Cluster configured on members: %s." % cluster_members)

    def grow_cluster(self, members):
        """Adds nodes to cluster."""
        cluster_members = ','.join(members)
        LOG.debug("Growing cluster with members: %s." % cluster_members)
        self.update_vertica("--add-hosts", cluster_members)
        self._export_conf_to_members(members)
        LOG.debug("Creating database with members: %s." % cluster_members)
        self.add_db_to_node(cluster_members)
        LOG.debug("Cluster configured on members: %s." % cluster_members)

    def shrink_cluster(self, members):
        """Removes nodes from cluster."""
        cluster_members = ','.join(members)
        LOG.debug("Shrinking cluster with members: %s." % cluster_members)
        self.remove_db_from_node(cluster_members)
        self.update_vertica("--remove-hosts", cluster_members)

    def wait_for_node_status(self, status='UP'):
        """Wait until all nodes are the same status"""
        # select node_state from nodes where node_state <> 'UP'
        def _wait_for_node_status():
            out, err = system.exec_vsql_command(self._get_database_password(),
                                                system.NODE_STATUS % status)
            LOG.debug("Polled vertica node states: %s" % out)

            if err:
                LOG.error(err)
                raise RuntimeError(_("Failed to query for root user."))

            return "0 rows" in out

        try:
            utils.poll_until(_wait_for_node_status, time_out=600,
                             sleep_time=15)
        except exception.PollTimeOut:
            raise RuntimeError(_("Timed out waiting for cluster to"
                                 "change to status %s") % status)
