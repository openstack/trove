# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2013 Hewlett-Packard Development Company, L.P.
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
#

from reddwarf.openstack.common import log as logging

from reddwarf.common import extensions
from reddwarf.common import wsgi
from reddwarf.common import cfg
from reddwarf.extensions.security_group import service


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


# The Extensions module from openstack common expects the classname of the
# extension to be loaded to be the exact same as the filename, except with
# a capital first letter. That's the reason this class has such a funky name.
class Security_group(extensions.ExtensionsDescriptor):

    def get_name(self):
        return "SecurityGroup"

    def get_description(self):
        return "Security Group related operations such as list \
security groups and manage security group rules."

    def get_alias(self):
        return "SecurityGroup"

    def get_namespace(self):
        return "http://TBD"

    def get_updated(self):
        return "2012-02-26T17:25:27-08:00"

    def get_resources(self):
        resources = []
        serializer = wsgi.ReddwarfResponseSerializer(
            body_serializers={'application/xml':
                              wsgi.ReddwarfXMLDictSerializer()})

        if CONF.reddwarf_security_groups_support:
            security_groups = extensions.ResourceExtension(
                '{tenant_id}/security-groups',
                service.SecurityGroupController(),
                deserializer=wsgi.ReddwarfRequestDeserializer(),
                serializer=serializer)
            resources.append(security_groups)

            security_group_rules = extensions.ResourceExtension(
                '{tenant_id}/security-group-rules',
                service.SecurityGroupRuleController(),
                deserializer=wsgi.ReddwarfRequestDeserializer(),
                serializer=serializer)
            resources.append(security_group_rules)

        return resources
