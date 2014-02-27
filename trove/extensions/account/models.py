# Copyright 2010-2011 OpenStack Foundation
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

from trove.openstack.common import log as logging

from trove.common.remote import create_nova_client
from trove.instance.models import DBInstance
from trove.extensions.mgmt.instances.models import MgmtInstances

LOG = logging.getLogger(__name__)


class Server(object):
    """Disguises the Nova account instance dict as a server object."""

    def __init__(self, server):
        self.id = server['id']
        self.status = server['status']
        self.name = server['name']
        self.host = server.get('host') or server['hostId']

    @staticmethod
    def list_from_account_server_list(servers):
        """Converts a list of server account dicts to this object."""
        return [Server(server) for server in servers]


class Account(object):
    """Contains all instances owned by an account."""

    def __init__(self, id, instances):
        self.id = id
        self.instances = instances

    @staticmethod
    def load(context, id):
        client = create_nova_client(context)
        account = client.accounts.get_instances(id)
        db_infos = DBInstance.find_all(tenant_id=id, deleted=False)
        servers = [Server(server) for server in account.servers]
        instances = MgmtInstances.load_status_from_existing(context, db_infos,
                                                            servers)
        return Account(id, instances)


class AccountsSummary(object):

    def __init__(self, accounts):
        self.accounts = accounts

    @classmethod
    def load(cls):
        # TODO(pdmars): This should probably be changed to a more generic
        # database filter query if one is added, however, this should suffice
        # for now.
        db_infos = DBInstance.find_all(deleted=False)
        tenant_ids_for_instances = [db_info.tenant_id for db_info in db_infos]
        tenant_ids = set(tenant_ids_for_instances)
        LOG.debug("All tenants with instances: %s" % tenant_ids)
        accounts = []
        for tenant_id in tenant_ids:
            num_instances = tenant_ids_for_instances.count(tenant_id)
            accounts.append({'id': tenant_id, 'num_instances': num_instances})
        return cls(accounts)
