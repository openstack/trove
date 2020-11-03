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

from oslo_log import log as logging

from trove.common.views import create_links
from trove.common import wsgi
from trove.instance import models

LOG = logging.getLogger(__name__)


class InstanceView(object):
    """Uses a SimpleInstance."""

    def __init__(self, instance, req=None):
        self.instance = instance
        self.req = req
        self.context = req.environ[wsgi.CONTEXT_KEY]

    def data(self):
        instance_dict = {
            "id": self.instance.id,
            "name": self.instance.name,
            "status": self.instance.status,
            "links": self._build_links(),
            "flavor": self._build_flavor_info(),
            "datastore": {"type": None, "version": None},
            "region": self.instance.region_name,
            "access": {}
        }
        if self.instance.datastore_version:
            instance_dict['datastore'] = {
                "type": self.instance.datastore.name,
                "version": self.instance.datastore_version.name
            }
        if self.context.is_admin:
            instance_dict['tenant_id'] = self.instance.tenant_id
        if self.instance.volume_support:
            instance_dict['volume'] = {'size': self.instance.volume_size}

        if self.instance.hostname:
            instance_dict['hostname'] = self.instance.hostname
        else:
            addresses = self.instance.get_visible_ip_addresses()
            if addresses:
                # NOTE(lxkong): 'ip' is deprecated in stable/ussuri and should
                # be removed in W.
                instance_dict['ip'] = [addr['address'] for addr in addresses]
                instance_dict['addresses'] = addresses

        if self.instance.slave_of_id is not None:
            instance_dict['replica_of'] = self._build_master_info()

        if self.instance.slaves:
            instance_dict['replicas'] = self._build_slaves_info()

        if self.instance.access:
            instance_dict['access'] = self.instance.access
        elif 'addresses' in instance_dict:
            for addr in instance_dict['addresses']:
                if addr.get('type') == 'public':
                    instance_dict['access']['is_public'] = True
                    break
            else:
                instance_dict['access']['is_public'] = False

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

    def _build_slaves_info(self):
        data = []
        for slave in self.instance.slaves:
            data.append({
                "id": slave.id,
                "links": create_links("instances", self.req, slave.id)
            })

        return data


class InstanceDetailView(InstanceView):
    """Works with a full-blown instance."""

    def __init__(self, instance, req):
        super(InstanceDetailView, self).__init__(instance,
                                                 req=req)

    def data(self):
        result = super(InstanceDetailView, self).data()
        result['instance']['created'] = self.instance.created
        result['instance']['updated'] = self.instance.updated
        result['instance']['service_status_updated'] = (self.instance.
                                                        service_status_updated)

        result['instance']['datastore']['version'] = None
        if self.instance.datastore_version:
            result['instance']['datastore']['version'] = \
                self.instance.datastore_version.name

        if self.instance.fault:
            result['instance']['fault'] = self._build_fault_info()

        if self.instance.configuration is not None:
            result['instance']['configuration'] = (self.
                                                   _build_configuration_info())

        if self.instance.locality:
            result['instance']['locality'] = self.instance.locality

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

        if self.context.is_admin:
            result['instance']['server_id'] = self.instance.server_id
            result['instance']['volume_id'] = self.instance.volume_id
            result['instance']['encrypted_rpc_messaging'] = (
                self.instance.encrypted_rpc_messaging)

        return result

    def _build_fault_info(self):
        return {
            "message": self.instance.fault.message,
            "created": self.instance.fault.updated,
            "details": self.instance.fault.details,
        }

    def _build_configuration_info(self):
        return {
            "id": self.instance.configuration.id,
            "name": self.instance.configuration.name,
            "links": create_links("configurations", self.req,
                                  self.instance.configuration.id)
        }


class InstancesView(object):
    """Shows a list of SimpleInstance objects."""

    def __init__(self, instances, item_view=InstanceView, req=None):
        self.instances = instances
        self.item_view = item_view
        self.req = req

    def data(self):
        data = []

        # Return instances in the order of 'created'
        # These are model instances
        for instance in sorted(self.instances, key=lambda ins: ins.created,
                               reverse=True):
            data.append(self.data_for_instance(instance))
        return {'instances': data}

    def data_for_instance(self, instance):
        view = self.item_view(instance, req=self.req)
        return view.data()['instance']


class DefaultConfigurationView(object):
    def __init__(self, config):
        self.config = config

    def data(self):
        config_dict = {}
        for key, val in self.config:
            config_dict[key] = val
        return {"instance": {"configuration": config_dict}}


class GuestLogView(object):

    def __init__(self, guest_log):
        self.guest_log = guest_log

    def data(self):
        return {
            'name': self.guest_log.name,
            'type': self.guest_log.type,
            'status': self.guest_log.status,
            'published': self.guest_log.published,
            'pending': self.guest_log.pending,
            'container': self.guest_log.container,
            'prefix': self.guest_log.prefix,
            'metafile': self.guest_log.metafile,
        }


class GuestLogsView(object):

    def __init__(self, guest_logs):
        self.guest_logs = guest_logs

    def data(self):
        return [GuestLogView(guestlog).data() for guestlog in self.guest_logs]


def convert_instance_count_to_list(instance_count):
    instance_list = []
    for row in instance_count:
        (_, name, id, md5, count, current, min_date, max_date) = row
        instance_list.append(
            {'module_name': name,
             'module_id': id,
             'module_md5': md5,
             'instance_count': count,
             'current': current,
             'min_updated_date': min_date,
             'max_updated_date': max_date
             })
    return instance_list
