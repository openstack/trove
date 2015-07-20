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

from oslo_log import log as logging
import oslo_messaging as messaging

from trove.common import cfg
from trove.common.rpc import version as rpc_version
from trove import rpc


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class API(object):
    """API for interacting with trove conductor."""

    def __init__(self, context):
        self.context = context
        super(API, self).__init__()

        target = messaging.Target(topic=CONF.conductor_queue,
                                  version=rpc_version.RPC_API_VERSION)

        self.version_cap = rpc_version.VERSION_ALIASES.get(
            CONF.upgrade_levels.conductor)
        self.client = self.get_client(target, self.version_cap)

    def get_client(self, target, version_cap, serializer=None):
        return rpc.get_client(target,
                              version_cap=version_cap,
                              serializer=serializer)

    def heartbeat(self, instance_id, payload, sent=None):
        LOG.debug("Making async call to cast heartbeat for instance: %s"
                  % instance_id)

        cctxt = self.client.prepare(version=self.version_cap)
        cctxt.cast(self.context, "heartbeat",
                   instance_id=instance_id,
                   sent=sent,
                   payload=payload)

    def update_backup(self, instance_id, backup_id, sent=None,
                      **backup_fields):
        LOG.debug("Making async call to cast update_backup for instance: %s"
                  % instance_id)

        cctxt = self.client.prepare(version=self.version_cap)
        cctxt.cast(self.context, "update_backup",
                   instance_id=instance_id,
                   backup_id=backup_id,
                   sent=sent,
                   **backup_fields)

    def report_root(self, instance_id, user):
        LOG.debug("Making async call to cast report_root for instance: %s"
                  % instance_id)
        cctxt = self.client.prepare(version=self.version_cap)
        cctxt.cast(self.context, "report_root",
                   instance_id=instance_id,
                   user=user)
