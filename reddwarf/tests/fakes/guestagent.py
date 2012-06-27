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

    def list_databases(self, limit=None, marker=None, include_marker=False):
        dbs = [self.dbs[name] for name in self.dbs]
        names = [db['_name'] for db in dbs]
        if marker in names:
            if not include_marker:
                # Cut off everything left of and including the marker item.
                dbs = dbs[names.index(marker) + 1:]
            else:
                dbs = dbs[names.index(marker):]
        next_marker = None
        if limit:
            if len(dbs) > limit:
                next_marker = dbs[limit - 1]['_name']
            dbs = dbs[:limit]
        return dbs, next_marker

    def list_users(self, limit=None, marker=None, include_marker=False):
        users = [self.users[name] for name in self.users]
        names = [user['_name'] for user in users]
        if marker in names:
            if not include_marker:
                users = users[names.index(marker) + 1:]
            else:
                users = users[names.index(marker):]
        next_marker = None
        if limit:
            if len(users) > limit:
                next_marker = users[limit - 1]['_name']
            users = users[:limit]
        return users, next_marker

    def prepare(self, memory_mb, databases, users, device_path=None,
                mount_point=None):
        from reddwarf.instance.models import InstanceServiceStatus
        from reddwarf.instance.models import ServiceStatuses
        from reddwarf.guestagent.models import AgentHeartBeat
        LOG.debug("users... %s" % users)
        LOG.debug("databases... %s" % databases)
        self.create_user(users)
        self.create_database(databases)

        def update_db():
            status = InstanceServiceStatus.find_by(instance_id=self.id)
            status.status = ServiceStatuses.RUNNING
            status.save()
            AgentHeartBeat.create(instance_id=self.id)
        EventSimulator.add_event(1.0, update_db)

    def restart(self):
        from reddwarf.instance.models import InstanceServiceStatus
        from reddwarf.instance.models import ServiceStatuses
        # All this does is restart, and shut off the status updates while it
        # does so. So there's actually nothing to do to fake this out except
        # take a nap.
        time.sleep(1)
        status = InstanceServiceStatus.find_by(instance_id=self.id)
        status.status = ServiceStatuses.RUNNING
        status.save()

    def start_mysql_with_conf_changes(self, updated_memory_size):
        from reddwarf.instance.models import InstanceServiceStatus
        from reddwarf.instance.models import ServiceStatuses
        status = InstanceServiceStatus.find_by(instance_id=self.id)
        status.status = ServiceStatuses.RUNNING
        status.save()

    def stop_mysql(self):
        from reddwarf.instance.models import InstanceServiceStatus
        from reddwarf.instance.models import ServiceStatuses
        status = InstanceServiceStatus.find_by(instance_id=self.id)
        status.status = ServiceStatuses.SHUTDOWN
        status.save()

    def get_volume_info(self):
        """Return used volume information in bytes."""
        return {'used': 175756487}


def get_or_create(id):
    if id not in DB:
        DB[id] = FakeGuest(id)
    return DB[id]


def fake_create_guest_client(context, id):
    return get_or_create(id)
