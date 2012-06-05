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

from reddwarf.common import config
from reddwarf.common import exception
from reddwarf.common import remote
from reddwarf.common import utils
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
        except exception.NotFound:
            raise exception.NotFound(uuid=id)
        server, volumes = inst_models.load_server_with_volumes(context,
                                                db_info.id,
                                                db_info.compute_instance_id)
        nova_client = remote.create_nova_client(context)
        volume_client = remote.create_nova_volume_client(context)
        guest = remote.create_guest_client(context, id)
        return InstanceTasks(context, db_info, server, volumes,
                             nova_client=nova_client,
                             volume_client=volume_client, guest=guest)

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
        except exception.PollTimeOut as pto:
            LOG.error("Timeout trying to rescan or resize the attached volume "
                      "filesystem for volume: %s" % self.volume_id)
        except Exception as e:
            LOG.error("Error encountered trying to rescan or resize the "
                      "attached volume filesystem for volume: %s"
                      % self.volume_id)
        finally:
            self.db_info.task_status = inst_models.InstanceTasks.NONE
            self.db_info.save()
