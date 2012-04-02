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
from reddwarf.tests.fakes.common import EventSimulator


LOG = logging.getLogger(__name__)


class FakeFlavor(object):

    def __init__(self, id, disk, name, ram):
        self.id = id
        self.disk = disk
        self.name = name
        self.ram = ram

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
        return {"id":self.id, "links":self.links}

class FakeFlavors(object):

    def __init__(self):
        self.db = {}
        self._add(1, 0, "m1.tiny", 512)
        self._add(2, 10, "m1.small", 2048)
        self._add(3, 10, "m1.medium", 4096)
        self._add(4, 10, "m1.large", 8192)
        self._add(5, 10, "m1.xlarge", 16384)

    def _add(self, *args, **kwargs):
        new_flavor = FakeFlavor(*args, **kwargs)
        self.db[new_flavor.id] = new_flavor

    def get(self, id):
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

class FakeServer(object):

    def __init__(self, parent, id, name, image_id, flavor_ref):
        self.id = id
        self.parent = parent
        self.name = name
        self.image_id = image_id
        self.flavor_ref = flavor_ref
        self.events = EventSimulator()
        self.schedule_status("BUILD", 0.0)

    @property
    def addresses(self):
        return ["We don't even use this."]

    def delete(self):
        self.schedule_status = []
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


class FakeServers(object):

    def __init__(self, flavors):
        self.db = {}
        self.flavors = flavors
        self.next_id = 10;
        self.events = EventSimulator()

    def create(self, name, image_id, flavor_ref, files):
        id = "FAKE_%d" % self.next_id
        self.next_id += 1
        server = FakeServer(self, id, name, image_id, flavor_ref)
        self.db[id] = server
        server.schedule_status("ACTIVE", 1)
        return server

    def get(self, id):
        if id not in self.db:
            LOG.error("Couldn't find id %s, collection=%s" % (id, self.db))
            raise nova_exceptions.NotFound(404, "Not found")
        else:
            return self.db[id]

    def list(self):
        return [v for (k, v) in self.db.items()]

    def schedule_delete(self, id, time_from_now):
        def delete_server():
            LOG.info("Simulated event ended, deleting server %s." % id)
            del self.db[id]
        self.events.add_event(time_from_now, delete_server)


# The global var contains the servers dictionary in use for the life of these
# tests.
FLAVORS = FakeFlavors()
SERVERS = FakeServers(FLAVORS)


class FakeClient(object):

    def __init__(self):
        self.servers = SERVERS
        self.flavors = FLAVORS


def fake_create_nova_client(*args, **kwargs):
    return FakeClient()
