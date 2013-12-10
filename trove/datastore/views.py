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


class DatastoreView(object):

    def __init__(self, datastore, req=None):
        self.datastore = datastore
        self.req = req

    def data(self):
        datastore_dict = {
            "id": self.datastore.id,
            "name": self.datastore.name,
            "links": self._build_links(),
        }

        return {"datastore": datastore_dict}

    def _build_links(self):
        return create_links("datastores", self.req,
                            self.datastore.id)


class DatastoresView(object):

    def __init__(self, datastores, req=None):
        self.datastores = datastores
        self.req = req

    def data(self):
        data = []
        for datastore in self.datastores:
            data.append(self.data_for_datastore(datastore))
        return {'datastores': data}

    def data_for_datastore(self, datastore):
        view = DatastoreView(datastore, req=self.req)
        return view.data()['datastore']


class DatastoreVersionView(object):

    def __init__(self, datastore_version, req=None):
        self.datastore_version = datastore_version
        self.req = req

    def data(self):
        datastore_version_dict = {
            "id": self.datastore_version.id,
            "name": self.datastore_version.name,
            "links": self._build_links(),
        }

        return {"version": datastore_version_dict}

    def _build_links(self):
        return create_links("datastores/versions",
                            self.req, self.datastore_version.id)


class DatastoreVersionsView(object):

    def __init__(self, datastore_versions, req=None):
        self.datastore_versions = datastore_versions
        self.req = req

    def data(self):
        data = []
        for datastore_version in self.datastore_versions:
            data.append(self.
                        data_for_datastore_version(datastore_version))
        return {'versions': data}

    def data_for_datastore_version(self, datastore_version):
        view = DatastoreVersionView(datastore_version, req=self.req)
        return view.data()['version']
