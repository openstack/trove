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
#

import os

from oslo_log import log as logging

from trove.guestagent.datastore.experimental.cassandra import service
from trove.guestagent.datastore import manager
from trove.guestagent import volume


LOG = logging.getLogger(__name__)


class Manager(manager.Manager):

    def __init__(self):
        self.appStatus = service.CassandraAppStatus()
        self.app = service.CassandraApp(self.appStatus)
        super(Manager, self).__init__('cassandra')

    @property
    def status(self):
        return self.appStatus

    def restart(self, context):
        self.app.restart()

    def start_db_with_conf_changes(self, context, config_contents):
        self.app.start_db_with_conf_changes(config_contents)

    def stop_db(self, context, do_not_start_on_reboot=False):
        self.app.stop_db(do_not_start_on_reboot=do_not_start_on_reboot)

    def reset_configuration(self, context, configuration):
        self.app.reset_configuration(configuration)

    def do_prepare(self, context, packages, databases, memory_mb, users,
                   device_path, mount_point, backup_info,
                   config_contents, root_password, overrides,
                   cluster_config, snapshot):
        """This is called from prepare in the base class."""
        self.app.install_if_needed(packages)
        self.app.init_storage_structure(mount_point)

        if config_contents or device_path:
            # Stop the db while we configure
            # FIXME(amrith) Once the cassandra bug
            # https://issues.apache.org/jira/browse/CASSANDRA-2356
            # is fixed, this code may have to be revisited.
            LOG.debug("Stopping database prior to changes.")
            self.app.stop_db()

            if config_contents:
                LOG.debug("Processing configuration.")
                self.app.write_config(config_contents)
                self.app.make_host_reachable()

            if device_path:
                device = volume.VolumeDevice(device_path)
                # unmount if device is already mounted
                device.unmount_device(device_path)
                device.format()
                if os.path.exists(mount_point):
                    # rsync exiting data
                    device.migrate_data(mount_point)
                # mount the volume
                device.mount(mount_point)
                LOG.debug("Mounting new volume.")

            LOG.debug("Restarting database after changes.")
            self.app.start_db()
