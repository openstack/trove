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

import json
import re

import os
from trove.common import cfg
from trove.common import utils as utils
from trove.common import exception
from trove.common import instance as ds_instance
from trove.common.exception import ProcessExecutionError
from trove.guestagent.datastore import service
from trove.guestagent.datastore.mongodb import system
from trove.openstack.common import log as logging
from trove.guestagent.common import operating_system
from trove.openstack.common.gettextutils import _

LOG = logging.getLogger(__name__)
CONF = cfg.CONF
CONFIG_FILE = (operating_system.
               file_discovery(system.CONFIG_CANDIDATES))


class MongoDBApp(object):
    """Prepares DBaaS on a Guest container."""

    def __init__(self, status):
        self.state_change_wait_time = CONF.state_change_wait_time
        self.status = status

    def install_if_needed(self, packages):
        """Prepare the guest machine with a MongoDB installation."""
        LOG.info(_("Preparing Guest as MongoDB."))
        if not system.PACKAGER.pkg_is_installed(packages):
            LOG.debug("Installing packages: %s." % str(packages))
            system.PACKAGER.pkg_install(packages, {}, system.TIME_OUT)
        LOG.info(_("Finished installing MongoDB server."))

    def _get_service(self):
        if self.status._is_query_router() is True:
            return (operating_system.
                    service_discovery(system.MONGOS_SERVICE_CANDIDATES))
        else:
            return (operating_system.
                    service_discovery(system.MONGOD_SERVICE_CANDIDATES))

    def _enable_db_on_boot(self):
        LOG.info(_("Enabling MongoDB on boot."))
        try:
            mongo_service = self._get_service()
            utils.execute_with_timeout(mongo_service['cmd_enable'],
                                       shell=True)
        except KeyError:
            raise RuntimeError(_("MongoDB service is not discovered."))

    def _disable_db_on_boot(self):
        LOG.info(_("Disabling MongoDB on boot."))
        try:
            mongo_service = self._get_service()
            utils.execute_with_timeout(mongo_service['cmd_disable'],
                                       shell=True)
        except KeyError:
            raise RuntimeError("MongoDB service is not discovered.")

    def stop_db(self, update_db=False, do_not_start_on_reboot=False):
        LOG.info(_("Stopping MongoDB."))
        if do_not_start_on_reboot:
            self._disable_db_on_boot()

        try:
            mongo_service = self._get_service()
            # TODO(ramashri) see if hardcoded values can be removed
            utils.execute_with_timeout(mongo_service['cmd_stop'],
                                       shell=True, timeout=100)
        except KeyError:
            raise RuntimeError(_("MongoDB service is not discovered."))

        if not self.status.wait_for_real_status_to_change_to(
                ds_instance.ServiceStatuses.SHUTDOWN,
                self.state_change_wait_time, update_db):
            LOG.error(_("Could not stop MongoDB."))
            self.status.end_install_or_restart()
            raise RuntimeError(_("Could not stop MongoDB"))

    def restart(self):
        LOG.info(_("Restarting MongoDB."))
        try:
            self.status.begin_restart()
            self.stop_db()
            self.start_db()
        finally:
            self.status.end_install_or_restart()

    def start_db(self, update_db=False):
        LOG.info(_("Starting MongoDB."))

        self._enable_db_on_boot()

        try:
            mongo_service = self._get_service()
            utils.execute_with_timeout(mongo_service['cmd_start'],
                                       shell=True)
        except ProcessExecutionError:
            pass
        except KeyError:
            raise RuntimeError("MongoDB service is not discovered.")

        if not self.status.wait_for_real_status_to_change_to(
                ds_instance.ServiceStatuses.RUNNING,
                self.state_change_wait_time, update_db):
            LOG.error(_("Start up of MongoDB failed."))
            # If it won't start, but won't die either, kill it by hand so we
            # don't let a rouge process wander around.
            try:
                out, err = utils.execute_with_timeout(
                    system.FIND_PID, shell=True)
                pid = "".join(out.split(" ")[1:2])
                utils.execute_with_timeout(
                    system.MONGODB_KILL % pid, shell=True)
            except exception.ProcessExecutionError:
                LOG.exception(_("Error killing MongoDB start command."))
                # There's nothing more we can do...
            self.status.end_install_or_restart()
            raise RuntimeError("Could not start MongoDB.")

    def start_db_with_conf_changes(self, config_contents):
        LOG.info(_("Starting MongoDB with configuration changes."))
        LOG.info(_("Configuration contents:\n %s.") % config_contents)
        if self.status.is_running:
            LOG.error(_("Cannot start MongoDB with configuration changes. "
                        "MongoDB state == %s.") % self.status)
            raise RuntimeError("MongoDB is not stopped.")
        self._write_config(config_contents)
        self.start_db(True)

    def reset_configuration(self, configuration):
        config_contents = configuration['config_contents']
        LOG.info(_("Resetting configuration."))
        self._write_config(config_contents)

    def update_config_contents(self, config_contents, parameters):
        LOG.info(_("Updating configuration contents."))
        if not config_contents:
            config_contents = self._read_config()

        contents = self._delete_config_parameters(config_contents,
                                                  parameters.keys())
        for param, value in parameters.items():
            if param and value:
                contents = self._add_config_parameter(contents,
                                                      param, value)
        return contents

    def _write_config(self, config_contents):
        """
        Update contents of MongoDB configuration file
        """
        LOG.info(_("Updating MongoDB config."))
        if config_contents:
            LOG.info(_("Writing %s.") % system.TMP_CONFIG)
            try:
                with open(system.TMP_CONFIG, 'w') as t:
                    t.write(config_contents)

                LOG.info(_("Moving %(a)s to %(b)s.")
                         % {'a': system.TMP_CONFIG, 'b': CONFIG_FILE})
                utils.execute_with_timeout("mv",
                                           system.TMP_CONFIG,
                                           CONFIG_FILE,
                                           run_as_root=True,
                                           root_helper="sudo")
            except Exception:
                os.unlink(system.TMP_CONFIG)
                raise
        else:
            LOG.debug("Empty config_contents. Do nothing.")

    def _read_config(self):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return f.read()
        except IOError:
            LOG.info(_("Config file %s not found.") % CONFIG_FILE)
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
        LOG.debug("Clearing storage at %s." % mount_point)
        try:
            cmd = "sudo rm -rf %s" % mount_point
            utils.execute_with_timeout(cmd, shell=True)
        except exception.ProcessExecutionError:
            LOG.exception(_("Error clearing storage."))

    def add_config_servers(self, config_server_hosts):
        """
        This method is used by query router (mongos) instances.
        """
        config_contents = self._read_config()
        configdb_contents = ','.join(['%s:27019' % host
                                      for host in config_server_hosts])
        LOG.debug("Config server list %s." % configdb_contents)
        # remove db path from config and update configdb
        contents = self._delete_config_parameters(config_contents,
                                                  ["dbpath", "nojournal",
                                                   "smallfiles", "journal",
                                                   "noprealloc", "configdb"])
        contents = self._add_config_parameter(contents,
                                              "configdb", configdb_contents)
        LOG.info(_("Rewriting configuration."))
        self.start_db_with_conf_changes(contents)

    def write_mongos_upstart(self):
        upstart_contents = (system.MONGOS_UPSTART_CONTENTS.
                            format(config_file_placeholder=CONFIG_FILE))

        LOG.info(_("Writing %s.") % system.TMP_MONGOS_UPSTART)

        with open(system.TMP_MONGOS_UPSTART, 'w') as t:
            t.write(upstart_contents)

        LOG.info(_("Moving %(a)s to %(b)s.")
                 % {'a': system.TMP_MONGOS_UPSTART,
                    'b': system.MONGOS_UPSTART})
        utils.execute_with_timeout("mv", system.TMP_MONGOS_UPSTART,
                                   system.MONGOS_UPSTART,
                                   run_as_root=True, root_helper="sudo")
        cmd = "sudo rm -f /etc/init/mongodb.conf"
        utils.execute_with_timeout(cmd, shell=True)

    def do_mongo(self, db_cmd):
        cmd = ('mongo --host ' + operating_system.get_ip_address() +
               ' --quiet --eval \'printjson(%s)\'' % db_cmd)
        # TODO(ramashri) see if hardcoded values can be removed
        out, err = utils.execute_with_timeout(cmd, shell=True, timeout=100)
        LOG.debug(out.strip())
        return (out, err)

    def add_shard(self, replica_set_name, replica_set_member):
        """
        This method is used by query router (mongos) instances.
        """
        cmd = 'db.adminCommand({addShard: "%s/%s:27017"})' % (
            replica_set_name, replica_set_member)
        self.do_mongo(cmd)

    def add_members(self, members):
        """
        This method is used by a replica-set member instance.
        """
        def clean_json(val):
            """
            This method removes from json, values that are functions like
            ISODate(), TimeStamp().
            """
            return re.sub(':\s*\w+\(\"?(.*?)\"?\)', r': "\1"', val)

        def check_initiate_status():
            """
            This method is used to verify replica-set status.
            """
            out, err = self.do_mongo("rs.status()")
            response = clean_json(out.strip())
            json_data = json.loads(response)

            if((json_data["ok"] == 1) and
               (json_data["members"][0]["stateStr"] == "PRIMARY") and
               (json_data["myState"] == 1)):
                    return True
            else:
                return False

        def check_rs_status():
            """
            This method is used to verify replica-set status.
            """
            out, err = self.do_mongo("rs.status()")
            response = clean_json(out.strip())
            json_data = json.loads(response)
            primary_count = 0

            if json_data["ok"] != 1:
                return False
            if len(json_data["members"]) != (len(members) + 1):
                return False
            for rs_member in json_data["members"]:
                if rs_member["state"] not in [1, 2, 7]:
                    return False
                if rs_member["health"] != 1:
                    return False
                if rs_member["state"] == 1:
                    primary_count += 1

            return primary_count == 1

        # initiate replica-set
        self.do_mongo("rs.initiate()")
        # TODO(ramashri) see if hardcoded values can be removed
        utils.poll_until(check_initiate_status, sleep_time=60, time_out=100)

        # add replica-set members
        for member in members:
            self.do_mongo('rs.add("' + member + '")')
         # TODO(ramashri) see if hardcoded values can be removed
        utils.poll_until(check_rs_status, sleep_time=60, time_out=100)


class MongoDbAppStatus(service.BaseDbStatus):

    is_config_server = None
    is_query_router = None

    def _is_config_server(self):
        if self.is_config_server is None:
            try:
                cmd = ("grep '^configsvr[ \t]*=[ \t]*true$' %s"
                       % CONFIG_FILE)
                utils.execute_with_timeout(cmd, shell=True)
                self.is_config_server = True
            except exception.ProcessExecutionError:
                self.is_config_server = False
        return self.is_config_server

    def _is_query_router(self):
        if self.is_query_router is None:
            try:
                cmd = ("grep '^configdb[ \t]*=.*$' %s"
                       % CONFIG_FILE)
                utils.execute_with_timeout(cmd, shell=True)
                self.is_query_router = True
            except exception.ProcessExecutionError:
                self.is_query_router = False
        return self.is_query_router

    def _get_actual_db_status(self):
        try:
            if self._is_config_server() is True:
                status_check = (system.CMD_STATUS %
                                (operating_system.get_ip_address() +
                                ' --port 27019'))
            else:
                status_check = (system.CMD_STATUS %
                                operating_system.get_ip_address())

            out, err = utils.execute_with_timeout(status_check, shell=True)
            if not err and "connected to:" in out:
                return ds_instance.ServiceStatuses.RUNNING
            else:
                return ds_instance.ServiceStatuses.SHUTDOWN
        except exception.ProcessExecutionError as e:
            LOG.exception(_("Process execution %s.") % e)
            return ds_instance.ServiceStatuses.SHUTDOWN
        except OSError as e:
            LOG.exception(_("OS Error %s.") % e)
            return ds_instance.ServiceStatuses.SHUTDOWN
