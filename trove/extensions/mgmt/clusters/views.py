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

from trove.cluster.views import ClusterView
from trove.common import strategy


class MgmtClusterView(ClusterView):

    def __init__(self, cluster, req=None, load_servers=True):
        super(MgmtClusterView, self).__init__(cluster, req, load_servers)

    def data(self):
        result = super(MgmtClusterView, self).data()
        result['cluster']['tenant_id'] = self.cluster.tenant_id
        result['cluster']['deleted'] = bool(self.cluster.deleted)
        if self.cluster.deleted_at:
            result['cluster']['deleted_at'] = self.cluster.deleted_at
        return result

    def build_instances(self):
        raise NotImplementedError()


class MgmtClustersView(object):
    """Shows a list of MgmtCluster objects."""

    def __init__(self, clusters, req=None):
        self.clusters = clusters
        self.req = req

    def data(self):
        data = []
        for cluster in self.clusters:
            data.append(self.data_for_cluster(cluster))
        return {'clusters': data}

    def data_for_cluster(self, cluster):
        view = load_mgmt_view(cluster, req=self.req, load_servers=False)
        return view.data()['cluster']


def load_mgmt_view(cluster, req, load_servers=True):
    manager = cluster.datastore_version.manager
    return strategy.load_api_strategy(manager).mgmt_cluster_view_class(
        cluster, req, load_servers)
