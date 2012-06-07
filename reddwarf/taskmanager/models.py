#    Copyright 2012 OpenStack LLC
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

import logging

from eventlet import greenthread

from novaclient import exceptions as nova_exceptions
from reddwarf.common import config
from reddwarf.common import remote
from reddwarf.common import utils
from reddwarf.common.exception import PollTimeOut
from reddwarf.common.exception import ReddwarfError
from reddwarf.common.remote import create_dns_client
from reddwarf.instance import models as inst_models


LOG = logging.getLogger(__name__)


class InstanceTasks:
    """
    Performs the various asynchronous instance related tasks.
    """

    def __init__(self, context, db_info, server, volumes,
                 nova_client=None, volume_client=None, guest=None):
        self.context = context
        self.db_info = db_info
        self.server = server
        self.volumes = volumes
        self.nova_client = nova_client
        self.volume_client = volume_client
        self.guest = guest

    @property
    def volume_id(self):
        return self.volumes[0]['id']

    @property
    def volume_mountpoint(self):
        mountpoint = self.volumes[0]['mountpoint']
        if mountpoint[0] is not "/":
            return "/%s" % mountpoint
        else:
            return mountpoint

    @staticmethod
    def load(context, id):
        if context is None:
            raise TypeError("Argument context not defined.")
        elif id is None:
            raise TypeError("Argument id not defined.")
        try:
            db_info = inst_models.DBInstance.find_by(id=id)
        except NotFound:
            raise NotFound(uuid=id)
        server, volumes = inst_models.load_server_with_volumes(context,
                                                db_info.id,
                                                db_info.compute_instance_id)
        nova_client = remote.create_nova_client(context)
        volume_client = remote.create_nova_volume_client(context)
        guest = remote.create_guest_client(context, id)
        return InstanceTasks(context, db_info, server, volumes,
                             nova_client=nova_client,
                             volume_client=volume_client, guest=guest)

    def delete_instance(self):
        try:
            self.server.delete()
        except Exception as ex:
            LOG.error("Error during delete compute server %s "
                      % self.server.id)
            LOG.error(ex)

        try:
            dns_support = config.Config.get("reddwarf_dns_support", 'False')
            LOG.debug(_("reddwarf dns support = %s") % dns_support)
            if utils.bool_from_string(dns_support):
                dns_api = create_dns_client(self.context)
                dns_api.delete_instance_entry(instance_id=self.db_info.id)
        except Exception as ex:
            LOG.error("Error during dns entry for instance %s "
                      % self.db_info.id )
            LOG.error(ex)

    def resize_volume(self, new_size):
        LOG.debug("%s: Resizing volume for instance: %s to %r GB"
                  % (greenthread.getcurrent(), self.server.id, new_size))
        self.volume_client.volumes.resize(self.volume_id, int(new_size))
        try:
            utils.poll_until(
                        lambda: self.volume_client.volumes.get(self.volume_id),
                        lambda volume: volume.status == 'in-use',
                        sleep_time=2,
                        time_out=int(config.Config.get('volume_time_out')))
            self.nova_client.volumes.rescan_server_volume(self.server,
                                                          self.volume_id)
            self.guest.resize_fs(self.volume_mountpoint)
        except PollTimeOut as pto:
            LOG.error("Timeout trying to rescan or resize the attached volume "
                      "filesystem for volume: %s" % self.volume_id)
        except Exception as e:
            LOG.error("Error encountered trying to rescan or resize the "
                      "attached volume filesystem for volume: %s"
                      % self.volume_id)
        finally:
            self.db_info.task_status = inst_models.InstanceTasks.NONE
            self.db_info.save()

    def resize_flavor(self, new_flavor_id, old_memory_size,
                      new_memory_size):
        def resize_status_msg():
            return "instance_id=%s, status=%s, flavor_id=%s, "\
                   "dest. flavor id=%s)" % (self.db_info.id,
                                            self.server.status,
                                            str(self.flavor['id']),
                                            str(new_flavor_id))

        try:
            LOG.debug("Instance %s calling stop_mysql..." % self.db_info.id)
            self.guest.stop_mysql()
            try:
                LOG.debug("Instance %s calling Compute resize..."
                          % self.db_info.id)
                self.server.resize(new_flavor_id)

                # Do initial check and confirm the status is appropriate.
                self._refresh_compute_server_info()
                if self.server.status != "RESIZE" and\
                   self.server.status != "VERIFY_RESIZE":
                    raise ReddwarfError("Unexpected status after " \
                            "call to resize! : %s" % resize_status_msg())

                # Wait for the flavor to change.
                utils.poll_until(
                    lambda: self.nova_client.servers.get(self.server.id),
                    lambda server: server.status != 'RESIZE',
                    sleep_time=2,
                    time_out=60 * 2)

                # Do check to make sure the status and flavor id are correct.
                if (str(self.server.flavor['id']) != str(new_flavor_id) or
                    self.server.status != "VERIFY_RESIZE"):
                    raise ReddwarfError("Assertion failed! flavor_id=%s "
                                        "and not %s"
                    % (self.server.status, str(self.server.flavor['id'])))

                # Confirm the resize with Nova.
                LOG.debug("Instance %s calling Compute confirm resize..."
                          % self.db_info.id)
                self.server.confirm_resize()
            except PollTimeOut as pto:
                LOG.error("Timeout trying to resize the flavor for instance "
                          " %s" % self.db_info.id)
            except Exception as ex:
                new_memory_size = old_memory_size
                LOG.error("Error during resize compute! Aborting action.")
                LOG.error(ex)
            finally:
                # Tell the guest to restart MySQL with the new RAM size.
                # This is in the finally because we have to call this, or
                # else MySQL could stay turned off on an otherwise usable
                # instance.
                LOG.debug("Instance %s starting mysql..." % self.db_info.id)
                self.guest.start_mysql_with_conf_changes(new_memory_size)
        finally:
            self.db_info.task_status = inst_models.InstanceTasks.NONE
            self.db_info.save()

    def _refresh_compute_server_info(self):
        """Refreshes the compute server field."""
        server = self.nova_client.servers.get(self.server.id)
        self.server = server
