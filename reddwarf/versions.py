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

import os
import routes
from xml.dom import minidom

from reddwarf.common import wsgi


class VersionsController(wsgi.Controller):

    def index(self, request):
        """Respond to a request for all OpenStack API versions."""
        versions = [Version("v0.1", "CURRENT", request.application_url)]
        return wsgi.Result(VersionsDataView(versions))


class Version(object):

    def __init__(self, name, status, base_url):
        self.name = name
        self.status = status
        self.base_url = base_url

    def data(self):
        return dict(name=self.name,
            status=self.status,
            links=[dict(rel="self",
                href=self.url())])

    def url(self):
        return os.path.join(self.base_url, self.name)

    def to_xml(self):
        doc = minidom.Document()
        version_elem = doc.createElement("version")
        version_elem.setAttribute("name", self.name)
        version_elem.setAttribute("status", self.status)
        links_elem = doc.createElement("links")
        link_elem = doc.createElement("link")
        link_elem.setAttribute("href", self.url())
        link_elem.setAttribute("rel", "self")
        links_elem.appendChild(link_elem)
        version_elem.appendChild(links_elem)
        return version_elem


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
        mapper.connect("/", controller=VersionsController().create_resource(),
            action="index")
        super(VersionsAPI, self).__init__(mapper)


def app_factory(global_conf, **local_conf):
    conf = global_conf.copy()
    conf.update(local_conf)
    return VersionsAPI()
