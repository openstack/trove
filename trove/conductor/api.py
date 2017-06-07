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
from trove.common.rpc import conductor_guest_serializer as sz
from trove.common.serializable_notification import SerializableNotification
from trove import rpc

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class API(object):
    """API for interacting with trove conductor.

    API version history:
        * 1.0 - Initial version.

    When updating this API, also update API_LATEST_VERSION
    """

    # API_LATEST_VERSION should bump the minor number each time
    # a method signature is added or changed
    API_LATEST_VERSION = '1.0'

    # API_BASE_VERSION should only change on major version upgrade
    API_BASE_VERSION = '1.0'

    VERSION_ALIASES = {
        'icehouse': '1.0',
        'juno': '1.0',
        'kilo': '1.0',
        'liberty': '1.0',
        'mitaka': '1.0',
        'newton': '1.0',

        'latest': API_LATEST_VERSION
    }

    def __init__(self, context):
        self.context = context
        super(API, self).__init__()

        version_cap = self.VERSION_ALIASES.get(
            CONF.upgrade_levels.conductor, CONF.upgrade_levels.conductor)
        target = messaging.Target(topic=CONF.conductor_queue,
                                  version=version_cap)

        self.client = self.get_client(target, version_cap)

    def get_client(self, target, version_cap, serializer=None):
        return rpc.get_client(target, key=CONF.instance_rpc_encr_key,
                              version_cap=version_cap,
                              serializer=serializer,
                              secure_serializer=sz.ConductorGuestSerializer)

    def heartbeat(self, instance_id, payload, sent=None):
        LOG.debug("Making async call to cast heartbeat for instance: %s",
                  instance_id)
        version = self.API_BASE_VERSION

        cctxt = self.client.prepare(version=version)
        cctxt.cast(self.context, "heartbeat",
                   instance_id=instance_id,
                   sent=sent,
                   payload=payload)

    def update_backup(self, instance_id, backup_id, sent=None,
                      **backup_fields):
        LOG.debug("Making async call to cast update_backup for instance: %s",
                  instance_id)
        version = self.API_BASE_VERSION

        cctxt = self.client.prepare(version=version)
        cctxt.cast(self.context, "update_backup",
                   instance_id=instance_id,
                   backup_id=backup_id,
                   sent=sent,
                   **backup_fields)

    def report_root(self, instance_id, user):
        LOG.debug("Making async call to cast report_root for instance: %s",
                  instance_id)
        version = self.API_BASE_VERSION
        cctxt = self.client.prepare(version=version)
        cctxt.cast(self.context, "report_root",
                   instance_id=instance_id,
                   user=user)

    def notify_end(self, **notification_args):
        LOG.debug("Making async call to cast end notification")
        version = self.API_BASE_VERSION
        cctxt = self.client.prepare(version=version)
        context = self.context
        serialized = SerializableNotification.serialize(context,
                                                        context.notification)
        cctxt.cast(self.context, "notify_end",
                   serialized_notification=serialized,
                   notification_args=notification_args)

    def notify_exc_info(self, message, exception):
        LOG.debug("Making async call to cast error notification")
        version = self.API_BASE_VERSION
        cctxt = self.client.prepare(version=version)
        context = self.context
        serialized = SerializableNotification.serialize(context,
                                                        context.notification)
        serialized.update({'instance_id': CONF.guest_id})
        cctxt.cast(self.context, "notify_exc_info",
                   serialized_notification=serialized,
                   message=message, exception=exception)
