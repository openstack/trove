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
from reddwarf.common import config
from reddwarf.common import utils

LOG = logging.getLogger(__name__)


def get_ip_address(addresses):
    if addresses is not None and \
       addresses.get('private') is not None and \
       len(addresses['private']) > 0:
        return [addr.get('addr') for addr in addresses['private']]
    if addresses is not None and\
       addresses.get('usernet') is not None and\
       len(addresses['usernet']) > 0:
        return [addr.get('addr') for addr in addresses['usernet']]


def get_volumes(volumes):
    LOG.debug("volumes - %s" % volumes)
    if volumes is not None and len(volumes) > 0:
        return {'size': volumes[0].get('size')}


class InstanceView(object):

    def __init__(self, instance, req=None, add_addresses=False,
                 add_volumes=False):
        self.instance = instance
        self.add_addresses = add_addresses
        self.add_volumes = add_volumes
        self.req = req

    def data(self):
        ip = get_ip_address(self.instance.addresses)
        volumes = get_volumes(self.instance.volumes)
        instance_dict = {
            "id": self.instance.id,
            "name": self.instance.name,
            "status": self.instance.status,
            "links": self._build_links()
        }
        dns_support = config.Config.get("reddwarf_dns_support", 'False')
        if utils.bool_from_string(dns_support):
            instance_dict['hostname'] = self.instance.db_info.hostname
        if self.add_addresses and ip is not None and len(ip) > 0:
            instance_dict['ip'] = ip
        if self.add_volumes and volumes is not None:
            instance_dict['volume'] = volumes
        LOG.debug(instance_dict)
        return {"instance": instance_dict}

    def _build_links(self):
        # TODO(ed-): Make generic, move to common?
        result = []
        scheme = 'https'  # Forcing https
        links = [link for link in self.instance.links]
        links = [link['href'] for link in links if link['rel'] == 'self']
        href_link = links[0]
        splitpath = href_link.split('/')
        endpoint = ''
        if self.req:
            endpoint = self.req.host
            splitpath = self.req.path.split('/')

        detailed = ''
        if splitpath[-1] == 'detail':
            detailed = '/detail'
            splitpath.pop(-1)

        instance_id = self.instance.id
        if str(splitpath[-1]) == str(instance_id):
            splitpath.pop(-1)
        href_template = "%(scheme)s://%(endpoint)s%(path)s/%(instance_id)s"
        for link in self.instance.links:
            rlink = link
            href = rlink['href']
            if rlink['rel'] == 'self':
                path = '/'.join(splitpath)
                href = href_template % locals()
            elif rlink['rel'] == 'bookmark':
                splitpath.pop(2)  # Remove the version.
                splitpath.pop(1)  # Remove the tenant id.
                path = '/'.join(splitpath)
                href = href_template % locals()

            rlink['href'] = href
            result.append(rlink)
        return result


class InstanceDetailView(InstanceView):

    def __init__(self, instance, req=None, add_addresses=False,
                 add_volumes=False):
        super(InstanceDetailView, self).__init__(instance,
                                                 req=req,
                                                 add_addresses=add_addresses,
                                                 add_volumes=add_volumes)

    def data(self):
        result = super(InstanceDetailView, self).data()
        result['instance']['created'] = self.instance.created
        result['instance']['flavor'] = self.instance.flavor
        result['instance']['updated'] = self.instance.updated
        return result


class InstancesView(object):

    def __init__(self, instances, req=None, add_addresses=False,
                 add_volumes=False):
        self.instances = instances
        self.add_addresses = add_addresses
        self.add_volumes = add_volumes
        self.req = req

    def data(self):
        data = []
        # These are model instances
        for instance in self.instances:
            data.append(self.data_for_instance(instance))
        return {'instances': data}

    def data_for_instance(self, instance):
        view = InstanceView(instance, req=self.req,
                            add_addresses=self.add_addresses)
        return view.data()['instance']


class InstancesDetailView(InstancesView):

    def data_for_instance(self, instance):
        return InstanceDetailView(instance, req=self.req,
                               add_addresses=self.add_addresses,
                               add_volumes=self.add_volumes).data()['instance']
