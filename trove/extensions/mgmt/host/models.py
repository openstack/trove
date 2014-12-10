# Copyright 2012 OpenStack Foundation
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
Model classes that extend the instances functionality for MySQL instances.
"""

from trove.openstack.common import log as logging
from trove.common.i18n import _

from trove.common import exception
from trove.instance.models import DBInstance
from trove.instance.models import InstanceServiceStatus
from trove.instance.models import SimpleInstance
from trove.common.remote import create_guest_client
from trove.common.remote import create_nova_client
from novaclient import exceptions as nova_exceptions


LOG = logging.getLogger(__name__)


class SimpleHost(object):

    def __init__(self, name, instance_count):
        self.name = name
        self.instance_count = instance_count

    @staticmethod
    def load_all(context):
        client = create_nova_client(context)
        LOG.debug("Client.rdhosts=" + str(client.rdhosts))
        rdhosts = client.rdhosts.list()
        LOG.debug("RDHOSTS=" + str(rdhosts))
        for rdhost in rdhosts:
            LOG.debug("rdhost=" + str(rdhost))
        return [SimpleHost(rdhost.name, rdhost.instanceCount)
                for rdhost in rdhosts]


class DetailedHost(object):

    def __init__(self, host_info):
        self.name = host_info.name
        self.percent_used = host_info.percentUsed
        self.total_ram = host_info.totalRAM
        self.used_ram = host_info.usedRAM
        self.instances = host_info.instances
        for instance in self.instances:
            instance['server_id'] = instance['uuid']
            del instance['uuid']
            try:
                db_info = DBInstance.find_by(
                    compute_instance_id=instance['server_id'])
                instance['id'] = db_info.id
                instance['tenant_id'] = db_info.tenant_id
                status = InstanceServiceStatus.find_by(
                    instance_id=db_info.id)
                instance_info = SimpleInstance(None, db_info, status)
                instance['status'] = instance_info.status
            except exception.TroveError as re:
                LOG.error(re)
                LOG.error(_("Compute Instance ID found with no associated RD "
                          "instance: %s.") % instance['server_id'])
                instance['id'] = None

    def update_all(self, context):
        num_i = len(self.instances)
        LOG.debug("Host %s has %s instances to update." % (self.name, num_i))
        failed_instances = []
        for instance in self.instances:
            client = create_guest_client(context, instance['id'])
            try:
                client.update_guest()
            except exception.TroveError as re:
                LOG.error(re)
                LOG.error(_("Unable to update instance: %s.") % instance['id'])
                failed_instances.append(instance['id'])
        if len(failed_instances) > 0:
            msg = _("Failed to update instances: %s.") % failed_instances
            raise exception.UpdateGuestError(msg)

    @staticmethod
    def load(context, name):
        client = create_nova_client(context)
        try:
            return DetailedHost(client.rdhosts.get(name))
        except nova_exceptions.NotFound:
            raise exception.NotFound(uuid=name)
