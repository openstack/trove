# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012 OpenStack Foundation
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

"""
Model classes that extend the instances functionality for volumes.
"""

from reddwarf.openstack.common import log as logging

from reddwarf.common.remote import create_nova_volume_client


LOG = logging.getLogger(__name__)


class StorageDevice(object):

    def __init__(self, storage_info):
        self.name = storage_info.name
        self.type = storage_info.type
        self.total_space = storage_info.capacity['total']
        self.total_avail = storage_info.capacity['available']
        self.prov_total = storage_info.provision['total']
        self.prov_avail = storage_info.provision['available']
        self.prov_percent = storage_info.provision['percent']
        self.used = storage_info.used


class StorageDevices(object):

    @staticmethod
    def load(context):
        client = create_nova_volume_client(context)
        rdstorages = client.rdstorage.list()
        for rdstorage in rdstorages:
            LOG.debug("rdstorage=" + str(rdstorage))
        return [StorageDevice(storage_info)
                for storage_info in rdstorages]
