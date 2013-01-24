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

from reddwarf.openstack.common import log as logging
import time

from reddwarf.tests.fakes.common import get_event_spawer
from reddwarf.common import exception as rd_exception

DB = {}
LOG = logging.getLogger(__name__)


class FakeGuest(object):

    def __init__(self, id):
        self.id = id
        self.users = {}
        self.dbs = {}
        self.root_was_enabled = False
        self.version = 1
        self.event_spawn = get_event_spawer()
        self.grants = {}

    def get_hwinfo(self):
        return {'mem_total': 524288, 'num_cpus': 1}

    def get_diagnostics(self):
        return {
            'version': str(self.version),
            'fd_size': 64,
            'vm_size': 29096,
            'vm_peak': 29160,
            'vm_rss': 2872,
            'vm_hwm': 2872,
            'threads': 2
        }

    def update_guest(self):
        LOG.debug("Updating guest %s" % self.id)
        self.version += 1

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

    def delete_queue(self):
        pass

    def enable_root(self):
        self.root_was_enabled = True
        return self._create_user({
            "_name": "root",
            "_password": "12345",
            "_databases": [],
        })

    def delete_user(self, user):
        if user['_name'] in self.users:
            del self.users[user['_name']]

    def is_root_enabled(self):
        return self.root_was_enabled

    def _list_resource(self, resource, limit=None, marker=None,
                       include_marker=False):
        names = sorted([name for name in resource])
        if marker in names:
            if not include_marker:
                # Cut off everything left of and including the marker item.
                names = names[names.index(marker) + 1:]
            else:
                names = names[names.index(marker):]
        next_marker = None
        if limit:
            if len(names) > limit:
                next_marker = names[limit - 1]
            names = names[:limit]
        return [resource[name] for name in names], next_marker

    def list_databases(self, limit=None, marker=None, include_marker=False):
        return self._list_resource(self.dbs, limit, marker, include_marker)

    def list_users(self, limit=None, marker=None, include_marker=False):
        return self._list_resource(self.users, limit, marker, include_marker)

    def get_user(self, username):
        return self.users.get(username, None)

    def prepare(self, memory_mb, databases, users, device_path=None,
                mount_point=None):
        from reddwarf.instance.models import DBInstance
        from reddwarf.instance.models import InstanceServiceStatus
        from reddwarf.instance.models import ServiceStatuses
        from reddwarf.guestagent.models import AgentHeartBeat
        LOG.debug("users... %s" % users)
        LOG.debug("databases... %s" % databases)
        instance_name = DBInstance.find_by(id=self.id).name
        self.create_user(users)
        self.create_database(databases)

        def update_db():
            status = InstanceServiceStatus.find_by(instance_id=self.id)
            if instance_name.endswith('GUEST_ERROR'):
                status.status = ServiceStatuses.FAILED
            else:
                status.status = ServiceStatuses.RUNNING
            status.save()
            AgentHeartBeat.create(instance_id=self.id)
        self.event_spawn(1.0, update_db)

    def _set_status(self, new_status='RUNNING'):
        from reddwarf.instance.models import InstanceServiceStatus
        from reddwarf.instance.models import ServiceStatuses
        print("Setting status to %s" % new_status)
        states = {'RUNNING': ServiceStatuses.RUNNING,
                  'SHUTDOWN': ServiceStatuses.SHUTDOWN,
                  }
        status = InstanceServiceStatus.find_by(instance_id=self.id)
        status.status = states[new_status]
        status.save()

    def restart(self):
        # All this does is restart, and shut off the status updates while it
        # does so. So there's actually nothing to do to fake this out except
        # take a nap.
        print("Sleeping for a second.")
        time.sleep(1)
        self._set_status('RUNNING')

    def start_mysql_with_conf_changes(self, updated_memory_size):
        time.sleep(2)
        self._set_status('RUNNING')

    def stop_mysql(self, do_not_start_on_reboot=False):
        self._set_status('SHUTDOWN')

    def get_volume_info(self):
        """Return used volume information in bytes."""
        return {'used': 175756487}

    def grant_access(self, username, databases):
        """Add a database to a users's grant list."""
        if username not in self.users:
            raise rd_exception.UserNotFound(
                "User %s cannot be found on the instance." % username)
        current_grants = self.grants.get((username, '%'), set())
        for db in databases:
            current_grants.add(db)
        self.grants[(username, '%')] = current_grants

    def revoke_access(self, username, database):
        """Remove a database from a users's grant list."""
        if username not in self.users:
            raise rd_exception.UserNotFound(
                "User %s cannot be found on the instance." % username)
        g = self.grants.get((username, '%'), set())
        if database not in self.grants.get((username, '%'), set()):
            raise rd_exception.DatabaseNotFound(
                "Database %s cannot be found on the instance." % database)
        current_grants = self.grants.get((username, '%'), set())
        if database in current_grants:
            current_grants.remove(database)
        self.grants[(username, '%')] = current_grants

    def list_access(self, username):
        if username not in self.users:
            raise rd_exception.UserNotFound(
                "User %s cannot be found on the instance." % username)
        current_grants = self.grants.get((username, '%'), set())
        dbs = [{'_name': db,
                '_collate': '',
                '_character_set': '',
                } for db in current_grants]
        return dbs


def get_or_create(id):
    if id not in DB:
        DB[id] = FakeGuest(id)
    return DB[id]


def fake_create_guest_client(context, id):
    return get_or_create(id)
