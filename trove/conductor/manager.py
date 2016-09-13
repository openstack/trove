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
from oslo_service import periodic_task

from trove.backup import models as bkup_models
from trove.common import cfg
from trove.common import exception as trove_exception
from trove.common.i18n import _
from trove.common.instance import ServiceStatus
from trove.common.rpc import version as rpc_version
from trove.common.serializable_notification import SerializableNotification
from trove.conductor.models import LastSeen
from trove.extensions.mysql import models as mysql_models
from trove.instance import models as inst_models

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class Manager(periodic_task.PeriodicTasks):

    target = messaging.Target(version=rpc_version.RPC_API_VERSION)

    def __init__(self):
        super(Manager, self).__init__(CONF)

    def _message_too_old(self, instance_id, method_name, sent):
        fields = {
            "instance": instance_id,
            "method": method_name,
            "sent": sent,
        }

        if sent is None:
            LOG.error(_("[Instance %s] sent field not present. Cannot "
                        "compare.") % instance_id)
            return False

        LOG.debug("Instance %(instance)s sent %(method)s at %(sent)s "
                  % fields)

        seen = None
        try:
            seen = LastSeen.load(instance_id=instance_id,
                                 method_name=method_name)
        except trove_exception.NotFound:
            # This is fine.
            pass

        if seen is None:
            LOG.debug("[Instance %s] Did not find any previous message. "
                      "Creating." % instance_id)
            seen = LastSeen.create(instance_id=instance_id,
                                   method_name=method_name,
                                   sent=sent)
            seen.save()
            return False

        last_sent = float(seen.sent)
        if last_sent < sent:
            LOG.debug("[Instance %s] Rec'd message is younger than last "
                      "seen. Updating." % instance_id)
            seen.sent = sent
            seen.save()
            return False

        LOG.info(_("[Instance %s] Rec'd message is older than last seen. "
                   "Discarding.") % instance_id)
        return True

    def heartbeat(self, context, instance_id, payload, sent=None):
        LOG.debug("Instance ID: %(instance)s, Payload: %(payload)s" %
                  {"instance": str(instance_id),
                   "payload": str(payload)})
        status = inst_models.InstanceServiceStatus.find_by(
            instance_id=instance_id)
        if self._message_too_old(instance_id, 'heartbeat', sent):
            return
        if payload.get('service_status') is not None:
            status.set_status(ServiceStatus.from_description(
                payload['service_status']))
        status.save()

    def update_backup(self, context, instance_id, backup_id,
                      sent=None, **backup_fields):
        LOG.debug("Instance ID: %(instance)s, Backup ID: %(backup)s" %
                  {"instance": str(instance_id),
                   "backup": str(backup_id)})
        backup = bkup_models.DBBackup.find_by(id=backup_id)
        # TODO(datsun180b): use context to verify tenant matches

        if self._message_too_old(instance_id, 'update_backup', sent):
            return

        # Some verification based on IDs
        if backup_id != backup.id:
            fields = {
                'expected': backup_id,
                'found': backup.id,
                'instance': str(instance_id),
            }
            LOG.error(_("[Instance: %(instance)s] Backup IDs mismatch! "
                        "Expected %(expected)s, found %(found)s") % fields)
            return
        if instance_id != backup.instance_id:
            fields = {
                'expected': instance_id,
                'found': backup.instance_id,
                'instance': str(instance_id),
            }
            LOG.error(_("[Instance: %(instance)s] Backup instance IDs "
                        "mismatch! Expected %(expected)s, found "
                        "%(found)s") % fields)
            return

        for k, v in backup_fields.items():
            if hasattr(backup, k):
                fields = {
                    'key': k,
                    'value': v,
                }
                LOG.debug("Backup %(key)s: %(value)s" % fields)
                setattr(backup, k, v)
        backup.save()

    def report_root(self, context, instance_id, user):
        mysql_models.RootHistory.create(context, instance_id, user)

    def notify_end(self, context, serialized_notification, notification_args):
        notification = SerializableNotification.deserialize(
            context, serialized_notification)
        notification.notify_end(**notification_args)

    def notify_exc_info(self, context, serialized_notification,
                        message, exception):
        notification = SerializableNotification.deserialize(
            context, serialized_notification)
        LOG.error(_("Guest exception on request %(req)s:\n%(exc)s")
                  % {'req': notification.request_id, 'exc': exception})
        notification.notify_exc_info(message, exception)
