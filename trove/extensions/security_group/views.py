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

from trove.openstack.common import log as logging
import os

LOG = logging.getLogger(__name__)


def _base_url(req):
    return req.application_url


class SecurityGroupView(object):

    def __init__(self, secgroup, rules, req, tenant_id):
        self.secgroup = secgroup
        self.rules = rules
        self.request = req
        self.tenant_id = tenant_id

    def _build_links(self):
        """Build the links for the secgroup"""
        base_url = _base_url(self.request)
        href = os.path.join(base_url, self.tenant_id,
                            "security-groups", str(self.secgroup['id']))
        links = [
            {
                'rel': 'self',
                'href': href
            }
        ]
        return links

    def _build_rules(self):
        rules = []

        if self.rules is None:
            return rules

        for rule in self.rules:
            rules.append({'id': str(rule['id']),
                          'protocol': rule['protocol'],
                          'from_port': rule['from_port'],
                          'to_port': rule['to_port'],
                          'cidr': rule['cidr'],
                          })
        return rules

    def data(self):
        return {"id": self.secgroup['id'],
                "name": self.secgroup['name'],
                "description": self.secgroup['description'],
                "instance_id": self.secgroup['instance_id'],
                "rules": self._build_rules(),
                "links": self._build_links(),
                "created": self.secgroup['created'],
                "updated": self.secgroup['updated']
                }

    def show(self):
        return {"security_group": self.data()}

    def create(self):
        return self.show()


class SecurityGroupsView(object):

    def __init__(self, secgroups, rules_dict, req, tenant_id):
        self.secgroups = secgroups
        self.rules = rules_dict
        self.request = req
        self.tenant_id = tenant_id

    def list(self):
        groups_data = []

        for secgroup in self.secgroups:
            rules = \
                self.rules[secgroup['id']] if self.rules is not None else None
            groups_data.append(SecurityGroupView(secgroup,
                                                 rules,
                                                 self.request,
                                                 self.tenant_id).data())

        return {"security_groups": groups_data}


class SecurityGroupRulesView(object):

    def __init__(self, rule, req, tenant_id):
        self.rule = rule
        self.request = req
        self.tenant_id = tenant_id

    def _build_create(self):
        return {"security_group_rule":
                {"id": str(self.rule['id']),
                 "security_group_id": self.rule['group_id'],
                 "protocol": self.rule['protocol'],
                 "from_port": self.rule['from_port'],
                 "to_port": self.rule['to_port'],
                 "cidr": self.rule['cidr'],
                 "created": self.rule['created']
                 }
                }

    def create(self):
        return self._build_create()
