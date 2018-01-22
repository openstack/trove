# Copyright (c) 2013 eBay Software Foundation
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
import os
import stat
import subprocess
import tempfile

from oslo_log import log as logging
from oslo_utils import netutils
import pexpect
import six

from trove.common import cfg
from trove.common.db import models
from trove.common import exception
from trove.common.i18n import _
from trove.common import instance as rd_instance
from trove.common import utils
from trove.guestagent.common import operating_system
from trove.guestagent.datastore.experimental.couchbase import system
from trove.guestagent.datastore import service
from trove.guestagent import pkg


LOG = logging.getLogger(__name__)
CONF = cfg.CONF
packager = pkg.Package()


class CouchbaseApp(object):
    """
    Handles installation and configuration of couchbase
    on a trove instance.
    """

    def __init__(self, status, state_change_wait_time=None):
        """
        Sets default status and state_change_wait_time
        """
        if state_change_wait_time:
            self.state_change_wait_time = state_change_wait_time
        else:
            self.state_change_wait_time = CONF.state_change_wait_time
        self.status = status

    def install_if_needed(self, packages):
        """
        Install couchbase if needed, do nothing if it is already installed.
        """
        LOG.info('Preparing Guest as Couchbase Server.')
        if not packager.pkg_is_installed(packages):
            LOG.debug('Installing Couchbase.')
            self._install_couchbase(packages)

    def initial_setup(self):
        self.ip_address = netutils.get_my_ipv4()
        mount_point = CONF.couchbase.mount_point
        try:
            LOG.info('Couchbase Server change data dir path.')
            operating_system.chown(mount_point, 'couchbase', 'couchbase',
                                   as_root=True)
            pwd = CouchbaseRootAccess.get_password()
            utils.execute_with_timeout(
                (system.cmd_node_init
                 % {'data_path': mount_point,
                    'IP': self.ip_address,
                    'PWD': pwd}), shell=True)
            operating_system.remove(system.INSTANCE_DATA_DIR, force=True,
                                    as_root=True)
            LOG.debug('Couchbase Server initialize cluster.')
            utils.execute_with_timeout(
                (system.cmd_cluster_init
                 % {'IP': self.ip_address, 'PWD': pwd}),
                shell=True)
            utils.execute_with_timeout(system.cmd_set_swappiness, shell=True)
            utils.execute_with_timeout(system.cmd_update_sysctl_conf,
                                       shell=True)
            LOG.info('Couchbase Server initial setup finished.')
        except exception.ProcessExecutionError:
            LOG.exception('Error performing initial Couchbase setup.')
            raise RuntimeError(_("Couchbase Server initial setup failed"))

    def _install_couchbase(self, packages):
        """
        Install the Couchbase Server.
        """
        LOG.debug('Installing Couchbase Server. Creating %s',
                  system.COUCHBASE_CONF_DIR)
        operating_system.create_directory(system.COUCHBASE_CONF_DIR,
                                          as_root=True)
        pkg_opts = {}
        packager.pkg_install(packages, pkg_opts, system.TIME_OUT)
        self.start_db()
        LOG.debug('Finished installing Couchbase Server.')

    def stop_db(self, update_db=False, do_not_start_on_reboot=False):
        self.status.stop_db_service(
            system.SERVICE_CANDIDATES, self.state_change_wait_time,
            disable_on_boot=do_not_start_on_reboot, update_db=update_db)

    def restart(self):
        self.status.restart_db_service(
            system.SERVICE_CANDIDATES, self.state_change_wait_time)

    def start_db(self, update_db=False):
        self.status.start_db_service(
            system.SERVICE_CANDIDATES, self.state_change_wait_time,
            enable_on_boot=True, update_db=update_db)

    def enable_root(self, root_password=None):
        return CouchbaseRootAccess.enable_root(root_password)

    def start_db_with_conf_changes(self, config_contents):
        LOG.info("Starting Couchbase with configuration changes.\n"
                 "Configuration contents:\n %s.", config_contents)
        if self.status.is_running:
            LOG.error("Cannot start Couchbase with configuration changes. "
                      "Couchbase state == %s.", self.status)
            raise RuntimeError(_("Couchbase is not stopped."))
        self._write_config(config_contents)
        self.start_db(True)

    def reset_configuration(self, configuration):
        config_contents = configuration['config_contents']
        LOG.debug("Resetting configuration.")
        self._write_config(config_contents)

    def _write_config(self, config_contents):
        """
        Update contents of Couchbase configuration file
        """
        return


class CouchbaseAppStatus(service.BaseDbStatus):
    """
    Handles all of the status updating for the couchbase guest agent.
    """

    def _get_actual_db_status(self):
        self.ip_address = netutils.get_my_ipv4()
        pwd = None
        try:
            pwd = CouchbaseRootAccess.get_password()
            return self._get_status_from_couchbase(pwd)
        except exception.ProcessExecutionError:
            # log the exception, but continue with native config approach
            LOG.exception("Error getting the Couchbase status.")

        try:
            out, err = utils.execute_with_timeout(
                system.cmd_get_password_from_config, shell=True)
        except exception.ProcessExecutionError:
            LOG.exception("Error getting the root password from the "
                          "native Couchbase config file.")
            return rd_instance.ServiceStatuses.SHUTDOWN

        config_pwd = out.strip() if out is not None else None
        if not config_pwd or config_pwd == pwd:
            LOG.debug("The root password from the native Couchbase config "
                      "file is either empty or already matches the "
                      "stored value.")
            return rd_instance.ServiceStatuses.SHUTDOWN

        try:
            status = self._get_status_from_couchbase(config_pwd)
        except exception.ProcessExecutionError:
            LOG.exception("Error getting Couchbase status using the "
                          "password parsed from the native Couchbase "
                          "config file.")
            return rd_instance.ServiceStatuses.SHUTDOWN

        # if the parsed root password worked, update the stored value to
        # avoid having to consult/parse the couchbase config file again.
        LOG.debug("Updating the stored value for the Couchbase "
                  "root password.")
        CouchbaseRootAccess().write_password_to_file(config_pwd)
        return status

    def _get_status_from_couchbase(self, pwd):
        out, err = utils.execute_with_timeout(
            (system.cmd_couchbase_status %
             {'IP': self.ip_address, 'PWD': pwd}),
            shell=True)
        server_stats = json.loads(out)
        if not err and server_stats["clusterMembership"] == "active":
            return rd_instance.ServiceStatuses.RUNNING
        else:
            return rd_instance.ServiceStatuses.SHUTDOWN

    def cleanup_stalled_db_services(self):
        utils.execute_with_timeout(system.cmd_kill)


class CouchbaseRootAccess(object):

    @classmethod
    def enable_root(cls, root_password=None):
        user = models.DatastoreUser.root(password=root_password)

        if root_password:
            CouchbaseRootAccess().write_password_to_file(root_password)
        else:
            CouchbaseRootAccess().set_password(user.password)
        return user.serialize()

    def set_password(self, root_password):
        self.ip_address = netutils.get_my_ipv4()
        child = pexpect.spawn(system.cmd_reset_pwd % {'IP': self.ip_address})
        try:
            child.expect('.*password.*')
            child.sendline(root_password)
            child.expect('.*(yes/no).*')
            child.sendline('yes')
            child.expect('.*successfully.*')
        except pexpect.TIMEOUT:
            child.delayafterclose = 1
            child.delayafterterminate = 1
            try:
                child.close(force=True)
            except pexpect.ExceptionPexpect:
                # Close fails to terminate a sudo process on some OSes.
                subprocess.call(['sudo', 'kill', str(child.pid)])

        self.write_password_to_file(root_password)

    def write_password_to_file(self, root_password):
        operating_system.create_directory(system.COUCHBASE_CONF_DIR,
                                          as_root=True)
        try:
            tempfd, tempname = tempfile.mkstemp()
            os.fchmod(tempfd, stat.S_IRUSR | stat.S_IWUSR)
            if isinstance(root_password, six.text_type):
                root_password = root_password.encode('utf-8')
            os.write(tempfd, root_password)
            os.fchmod(tempfd, stat.S_IRUSR)
            os.close(tempfd)
        except OSError as err:
            message = _("An error occurred in saving password "
                        "(%(errno)s). %(strerror)s.") % {
                            "errno": err.errno,
                            "strerror": err.strerror}
            LOG.exception(message)
            raise RuntimeError(message)

        operating_system.move(tempname, system.pwd_file, as_root=True)

    @staticmethod
    def get_password():
        pwd = "password"
        if os.path.exists(system.pwd_file):
            with open(system.pwd_file) as file:
                pwd = file.readline().strip()
        return pwd
