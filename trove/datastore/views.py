# Copyright 2013 OpenStack Foundation
# Copyright 2013 Rackspace Hosting
# Copyright 2013 Hewlett-Packard Development Company, L.P.
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
#

from trove.common.views import create_links
from trove.common import wsgi


class DatastoreView(object):

    def __init__(self, datastore, datastore_versions, req=None):
        self.datastore = datastore
        self.datastore_versions = datastore_versions
        self.req = req

    def data(self):
        datastore_dict = {
            "id": self.datastore.id,
            "name": self.datastore.name,
            "links": self._build_links(),
        }
        datastore_dict.update(DatastoreVersionsView(self.datastore_versions,
                                                    self.req).data(False))
        default_version = self.datastore.default_version_id
        if default_version:
            datastore_dict["default_version"] = default_version

        return {"datastore": datastore_dict}

    def _build_links(self):
        return create_links("datastores", self.req,
                            self.datastore.id)


class DatastoresView(object):

    def __init__(self, datastores, datastores_versions, req=None):
        self.datastores = datastores
        self.datastores_versions = datastores_versions
        self.req = req

    def data(self):
        data = []
        for datastore in self.datastores:
            datastores_versions = [
                datastore_version
                for datastore_version in self.datastores_versions
                if datastore_version.datastore_id == datastore.id]
            data.append(self.data_for_datastore(datastore,
                                                datastores_versions))
        return {'datastores': data}

    def data_for_datastore(self, datastore, datastore_versions):
        view = DatastoreView(datastore, datastore_versions, req=self.req)
        return view.data()['datastore']


class DatastoreVersionView(object):

    def __init__(self, datastore_version, req=None):
        self.datastore_version = datastore_version
        self.req = req
        self.context = req.environ[wsgi.CONTEXT_KEY]

    def data(self, include_datastore_id=True):
        datastore_version_dict = {
            "id": self.datastore_version.id,
            "name": self.datastore_version.name,
            "links": self._build_links(),
        }
        if include_datastore_id:
            datastore_version_dict["datastore"] = (self.datastore_version.
                                                   datastore_id)
        if self.context.is_admin:
            datastore_version_dict['active'] = self.datastore_version.active
            datastore_version_dict['packages'] = (self.datastore_version.
                                                  packages)
            datastore_version_dict['image'] = self.datastore_version.image_id
        return {"version": datastore_version_dict}

    def _build_links(self):
        return create_links("datastores/versions",
                            self.req, self.datastore_version.id)


class DatastoreVersionsView(object):

    def __init__(self, datastore_versions, req=None):
        self.datastore_versions = datastore_versions
        self.req = req

    def data(self, include_datastore_id=True):
        data = []
        for datastore_version in self.datastore_versions:
            data.append(self.
                        data_for_datastore_version(datastore_version,
                                                   include_datastore_id))
        return {'versions': data}

    def data_for_datastore_version(self, datastore_version,
                                   include_datastore_id):
        view = DatastoreVersionView(datastore_version, req=self.req)
        return view.data(include_datastore_id)['version']
