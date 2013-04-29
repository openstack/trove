#    Copyright 2012 OpenStack Foundation
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

from reddwarf.openstack.common import log as logging

from reddwarf.common.remote import create_nova_client
from reddwarf.common.remote import create_nova_volume_client
from reddwarf.instance import models as imodels
from reddwarf.instance.models import load_instance
from reddwarf.instance import models as instance_models
from reddwarf.extensions.mysql import models as mysql_models


LOG = logging.getLogger(__name__)


def load_mgmt_instances(context, deleted=None):
    client = create_nova_client(context)
    mgmt_servers = client.rdservers.list()
    db_infos = None
    if deleted is not None:
        db_infos = instance_models.DBInstance.find_all(deleted=deleted)
    else:
        db_infos = instance_models.DBInstance.find_all()
    instances = MgmtInstances.load_status_from_existing(
        context,
        db_infos,
        mgmt_servers)
    return instances


def load_mgmt_instance(cls, context, id):
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
    def deleted(self):
        return self.db_info.deleted

    @property
    def deleted_at(self):
        return self.db_info.deleted_at

    @classmethod
    def load(cls, context, id):
        return load_mgmt_instance(cls, context, id)

    @property
    def task_description(self):
        return self.db_info.task_description


class DetailedMgmtInstance(SimpleMgmtInstance):

    def __init__(self, *args, **kwargs):
        super(DetailedMgmtInstance, self).__init__(*args, **kwargs)
        self.volume = None
        self.volume_used = None
        self.root_history = None

    @classmethod
    def load(cls, context, id):
        instance = load_mgmt_instance(cls, context, id)
        client = create_nova_volume_client(context)
        try:
            instance.volume = client.volumes.get(instance.volume_id)
        except Exception as ex:
            instance.volume = None
        # Populate the volume_used attribute from the guest agent.
        instance_models.load_guest_info(instance, context, id)
        instance.root_history = mysql_models.RootHistory.load(context=context,
                                                              instance_id=id)
        return instance


class MgmtInstance(imodels.Instance):

    def get_diagnostics(self):
        return self.get_guest().get_diagnostics()

    def stop_mysql(self):
        return self.get_guest().stop_mysql()

    def get_hwinfo(self):
        return self.get_guest().get_hwinfo()


class MgmtInstances(imodels.Instances):

    @staticmethod
    def load_status_from_existing(context, db_infos, servers):

        def load_instance(context, db, status, server=None):
            return SimpleMgmtInstance(context, db, server, status)

        if context is None:
            raise TypeError("Argument context not defined.")
        find_server = imodels.create_server_list_matcher(servers)
        instances = imodels.Instances._load_servers_status(load_instance,
                                                           context, db_infos,
                                                           find_server)
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
