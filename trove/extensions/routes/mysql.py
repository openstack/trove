# Copyright 2011 OpenStack Foundation
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

from trove.openstack.common import log as logging

from trove.common import extensions
from trove.extensions.mysql import service


LOG = logging.getLogger(__name__)


class Mysql(extensions.ExtensionsDescriptor):

    def get_name(self):
        return "Mysql"

    def get_description(self):
        return "Non essential MySQL services such as users and schemas"

    def get_alias(self):
        return "MYSQL"

    def get_namespace(self):
        return "http://TBD"

    def get_updated(self):
        return "2011-01-22T13:25:27-06:00"

    def get_resources(self):
        resources = []

        resource = extensions.ResourceExtension(
            'databases',
            service.SchemaController(),
            parent={'member_name': 'instance',
                    'collection_name': '{tenant_id}/instances'})
        resources.append(resource)

        resource = extensions.ResourceExtension(
            'users',
            service.UserController(),
            parent={'member_name': 'instance',
                    'collection_name': '{tenant_id}/instances'},
            member_actions={'update': 'PUT'},
            collection_actions={'update_all': 'PUT'})
        resources.append(resource)

        collection_url = '{tenant_id}/instances/:instance_id/users'
        resource = extensions.ResourceExtension(
            'databases',
            service.UserAccessController(),
            parent={'member_name': 'user',
                    'collection_name': collection_url},
            collection_actions={'update': 'PUT'})
        resources.append(resource)

        resource = extensions.ResourceExtension(
            'root',
            service.RootController(),
            parent={'member_name': 'instance',
                    'collection_name': '{tenant_id}/instances'})
        resources.append(resource)

        return resources
