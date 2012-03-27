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

import logging

from reddwarf.common import extensions
from reddwarf.extensions.mysql import service


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
            '{tenant_id}/schemas/{instance_id}',
            service.SchemaController())
        resources.append(resource)
        resource = extensions.ResourceExtension(
            '{tenant_id}/users/{instance_id}',
            service.UserController())
        resources.append(resource)

        return resources
