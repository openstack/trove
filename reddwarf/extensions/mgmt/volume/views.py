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


class StorageView(object):

    def __init__(self, storage):
        self.storage = storage

    def data(self):
        return {'name': self.storage.name,
                'type': self.storage.type,
                'capacity': {'total': self.storage.total_space,
                             'available': self.storage.total_avail},
                'provision': {'total': self.storage.prov_total,
                              'available': self.storage.prov_avail,
                              'percent': self.storage.prov_percent},
                'used': self.storage.used}


class StoragesView(object):

    def __init__(self, storages):
        self.storages = storages

    def data(self):
        data = [StorageView(storage).data() for storage in self.storages]
        return {'devices': data}
