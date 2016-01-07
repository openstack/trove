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

import json

from oslo_log import log as logging

from trove.common import cfg
from trove.common import exception
from trove.common.i18n import _
from trove.common import instance as rd_instance
from trove.common import utils as utils
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
        LOG.debug("state_change_wait_time = %s." % self.state_change_wait_time)
        self.status = status

    def install_if_needed(self, packages):
        """
        Install CouchDB if needed, do nothing if it is already installed.
        """
        LOG.info(_('Preparing guest as a CouchDB server.'))
        if not packager.pkg_is_installed(packages):
            LOG.debug("Installing packages: %s." % str(packages))
            packager.pkg_install(packages, {}, system.TIME_OUT)
        LOG.info(_("Finished installing CouchDB server."))

    def change_permissions(self):
        """
        When CouchDB is installed, a default user 'couchdb' is created.
        Inorder to start/stop/restart CouchDB service as the current
        OS user, add this user to the 'couchdb' group and provide read/
        write access to the 'couchdb' group.
        """
        try:
            LOG.debug("Changing permissions.")
            operating_system.chown(
                COUCHDB_LIB_DIR, 'couchdb', 'couchdb', as_root=True
            )
            operating_system.chown(
                COUCHDB_LOG_DIR, 'couchdb', 'couchdb', as_root=True
            )
            operating_system.chown(
                COUCHDB_BIN_DIR, 'couchdb', 'couchdb', as_root=True
            )
            operating_system.chown(
                COUCHDB_CONFIG_DIR, 'couchdb', 'couchdb', as_root=True
            )
            operating_system.chmod(COUCHDB_LIB_DIR, FileMode.ADD_GRP_RW,
                                   as_root=True)
            operating_system.chmod(COUCHDB_LOG_DIR, FileMode.ADD_GRP_RW,
                                   as_root=True)
            operating_system.chmod(COUCHDB_BIN_DIR, FileMode.ADD_GRP_RW,
                                   as_root=True)
            operating_system.chmod(COUCHDB_CONFIG_DIR, FileMode.ADD_GRP_RW,
                                   as_root=True)
            self.execute_change_permission_commands(
                system.UPDATE_GROUP_MEMBERSHIP
            )
            LOG.debug("Successfully changed permissions.")
        except exception.ProcessExecutionError:
            LOG.exception(_("Error changing permissions."))

    def execute_change_permission_commands(self, chng_perm_cmd):
        out, err = utils.execute_with_timeout(chng_perm_cmd, shell=True)
        if err:
            raise exception.ProcessExecutionError(cmd=chng_perm_cmd,
                                                  stderr=err,
                                                  stdout=out)

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
            LOG.debug("CouchDB status = %r" % out)
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
