# Copyright 2016 Tesora, Inc
#
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


class VolumeTypeView(object):

    def __init__(self, volume_type, req=None):
        self.volume_type = volume_type
        self.req = req

    def data(self):
        volume_type = {
            'id': self.volume_type.id,
            'name': self.volume_type.name,
            'is_public': self.volume_type.is_public,
            'description': self.volume_type.description
        }
        return {"volume_type": volume_type}


class VolumeTypesView(object):

    def __init__(self, volume_types, req=None):
        self.volume_types = volume_types
        self.req = req

    def data(self):
        data = []
        for volume_type in self.volume_types:
            data.append(VolumeTypeView(volume_type,
                                       req=self.req).data()['volume_type'])

        return {"volume_types": data}
