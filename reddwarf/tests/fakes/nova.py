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

import logging
from novaclient.v1_1.client import Client
from novaclient import exceptions as nova_exceptions
import time
import uuid
from reddwarf.tests.fakes.common import EventSimulator


LOG = logging.getLogger(__name__)


class FakeFlavor(object):

    def __init__(self, id, disk, name, ram):
        self.id = id
        self.disk = disk
        self.name = name
        self.ram = ram
        self.vcpus = 10

    @property
    def links(self):
        return [{
            "href": "http://localhost:8774/v2/"
                "5064d71eb09c47e1956cf579822bae9a/flavors/%s" % self.id,
            "rel": link_type
            } for link_type in ['self', 'bookmark']]

    @property
    def href_suffix(self):
        return "flavors/%s" % self.id

    def to_dict(self):
        return {"id": self.id, "links": self.links}


class FakeFlavors(object):

    def __init__(self):
        self.db = {}
        self._add(1, 0, "m1.tiny", 512)
        self._add(2, 10, "m1.small", 2048)
        self._add(3, 10, "m1.medium", 4096)
        self._add(4, 10, "m1.large", 8192)
        self._add(5, 10, "m1.xlarge", 16384)
        self._add(6, 0, "tinier", 506)
        self._add(7, 0, "m1.rd-tiny", 512)
        self._add(8, 0, "m1.rd-smaller", 768)

    def _add(self, *args, **kwargs):
        new_flavor = FakeFlavor(*args, **kwargs)
        self.db[new_flavor.id] = new_flavor

    def get(self, id):
        id = int(id)
        if id not in self.db:
            raise nova_exceptions.NotFound(404, "Flavor id not found %s" % id)
        return self.db[id]

    def get_by_href(self, href):
        for id in self.db:
            value = self.db[id]
            # Use inexact match since faking the exact endpoints would be
            # difficult.
            if href.endswith(value.href_suffix):
                return value
        raise nova_exceptions.NotFound(404, "Flavor href not found %s" % href)

    def list(self):
        return [self.get(id) for id in self.db]


class FakeServer(object):

    def __init__(self, parent, owner, id, name, image_id, flavor_ref,
                 block_device_mapping, volumes):
        self.owner = owner  # This is a context.
        self.id = id
        self.parent = parent
        self.name = name
        self.image_id = image_id
        self.flavor_ref = flavor_ref
        self.events = EventSimulator()
        self.schedule_status("BUILD", 0.0)
        self.volumes = volumes
        for volume in self.volumes:
            volume.set_attachment(id)

    @property
    def addresses(self):
        return {"private": [{"addr":"123.123.123.123"}]}

    def confirm_resize(self):
        if self.status != "VERIFY_RESIZE":
            raise RuntimeError("Not in resize confirm mode.")
        self._current_status = "ACTIVE"

    def delete(self):
        self.schedule_status = []
        # TODO(pdmars): This is less than ideal, but a quick way to force it 
        # into the error state before scheduling the delete. 
        if self.name.endswith("_ERROR_ON_DELETE"):
            self._current_status = "ERROR"
        else:
            self._current_status = "SHUTDOWN"
        self.parent.schedule_delete(self.id, 1.5)

    @property
    def flavor(self):
        return FLAVORS.get_by_href(self.flavor_ref).to_dict()

    @property
    def links(self):
        return [{
            "href": "https://localhost:9999/v1.0/1234/instances/%s" % self.id,
            "rel": link_type
            } for link_type in ['self', 'bookmark']]

    def resize(self, new_flavor_id):
        self._current_status = "RESIZE"

        def set_to_confirm_mode():
            self._current_status = "VERIFY_RESIZE"

        def set_flavor():
            flavor = self.parent.flavors.get(new_flavor_id)
            self.flavor_ref = flavor.links[0]['href']
            self.events.add_event(1, set_to_confirm_mode)

        self.events.add_event(1, set_flavor)

    def schedule_status(self, new_status, time_from_now):
        """Makes a new status take effect at the given time."""
        def set_status():
            self._current_status = new_status
        self.events.add_event(time_from_now, set_status)

    @property
    def status(self):
        return self._current_status

    @property
    def created(self):
        return "2012-01-25T21:55:51Z"

    @property
    def updated(self):
        return "2012-01-25T21:55:51Z"


# The global var contains the servers dictionary in use for the life of these
# tests.
FAKE_SERVERS_DB = {}


class FakeServers(object):

    def __init__(self, context, flavors):
        self.context = context
        self.db = FAKE_SERVERS_DB
        self.flavors = flavors
        self.events = EventSimulator()

    def can_see(self, id):
        """Can this FakeServers, with its context, see some resource?"""
        server = self.db[id]
        return self.context.is_admin or \
               server.owner.tenant == self.context.tenant

    def create(self, name, image_id, flavor_ref, files, block_device_mapping):
        id = "FAKE_%s" % uuid.uuid4()
        volumes = self._get_volumes_from_bdm(block_device_mapping)
        server = FakeServer(self, self.context, id, name, image_id, flavor_ref,
                            block_device_mapping, volumes)
        self.db[id] = server
        server.schedule_status("ACTIVE", 1)
        LOG.info("FAKE_SERVERS_DB : %s" % str(FAKE_SERVERS_DB))
        return server

    def _get_volumes_from_bdm(self, block_device_mapping):
        volumes = []
        if block_device_mapping is not None:
            # block_device_mapping is a dictionary, where the key is the
            # device name on the compute instance and the mapping info is a
            # set of fields in a string, seperated by colons.
            # For each device, find the volume, and record the mapping info
            # to another fake object and attach it to the volume
            # so that the fake API can later retrieve this.
            for device in block_device_mapping:
                mapping = block_device_mapping[device]
                (id, _type, size, delete_on_terminate) = mapping.split(":")
                volume = self.volumes.get(id)
                volume.mapping = FakeBlockDeviceMappingInfo(id, device,
                    _type, size, delete_on_terminate)
                volumes.append(volume)
        return volumes

    def get(self, id):
        if id not in self.db:
            LOG.error("Couldn't find server id %s, collection=%s" % (id,
                                                                     self.db))
            raise nova_exceptions.NotFound(404, "Not found")
        else:
            if self.can_see(id):
                return self.db[id]
            else:
                raise nova_exceptions.NotFound(404, "Bad permissions")

    def get_server_volumes(self, server_id):
        """Fake method we've added to grab servers from the volume."""
        return [volume.mapping
                for volume in self.get(server_id).volumes
                if volume.mapping is not None]

    def list(self):
        return [v for (k, v) in self.db.items() if self.can_see(v.id)]

    def schedule_delete(self, id, time_from_now):
        def delete_server():
            LOG.info("Simulated event ended, deleting server %s." % id)
            del self.db[id]
        self.events.add_event(time_from_now, delete_server)


class FakeServerVolumes(object):

    def __init__(self, context):
        self.context = context

    def get_server_volumes(self, server_id):
        class ServerVolumes(object):
            def __init__(self, block_device_mapping):
                LOG.debug("block_device_mapping = %s" % block_device_mapping)
                device = block_device_mapping['vdb']
                (self.volumeId,
                    self.type,
                    self.size,
                    self.delete_on_terminate) = device.split(":")
        fake_servers = FakeServers(self.context, FLAVORS)
        server = fake_servers.get(server_id)
        return [ServerVolumes(server.block_device_mapping)]


class FakeVolume(object):

    def __init__(self, parent, owner, id, size, display_name,
                 display_description):
        self.attachments = []
        self.parent = parent
        self.owner = owner  # This is a context.
        self.id = id
        self.size = size
        self.display_name = display_name
        self.display_description = display_description
        self.events = EventSimulator()
        self.schedule_status("BUILD", 0.0)
        # For some reason we grab this thing from device then call it mount
        # point.
        self.device = "/var/lib/mysql"

    def __repr__(self):
        return ("FakeVolume(id=%s, size=%s, "
               "display_name=%s, display_description=%s)") % (self.id,
               self.size, self.display_name, self.display_description)

    def get(self, key):
        return getattr(self, key)

    def schedule_status(self, new_status, time_from_now):
        """Makes a new status take effect at the given time."""
        def set_status():
            self._current_status = new_status
        self.events.add_event(time_from_now, set_status)

    def set_attachment(self, server_id):
        """Fake method we've added to set attachments. Idempotent."""
        for attachment in self.attachments:
            if attachment['server_id'] == server_id:
                return  # Do nothing
        self.attachments.append({'server_id': server_id,
                                 'device': self.device})

    @property
    def status(self):
        return self._current_status


class FakeBlockDeviceMappingInfo(object):

    def __init__(self, id, device, _type, size, delete_on_terminate):
        self.volumeId = id
        self.device = device
        self.type = _type
        self.size = size
        self.delete_on_terminate = delete_on_terminate


FAKE_VOLUMES_DB = {}


class FakeVolumes(object):

    def __init__(self, context):
        self.context = context
        self.db = FAKE_VOLUMES_DB
        self.events = EventSimulator()

    def can_see(self, id):
        """Can this FakeVolumes, with its context, see some resource?"""
        server = self.db[id]
        return self.context.is_admin or \
               server.owner.tenant == self.context.tenant

    def get(self, id):
        if id not in self.db:
            LOG.error("Couldn't find volume id %s, collection=%s" % (id,
                                                                     self.db))
            raise nova_exceptions.NotFound(404, "Not found")
        else:
            if self.can_see(id):
                return self.db[id]
            else:
                raise nova_exceptions.NotFound(404, "Bad permissions")

    def create(self, size, display_name=None, display_description=None):
        id = "FAKE_VOL_%s" % uuid.uuid4()
        volume = FakeVolume(self, self.context, id, size, display_name,
                            display_description)
        self.db[id] = volume
        volume.schedule_status("available", 2)
        LOG.info("FAKE_VOLUMES_DB : %s" % FAKE_VOLUMES_DB)
        return volume

    def list(self, detailed=True):
        return [self.db[key] for key in self.db]

    def resize(self, volume_id, new_size):
        volume = self.get(volume_id)

        def finish_resize():
            volume._current_status = "in-use"
            volume.size = new_size
        self.events.add_event(1.0, finish_resize)


FLAVORS = FakeFlavors()


class FakeClient(object):

    def __init__(self, context):
        self.context = context
        self.flavors = FLAVORS
        self.servers = FakeServers(context, self.flavors)
        self.volumes = FakeVolumes(context)
        self.servers.volumes = self.volumes

    def get_server_volumes(self, server_id):
        return self.servers.get_server_volumes(server_id)


CLIENT_DATA = {}


def get_client_data(context):
    if context not in CLIENT_DATA:
        nova_client = FakeClient(context)
        volume_client = FakeClient(context)
        nova_client.volumes = volume_client
        volume_client.servers = nova_client
        CLIENT_DATA[context] = {
            'nova': nova_client,
            'volume': volume_client
        }
    return CLIENT_DATA[context]


def fake_create_nova_client(context):
    return get_client_data(context)['nova']


def fake_create_nova_volume_client(context):
    return get_client_data(context)['volume']
