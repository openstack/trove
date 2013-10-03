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

import re
from trove.openstack.common import log as logging
from trove.common import cfg
from trove.common.views import create_links
from trove.instance import models

LOG = logging.getLogger(__name__)

CONF = cfg.CONF


def get_ip_address(addresses):
    if addresses is None:
        return None
    IPs = []
    for label in addresses:
        if (re.search(CONF.network_label_regex, label) and
                len(addresses[label]) > 0):
            IPs.extend([addr.get('addr') for addr in addresses[label]])
    return IPs


class InstanceView(object):
    """Uses a SimpleInstance."""

    def __init__(self, instance, req=None):
        self.instance = instance
        self.req = req

    def data(self):
        instance_dict = {
            "id": self.instance.id,
            "name": self.instance.name,
            "status": self.instance.status,
            "links": self._build_links(),
            "flavor": self._build_flavor_info(),
        }
        if CONF.trove_volume_support:
            instance_dict['volume'] = {'size': self.instance.volume_size}

        LOG.debug(instance_dict)
        return {"instance": instance_dict}

    def _build_links(self):
        return create_links("instances", self.req, self.instance.id)

    def _build_flavor_info(self):
        return {
            "id": self.instance.flavor_id,
            "links": self._build_flavor_links()
        }

    def _build_flavor_links(self):
        return create_links("flavors", self.req,
                            self.instance.flavor_id)


class InstanceDetailView(InstanceView):
    """Works with a full-blown instance."""

    def __init__(self, instance, req):
        super(InstanceDetailView, self).__init__(instance,
                                                 req=req)

    def data(self):
        result = super(InstanceDetailView, self).data()
        result['instance']['created'] = self.instance.created
        result['instance']['updated'] = self.instance.updated

        dns_support = CONF.trove_dns_support
        if dns_support:
            result['instance']['hostname'] = self.instance.hostname

        if CONF.add_addresses:
            ip = get_ip_address(self.instance.addresses)
            if ip is not None and len(ip) > 0:
                result['instance']['ip'] = ip

        if (isinstance(self.instance, models.DetailInstance) and
                self.instance.volume_used):
            used = self.instance.volume_used
            if CONF.trove_volume_support:
                result['instance']['volume']['used'] = used
            else:
                # either ephemeral or root partition
                result['instance']['local_storage'] = {'used': used}

        return result


class InstancesView(object):
    """Shows a list of SimpleInstance objects."""

    def __init__(self, instances, req=None):
        self.instances = instances
        self.req = req

    def data(self):
        data = []
        # These are model instances
        for instance in self.instances:
            data.append(self.data_for_instance(instance))
        return {'instances': data}

    def data_for_instance(self, instance):
        view = InstanceView(instance, req=self.req)
        return view.data()['instance']
