# vim: tabstop=4 shiftwidth=4 softtabstop=4

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
from trove.common import wsgi
from trove.extensions.mgmt.instances.service import MgmtInstanceController
from trove.extensions.mgmt.host.service import HostController
from trove.extensions.mgmt.quota.service import QuotaController
from trove.extensions.mgmt.host.instance import service as hostservice
from trove.extensions.mgmt.volume.service import StorageController


LOG = logging.getLogger(__name__)


class Mgmt(extensions.ExtensionsDescriptor):

    def get_name(self):
        return "Mgmt"

    def get_description(self):
        return "MGMT services such as details diagnostics"

    def get_alias(self):
        return "Mgmt"

    def get_namespace(self):
        return "http://TBD"

    def get_updated(self):
        return "2011-01-22T13:25:27-06:00"

    def get_resources(self):
        resources = []
        serializer = wsgi.TroveResponseSerializer(
            body_serializers={'application/xml':
                              wsgi.TroveXMLDictSerializer()})
        instances = extensions.ResourceExtension(
            '{tenant_id}/mgmt/instances',
            MgmtInstanceController(),
            deserializer=wsgi.TroveRequestDeserializer(),
            serializer=serializer,
            member_actions={'root': 'GET',
                            'diagnostics': 'GET',
                            'hwinfo': 'GET',
                            'action': 'POST'})
        resources.append(instances)

        hosts = extensions.ResourceExtension(
            '{tenant_id}/mgmt/hosts',
            HostController(),
            deserializer=wsgi.RequestDeserializer(),
            serializer=serializer,
            member_actions={})
        resources.append(hosts)

        quota = extensions.ResourceExtension(
            '{tenant_id}/mgmt/quotas',
            QuotaController(),
            deserializer=wsgi.RequestDeserializer(),
            serializer=serializer,
            member_actions={})
        resources.append(quota)

        storage = extensions.ResourceExtension(
            '{tenant_id}/mgmt/storage',
            StorageController(),
            deserializer=wsgi.RequestDeserializer(),
            serializer=serializer,
            member_actions={})
        resources.append(storage)

        host_instances = extensions.ResourceExtension(
            'instances',
            hostservice.HostInstanceController(),
            parent={'member_name': 'host',
                    'collection_name': '{tenant_id}/mgmt/hosts'},
            deserializer=wsgi.RequestDeserializer(),
            serializer=serializer,
            collection_actions={'action': 'POST'})
        resources.append(host_instances)

        return resources
