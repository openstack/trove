#Copyright [2015] Hewlett-Packard Development Company, L.P.
#Licensed under the Apache License, Version 2.0 (the "License");
#you may not use this file except in compliance with the License.
#You may obtain a copy of the License at
#
#http://www.apache.org/licenses/LICENSE-2.0
#
#Unless required by applicable law or agreed to in writing, software
#distributed under the License is distributed on an "AS IS" BASIS,
#WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#See the License for the specific language governing permissions and
#limitations under the License.

import ConfigParser
import os
import tempfile

from trove.common import cfg
from trove.common import exception
from trove.common import utils as utils
from trove.common import instance as rd_instance
from trove.guestagent.common import operating_system
from trove.guestagent.datastore import service
from trove.guestagent import pkg
from trove.guestagent import volume
from trove.guestagent.datastore.experimental.vertica import system
from trove.openstack.common import log as logging
from trove.common.i18n import _

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
                #UP status is confirmed
                LOG.info(_("Service Status is RUNNING."))
                return rd_instance.ServiceStatuses.RUNNING
            elif out.strip() == "":
                #nothing returned, means no db running lets verify
                out, err = system.shell_execute(system.STATUS_DB_DOWN,
                                                "dbadmin")
                if out.strip() == DB_NAME:
                    #DOWN status is confirmed
                    LOG.info(_("Service Status is SHUTDOWN."))
                    return rd_instance.ServiceStatuses.SHUTDOWN
                else:
                    return rd_instance.ServiceStatuses.UNKNOWN
        except exception.ProcessExecutionError:
            LOG.exception(_("Failed to get database status."))
            return rd_instance.ServiceStatuses.CRASHED


class VerticaApp(object):
    """Prepares DBaaS on a Guest container."""

    def __init__(self, status):
        self.state_change_wait_time = CONF.state_change_wait_time
        self.status = status

    def _enable_db_on_boot(self):
        command = (system.SET_RESTART_POLICY % (DB_NAME, "always"))
        try:
            system.shell_execute(command, "dbadmin")
        except exception.ProcessExecutionError:
            LOG.exception(_("Failed to enable db on boot."))
            raise

    def _disable_db_on_boot(self):
        command = (system.SET_RESTART_POLICY % (DB_NAME, "never"))
        try:
            system.shell_execute(command, "dbadmin")
        except exception.ProcessExecutionError:
            LOG.exception(_("Failed to disable db on boot."))
            raise

    def stop_db(self, update_db=False, do_not_start_on_reboot=False):
        """Stop the database."""
        LOG.info(_("Stopping Vertica."))
        if do_not_start_on_reboot:
            self._disable_db_on_boot()
        # Using Vertica adminTools to stop db.
        db_password = self._get_database_password()
        stop_db_command = (system.STOP_DB % (DB_NAME, db_password))
        system.shell_execute(stop_db_command, "dbadmin")
        if not self.status.wait_for_real_status_to_change_to(
                rd_instance.ServiceStatuses.SHUTDOWN,
                self.state_change_wait_time, update_db):
            LOG.error(_("Could not stop Vertica."))
            self.status.end_install_or_restart()
            raise RuntimeError("Could not stop Vertica!")

    def start_db(self, update_db=False):
        """Start the database."""
        LOG.info(_("Starting Vertica."))
        self._enable_db_on_boot()
        # Using Vertica adminTools to start db.
        db_password = self._get_database_password()
        start_db_command = (system.START_DB % (DB_NAME, db_password))
        system.shell_execute(start_db_command, "dbadmin")
        if not self.status.wait_for_real_status_to_change_to(
                rd_instance.ServiceStatuses.RUNNING,
                self.state_change_wait_time, update_db):
            LOG.error(_("Start up of Vertica failed."))
            self.status.end_install_or_restart()
            raise RuntimeError("Could not start Vertica!")

    def restart(self):
        """Restart the database."""
        try:
            self.status.begin_restart()
            self.stop_db()
            self.start_db()
        finally:
            self.status.end_install_or_restart()

    def create_db(self, members=operating_system.get_ip_address()):
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
        LOG.info(_("Vertica database create completed."))

    def install_vertica(self, members=operating_system.get_ip_address()):
        """Prepare the guest machine with a Vertica db creation."""
        LOG.info(_("Installing Vertica Server."))
        try:
            # Create db after install
            install_vertica_cmd = (system.INSTALL_VERTICA % (members,
                                                             MOUNT_POINT))
            system.shell_execute(install_vertica_cmd)
        except exception.ProcessExecutionError:
            LOG.exception(_("install_vertica failed."))
        self._generate_database_password()
        LOG.info(_("install_vertica completed."))

    def complete_install_or_restart(self):
        self.status.end_install_or_restart()

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
