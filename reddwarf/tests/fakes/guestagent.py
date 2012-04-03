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


from reddwarf.tests.fakes.common import EventSimulator


DB = {}
LOG = logging.getLogger(__name__)


class FakeGuest(object):

    def __init__(self, id):
        self.id = id

    def prepare(self, memory_mb, databases):
        from reddwarf.instance.models import InstanceServiceStatus
        from reddwarf.instance.models import ServiceStatuses

        def update_db():
            status = InstanceServiceStatus.find_by(instance_id=self.id)
            status.status = ServiceStatuses.RUNNING
            status.save()
        EventSimulator.add_event(2.0, update_db)


def get_or_create(id):
    if id not in DB:
        DB[id] = FakeGuest(id)
    return DB[id]


def fake_create_guest_client(context, id):
    return get_or_create(id)
