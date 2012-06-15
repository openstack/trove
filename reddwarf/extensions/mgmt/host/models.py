# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012 OpenStack LLC.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http: //www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""
Model classes that extend the instances functionality for MySQL instances.
"""

import logging

from reddwarf import db

from reddwarf.common import config
from reddwarf.common import exception
from reddwarf.common import utils
from reddwarf.instance import models as base_models
from reddwarf.instance.models import DBInstance
from reddwarf.guestagent.db import models as guest_models
from reddwarf.common.remote import create_guest_client
from reddwarf.common.remote import create_nova_client
from novaclient import exceptions as nova_exceptions


CONFIG = config.Config
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
            except exception.ReddwarfError as re:
                LOG.error(re)
                LOG.error("Compute Instance ID found with no associated RD "
                    "instance: %s" % instance['server_id'])
                instance['id'] = None


    @staticmethod
    def load(context, name):
        client = create_nova_client(context)
        try:
            return DetailedHost(client.rdhosts.get(name))
        except nova_exceptions.NotFound:
            raise exception.NotFound(uuid=name)
