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

from trove.common import cfg
from trove.common.views import create_links
from trove.instance import models
from trove.openstack.common import log as logging

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


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
            "datastore": {"type": self.instance.datastore.name,
                          "version": self.instance.datastore_version.name},
        }
        if self.instance.volume_support:
            instance_dict['volume'] = {'size': self.instance.volume_size}

        if self.instance.hostname:
            instance_dict['hostname'] = self.instance.hostname
        else:
            ip = self.instance.get_visible_ip_addresses()
            if ip:
                instance_dict['ip'] = ip

        if self.instance.slave_of_id is not None:
            instance_dict['replica_of'] = self._build_master_info()

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

    def _build_master_info(self):
        return {
            "id": self.instance.slave_of_id,
            "links": create_links("instances", self.req,
                                  self.instance.slave_of_id)
        }


class InstanceDetailView(InstanceView):
    """Works with a full-blown instance."""

    def __init__(self, instance, req):
        super(InstanceDetailView, self).__init__(instance,
                                                 req=req)

    def data(self):
        result = super(InstanceDetailView, self).data()
        result['instance']['created'] = self.instance.created
        result['instance']['updated'] = self.instance.updated

        result['instance']['datastore']['version'] = (self.instance.
                                                      datastore_version.name)

        if self.instance.slaves:
            result['instance']['replicas'] = self._build_slaves_info()

        if self.instance.configuration is not None:
            result['instance']['configuration'] = (self.
                                                   _build_configuration_info())

        if (isinstance(self.instance, models.DetailInstance) and
                self.instance.volume_used):
            used = self.instance.volume_used
            if self.instance.volume_support:
                result['instance']['volume']['used'] = used
            else:
                # either ephemeral or root partition
                result['instance']['local_storage'] = {'used': used}

        if self.instance.root_password:
            result['instance']['password'] = self.instance.root_password

        if self.instance.cluster_id:
            result['instance']['cluster_id'] = self.instance.cluster_id

        if self.instance.shard_id:
            result['instance']['shard_id'] = self.instance.shard_id

        return result

    def _build_slaves_info(self):
        data = []
        for slave in self.instance.slaves:
            data.append({
                "id": slave.id,
                "links": create_links("instances", self.req, slave.id)
            })
        return data

    def _build_configuration_info(self):
        return {
            "id": self.instance.configuration.id,
            "name": self.instance.configuration.name,
            "links": create_links("configurations", self.req,
                                  self.instance.configuration.id)
        }


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


class DefaultConfigurationView(object):
    def __init__(self, config):
        self.config = config

    def data(self):
        config_dict = {}
        for key, val in self.config:
            config_dict[key] = val
        return {"instance": {"configuration": config_dict}}
