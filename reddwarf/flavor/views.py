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
        self.req = req

    def data(self):
        return {"flavor": {
            'id': self.flavor.id,
            'links': self._build_links(),
            'name': self.flavor.name,
            }}

    def _build_links(self):
        result = []
        #scheme = self.req.scheme
        scheme = 'https'  # Forcing https
        endpoint = self.req.host
        splitpath = self.req.path.split('/')
        detailed = ''
        if splitpath[-1] == 'detail':
            detailed = '/detail'
            splitpath.pop(-1)
        flavorid = self.flavor.id
        if splitpath[-1] == flavorid:
            splitpath.pop(-1)
        href_template = "%(scheme)s://%(endpoint)s%(path)s/%(flavorid)s"
        for link in self.flavor.links:
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
    view = FlavorView

    def __init__(self, flavors, req=None):
        self.flavors = flavors
        self.req = req

    def data(self, detailed=False):
        data = []
        for flavor in self.flavors:
            data.append(self.view(flavor, req=self.req).data()['flavor'])
        return {"flavors": data}


class FlavorsDetailView(FlavorsView):
    view = FlavorDetailView
