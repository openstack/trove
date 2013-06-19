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

import os
import routes
from xml.dom import minidom

from trove.common import wsgi


VERSIONS = {
    "1.0": {
        "id": "v1.0",
        "status": "CURRENT",
        "updated": "2012-08-01T00:00:00Z",
        "links": [],
    },
}


class VersionsController(wsgi.Controller):

    def index(self, request):
        """Respond to a request for API versions."""
        versions = []
        for key, data in VERSIONS.items():
            v = BaseVersion(
                data["id"],
                data["status"],
                request.application_url,
                data["updated"])
            versions.append(v)
        return wsgi.Result(VersionsDataView(versions))

    def show(self, request):
        """Respond to a request for a specific API version."""
        data = VERSIONS[request.url_version]
        v = Version(data["id"], data["status"],
                    request.application_url, data["updated"])
        return wsgi.Result(VersionDataView(v))


class BaseVersion(object):

    def __init__(self, id, status, base_url, updated):
        self.id = id
        self.status = status
        self.base_url = base_url
        self.updated = updated

    def data(self):
        return {
            "id": self.id,
            "status": self.status,
            "updated": self.updated,
            "links": [{"rel": "self", "href": self.url()}],
        }

    def url(self):
        url = os.path.join(self.base_url, self.id)
        if not url.endswith("/"):
            return url + "/"
        return url

    def to_xml(self):
        doc = minidom.Document()
        version_elem = doc.createElement("version")
        version_elem.setAttribute("id", self.id)
        version_elem.setAttribute("status", self.status)
        version_elem.setAttribute("updated", self.updated)
        links_elem = doc.createElement("links")
        link_elem = doc.createElement("link")
        link_elem.setAttribute("href", self.url())
        link_elem.setAttribute("rel", "self")
        links_elem.appendChild(link_elem)
        version_elem.appendChild(links_elem)
        return version_elem


class Version(BaseVersion):

    def url(self):
        if not self.base_url.endswith("/"):
            return self.base_url + "/"
        return self.base_url


class VersionDataView(object):

    def __init__(self, version):
        self.version = version

    def data_for_json(self):
        return {'version': self.version.data()}

    def data_for_xml(self):
        return {'version': self.version}


class VersionsDataView(object):

    def __init__(self, versions):
        self.versions = versions

    def data_for_json(self):
        return {'versions': [version.data() for version in self.versions]}

    def data_for_xml(self):
        return {'versions': self.versions}


class VersionsAPI(wsgi.Router):
    def __init__(self):
        mapper = routes.Mapper()
        versions_resource = VersionsController().create_resource()
        mapper.connect("/", controller=versions_resource, action="index")
        super(VersionsAPI, self).__init__(mapper)


def app_factory(global_conf, **local_conf):
    conf = global_conf.copy()
    conf.update(local_conf)
    return VersionsAPI()
