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


def load_mgmt_instances(context):
    client = create_nova_client(context)
    mgmt_servers = client.rdservers.list()
    db_infos = instance_models.DBInstance.find_all()
    instances = MgmtInstances.load_status_from_existing(context,
                                        db_infos, mgmt_servers)
    return instances


class SimpleMgmtInstance(imodels.BaseInstance):

    def __init__(self, context, db_info, server, service_status):
        super(SimpleMgmtInstance, self).__init__(context, db_info, server,
                                                 service_status)

    @property
    def status(self):
        if self.deleted:
            return imodels.InstanceStatus.SHUTDOWN
        return super(SimpleMgmtInstance, self).status

    @property
    def local_id(self):
        if self.server:
            return self.server.local_id
        else:
            return None

    @property
    def host(self):
        if self.server:
            return self.server.host
        else:
            return ""

    @property
    def deleted(self):
        if self.server:
            return self.server.deleted
        else:
            return ""

    @property
    def deleted_at(self):
        if self.server:
            return self.server.deleted_at
        else:
            return ""

    @property
    def task_description(self):
        return self.db_info.task_description

    @classmethod
    def load(cls, context, id):
        try:
            instance = load_instance(cls, context, id, needs_server=True)
            client = create_nova_client(context)
            server = client.rdservers.get(instance.server_id)
            instance.server.host = server.host
            instance.server.deleted = server.deleted
            instance.server.deleted_at = server.deleted_at
            instance.server.local_id = server.local_id
            assert instance.server is not None

        except Exception as e:
            LOG.error(e)
            instance = load_instance(cls, context, id, needs_server=False)
        return instance


class MgmtInstance(imodels.Instance):

    def get_diagnostics(self):
        return self.get_guest().get_diagnostics()

    def stop_mysql(self):
        return self.get_guest().stop_mysql()


class MgmtInstances(imodels.Instances):

    @staticmethod
    def load_status_from_existing(context, db_infos, servers):

        def load_instance(context, db, status, server=None):
            return SimpleMgmtInstance(context, db, server, status)

        if context is None:
            raise TypeError("Argument context not defined.")
        find_server = imodels.create_server_list_matcher(servers)
        instances = imodels.Instances._load_servers_status(load_instance, context,
                                                     db_infos, find_server)
        _load_servers(instances, find_server)
        return instances


def _load_servers(instances, find_server):
    for instance in instances:
        db = instance.db_info
        instance.server = None
        try:
            server = find_server(db.id, db.compute_instance_id)
            instance.server = server
        except Exception as ex:
            LOG.error(ex)
    return instances


