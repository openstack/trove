# Copyright [2015] Hewlett-Packard Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


class DatastoreVersionView(object):

    def __init__(self, datastore_version):
        self.datastore_version = datastore_version

    def data(self):
        datastore_version_dict = {
            "id": self.datastore_version.id,
            "name": self.datastore_version.name,
            "version": self.datastore_version.version,
            "datastore_id": self.datastore_version.datastore_id,
            "datastore_name": self.datastore_version.datastore_name,
            "datastore_manager": self.datastore_version.manager,
            "image": self.datastore_version.image_id,
            "image_tags": (self.datastore_version.image_tags.split(',')
                           if self.datastore_version.image_tags else ['']),
            "packages": (self.datastore_version.packages.split(
                ',') if self.datastore_version.packages else ['']),
            "active": self.datastore_version.active,
            "default": self.datastore_version.default}

        return {'version': datastore_version_dict}


class DatastoreVersionsView(object):

    def __init__(self, datastore_versions):
        self.datastore_versions = datastore_versions

    def data(self):
        data = []
        for datastore_version in self.datastore_versions:
            data.append(
                DatastoreVersionView(datastore_version).data()['version'])

        return {'versions': data}
