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
LOG = logging.getLogger(__name__)


def get_ip_address(addresses):
    if addresses is not None and \
       addresses.get('private') is not None and \
       len(addresses['private']) > 0:
        return [addr.get('addr') for addr in addresses['private']]


def get_volumes(volumes):
    LOG.debug("volumes - %s" % volumes)
    if volumes is not None and len(volumes) > 0:
        return {'size': volumes[0].get('size')}


class InstanceView(object):

    def __init__(self, instance, add_addresses=False, add_volumes=False):
        self.instance = instance
        self.add_addresses = add_addresses
        self.add_volumes = add_volumes

    def data(self):
        ip = get_ip_address(self.instance.addresses)
        volumes = get_volumes(self.instance.volumes)
        instance_dict = {
            "id": self.instance.id,
            "name": self.instance.name,
            "status": self.instance.status,
            "links": self.instance.links
        }
        if self.add_addresses and ip is not None and len(ip) > 0:
            instance_dict['ip'] = ip
        if self.add_volumes and volumes is not None:
            instance_dict['volume'] = volumes
        LOG.debug(instance_dict)
        return {"instance": instance_dict}


class InstanceDetailView(InstanceView):

    def __init__(self, instance, add_addresses=False, roothistory=None):
        super(InstanceDetailView, self).__init__(instance, add_addresses)
        self.roothistory = roothistory

    def data(self):
        result = super(InstanceDetailView, self).data()
        result['instance']['created'] = self.instance.created
        result['instance']['flavor'] = self.instance.flavor
        result['instance']['updated'] = self.instance.updated
        if self.roothistory:
            result['instance']['root_enabled_at'] = self.roothistory.created
            result['instance']['root_enabled_by'] = self.roothistory.user
        return result


class InstancesView(object):

    def __init__(self, instances, add_addresses=False, add_volumes=False):
        self.instances = instances
        self.add_addresses = add_addresses
        self.add_volumes = add_volumes

    def data(self):
        data = []
        # These are model instances
        for instance in self.instances:
            data.append(self.data_for_instance(instance))
        return {'instances': data}

    def data_for_instance(self, instance):
        return InstanceView(instance,
                            self.add_addresses).data()['instance']


class InstancesDetailView(InstancesView):

    def data_for_instance(self, instance):
        return InstanceDetailView(instance,
                                  self.add_addresses,
                                  self.add_volumes).data()['instance']
