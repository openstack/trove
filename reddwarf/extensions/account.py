# Copyright 2012 OpenStack LLC.
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
from reddwarf.common import wsgi
from reddwarf.extensions.account import service


LOG = logging.getLogger(__name__)


class Account(extensions.ExtensionsDescriptor):

    def get_name(self):
        return "Account"

    def get_description(self):
        return "Account information with instances"

    def get_alias(self):
        return "Account"

    def get_namespace(self):
        return "http://TBD"

    def get_updated(self):
        return "2012-06-07T13:25:27-06:00"

    def get_resources(self):
        resources = []
        serializer = wsgi.ReddwarfResponseSerializer(
            body_serializers={'application/xml':
                              wsgi.ReddwarfXMLDictSerializer()})
        resource = extensions.ResourceExtension(
            '{tenant_id}/mgmt/accounts',
            service.AccountController(),
            deserializer=wsgi.RequestDeserializer(),
            serializer=serializer)
        resources.append(resource)

        return resources
