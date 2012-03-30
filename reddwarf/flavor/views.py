# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2012 OpenStack LLC.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http: //www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

class FlavorView(object):

    def __init__(self, flavor, req=None):
        self.flavor = flavor
        self.flavor.req = req

    def data(self):
        return {"flavor": {
            'id': self.flavor.id,
            'links': self.flavor.links,
            'name': self.flavor.name,
            }}


class FlavorDetailView(FlavorView):

    def data(self):
        result = super(FlavorDetailView, self).data()
        details = {
            'ram': self.flavor.ram,
            'vcpus': self.flavor.vcpus,
            }
        result["flavor"].update(details)
        return result


class FlavorsView(object):

    def __init__(self, flavors, req=None):
        self.flavors = flavors
        self.req = req

    def data(self, detailed=False):
        data = []
        for flavor in self.flavors:
            if detailed:
                data.append(FlavorDetailView(flavor, req=self.req).data()['flavor'])
            else:
                data.append(FlavorView(flavor, req=self.req).data()['flavor'])

        return {"flavors": data}
