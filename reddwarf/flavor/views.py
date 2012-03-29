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

    def __init__(self, flavor):
        self.flavor = flavor

    def data(self, req=None):
        self.flavor.req = req # For building the links.
        return {"flavor": {
            'id': self.flavor.id,
            'links': self.flavor.links,
            'name': self.flavor.name,
            'ram': self.flavor.ram,
            }}


class FlavorDetailView(FlavorView):

    def data(self, req=None):
        result = super(FlavorDetailView, self).data(req)
        details = {
            "vcpus": self.flavor.vcpus,
            }
        result["flavor"].update(details)
        return result


class FlavorsView(object):

    def __init__(self, flavors):
        self.flavors = flavors

    def data(self, req=None, detailed=False):
        data = []
        for flavor in self.flavors:
            if detailed:
                data.append(FlavorDetailView(flavor).data(req)['flavor'])
            else:
                data.append(FlavorView(flavor).data(req)['flavor'])

        return {"flavors": data}
