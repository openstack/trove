# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2012 OpenStack Foundation
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

from trove.openstack.common import log as logging
import time
import re

from trove.tests.fakes.common import get_event_spawer
from trove.common import exception as rd_exception
from trove.common import instance as rd_instance
from trove.tests.util import unquote_user_host

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

        # Our default admin user.
        self._create_user({
            "_name": "os_admin",
            "_host": "%",
            "_password": "12345",
            "_databases": [],
        })

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

    def _check_username(self, username):
        unsupported_chars = re.compile("^\s|\s$|'|\"|;|`|,|/|\\\\")
        if (not username or
                unsupported_chars.search(username) or
                ("%r" % username).find("\\") != -1):
            raise ValueError("'%s' is not a valid user name." % username)
        if len(username) > 16:
            raise ValueError("User name '%s' is too long. Max length = 16" %
                             username)

    def change_passwords(self, users):
        for user in users:
            # Use the model to check validity.
            username = user['name']
            self._check_username(username)
            hostname = user['host']
            password = user['password']
            if (username, hostname) not in self.users:
                raise rd_exception.UserNotFound(
                    "User %s@%s cannot be found on the instance."
                    % (username, hostname))
            self.users[(username, hostname)]['password'] = password

    def update_attributes(self, username, hostname, user_attrs):
        LOG.debug("Updating attributes")
        self._check_username(username)
        if (username, hostname) not in self.users:
                raise rd_exception.UserNotFound(
                    "User %s@%s cannot be found on the instance."
                    % (username, hostname))
        new_name = user_attrs.get('name')
        new_host = user_attrs.get('host')
        new_password = user_attrs.get('password')
        old_name = username
        old_host = hostname
        name = new_name or old_name
        host = new_host or old_host
        if new_name or new_host:
            old_grants = self.grants.get((old_name, old_host), set())
            self._create_user({
                "_name": name,
                "_host": host,
                "_password": self.users[(old_name, host)]['_password'],
                "_databases": [],
            })
            self.grants[(name, host)] = old_grants
            del self.users[(old_name, old_host)]
        if new_password:
            self.users[(name, host)]['_password'] = new_password

    def create_database(self, databases):
        for db in databases:
            self.dbs[db['_name']] = db

    def create_user(self, users):
        for user in users:
            self._create_user(user)

    def _create_user(self, user):
        username = user['_name']
        self._check_username(username)
        hostname = user['_host']
        if hostname is None:
            hostname = '%'
        self.users[(username, hostname)] = user
        print("CREATING %s @ %s" % (username, hostname))
        databases = [db['_name'] for db in user['_databases']]
        self.grant_access(username, hostname, databases)
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
            "_host": "%",
            "_password": "12345",
            "_databases": [],
        })

    def delete_user(self, user):
        username = user['_name']
        self._check_username(username)
        hostname = user['_host']
        self.grants[(username, hostname)] = set()
        if (username, hostname) in self.users:
            del self.users[(username, hostname)]

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
        # The markers for users are a composite of the username and hostname.
        names = sorted(["%s@%s" % (name, host) for (name, host) in self.users])
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
        return ([self.users[unquote_user_host(userhost)]
                 for userhost in names], next_marker)

    def get_user(self, username, hostname):
        self._check_username(username)
        for (u, h) in self.users:
            print("%r @ %r" % (u, h))
        if (username, hostname) not in self.users:
            raise rd_exception.UserNotFound(
                "User %s@%s cannot be found on the instance."
                % (username, hostname))
        return self.users.get((username, hostname), None)

    def prepare(self, memory_mb, databases, users, device_path=None,
                mount_point=None, backup_id=None, config_contents=None):
        from trove.instance.models import DBInstance
        from trove.instance.models import InstanceServiceStatus
        from trove.guestagent.models import AgentHeartBeat
        LOG.debug("users... %s" % users)
        LOG.debug("databases... %s" % databases)
        instance_name = DBInstance.find_by(id=self.id).name
        self.create_user(users)
        self.create_database(databases)

        def update_db():
            status = InstanceServiceStatus.find_by(instance_id=self.id)
            if instance_name.endswith('GUEST_ERROR'):
                status.status = rd_instance.ServiceStatuses.FAILED
            else:
                status.status = rd_instance.ServiceStatuses.RUNNING
            status.save()
            AgentHeartBeat.create(instance_id=self.id)
        self.event_spawn(1.0, update_db)

    def _set_status(self, new_status='RUNNING'):
        from trove.instance.models import InstanceServiceStatus
        print("Setting status to %s" % new_status)
        states = {'RUNNING': rd_instance.ServiceStatuses.RUNNING,
                  'SHUTDOWN': rd_instance.ServiceStatuses.SHUTDOWN,
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

    def reset_configuration(self, config):
        # There's nothing to do here, since there is no config to update.
        pass

    def start_db_with_conf_changes(self, config_contents):
        time.sleep(2)
        self._set_status('RUNNING')

    def stop_db(self, do_not_start_on_reboot=False):
        self._set_status('SHUTDOWN')

    def get_volume_info(self):
        """Return used volume information in GB."""
        return {'used': 0.16}

    def grant_access(self, username, hostname, databases):
        """Add a database to a users's grant list."""
        if (username, hostname) not in self.users:
            raise rd_exception.UserNotFound(
                "User %s cannot be found on the instance." % username)
        current_grants = self.grants.get((username, hostname), set())
        for db in databases:
            current_grants.add(db)
        self.grants[(username, hostname)] = current_grants

    def revoke_access(self, username, hostname, database):
        """Remove a database from a users's grant list."""
        if (username, hostname) not in self.users:
            raise rd_exception.UserNotFound(
                "User %s cannot be found on the instance." % username)
        g = self.grants.get((username, hostname), set())
        if database not in self.grants.get((username, hostname), set()):
            raise rd_exception.DatabaseNotFound(
                "Database %s cannot be found on the instance." % database)
        current_grants = self.grants.get((username, hostname), set())
        if database in current_grants:
            current_grants.remove(database)
        self.grants[(username, hostname)] = current_grants

    def list_access(self, username, hostname):
        if (username, hostname) not in self.users:
            raise rd_exception.UserNotFound(
                "User %s cannot be found on the instance." % username)
        current_grants = self.grants.get((username, hostname), set())
        dbs = [{'_name': db,
                '_collate': '',
                '_character_set': '',
                } for db in current_grants]
        return dbs

    def create_backup(self, backup_id):
        from trove.backup.models import Backup, BackupState
        backup = Backup.get_by_id(context=None, backup_id=backup_id)

        def finish_create_backup():
            backup.state = BackupState.COMPLETED
            backup.save()
        self.event_spawn(1.0, finish_create_backup)


def get_or_create(id):
    if id not in DB:
        DB[id] = FakeGuest(id)
    return DB[id]


def fake_create_guest_client(context, id):
    return get_or_create(id)
