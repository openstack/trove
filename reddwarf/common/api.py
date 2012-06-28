#    Copyright 2012 OpenStack LLC
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

import routes

from reddwarf.openstack.common import rpc
from reddwarf.common import wsgi
from reddwarf.versions import VersionsController
from reddwarf.flavor.service import FlavorController
from reddwarf.instance.service import InstanceController
from reddwarf.extensions.mgmt.host.instance.service import HostInstanceController


class API(wsgi.Router):
    """API"""
    def __init__(self):
        mapper = routes.Mapper()
        super(API, self).__init__(mapper)
        self._instance_router(mapper)
        self._flavor_router(mapper)
        self._versions_router(mapper)

    def _versions_router(self, mapper):
        versions_resource = VersionsController().create_resource()
        mapper.connect("/", controller=versions_resource, action="show")

    def _instance_router(self, mapper):
        instance_resource = InstanceController().create_resource()
        path = "/{tenant_id}/instances"
        mapper.resource("instance", path, controller=instance_resource,
                        member={'action': 'POST'})

    def _flavor_router(self, mapper):
        flavor_resource = FlavorController().create_resource()
        path = "/{tenant_id}/flavors"
        mapper.resource("flavor", path, controller=flavor_resource)

    def _host_instance_router(self, mapper):
        host_instance_resource = HostInstanceController().create_resource()
        path = "/{tenant_id}/mgmt/hosts/{host_id}/instances"
        mapper.resource("hostinstance", path,
                        controller=host_instance_resource,
                        member={'action': 'POST'})


def app_factory(global_conf, **local_conf):
    return API()
