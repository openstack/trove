# Copyright 2014 eBay Software Foundation
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

from trove.common import cfg
from trove.common.strategies.cluster import base
from trove.guestagent import api as guest_api
from trove.openstack.common import log as logging


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class MongoDbGuestAgentStrategy(base.BaseGuestAgentStrategy):

    @property
    def guest_client_class(self):
        return MongoDbGuestAgentAPI


class MongoDbGuestAgentAPI(guest_api.API):

    def add_shard(self, replica_set_name, replica_set_member):
        LOG.debug("Adding shard with replSet %(replica_set_name)s and member "
                  "%(replica_set_member)s for instance "
                  "%(id)s" % {'replica_set_name': replica_set_name,
                              'replica_set_member': replica_set_member,
                              'id': self.id})
        return self._call("add_shard", guest_api.AGENT_HIGH_TIMEOUT,
                          self.version_cap,
                          replica_set_name=replica_set_name,
                          replica_set_member=replica_set_member)

    def add_members(self, members):
        LOG.debug("Adding members %(members)s on instance %(id)s" % {
            'members': members, 'id': self.id})
        return self._call("add_members", guest_api.AGENT_HIGH_TIMEOUT,
                          self.version_cap, members=members)

    def add_config_servers(self, config_servers):
        LOG.debug("Adding config servers %(config_servers)s for instance "
                  "%(id)s" % {'config_servers': config_servers,
                              'id': self.id})
        return self._call("add_config_servers", guest_api.AGENT_HIGH_TIMEOUT,
                          self.version_cap, config_servers=config_servers)

    def cluster_complete(self):
        LOG.debug("Notify regarding cluster install completion")
        return self._call("cluster_complete", guest_api.AGENT_LOW_TIMEOUT,
                          self.version_cap)

    def get_key(self):
        LOG.debug("Requesting cluster key from guest")
        return self._call("get_key", guest_api.AGENT_LOW_TIMEOUT,
                          self.version_cap)

    def create_admin_user(self, password):
        LOG.debug("Creating admin user")
        return self._call("create_admin_user", guest_api.AGENT_HIGH_TIMEOUT,
                          self.version_cap, password=password)
