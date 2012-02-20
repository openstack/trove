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
                "links": self.servers_viewbuilder._get_links(request, instance.id),
                },
            }

    def index(self, request, servers):
        """Show a list of servers without many details."""
        return self._list_view(self.basic, request, servers)

    def _list_view(self, func, request, servers):
        """Provide a view for a list of instances."""
        # This is coming back as a server entity but we change it to instances
        instance_list = [func(request, instance)["instance"] for instance in servers]
        servers_links = self.servers_viewbuilder._get_collection_links(request, servers)
        instances_dict = dict(instances=instance_list)

        if servers_links:
            instances_dict["servers_links"] = servers_links

        return instances_dict



























#
#
#    def _build_basic(self, server, req, status_lookup):
#        """Build the very basic information for an instance"""
#        instance = {}
#        instance['id'] = server['uuid']
#        instance['name'] = server['name']
#        instance['status'] = status_lookup.get_status_from_server(server).status
#        instance['links'] = self._build_links(req, instance)
#        return instance
#
#    def _build_detail(self, server, req, instance):
#        """Build out a more detailed view of the instance"""
#        flavor_view = flavors.ViewBuilder(_base_url(req), _project_id(req))
#        instance['flavor'] = server['flavor']
#        instance['flavor']['links'] = flavor_view._build_links(instance['flavor'])
#        instance['created'] = server['created']
#        instance['updated'] = server['updated']
#        # Add the hostname
#        if 'hostname' in server:
#            instance['hostname'] = server['hostname']
#
#        # Add volume information
#        dbvolume = self.build_volume(server)
#        if dbvolume:
#            instance['volume'] = dbvolume
#        return instance
#
#    @staticmethod
#    def _build_links(req, instance):
#        """Build the links for the instance"""
#        base_url = _base_url(req)
#        href = os.path.join(base_url, _project_id(req),
#            "instances", str(instance['id']))
#        bookmark = os.path.join(nova_common.remove_version_from_href(base_url),
#            "instances", str(instance['id']))
#        links = [
#                {
#                'rel': 'self',
#                'href': href
#            },
#                {
#                'rel': 'bookmark',
#                'href': bookmark
#            }
#        ]
#        return links
#
#    def build_index(self, server, req, status_lookup):
#        """Build the response for an instance index call"""
#        return self._build_basic(server, req, status_lookup)
#
#    def build_detail(self, server, req, status_lookup):
#        """Build the response for an instance detail call"""
#        instance = self._build_basic(server, req, status_lookup)
#        instance = self._build_detail(server, req, instance)
#        return instance
#
#    def build_single(self, server, req, status_lookup, databases=None,
#                     root_enabled=False, create=False):
#        """
#        Given a server (obtained from the servers API) returns an instance.
#        """
#        instance = self._build_basic(server, req, status_lookup)
#        instance = self._build_detail(server, req, instance)
#        if not create:
#            # Add Database and root_enabled
#            instance['databases'] = databases
#            instance['rootEnabled'] = root_enabled
#
#        return instance
#
#    @staticmethod
#    def build_volume(server):
#        """Given a server dict returns the instance volume dict."""
#        try:
#            volumes = server['volumes']
#            volume_dict = volumes[0]
#        except (KeyError, IndexError):
#            return None
#        if len(volumes) > 1:
#            error_msg = {'instanceId': server['id'],
#                         'msg': "> 1 volumes in the underlying instance!"}
#            LOG.error(error_msg)
#            notifier.notify(notifier.publisher_id("reddwarf-api"),
#                'reddwarf.instance.list', notifier.ERROR,
#                error_msg)
#        return {'size': volume_dict['size']}
#
#
#class MgmtViewBuilder(ViewBuilder):
#    """Management views for an instance"""
#
#    def __init__(self):
#        super(MgmtViewBuilder, self).__init__()
#
#    def build_mgmt_single(self, server, instance_ref, req, status_lookup):
#        """Build out the management view for a single instance"""
#        instance = self._build_basic(server, req, status_lookup)
#        instance = self._build_detail(server, req, instance)
#        instance = self._build_server_details(server, instance)
#        instance = self._build_compute_api_details(instance_ref, instance)
#        return instance
#
#    def build_guest_info(self, instance, status=None, dbs=None, users=None,
#                         root_enabled=None):
#        """Build out all possible information for a guest"""
#        instance['guest_status'] = status.get_guest_status()
#        instance['databases'] = dbs
#        instance['users'] = users
#        root_history = self.build_root_history(instance['id'],
#            root_enabled)
#        instance['root_enabled_at'] = root_history['root_enabled_at']
#        instance['root_enabled_by'] = root_history['root_enabled_by']
#        return instance
#
#    def build_root_history(self, id, root_enabled):
#        if root_enabled is not None:
#            return {
#                'id': id,
#                'root_enabled_at': root_enabled.created_at,
#                'root_enabled_by': root_enabled.user_id}
#        else:
#            return {
#                'id': id,
#                'root_enabled_at': 'Never',
#                'root_enabled_by': 'Nobody'
#            }
#
#    @staticmethod
#    def _build_server_details(server, instance):
#        """Build more information from the servers api"""
#        instance['addresses'] = server['addresses']
#        del instance['links']
#        return instance
#
#    @staticmethod
#    def _build_compute_api_details(instance_ref, instance):
#        """Build out additional information from the compute api"""
#        instance['server_state_description'] = instance_ref['vm_state']
#        instance['host'] = instance_ref['host']
#        instance['account_id'] = instance_ref['user_id']
#        return instance
#
#    @staticmethod
#    def build_volume(server):
#        """Build out a more detailed volumes view"""
#        if 'volumes' in server:
#            volumes = server['volumes']
#            volume_dict = volumes[0]
#        else:
#            volume_dict = None
#        return volume_dict
