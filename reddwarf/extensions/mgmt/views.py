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

from collections import defaultdict


def tree():
    return defaultdict(tree)


def get_ip_address(addresses):
    if addresses is not None and \
       addresses.get('private') is not None and \
       len(addresses['private']) > 0:
        return [addr.get('addr') for addr in addresses['private']]


class InstanceView(object):

    def __init__(self, instance, add_addresses=False):
        self.instance = instance
        self.add_addresses = add_addresses

    def data(self):
        ip = get_ip_address(self.instance.addresses)
        instance_dict = {
            "tenant_id": self.instance.server.tenant_id,
            "id": self.instance.id,
            "name": self.instance.name,
            "status": self.instance.status,
            "links": self.instance.links,
            "created": self.instance.created,
            "flavor": self.instance.flavor,
            "updated": self.instance.updated
        }
        if self.add_addresses and ip is not None and len(ip) > 0:
            instance_dict['ip'] = ip
        return {"instance": instance_dict}


class InstancesView(InstanceView):

    def __init__(self, instances, add_addresses=False):
        self.instances = instances
        self.add_addresses = add_addresses

    def data(self):
        data = []
        # These are model instances
        for instance in self.instances:
            data.append(self.data_for_instance(instance))
        return {'instances': data}

    def data_for_instance(self, instance):
        return InstanceView(instance,
                            self.add_addresses).data()['instance']


class RootHistoryView(object):

    def __init__(self, instance_id, enabled='Never', user_id='Nobody'):
        self.instance_id = instance_id
        self.enabled = enabled
        self.user = user_id

    def data(self):
        res = tree()
        res['root_history']['id'] = self.instance_id
        res['root_history']['enabled'] = self.enabled
        res['root_history']['user'] = self.user
        return res
