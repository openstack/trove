# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack LLC.
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

import webob.exc

from nova.api.openstack import extensions
from nova import log as logging

LOG = logging.getLogger('reddwarf.api.database.contrib.databases')

class DatabasesController(object):

    def index(self, req):
        LOG.info("index call databases")
        return "This is a index of databases"

class UsersController(object):

    def index(self, req):
        LOG.info("index call users")
        return "This is a index of users"


#class DatabasesControllerExtension(wsgi.Controller):
#    @wsgi.action('test_func')
#    def _test_func(self, req, id, body):
#
#        return "Test Func called."

class Databases(extensions.ExtensionDescriptor):
    """The Databases Extension"""

    name = "Databases"
    alias = "DATABASES"
    namespace = "http://TBD"
    updated = "2011-01-22T13:25:27-06:00"

    def __init__(self, ext_mgr):
        ext_mgr.register(self)

    def get_resources(self):
        resources = []
        resource = extensions.ResourceExtension('databases',
            DatabasesController())
        resources.append(resource)
        resource = extensions.ResourceExtension('users',
            UsersController())
        resources.append(resource)

        return resources

    def get_controller_extensions(self):
        extension_list = []

        extension_set = [
#            (DatabasesControllerExtension, 'instances'),
#            (FoxInSocksFlavorGooseControllerExtension, 'flavors'),
#            (FoxInSocksFlavorBandsControllerExtension, 'flavors'),
        ]
        for klass, collection in extension_set:
            controller = klass()
            ext = extensions.ControllerExtension(self, collection, controller)
            extension_list.append(ext)

        return extension_list
