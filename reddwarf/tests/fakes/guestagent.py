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
import time

from reddwarf.tests.fakes.common import EventSimulator

DB = {}
LOG = logging.getLogger(__name__)


class FakeGuest(object):

    def __init__(self, id):
        self.id = id
        self.users = {}
        self.dbs = {}
        self.root_was_enabled = False

    def create_database(self, databases):
        for db in databases:
            self.dbs[db['_name']] = db

    def create_user(self, users):
        for user in users:
            self._create_user(user)

    def _create_user(self, user):
        self.users[user['_name']] = user
        return user

    def delete_database(self, database):
        if database['_name'] in self.dbs:
            del self.dbs[database['_name']]

    def delete_user(self, user):
        if user['_name'] in self.users:
            del self.users[user['_name']]

    def enable_root(self):
        self.root_was_enabled = True
        return self._create_user({
            "_name": "root",
            "_password": "12345",
            "_databases": [],
        })

    def is_root_enabled(self):
        return self.root_was_enabled

    def list_databases(self):
        return [self.dbs[name] for name in self.dbs]

    def list_users(self):
        return [self.users[name] for name in self.users]

    def prepare(self, memory_mb, databases, users):
        from reddwarf.instance.models import InstanceServiceStatus
        from reddwarf.instance.models import ServiceStatuses
        def update_db():
            status = InstanceServiceStatus.find_by(instance_id=self.id)
            status.status = ServiceStatuses.RUNNING
            status.save()
        EventSimulator.add_event(2.0, update_db)

    def restart(self):
        # All this does is restart, and shut off the status updates while it
        # does so. So there's actually nothing to do to fake this out except
        # take a nap.
        time.sleep(1)

    def start_mysql_with_conf_changes(self, updated_memory_size):
        from reddwarf.instance.models import InstanceServiceStatus
        from reddwarf.instance.models import ServiceStatuses
        def update_db():
            status = InstanceServiceStatus.find_by(instance_id=self.id)
            status.status = ServiceStatuses.RUNNING
            status.save()
        EventSimulator.add_event(0.5, update_db)

    def stop_mysql(self):
        from reddwarf.instance.models import InstanceServiceStatus
        from reddwarf.instance.models import ServiceStatuses
        def update_db():
            status = InstanceServiceStatus.find_by(instance_id=self.id)
            status.status = ServiceStatuses.SHUTDOWN
            status.save()
        EventSimulator.add_event(0.5, update_db)


def get_or_create(id):
    if id not in DB:
        DB[id] = FakeGuest(id)
    return DB[id]


def fake_create_guest_client(context, id):
    return get_or_create(id)
