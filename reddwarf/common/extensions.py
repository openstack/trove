# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack LLC.
# Copyright 2011 Justin Santa Barbara
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

from reddwarf.openstack.common import extensions

ExtensionsDescriptor = extensions.ExtensionDescriptor
ResourceExtension = extensions.ResourceExtension

def factory(global_config, **local_config):
    """Paste factory."""
    def _factory(app):
        extensions.DEFAULT_XMLNS = "http://docs.openstack.org/reddwarf"
        ext_mgr = TenantExtensionManager(
            global_config.get('api_extensions_path', ''))
        return extensions.ExtensionMiddleware(app, global_config, ext_mgr)
    return _factory


# Not sure if this is the way we should do it.
# Might need to make openstack common more extensible for tenants
# or any random values in the routes methods (index, show, etc...)
class TenantExtensionManager(extensions.ExtensionManager):

    def __init__(self, path):
        super(TenantExtensionManager, self).__init__(path)

    #TODO(hub-cap): fix openstack-common.extensions to work with tenant ids
    def get_resources(self):
        """Returns a list of ResourceExtension objects."""
        resources = []
        extension_resource = TenantExtensionsResource(self)
        res_ext = extensions.ResourceExtension('{tenant_id}/extensions',
            extension_resource,
            serializer=extension_resource.serializer)
        resources.append(res_ext)
        for alias, ext in self.extensions.iteritems():
            try:
                resources.extend(ext.get_resources())
            except AttributeError:
                # NOTE(dprince): Extension aren't required to have resource
                # extensions
                pass
        return resources


class TenantExtensionsResource(extensions.ExtensionsResource):

    def __init__(self, extension_manager):
        super(TenantExtensionsResource, self).__init__(extension_manager)

    def index(self, req, tenant_id):
        return super(TenantExtensionsResource, self).index(req)

    def show(self, req, id, tenant_id):
        return super(TenantExtensionsResource, self).show(req, id)

    def delete(self, req, id, tenant_id):
        return super(TenantExtensionsResource, self).delete(req, id)

    def create(self, req, tenant_id):
        return super(TenantExtensionsResource, self).create(req)