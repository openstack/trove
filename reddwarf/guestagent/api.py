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

    def _call(self, method_name, **kwargs):
        try:
            return rpc.call(self.context, self._get_routing_key(),
                            {"method": method_name, "args": kwargs})
        except Exception as e:
            LOG.error(e)
            raise exception.GuestError(original_message=str(e))

    def _cast(self, method_name, **kwargs):
        try:
            rpc.cast(self.context, self._get_routing_key(),
                     {"method": method_name,
                      "args": kwargs})
        except Exception as e:
            LOG.error(e)
            raise exception.GuestError(original_message=str(e))

    def _cast_with_consumer(self, method_name, **kwargs):
        try:
            rpc.cast_with_consumer(self.context, self._get_routing_key(),
                                   {"method": method_name, "args": kwargs})
        except Exception as e:
            LOG.error(e)
            raise exception.GuestError(original_message=str(e))

    def _get_routing_key(self):
        """Create the routing key based on the container id"""
        return "guestagent.%s" % self.id

    def create_user(self, users):
        """Make an asynchronous call to create a new database user"""
        LOG.debug(_("Creating Users for Instance %s"), self.id)
        self._cast("create_user", users=users)

    def list_users(self):
        """Make an asynchronous call to list database users"""
        LOG.debug(_("Listing Users for Instance %s"), self.id)
        return self._call("list_users")

    def delete_user(self, user):
        """Make an asynchronous call to delete an existing database user"""
        LOG.debug(_("Deleting user %s for Instance %s"), user, self.id)
        return self._cast("delete_user", user=user)

    def create_database(self, databases):
        """Make an asynchronous call to create a new database
           within the specified container"""
        LOG.debug(_("Creating databases for Instance %s"), self.id)
        self._cast("create_database", databases=databases)

    def list_databases(self):
        """Make an asynchronous call to list databases"""
        LOG.debug(_("Listing databases for Instance %s"), self.id)
        return self._call("list_databases")

    def delete_database(self, database):
        """Make an asynchronous call to delete an existing database
           within the specified container"""
        LOG.debug(_("Deleting database %s for Instance %s"), database, self.id)
        self._cast("delete_database", database=database)

    def enable_root(self):
        """Make a synchronous call to enable the root user for
           access from anywhere"""
        LOG.debug(_("Enable root user for Instance %s"), self.id)
        return self._call("enable_root")

    def disable_root(self):
        """Make a synchronous call to disable the root user for
           access from anywhere"""
        LOG.debug(_("Disable root user for Instance %s"), self.id)
        return self._call("disable_root")

    def is_root_enabled(self):
        """Make a synchronous call to check if root access is
           available for the container"""
        LOG.debug(_("Check root access for Instance %s"), self.id)
        return self._call("is_root_enabled")

    def get_diagnostics(self):
        """Make a synchronous call to get diagnostics for the container"""
        LOG.debug(_("Check diagnostics on Instance %s"), self.id)
        return self._call("get_diagnostics")

    def prepare(self, memory_mb, databases, users,
                device_path='/dev/vdb', mount_point='/mnt/volume'):
        """Make an asynchronous call to prepare the guest
           as a database container"""
        LOG.debug(_("Sending the call to prepare the Guest"))
        self._cast_with_consumer("prepare", databases=databases,
            memory_mb=memory_mb, users=users, device_path=device_path,
            mount_point=mount_point)

    def restart(self):
        """Restart the MySQL server."""
        LOG.debug(_("Sending the call to restart MySQL on the Guest."))
        self._call("restart")

    def start_mysql_with_conf_changes(self, updated_memory_size):
        """Start the MySQL server."""
        LOG.debug(_("Sending the call to start MySQL on the Guest."))
        self._call("start_mysql_with_conf_changes",
                   updated_memory_size=updated_memory_size)

    def stop_mysql(self):
        """Stop the MySQL server."""
        LOG.debug(_("Sending the call to stop MySQL on the Guest."))
        self._call("stop_mysql")

    def upgrade(self):
        """Make an asynchronous call to self upgrade the guest agent"""
        LOG.debug(_("Sending an upgrade call to nova-guest"))
        self._cast_with_consumer("upgrade")
