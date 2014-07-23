# Copyright 2014 Hewlett-Packard Development Company, L.P.
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

from trove.common import exception
from trove.common import remote
from trove.network import base
from trove.openstack.common import log as logging
from neutronclient.common import exceptions as neutron_exceptions


LOG = logging.getLogger(__name__)

CONST = {'IPv4': "IPv4",
         'IPv6': "IPv6",
         'INGRESS': "ingress",
         'EGRESS': "egress",
         'PROTO_NAME_TCP': 'tcp',
         'PROTO_NAME_ICMP': 'icmp',
         'PROTO_NAME_ICMP_V6': 'icmpv6',
         'PROTO_NAME_UDP': 'udp'}


class NovaNetworkStruct(object):
    def __init__(self, **properties):
        self.__dict__.update(properties)


class NeutronDriver(base.NetworkDriver):

    def __init__(self, context):
        try:
            self.client = remote.create_neutron_client(context)
        except neutron_exceptions.NeutronClientException as e:
            raise exception.TroveError(str(e))

    def get_sec_group_by_id(self, group_id):
        try:
            return self.client.show_security_group(security_group=group_id)
        except neutron_exceptions.NeutronClientException as e:
            LOG.exception('Failed to get remote security group')
            raise exception.TroveError(str(e))

    def create_security_group(self, name, description):
        try:
            sec_group_body = {"security_group": {"name": name,
                                                 "description": description}}
            sec_group = self.client.create_security_group(body=sec_group_body)
            return self._convert_to_nova_security_group_format(
                sec_group.get('security_group', sec_group))

        except neutron_exceptions.NeutronClientException as e:
            LOG.exception('Failed to create remote security group')
            raise exception.SecurityGroupCreationError(str(e))

    def delete_security_group(self, sec_group_id):
        try:
            self.client.delete_security_group(security_group=sec_group_id)
        except neutron_exceptions.NeutronClientException as e:
            LOG.exception('Failed to delete remote security group')
            raise exception.SecurityGroupDeletionError(str(e))

    def add_security_group_rule(self, sec_group_id, protocol,
                                from_port, to_port, cidr,
                                direction=CONST['INGRESS'],
                                ethertype=CONST['IPv4']):
        try:
            secgroup_rule_body = {"security_group_rule":
                                  {"security_group_id": sec_group_id,
                                   "protocol": protocol,
                                   "port_range_min": from_port,
                                   "port_range_max": to_port,
                                   "remote_ip_prefix": cidr,
                                   "direction": direction,  # ingress | egress
                                   "ethertype": ethertype,  # IPv4 | IPv6
                                   }}

            secgroup_rule = self.client.create_security_group_rule(
                secgroup_rule_body)
            return self._convert_to_nova_security_group_rule_format(
                secgroup_rule.get('security_group_rule', secgroup_rule))
        except neutron_exceptions.NeutronClientException as e:
             # ignore error if rule already exists
            if e.status_code == 409:
                LOG.exception("secgroup rule already exists")
            else:
                LOG.exception('Failed to add rule to remote security group')
                raise exception.SecurityGroupRuleCreationError(str(e))

    def delete_security_group_rule(self, sec_group_rule_id):
        try:
            self.client.delete_security_group_rule(
                security_group_rule=sec_group_rule_id)

        except neutron_exceptions.NeutronClientException as e:
            LOG.exception('Failed to delete rule to remote security group')
            raise exception.SecurityGroupRuleDeletionError(str(e))

    def _convert_to_nova_security_group_format(self, security_group):
        nova_group = {}
        nova_group['id'] = security_group['id']
        nova_group['description'] = security_group['description']
        nova_group['name'] = security_group['name']
        nova_group['project_id'] = security_group['tenant_id']
        nova_group['rules'] = []
        for rule in security_group.get('security_group_rules', []):
            if rule['direction'] == 'ingress':
                nova_group['rules'].append(
                    self._convert_to_nova_security_group_rule_format(rule))

        return NovaNetworkStruct(**nova_group)

    def _convert_to_nova_security_group_rule_format(self, rule):
        nova_rule = {}
        nova_rule['id'] = rule['id']
        nova_rule['parent_group_id'] = rule['security_group_id']
        nova_rule['protocol'] = rule['protocol']
        if (nova_rule['protocol'] and rule.get('port_range_min') is None and
                rule.get('port_range_max') is None):
            if rule['protocol'].upper() in ['TCP', 'UDP']:
                nova_rule['from_port'] = 1
                nova_rule['to_port'] = 65535
            else:
                nova_rule['from_port'] = -1
                nova_rule['to_port'] = -1
        else:
            nova_rule['from_port'] = rule.get('port_range_min')
            nova_rule['to_port'] = rule.get('port_range_max')
        nova_rule['group_id'] = rule['remote_group_id']
        nova_rule['cidr'] = rule.get('remote_ip_prefix')
        return NovaNetworkStruct(**nova_rule)
