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

from reddwarf.common import config
from reddwarf.common.remote import create_nova_client
from reddwarf.instance import models as imodels
from reddwarf.instance.models import load_instance
from reddwarf.instance import models as instance_models


CONFIG = config.Config
LOG = logging.getLogger(__name__)


def load_mgmt_instance(cls, context, id):
    instance = load_instance(cls, context, id, needs_server=True)
    return instance


def load_mgmt_instances(context):
    client = create_nova_client(context)
    mgmt = client.mgmt.get_servers()
    db_infos = instance_models.DBInstance.find_all()
    instances = MgmtInstances.load_status_from_existing(context,
                                        db_infos, mgmt.servers)
    return instances


class SimpleMgmtInstance(imodels.BaseInstance):

    @property
    def host(self):
        return self.server.host if self.server else ""

    @property
    def deleted(self):
        return self.server.deleted if self.server else ""

    @property
    def deleted_at(self):
        return self.server.deleted_at if self.server else ""


class MgmtInstance(imodels.Instance):

    def get_diagnostics(self):
        return self.get_guest().get_diagnostics()


class MgmtInstances(imodels.Instances):

    @staticmethod
    def load_status_from_existing(context, db_infos, servers):

        def load_instance(context, db, status, server=None):
            return SimpleMgmtInstance(context, db, server, status)

        if context is None:
            raise TypeError("Argument context not defined.")

        find_server = imodels.create_server_list_matcher(
                                        _convert_server_objects(servers))
        ret = imodels.Instances._load_servers_status(load_instance, context,
                                                     db_infos, find_server)
        return ret


def _convert_server_objects(servers):
    server_objs = []
    for server in servers:
        server_objs.append(Server(server))
    return server_objs


class Server(object):

    def __init__(self, server):
        self.id = server['id']
        self.status = server['status']
        self.name = server['name']
        self.host = server['host']
        if 'deleted' in server:
            self.deleted = server['deleted']
        if 'deleted_at' in server:
            self.deleted_at = server['deleted_at']
