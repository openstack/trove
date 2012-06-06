# Copyright 2012 OpenStack LLC.
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


"""
Routes all the requests to the task manager.
"""


import logging

from reddwarf import rpc
from reddwarf.common import config
from reddwarf.common import exception
from reddwarf.common import utils


LOG = logging.getLogger(__name__)


class API(object):
    """API for interacting with the task manager."""

    def __init__(self, context):
        self.context = context

    def _call(self, method_name, **kwargs):
        try:
            return rpc.call(self.context, self._get_routing_key(),
                            {"method": method_name, "args": kwargs})
        except Exception as e:
            LOG.error(e)
            raise exception.TaskManagerError(original_message=str(e))

    def _cast(self, method_name, **kwargs):
        try:
            rpc.cast(self.context, self._get_routing_key(),
                    {"method": method_name, "args": kwargs})
        except Exception as e:
            LOG.error(e)
            raise exception.TaskManagerError(original_message=str(e))

    def _get_routing_key(self):
        """Create the routing key for the taskmanager"""
        return "taskmanager"

    def resize_volume(self, new_size, instance_id):
        LOG.debug("Making async call to resize volume for instance: %s"
                 % instance_id)
        self._cast("resize_volume", new_size=new_size, instance_id=instance_id)

    def resize_flavor(self, instance_id, new_flavor_id, old_flavor_size,
                      new_flavor_size):
        LOG.debug("Making async call to resize flavor for instance: %s" %
                  instance_id)
        self._cast("resize_flavor", instance_id=instance_id,
                   new_flavor_id=new_flavor_id,
                   old_flavor_size=old_flavor_size,
                   new_flavor_size=new_flavor_size)

    def delete_instance(self, instance_id):
        LOG.debug("Making async call to delete instance: %s" % instance_id)
        self._cast("delete_instance", instance_id=instance_id)
