# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2011 OpenStack, LLC.
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

"""
Handles all request to the Platform or Guest VM
"""


import logging
from reddwarf import rpc
from reddwarf.common import config
from reddwarf.common import exception
from reddwarf.common import utils
# from nova.db import api as dbapi


LOG = logging.getLogger(__name__)


class API(object):
    """API for interacting with the guest manager."""

    def __init__(self, context, id):
        self.context = context
        self.id = id

    def _get_routing_key(self):
        """Create the routing key based on the container id"""
        return "guestagent.%s" % self.id

    def create_user(self, users):
        """Make an asynchronous call to create a new database user"""
        LOG.debug("Creating Users for Instance %s", self.id)
        rpc.cast(self.context, self._get_routing_key(),
                 {"method": "create_user",
                  "args": {"users": users}
                 })

    def list_users(self):
        """Make an asynchronous call to list database users"""
        LOG.debug("Listing Users for Instance %s", self.id)
        return rpc.call(context, self._get_routing_key(),
                 {"method": "list_users"})

    def delete_user(self, user):
        """Make an asynchronous call to delete an existing database user"""
        LOG.debug("Deleting user %s for Instance %s", user, self.id)
        rpc.cast(self.context, self._get_routing_key(),
                 {"method": "delete_user",
                  "args": {"user": user}
                 })

    def create_database(self, databases):
        """Make an asynchronous call to create a new database
           within the specified container"""
        LOG.debug("Creating databases for Instance %s", self.id)
        rpc.cast(self.context, self._get_routing_key(),
                 {"method": "create_database",
                  "args": {"databases": databases}
                 })

    def list_databases(self):
        """Make an asynchronous call to list database users"""
        LOG.debug("Listing Users for Instance %s", self.id)
        return rpc.call(self.context, self._get_routing_key(),
                 {"method": "list_databases"})

    def delete_database(self, database):
        """Make an asynchronous call to delete an existing database
           within the specified container"""
        LOG.debug("Deleting database %s for Instance %s", database, self.id)
        rpc.cast(self.context, self._get_routing_key(),
                 {"method": "delete_database",
                  "args": {"database": database}
                 })

    def enable_root(self):
        """Make a synchronous call to enable the root user for
           access from anywhere"""
        LOG.debug("Enable root user for Instance %s", self.id)
        return rpc.call(self.context, self._get_routing_key(),
                 {"method": "enable_root"})

    def disable_root(self):
        """Make a synchronous call to disable the root user for
           access from anywhere"""
        LOG.debug("Disable root user for Instance %s", self.id)
        return rpc.call(self.context, self._get_routing_key(),
                 {"method": "disable_root"})

    def is_root_enabled(self):
        """Make a synchronous call to check if root access is
           available for the container"""
        LOG.debug("Check root access for Instance %s", self.id)
        return rpc.call(self.context, self._get_routing_key(),
                 {"method": "is_root_enabled"})

    def get_diagnostics(self):
        """Make a synchronous call to get diagnostics for the container"""
        LOG.debug("Check diagnostics on Instance %s", self.id)
        return rpc.call(self.context, self._get_routing_key(),
                 {"method": "get_diagnostics"})

    def prepare(self, memory_mb, databases):
        """Make an asynchronous call to prepare the guest
           as a database container"""
        LOG.debug(_("Sending the call to prepare the Guest"))
        rpc.cast_with_consumer(self.context, self._get_routing_key(),
                 {"method": "prepare",
                  "args": {"databases": databases,
                           "memory_mb": memory_mb}
                 })

    def restart(self):
        """Restart the MySQL server."""
        LOG.debug(_("Sending the call to restart MySQL on the Guest."))
        rpc.call(self.context, self._get_routing_key(),
                 {"method": "restart",
                  "args": {}
                 })

    def start_mysql_with_conf_changes(self, updated_memory_size):
        """Start the MySQL server."""
        LOG.debug(_("Sending the call to start MySQL on the Guest."))
        try:
            rpc.call(self.context, self._get_routing_key(),
                    {"method": "start_mysql_with_conf_changes",
                     "args": {'updated_memory_size': updated_memory_size}
                    })
        except Exception as e:
            LOG.error(e)
            raise exception.GuestError(original_message=str(e))

    def stop_mysql(self):
        """Stop the MySQL server."""
        LOG.debug(_("Sending the call to stop MySQL on the Guest."))
        try:
            rpc.call(self.context, self._get_routing_key(),
                    {"method": "stop_mysql",
                     "args": {}
                    })
        except Exception as e:
            LOG.error(e)
            raise exception.GuestError(original_message=str(e))

    def upgrade(self):
        """Make an asynchronous call to self upgrade the guest agent"""
        topic = self._get_routing_key()
        LOG.debug("Sending an upgrade call to nova-guest %s", topic)
        rpc.cast_with_consumer(self.context, topic, {"method": "upgrade"})
