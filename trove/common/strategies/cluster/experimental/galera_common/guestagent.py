# Copyright [2015] Hewlett-Packard Development Company, L.P.
# Copyright 2016 Tesora Inc.
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
from trove.common.strategies.cluster import base as cluster_base
from trove.guestagent import api as guest_api


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class GaleraCommonGuestAgentStrategy(cluster_base.BaseGuestAgentStrategy):

    @property
    def guest_client_class(self):
        return GaleraCommonGuestAgentAPI


class GaleraCommonGuestAgentAPI(guest_api.API):

    def install_cluster(self, replication_user, cluster_configuration,
                        bootstrap):
        """Install the cluster."""
        LOG.debug("Installing Galera cluster.")
        self._call("install_cluster", CONF.cluster_usage_timeout,
                   self.version_cap,
                   replication_user=replication_user,
                   cluster_configuration=cluster_configuration,
                   bootstrap=bootstrap)

    def reset_admin_password(self, admin_password):
        """Store this password on the instance as the admin password."""
        self._call("reset_admin_password", CONF.cluster_usage_timeout,
                   self.version_cap,
                   admin_password=admin_password)

    def cluster_complete(self):
        """Set the status that the cluster is build is complete."""
        LOG.debug("Notifying cluster install completion.")
        return self._call("cluster_complete", guest_api.AGENT_HIGH_TIMEOUT,
                          self.version_cap)

    def get_cluster_context(self):
        """Get the context of the cluster."""
        LOG.debug("Getting the cluster context.")
        return self._call("get_cluster_context", guest_api.AGENT_HIGH_TIMEOUT,
                          self.version_cap)

    def write_cluster_configuration_overrides(self, cluster_configuration):
        """Write an updated the cluster configuration."""
        LOG.debug("Writing an updated the cluster configuration.")
        self._call("write_cluster_configuration_overrides",
                   guest_api.AGENT_HIGH_TIMEOUT,
                   self.version_cap,
                   cluster_configuration=cluster_configuration)
