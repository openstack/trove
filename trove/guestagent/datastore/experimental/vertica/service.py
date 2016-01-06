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

import ConfigParser
import os
import subprocess
import tempfile

from oslo_log import log as logging
from oslo_utils import netutils

from trove.common import cfg
from trove.common import exception
from trove.common.i18n import _
from trove.common.i18n import _LI
from trove.common import instance as rd_instance
from trove.common import utils as utils
from trove.guestagent.datastore.experimental.vertica import system
from trove.guestagent.datastore import service
from trove.guestagent.db import models
from trove.guestagent import pkg
from trove.guestagent import volume

LOG = logging.getLogger(__name__)
CONF = cfg.CONF
packager = pkg.Package()
DB_NAME = 'db_srvr'
MOUNT_POINT = CONF.vertica.mount_point


class VerticaAppStatus(service.BaseDbStatus):

    def _get_actual_db_status(self):
        """Get the status of dbaas and report it back."""
        try:
            out, err = system.shell_execute(system.STATUS_ACTIVE_DB,
                                            "dbadmin")
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

    def _enable_db_on_boot(self):
        try:
            command = ["sudo", "su", "-", "dbadmin", "-c",
                       (system.SET_RESTART_POLICY % (DB_NAME, "always"))]
            subprocess.Popen(command)
            command = ["sudo", "su", "-", "root", "-c",
                       (system.VERTICA_AGENT_SERVICE_COMMAND % "enable")]
            subprocess.Popen(command)
        except Exception:
            LOG.exception(_("Failed to enable db on boot."))
            raise RuntimeError("Could not enable db on boot.")

    def _disable_db_on_boot(self):
        try:
            command = (system.SET_RESTART_POLICY % (DB_NAME, "never"))
            system.shell_execute(command, "dbadmin")
            command = (system.VERTICA_AGENT_SERVICE_COMMAND % "disable")
            system.shell_execute(command)
        except exception.ProcessExecutionError:
            LOG.exception(_("Failed to disable db on boot."))
            raise RuntimeError("Could not disable db on boot.")

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
            out, err = system.shell_execute(system.STATUS_ACTIVE_DB, "dbadmin")
            if out.strip() == DB_NAME:
                system.shell_execute(stop_db_command, "dbadmin")
                if not self.status._is_restarting:
                    if not self.status.wait_for_real_status_to_change_to(
                            rd_instance.ServiceStatuses.SHUTDOWN,
                            self.state_change_wait_time, update_db):
                        LOG.error(_("Could not stop Vertica."))
                        self.status.end_restart()
                        raise RuntimeError("Could not stop Vertica!")
                LOG.debug("Database stopped.")
            else:
                LOG.debug("Database is not running.")
        except exception.ProcessExecutionError:
            LOG.exception(_("Failed to stop database."))
            raise RuntimeError("Could not stop database.")

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
            start_db_command = ["sudo", "su", "-", "dbadmin", "-c",
                                (system.START_DB % (DB_NAME, db_password))]
            subprocess.Popen(start_db_command)
            if not self.status._is_restarting:
                self.status.end_restart()
            LOG.debug("Database started.")
        except Exception:
            raise RuntimeError("Could not start Vertica!")

    def start_db_with_conf_changes(self, config_contents):
        """
         Currently all that this method does is to start Vertica. This method
         needs to be implemented to enable volume resize on guestagent side.
        """
        LOG.info(_("Starting Vertica with configuration changes."))
        self.start_db(True)

    def restart(self):
        """Restart the database."""
        try:
            self.status.begin_restart()
            self.stop_db()
            self.start_db()
        finally:
            self.status.end_restart()

    def create_db(self, members=netutils.get_my_ipv4()):
        """Prepare the guest machine with a Vertica db creation."""
        LOG.info(_("Creating database on Vertica host."))
        try:
            # Create db after install
            db_password = self._get_database_password()
            create_db_command = (system.CREATE_DB % (members, DB_NAME,
                                                     MOUNT_POINT, MOUNT_POINT,
                                                     db_password))
            system.shell_execute(create_db_command, "dbadmin")
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
                    LOG.error(err)
                    raise RuntimeError(_("Failed to create library %s.")
                                       % lib_name)
                out, err = system.exec_vsql_command(
                    password,
                    system.CREATE_SOURCE % (func_name, language,
                                            factory, lib_name)
                )
                if err:
                    LOG.error(err)
                    raise RuntimeError(_("Failed to create source %s.")
                                       % func_name)
                loaded_udls.append(func_name)
            else:
                LOG.warning("Skipping %s as path %s not found." %
                            (func_name, path))
        LOG.info(_("The following UDL functions are available for use: %s")
                 % loaded_udls)

    def _generate_database_password(self):
        """Generate and write the password to vertica.cnf file."""
        config = ConfigParser.ConfigParser()
        config.add_section('credentials')
        config.set('credentials', 'dbadmin_password',
                   utils.generate_random_password())
        self.write_config(config)

    def write_config(self, config,
                     unlink_function=os.unlink,
                     temp_function=tempfile.NamedTemporaryFile):
        """Write the configuration contents to vertica.cnf file."""
        LOG.debug('Defining config holder at %s.' % system.VERTICA_CONF)
        tempfile = temp_function(delete=False)
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
            config = ConfigParser.ConfigParser()
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
        command = ("VERT_DBA_USR=dbadmin VERT_DBA_HOME=/home/dbadmin "
                   "VERT_DBA_GRP=verticadba /opt/vertica/oss/python/bin/python"
                   " -m vertica.local_coerce")
        try:
            self._set_readahead_for_disks()
            system.shell_execute(command)
        except exception.ProcessExecutionError:
            LOG.exception(_("Failed to prepare for install_vertica."))
            raise

    def _create_user(self, username, password, role):
        """Creates a user, granting and enabling the given role for it."""
        LOG.info(_("Creating user in Vertica database."))
        out, err = system.exec_vsql_command(self._get_database_password(),
                                            system.CREATE_USER %
                                            (username, password))
        if not err:
            self._grant_role(username, role)
        if err:
            LOG.error(err)
            raise RuntimeError(_("Failed to create user %s.") % username)

    def _grant_role(self, username, role):
        """Grants a role to the user on the schema."""
        out, err = system.exec_vsql_command(self._get_database_password(),
                                            system.GRANT_TO_USER
                                            % (role, username))
        if not err:
            out, err = system.exec_vsql_command(self._get_database_password(),
                                                system.ENABLE_FOR_USER
                                                % (username, role))
            if err:
                LOG.error(err)

    def enable_root(self, root_password=None):
        """Resets the root password."""
        LOG.info(_LI("Enabling root."))
        user = models.RootUser()
        user.name = "root"
        user.host = "%"
        user.password = root_password or utils.generate_random_password()
        if not self.is_root_enabled():
            self._create_user(user.name, user.password, 'pseudosuperuser')
        else:
            LOG.debug("Updating %s password." % user.name)
            try:
                out, err = system.exec_vsql_command(
                    self._get_database_password(),
                    system.ALTER_USER_PASSWORD % (user.name, user.password))
                if err:
                    LOG.error(err)
                    raise RuntimeError(_("Failed to update %s password.")
                                       % user.name)
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
                                             'root'), 'dbadmin')
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
            with tempfile.NamedTemporaryFile(delete=False) as tempkeyfile:
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
