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
import yaml
from trove.common import cfg
from trove.common import utils
from trove.common import exception
from trove.common import instance as rd_instance
from trove.guestagent.common import operating_system
from trove.guestagent.datastore.cassandra import system
from trove.guestagent.datastore import service
from trove.guestagent import pkg
from trove.openstack.common import log as logging
from trove.common.i18n import _


LOG = logging.getLogger(__name__)
CONF = cfg.CONF

packager = pkg.Package()


class CassandraApp(object):
    """Prepares DBaaS on a Guest container."""

    def __init__(self, status):
        """By default login with root no password for initial setup."""
        self.state_change_wait_time = CONF.state_change_wait_time
        self.status = status

    def install_if_needed(self, packages):
        """Prepare the guest machine with a cassandra server installation."""
        LOG.info(_("Preparing Guest as a Cassandra Server"))
        if not packager.pkg_is_installed(packages):
            self._install_db(packages)
        LOG.debug("Cassandra install_if_needed complete")

    def complete_install_or_restart(self):
        self.status.end_install_or_restart()

    def _enable_db_on_boot(self):
        utils.execute_with_timeout(system.ENABLE_CASSANDRA_ON_BOOT,
                                   shell=True)

    def _disable_db_on_boot(self):
        utils.execute_with_timeout(system.DISABLE_CASSANDRA_ON_BOOT,
                                   shell=True)

    def init_storage_structure(self, mount_point):
        try:
            cmd = system.INIT_FS % mount_point
            utils.execute_with_timeout(cmd, shell=True)
        except exception.ProcessExecutionError:
            LOG.exception(_("Error while initiating storage structure."))

    def start_db(self, update_db=False):
        self._enable_db_on_boot()
        try:
            utils.execute_with_timeout(system.START_CASSANDRA,
                                       shell=True)
        except exception.ProcessExecutionError:
            LOG.exception(_("Error starting Cassandra"))
            pass

        if not (self.status.
                wait_for_real_status_to_change_to(
                rd_instance.ServiceStatuses.RUNNING,
                self.state_change_wait_time,
                update_db)):
            try:
                utils.execute_with_timeout(system.CASSANDRA_KILL,
                                           shell=True)
            except exception.ProcessExecutionError:
                LOG.exception(_("Error killing Cassandra start command."))
            self.status.end_install_or_restart()
            raise RuntimeError(_("Could not start Cassandra"))

    def stop_db(self, update_db=False, do_not_start_on_reboot=False):
        if do_not_start_on_reboot:
            self._disable_db_on_boot()
        utils.execute_with_timeout(system.STOP_CASSANDRA,
                                   shell=True,
                                   timeout=system.SERVICE_STOP_TIMEOUT)

        if not (self.status.wait_for_real_status_to_change_to(
                rd_instance.ServiceStatuses.SHUTDOWN,
                self.state_change_wait_time, update_db)):
            LOG.error(_("Could not stop Cassandra."))
            self.status.end_install_or_restart()
            raise RuntimeError(_("Could not stop Cassandra."))

    def restart(self):
        try:
            self.status.begin_restart()
            LOG.info(_("Restarting Cassandra server."))
            self.stop_db()
            self.start_db()
        finally:
            self.status.end_install_or_restart()

    def _install_db(self, packages):
        """Install cassandra server"""
        LOG.debug("Installing cassandra server.")
        packager.pkg_install(packages, None, system.INSTALL_TIMEOUT)
        LOG.debug("Finished installing Cassandra server")

    def write_config(self, config_contents):
        LOG.debug('Defining temp config holder at %s.' %
                  system.CASSANDRA_TEMP_CONF)

        try:
            with open(system.CASSANDRA_TEMP_CONF, 'w+') as conf:
                conf.write(config_contents)

            LOG.info(_('Writing new config.'))

            utils.execute_with_timeout("sudo", "mv",
                                       system.CASSANDRA_TEMP_CONF,
                                       system.CASSANDRA_CONF)
        except Exception:
            os.unlink(system.CASSANDRA_TEMP_CONF)
            raise

    def read_conf(self):
        """Returns cassandra.yaml in dict structure."""

        LOG.debug("Opening cassandra.yaml.")
        with open(system.CASSANDRA_CONF, 'r') as config:
            LOG.debug("Preparing YAML object from cassandra.yaml.")
            yamled = yaml.load(config.read())
        return yamled

    def update_config_with_single(self, key, value):
        """Updates single key:value in 'cassandra.yaml'."""

        yamled = self.read_conf()
        yamled.update({key: value})
        LOG.debug("Updating cassandra.yaml with %(key)s: %(value)s."
                  % {'key': key, 'value': value})
        dump = yaml.dump(yamled, default_flow_style=False)
        LOG.debug("Dumping YAML to stream.")
        self.write_config(dump)

    def update_conf_with_group(self, group):
        """Updates group of key:value in 'cassandra.yaml'."""

        yamled = self.read_conf()
        for key, value in group.iteritems():
            if key == 'seed':
                (yamled.get('seed_provider')[0].
                 get('parameters')[0].
                 update({'seeds': value}))
            else:
                yamled.update({key: value})
            LOG.debug("Updating cassandra.yaml with %(key)s: %(value)s."
                      % {'key': key, 'value': value})
        dump = yaml.dump(yamled, default_flow_style=False)
        LOG.debug("Dumping YAML to stream")
        self.write_config(dump)

    def make_host_reachable(self):
        updates = {
            'rpc_address': "0.0.0.0",
            'broadcast_rpc_address': operating_system.get_ip_address(),
            'listen_address': operating_system.get_ip_address(),
            'seed': operating_system.get_ip_address()
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


class CassandraAppStatus(service.BaseDbStatus):

    def _get_actual_db_status(self):
        try:
            # If status check would be successful,
            # bot stdin and stdout would contain nothing
            out, err = utils.execute_with_timeout(system.CASSANDRA_STATUS,
                                                  shell=True)
            if "Connection error. Could not connect to" not in err:
                return rd_instance.ServiceStatuses.RUNNING
            else:
                return rd_instance.ServiceStatuses.SHUTDOWN
        except (exception.ProcessExecutionError, OSError):
            LOG.exception(_("Error getting Cassandra status"))
            return rd_instance.ServiceStatuses.SHUTDOWN
