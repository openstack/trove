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


class InstanceView(object):

    def __init__(self, instance):
        self.instance = instance

    def data(self):
        instance_dict = {
            "id": self.instance.id,
            "name": self.instance.name,
            "status": self.instance.status,
            "links": self.instance.links
        }
        return {"instance": instance_dict}


class InstanceDetailView(InstanceView):

    def data(self):
        result = super(InstanceDetailView, self).data()
        result['instance']['created'] = self.instance.created
        result['instance']['flavor'] = self.instance.flavor
        result['instance']['updated'] = self.instance.updated
        return result


class InstancesView(object):

    def __init__(self, instances):
        self.instances = instances

    def data(self):
        data = []
        # These are model instances
        for instance in self.instances:
            data.append(self.data_for_instance(instance))
        return {'instances': data}

    def data_for_instance(self, instance):
        return InstanceView(instance).data()['instance']


class InstancesDetailView(InstancesView):

    def data_for_instance(self, instance):
        return InstanceDetailView(instance).data()['instance']
