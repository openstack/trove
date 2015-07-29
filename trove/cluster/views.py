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

from oslo_log import log as logging

from trove.common import cfg
from trove.common.strategies.cluster import strategy
from trove.common.views import create_links
from trove.instance.views import InstanceDetailView

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class ClusterView(object):

    def __init__(self, cluster, req=None, load_servers=True):
        self.cluster = cluster
        self.req = req
        self.load_servers = load_servers

    def data(self):
        instances, ip_list = self.build_instances()
        cluster_dict = {
            "id": self.cluster.id,
            "name": self.cluster.name,
            "task": {"id": self.cluster.task_id,
                     "name": self.cluster.task_name,
                     "description": self.cluster.task_description},
            "created": self.cluster.created,
            "updated": self.cluster.updated,
            "links": self._build_links(),
            "datastore": {"type": self.cluster.datastore.name,
                          "version": self.cluster.datastore_version.name},
            "instances": instances
        }
        if ip_list:
            cluster_dict["ip"] = ip_list

        extended_properties = self.get_extended_properties()
        if extended_properties:
            cluster_dict["extended_properties"] = extended_properties

        LOG.debug(cluster_dict)
        return {"cluster": cluster_dict}

    def _build_links(self):
        return create_links("clusters", self.req, self.cluster.id)

    def _build_instances(self, ip_to_be_published_for=[],
                         instance_dict_to_be_published_for=[]):
        instances = []
        ip_list = []
        if self.load_servers:
            cluster_instances = self.cluster.instances
        else:
            cluster_instances = self.cluster.instances_without_server
        for instance in cluster_instances:
            instance_dict = {
                "id": instance.id,
                "name": instance.name,
                "type": instance.type,
                "links": create_links("instances", self.req, instance.id)
            }
            if instance.shard_id:
                instance_dict["shard_id"] = instance.shard_id
            if self.load_servers:
                instance_dict["status"] = instance.status
                if CONF.get(instance.datastore_version.manager).volume_support:
                    instance_dict["volume"] = {"size": instance.volume_size}
                instance_dict["flavor"] = self._build_flavor_info(
                    instance.flavor_id)
            instance_ips = instance.get_visible_ip_addresses()
            if self.load_servers and instance_ips:
                instance_dict["ip"] = instance_ips
                if instance.type in ip_to_be_published_for:
                    ip_list.append(instance_ips[0])
            if instance.type in instance_dict_to_be_published_for:
                instances.append(instance_dict)
        ip_list.sort()
        return instances, ip_list

    def build_instances(self):
        raise NotImplementedError()

    def get_extended_properties(self):
        return None

    def _build_flavor_info(self, flavor_id):
        return {
            "id": flavor_id,
            "links": create_links("flavors", self.req, flavor_id)
        }


class ClusterInstanceDetailView(InstanceDetailView):
    def __init__(self, instance, req):
        super(ClusterInstanceDetailView, self).__init__(instance, req=req)

    def data(self):
        result = super(ClusterInstanceDetailView, self).data()
        return result


class ClustersView(object):
    def __init__(self, clusters, req=None):
        self.clusters = clusters
        self.req = req

    def data(self):
        data = []
        for cluster in self.clusters:
            data.append(self.data_for_cluster(cluster))
        return {'clusters': data}

    def data_for_cluster(self, cluster):
        view = load_view(cluster, req=self.req, load_servers=False)
        return view.data()['cluster']


def load_view(cluster, req, load_servers=True):
    manager = cluster.datastore_version.manager
    return strategy.load_api_strategy(manager).cluster_view_class(
        cluster, req, load_servers)
