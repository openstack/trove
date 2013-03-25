#    Copyright 2012 OpenStack Foundation
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

from reddwarf.common import wsgi
from reddwarf.flavor.service import FlavorController
from reddwarf.instance.service import InstanceController
from reddwarf.limits.service import LimitsController
from reddwarf.backup.service import BackupController
from reddwarf.versions import VersionsController


class API(wsgi.Router):
    """API"""
    def __init__(self):
        mapper = routes.Mapper()
        super(API, self).__init__(mapper)
        self._instance_router(mapper)
        self._flavor_router(mapper)
        self._versions_router(mapper)
        self._limits_router(mapper)
        self._backups_router(mapper)

    def _versions_router(self, mapper):
        versions_resource = VersionsController().create_resource()
        mapper.connect("/", controller=versions_resource, action="show")

    def _instance_router(self, mapper):
        instance_resource = InstanceController().create_resource()
        path = "/{tenant_id}/instances"
        mapper.resource("instance", path, controller=instance_resource,
                        member={'action': 'POST', 'backups': 'GET'})

    def _flavor_router(self, mapper):
        flavor_resource = FlavorController().create_resource()
        path = "/{tenant_id}/flavors"
        mapper.resource("flavor", path, controller=flavor_resource)

    def _limits_router(self, mapper):
        limits_resource = LimitsController().create_resource()
        path = "/{tenant_id}/limits"
        mapper.resource("limits", path, controller=limits_resource)

    def _backups_router(self, mapper):
        backups_resource = BackupController().create_resource()
        path = "/{tenant_id}/backups"
        mapper.resource("backups", path, controller=backups_resource,
                        member={'action': 'POST'})


def app_factory(global_conf, **local_conf):
    return API()
