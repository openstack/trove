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

from trove.backup import models as bkup_models
from trove.common.context import TroveContext
from trove.common.instance import ServiceStatus
from trove.instance import models as t_models
from trove.openstack.common import periodic_task
from trove.openstack.common import log as logging
from trove.common import cfg

LOG = logging.getLogger(__name__)
RPC_API_VERSION = "1.0"
CONF = cfg.CONF


class Manager(periodic_task.PeriodicTasks):

    def __init__(self):
        super(Manager, self).__init__()
        self.admin_context = TroveContext(
            user=CONF.nova_proxy_admin_user,
            auth_token=CONF.nova_proxy_admin_pass,
            tenant=CONF.nova_proxy_admin_tenant_name)

    def heartbeat(self, context, instance_id, payload):
        LOG.debug("Instance ID: %s" % str(instance_id))
        LOG.debug("Payload: %s" % str(payload))
        status = t_models.InstanceServiceStatus.find_by(
            instance_id=instance_id)
        if payload.get('service_status') is not None:
            status.set_status(ServiceStatus.from_description(
                payload['service_status']))
        status.save()

    def update_backup(self, context, instance_id, backup_id,
                      **backup_fields):
        LOG.debug("Instance ID: %s" % str(instance_id))
        LOG.debug("Backup ID: %s" % str(backup_id))
        backup = bkup_models.DBBackup.find_by(id=backup_id)
        # TODO(datsun180b): use context to verify tenant matches

        # Some verification based on IDs
        if backup_id != backup.id:
            LOG.error("Backup IDs mismatch! Expected %s, found %s" %
                      (backup_id, backup.id))
            return
        if instance_id != backup.instance_id:
            LOG.error("Backup instance IDs mismatch! Expected %s, found %s" %
                      (instance_id, backup.instance_id))
            return

        for k, v in backup_fields.items():
            if hasattr(backup, k):
                LOG.debug("Backup %s: %s" % (k, v))
                setattr(backup, k, v)
        backup.save()
