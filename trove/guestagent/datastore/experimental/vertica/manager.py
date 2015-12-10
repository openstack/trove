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

from oslo_log import log as logging

from trove.common.i18n import _
from trove.common import instance as rd_ins
from trove.guestagent.datastore.experimental.vertica.service import (
    VerticaAppStatus)
from trove.guestagent.datastore.experimental.vertica.service import VerticaApp
from trove.guestagent.datastore import manager
from trove.guestagent import volume


LOG = logging.getLogger(__name__)


class Manager(manager.Manager):

    def __init__(self):
        self.appStatus = VerticaAppStatus()
        self.app = VerticaApp(self.appStatus)
        super(Manager, self).__init__('vertica')

    @property
    def status(self):
        return self.appStatus

    def do_prepare(self, context, packages, databases, memory_mb, users,
                   device_path, mount_point, backup_info,
                   config_contents, root_password, overrides,
                   cluster_config, snapshot):
        """This is called from prepare in the base class."""
        if device_path:
            device = volume.VolumeDevice(device_path)
            # unmount if device is already mounted
            device.unmount_device(device_path)
            device.format()
            if os.path.exists(mount_point):
                # rsync any existing data
                device.migrate_data(mount_point)
                # mount the volume
                device.mount(mount_point)
                LOG.debug("Mounted the volume.")
        self.app.install_if_needed(packages)
        self.app.prepare_for_install_vertica()
        if cluster_config is None:
            self.app.install_vertica()
            self.app.create_db()
            self.app.add_udls()
        elif cluster_config['instance_type'] not in ["member", "master"]:
            raise RuntimeError(_("Bad cluster configuration: instance type "
                               "given as %s.") %
                               cluster_config['instance_type'])

    def restart(self, context):
        LOG.debug("Restarting the database.")
        self.app.restart()
        LOG.debug("Restarted the database.")

    def stop_db(self, context, do_not_start_on_reboot=False):
        LOG.debug("Stopping the database.")
        self.app.stop_db(do_not_start_on_reboot=do_not_start_on_reboot)
        LOG.debug("Stopped the database.")

    def enable_root(self, context):
        LOG.debug("Enabling root.")
        return self.app.enable_root()

    def enable_root_with_password(self, context, root_password=None):
        LOG.debug("Enabling root.")
        return self.app.enable_root(root_password)

    def is_root_enabled(self, context):
        LOG.debug("Checking if root is enabled.")
        return self.app.is_root_enabled()

    def start_db_with_conf_changes(self, context, config_contents):
        LOG.debug("Starting with configuration changes.")
        self.app.start_db_with_conf_changes(config_contents)

    def get_public_keys(self, context, user):
        LOG.debug("Retrieving public keys for %s." % user)
        return self.app.get_public_keys(user)

    def authorize_public_keys(self, context, user, public_keys):
        LOG.debug("Authorizing public keys for %s." % user)
        return self.app.authorize_public_keys(user, public_keys)

    def install_cluster(self, context, members):
        try:
            LOG.debug("Installing cluster on members: %s." % members)
            self.app.install_cluster(members)
            self.app.add_udls()
            LOG.debug("install_cluster call has finished.")
        except Exception:
            LOG.exception(_('Cluster installation failed.'))
            self.appStatus.set_status(rd_ins.ServiceStatuses.FAILED)
            raise

    def grow_cluster(self, context, members):
        try:
            LOG.debug("Growing cluster to members: %s." % members)
            self.app.grow_cluster(members)
            LOG.debug("grow_cluster call has finished.")
        except Exception:
            LOG.exception(_('Cluster grow failed.'))
            self.appStatus.set_status(rd_ins.ServiceStatuses.FAILED)
            raise

    def shrink_cluster(self, context, members):
        try:
            LOG.debug("Shrinking cluster members: %s." % members)
            self.app.shrink_cluster(members)
            LOG.debug("shrink_cluster call has finished.")
        except Exception:
            LOG.exception(_('Cluster shrink failed.'))
            self.appStatus.set_status(rd_ins.ServiceStatuses.FAILED)
            raise

    def mark_design_ksafe(self, context, k):
        try:
            LOG.debug("Setting vertica k-safety to %s." % k)
            self.app.mark_design_ksafe(k)
        except Exception:
            LOG.exception(_('K-safety setting failed.'))
            self.appStatus.set_status(rd_ins.ServiceStatuses.FAILED)
            raise
