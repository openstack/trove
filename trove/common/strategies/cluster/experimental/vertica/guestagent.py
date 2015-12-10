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

from trove.common import cfg
from trove.common.strategies.cluster import base
from trove.guestagent import api as guest_api


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class VerticaGuestAgentStrategy(base.BaseGuestAgentStrategy):

    @property
    def guest_client_class(self):
        return VerticaGuestAgentAPI


class VerticaGuestAgentAPI(guest_api.API):

    def get_public_keys(self, user):
        LOG.debug("Getting public keys for user: %s." % user)
        return self._call("get_public_keys", guest_api.AGENT_HIGH_TIMEOUT,
                          self.version_cap, user=user)

    def authorize_public_keys(self, user, public_keys):
        LOG.debug("Authorizing public keys for user: %s." % user)
        return self._call("authorize_public_keys",
                          guest_api.AGENT_HIGH_TIMEOUT, self.version_cap,
                          user=user, public_keys=public_keys)

    def install_cluster(self, members):
        LOG.debug("Installing Vertica cluster on members: %s." % members)
        return self._call("install_cluster", CONF.cluster_usage_timeout,
                          self.version_cap, members=members)

    def grow_cluster(self, members):
        LOG.debug("Growing Vertica cluster with members: %s." % members)
        return self._call("grow_cluster", CONF.cluster_usage_timeout,
                          self.version_cap, members=members)

    def shrink_cluster(self, members):
        LOG.debug("Shrinking Vertica cluster with members: %s." % members)
        return self._call("shrink_cluster", CONF.cluster_usage_timeout,
                          self.version_cap, members=members)

    def mark_design_ksafe(self, k):
        LOG.debug("Setting vertica k-safety level to : %s." % k)
        return self._call("mark_design_ksafe", CONF.cluster_usage_timeout,
                          self.version_cap, k=k)

    def cluster_complete(self):
        LOG.debug("Notifying cluster install completion.")
        return self._call("cluster_complete", guest_api.AGENT_HIGH_TIMEOUT,
                          self.version_cap)
