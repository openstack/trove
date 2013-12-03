#    Copyright 2013 OpenStack Foundation
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


from trove.common import cfg
from trove.openstack.common.rpc import proxy
from trove.openstack.common import log as logging


CONF = cfg.CONF
LOG = logging.getLogger(__name__)
RPC_API_VERSION = "1.0"


class API(proxy.RpcProxy):
    """API for interacting with trove conductor."""

    def __init__(self, context):
        self.context = context
        super(API, self).__init__(self._get_routing_key(), RPC_API_VERSION)

    def _get_routing_key(self):
        """Create the routing key for conductor."""
        return CONF.conductor_queue

    def heartbeat(self, instance_id, payload):
        LOG.debug("Making async call to cast heartbeat for instance: %s"
                  % instance_id)
        self.cast(self.context, self.make_msg("heartbeat",
                                              instance_id=instance_id,
                                              payload=payload))

    def update_backup(self, instance_id, backup_id, **backup_fields):
        LOG.debug("Making async call to cast update_backup for instance: %s"
                  % instance_id)
        self.cast(self.context, self.make_msg("update_backup",
                                              instance_id=instance_id,
                                              backup_id=backup_id,
                                              **backup_fields))
