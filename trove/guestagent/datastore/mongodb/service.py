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

import re

import os
from trove.common import cfg
from trove.common import utils as utils
from trove.common import exception
from trove.common import instance as rd_instance
from trove.common.exception import ProcessExecutionError
from trove.guestagent.datastore import service
from trove.guestagent.datastore.mongodb import system
from trove.openstack.common import log as logging
from trove.guestagent.common import operating_system
from trove.openstack.common.gettextutils import _

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class MongoDBApp(object):
    """Prepares DBaaS on a Guest container."""

    def __init__(self, status):
        self.state_change_wait_time = CONF.state_change_wait_time
        self.status = status

    def install_if_needed(self, packages):
        """Prepare the guest machine with a MongoDB installation."""
        LOG.info(_("Preparing Guest as MongoDB"))
        if not system.PACKAGER.pkg_is_installed(packages):
            LOG.debug("Installing packages: %s" % str(packages))
            system.PACKAGER.pkg_install(packages, {}, system.TIME_OUT)
        LOG.info(_("Finished installing MongoDB server"))

    def _enable_db_on_boot(self):
        LOG.info(_("Enabling MongoDB on boot"))
        try:
            mongodb_service = operating_system.service_discovery(
                system.SERVICE_CANDIDATES)
            utils.execute_with_timeout(mongodb_service['cmd_enable'],
                                       shell=True)
        except KeyError:
            raise RuntimeError(_("MongoDB service is not discovered."))

    def _disable_db_on_boot(self):
        LOG.info(_("Disabling MongoDB on boot"))
        try:
            mongodb_service = operating_system.service_discovery(
                system.SERVICE_CANDIDATES)
            utils.execute_with_timeout(mongodb_service['cmd_disable'],
                                       shell=True)
        except KeyError:
            raise RuntimeError("MongoDB service is not discovered.")

    def stop_db(self, update_db=False, do_not_start_on_reboot=False):
        LOG.info(_("Stopping MongoDB"))
        if do_not_start_on_reboot:
            self._disable_db_on_boot()

        try:
            mongodb_service = operating_system.service_discovery(
                system.SERVICE_CANDIDATES)
            utils.execute_with_timeout(mongodb_service['cmd_stop'],
                                       shell=True)
        except KeyError:
            raise RuntimeError(_("MongoDB service is not discovered."))

        if not self.status.wait_for_real_status_to_change_to(
                rd_instance.ServiceStatuses.SHUTDOWN,
                self.state_change_wait_time, update_db):
            LOG.error(_("Could not stop MongoDB"))
            self.status.end_install_or_restart()
            raise RuntimeError(_("Could not stop MongoDB"))

    def restart(self):
        LOG.info(_("Restarting MongoDB"))
        try:
            self.status.begin_restart()
            self.stop_db()
            self.start_db()
        finally:
            self.status.end_install_or_restart()

    def start_db(self, update_db=False):
        LOG.info(_("Starting MongoDB"))

        self._enable_db_on_boot()

        try:
            mongodb_service = operating_system.service_discovery(
                system.SERVICE_CANDIDATES)
            utils.execute_with_timeout(mongodb_service['cmd_start'],
                                       shell=True)
        except ProcessExecutionError:
            pass
        except KeyError:
            raise RuntimeError("MongoDB service is not discovered.")

        if not self.status.wait_for_real_status_to_change_to(
                rd_instance.ServiceStatuses.RUNNING,
                self.state_change_wait_time, update_db):
            LOG.error(_("Start up of MongoDB failed"))
            # If it won't start, but won't die either, kill it by hand so we
            # don't let a rouge process wander around.
            try:
                out, err = utils.execute_with_timeout(
                    system.FIND_PID, shell=True)
                pid = "".join(out.split(" ")[1:2])
                utils.execute_with_timeout(
                    system.MONGODB_KILL % pid, shell=True)
            except exception.ProcessExecutionError as p:
                LOG.error("Error killing stalled MongoDB start command.")
                LOG.error(p)
                # There's nothing more we can do...
            self.status.end_install_or_restart()
            raise RuntimeError("Could not start MongoDB")

    def start_db_with_conf_changes(self, config_contents):
        LOG.info(_("Starting MongoDB with configuration changes"))
        LOG.info(_("Configuration contents:\n %s") % config_contents)
        if self.status.is_running:
            LOG.error(_("Cannot start MongoDB with configuration changes. "
                        "MongoDB state == %s!") % self.status)
            raise RuntimeError("MongoDB is not stopped.")
        self._write_config(config_contents)
        self.start_db(True)

    def reset_configuration(self, configuration):
        config_contents = configuration['config_contents']
        LOG.info(_("Resetting configuration"))
        self._write_config(config_contents)

    def update_config_contents(self, config_contents, parameters):
        if not config_contents:
            config_contents = self._read_config()

        contents = self._delete_config_parameters(config_contents,
                                                  parameters.keys())
        for param, value in parameters.iteritems():
            if param and value:
                contents = self._add_config_parameter(contents,
                                                      param, value)

        return contents

    def _write_config(self, config_contents):
        """
        Update contents of MongoDB configuration file
        """
        LOG.info(_("Updating MongoDB config"))
        if config_contents:
            LOG.info(_("Writing %s") % system.TMP_CONFIG)
            try:
                with open(system.TMP_CONFIG, 'w') as t:
                    t.write(config_contents)

                LOG.info(_("Moving %(a)s to %(b)s")
                         % {'a': system.TMP_CONFIG,
                            'b': system.CONFIG})
                utils.execute_with_timeout("mv",
                                           system.TMP_CONFIG,
                                           system.CONFIG,
                                           run_as_root=True,
                                           root_helper="sudo")
            except Exception:
                os.unlink(system.TMP_CONFIG)
                raise
        else:
            LOG.info(_("Empty config_contents. Do nothing"))

    def _read_config(self):
        try:
            with open(system.CONFIG, 'r') as f:
                return f.read()
        except IOError:
            LOG.info(_("Config file %s not found") % system.CONFIG)
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
        try:
            cmd = "sudo rm -rf %s" % mount_point
            utils.execute_with_timeout(cmd, shell=True)
        except exception.ProcessExecutionError as e:
            LOG.error(_("Process execution %s") % e)


class MongoDbAppStatus(service.BaseDbStatus):
    def _get_actual_db_status(self):
        try:
            status_check = (system.CMD_STATUS %
                            operating_system.get_ip_address())
            out, err = utils.execute_with_timeout(status_check, shell=True)
            if not err and "connected to:" in out:
                return rd_instance.ServiceStatuses.RUNNING
            else:
                return rd_instance.ServiceStatuses.SHUTDOWN
        except exception.ProcessExecutionError as e:
            LOG.error(_("Process execution %s") % e)
            return rd_instance.ServiceStatuses.SHUTDOWN
        except OSError as e:
            LOG.error(_("OS Error %s") % e)
            return rd_instance.ServiceStatuses.SHUTDOWN
