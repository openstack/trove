#    Copyright 2011 OpenStack LLC
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

import os


from nova import log as logging
from nova.api.openstack.compute.views import servers as views_servers
#from reddwarf.api.database.views import flavors


LOG = logging.getLogger('reddwarf.api.views.instance')
LOG.setLevel(logging.DEBUG)


def _project_id(req):
    return getattr(req.environ['nova.context'], 'project_id', '')


def _base_url(req):
    return req.application_url


class ViewBuilder(object):
    """Views for an instance"""

    def __init__(self):
        self.servers_viewbuilder = views_servers.ViewBuilder()

    def basic(self, request, instance):
        return {
            "instance": {
                "id": instance.id,
                "name": instance.name,
                "links": self.servers_viewbuilder._get_links(request,
                                                             instance.id),
                },
            }

    def index(self, request, servers):
        """Show a list of servers without many details."""
        return self._list_view(self.basic, request, servers)

    def _list_view(self, func, request, servers):
        """Provide a view for a list of instances."""
        # This is coming back as a server entity but we change it to instances
        instance_list = [func(request, instance)["instance"]
                         for instance in servers]
        servers_links = self.servers_viewbuilder._get_collection_links(
            request, servers)
        instances_dict = dict(instances=instance_list)

        if servers_links:
            instances_dict["servers_links"] = servers_links

        return instances_dict
