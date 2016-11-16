# Copyright [2015] Hewlett-Packard Development Company, L.P.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from oslo_log import log as logging

from trove.common.strategies.cluster import base
from trove.guestagent import api as guest_api


LOG = logging.getLogger(__name__)


class RedisGuestAgentStrategy(base.BaseGuestAgentStrategy):

    @property
    def guest_client_class(self):
        return RedisGuestAgentAPI


class RedisGuestAgentAPI(guest_api.API):
    """Cluster Specific Datastore Guest API

    **** VERSION CONTROLLED API ****

    The methods in this class are subject to version control as
    coordinated by guestagent/api.py.  Whenever a change is made to
    any API method in this class, add a version number and comment
    to the top of guestagent/api.py and use the version number as
    appropriate in this file
    """

    def get_node_ip(self):
        LOG.debug("Retrieve ip info from node.")
        version = guest_api.API.API_BASE_VERSION

        return self._call("get_node_ip",
                          guest_api.AGENT_HIGH_TIMEOUT,
                          version=version)

    def get_node_id_for_removal(self):
        LOG.debug("Validating cluster node removal.")
        version = guest_api.API.API_BASE_VERSION

        return self._call("get_node_id_for_removal",
                          guest_api.AGENT_HIGH_TIMEOUT,
                          version=version)

    def remove_nodes(self, node_ids):
        LOG.debug("Removing nodes from cluster.")
        version = guest_api.API.API_BASE_VERSION

        return self._call("remove_nodes", guest_api.AGENT_HIGH_TIMEOUT,
                          version=version, node_ids=node_ids)

    def cluster_meet(self, ip, port):
        LOG.debug("Joining node to cluster.")
        version = guest_api.API.API_BASE_VERSION

        return self._call("cluster_meet", guest_api.AGENT_HIGH_TIMEOUT,
                          version=version, ip=ip, port=port)

    def cluster_addslots(self, first_slot, last_slot):
        LOG.debug("Adding slots %s-%s to cluster.", first_slot, last_slot)
        version = guest_api.API.API_BASE_VERSION

        return self._call("cluster_addslots",
                          guest_api.AGENT_HIGH_TIMEOUT,
                          version=version,
                          first_slot=first_slot, last_slot=last_slot)

    def cluster_complete(self):
        LOG.debug("Notifying cluster install completion.")
        version = guest_api.API.API_BASE_VERSION

        return self._call("cluster_complete", guest_api.AGENT_HIGH_TIMEOUT,
                          version=version)
