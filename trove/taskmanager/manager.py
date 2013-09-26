# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack Foundation
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
from trove.common.context import TroveContext

import trove.extensions.mgmt.instances.models as mgmtmodels
import trove.common.cfg as cfg
from trove.common import exception
from trove.openstack.common import log as logging
from trove.openstack.common import importutils
from trove.openstack.common import periodic_task
from trove.taskmanager import models
from trove.taskmanager.models import FreshInstanceTasks

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
        if CONF.exists_notification_transformer:
            self.exists_transformer = importutils.import_object(
                CONF.exists_notification_transformer,
                context=self.admin_context)

    def resize_volume(self, context, instance_id, new_size):
        instance_tasks = models.BuiltInstanceTasks.load(context, instance_id)
        instance_tasks.resize_volume(new_size)

    def resize_flavor(self, context, instance_id, old_flavor, new_flavor):
        instance_tasks = models.BuiltInstanceTasks.load(context, instance_id)
        instance_tasks.resize_flavor(old_flavor, new_flavor)

    def reboot(self, context, instance_id):
        instance_tasks = models.BuiltInstanceTasks.load(context, instance_id)
        instance_tasks.reboot()

    def restart(self, context, instance_id):
        instance_tasks = models.BuiltInstanceTasks.load(context, instance_id)
        instance_tasks.restart()

    def migrate(self, context, instance_id, host):
        instance_tasks = models.BuiltInstanceTasks.load(context, instance_id)
        instance_tasks.migrate(host)

    def delete_instance(self, context, instance_id):
        try:
            instance_tasks = models.BuiltInstanceTasks.load(context,
                                                            instance_id)
            instance_tasks.delete_async()
        except exception.UnprocessableEntity:
            instance_tasks = models.FreshInstanceTasks.load(context,
                                                            instance_id)
            instance_tasks.delete_async()

    def delete_backup(self, context, backup_id):
        models.BackupTasks.delete_backup(context, backup_id)

    def create_backup(self, context, backup_id, instance_id):
        instance_tasks = models.BuiltInstanceTasks.load(context, instance_id)
        instance_tasks.create_backup(backup_id)

    def create_instance(self, context, instance_id, name, flavor,
                        image_id, databases, users, service_type,
                        volume_size, security_groups, backup_id,
                        availability_zone):
        instance_tasks = FreshInstanceTasks.load(context, instance_id)
        instance_tasks.create_instance(flavor, image_id,
                                       databases, users, service_type,
                                       volume_size, security_groups,
                                       backup_id, availability_zone)

    if CONF.exists_notification_transformer:
        @periodic_task.periodic_task(
            ticks_between_runs=CONF.exists_notification_ticks)
        def publish_exists_event(self, context):
            """
            Push this in Instance Tasks to fetch a report/collection
            :param context: currently None as specied in bin script
            """
            mgmtmodels.publish_exist_events(self.exists_transformer,
                                            self.admin_context)
