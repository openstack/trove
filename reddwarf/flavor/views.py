# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2012 OpenStack Foundation
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


from reddwarf.common.views import create_links


class FlavorView(object):

    def __init__(self, flavor, req=None):
        self.flavor = flavor
        self.req = req

    def data(self):
        return {
            "flavor": {
                'id': int(self.flavor.id),
                'links': self._build_links(),
                'name': self.flavor.name,
                'ram': self.flavor.ram,
            }
        }

    def _build_links(self):
        return create_links("flavors", self.req, self.flavor.id)


class FlavorsView(object):
    view = FlavorView

    def __init__(self, flavors, req=None):
        self.flavors = flavors
        self.req = req

    def data(self):
        data = []
        for flavor in self.flavors:
            data.append(self.view(flavor, req=self.req).data()['flavor'])
        return {"flavors": data}
