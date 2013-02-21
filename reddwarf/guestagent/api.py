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

from eventlet import Timeout

from reddwarf.common import cfg
from reddwarf.common import exception
from reddwarf.common import utils
from reddwarf.guestagent import models as agent_models
from reddwarf.openstack.common import log as logging
from reddwarf.openstack.common import rpc
from reddwarf.openstack.common.rpc import proxy
from reddwarf.openstack.common.gettextutils import _

CONF = cfg.CONF
LOG = logging.getLogger(__name__)
AGENT_LOW_TIMEOUT = CONF.agent_call_low_timeout
AGENT_HIGH_TIMEOUT = CONF.agent_call_high_timeout
RPC_API_VERSION = "1.0"


class API(proxy.RpcProxy):
    """API for interacting with the guest manager."""

    def __init__(self, context, id):
        self.context = context
        self.id = id
        super(API, self).__init__(self._get_routing_key(),
                                  RPC_API_VERSION)

    def _call(self, method_name, timeout_sec, **kwargs):
        LOG.debug("Calling %s" % method_name)
        try:
            result = self.call(self.context,
                               self.make_msg(method_name, **kwargs),
                               timeout=timeout_sec)

            LOG.debug("Result is %s" % result)
            return result
        except Exception as e:
            LOG.error(e)
            raise exception.GuestError(original_message=str(e))
        except Timeout as t:
            if t is not timeout:
                raise
            else:
                raise exception.GuestTimeout()

    def _cast(self, method_name, **kwargs):
        LOG.debug("Casting %s" % method_name)
        try:
            self.cast(self.context, self.make_msg(method_name, **kwargs),
                      topic=kwargs.get('topic'),
                      version=kwargs.get('version'))
        except Exception as e:
            LOG.error(e)
            raise exception.GuestError(original_message=str(e))

    def _cast_with_consumer(self, method_name, **kwargs):
        try:
            conn = rpc.create_connection(new=True)
            conn.create_consumer(self._get_routing_key(), None, fanout=False)
        except Exception as e:
            LOG.error(e)
            raise exception.GuestError(original_message=str(e))
        finally:
            if conn:
                conn.close()

        # leave the cast call out of the hackity consumer create
        self._cast(method_name, **kwargs)

    def delete_queue(self):
        """Deletes the queue."""
        rpc.delete_queue(self.context, self._get_routing_key())

    def _get_routing_key(self):
        """Create the routing key based on the container id"""
        return "guestagent.%s" % self.id

    def _check_for_hearbeat(self):
        """Preemptively raise GuestTimeout if heartbeat is old."""
        try:
            agent = agent_models.AgentHeartBeat.find_by(instance_id=self.id)
            if agent_models.AgentHeartBeat.is_active(agent):
                return True
        except exception.ModelNotFoundError as mnfe:
            LOG.warn(mnfe)
        raise exception.GuestTimeout()

    def change_passwords(self, users):
        """Make an asynchronous call to change the passwords of one or more
           users."""
        LOG.debug(_("Changing passwords for users on Instance %s"), self.id)
        self._cast("change_passwords", users=users)

    def create_user(self, users):
        """Make an asynchronous call to create a new database user"""
        LOG.debug(_("Creating Users for Instance %s"), self.id)
        self._cast("create_user", users=users)

    def get_user(self, username):
        """Make an asynchronous call to get a single database user."""
        LOG.debug(_("Getting a user on Instance %s"), self.id)
        LOG.debug("User name is %s" % username)
        return self._call("get_user", AGENT_LOW_TIMEOUT, username=username)

    def list_access(self, username):
        """Show all the databases to which a user has more than USAGE."""
        LOG.debug(_("Showing user grants on Instance %s"), self.id)
        LOG.debug("User name is %s" % username)
        return self._call("list_access", AGENT_LOW_TIMEOUT, username=username)

    def grant_access(self, username, databases):
        """Give a user permission to use a given database."""
        return self._call("grant_access", AGENT_LOW_TIMEOUT,
                          username=username, databases=databases)

    def revoke_access(self, username, database):
        """Remove a user's permission to use a given database."""
        return self._call("revoke_access", AGENT_LOW_TIMEOUT,
                          username=username, database=database)

    def list_users(self, limit=None, marker=None, include_marker=False):
        """Make an asynchronous call to list database users"""
        LOG.debug(_("Listing Users for Instance %s"), self.id)
        return self._call("list_users", AGENT_LOW_TIMEOUT, limit=limit,
                          marker=marker, include_marker=include_marker)

    def delete_user(self, user):
        """Make an asynchronous call to delete an existing database user"""
        LOG.debug(_("Deleting user %s for Instance %s"), user, self.id)
        return self._cast("delete_user", user=user)

    def create_database(self, databases):
        """Make an asynchronous call to create a new database
           within the specified container"""
        LOG.debug(_("Creating databases for Instance %s"), self.id)
        self._cast("create_database", databases=databases)

    def list_databases(self, limit=None, marker=None, include_marker=False):
        """Make an asynchronous call to list databases"""
        LOG.debug(_("Listing databases for Instance %s"), self.id)
        return self._call("list_databases", AGENT_LOW_TIMEOUT, limit=limit,
                          marker=marker, include_marker=include_marker)

    def delete_database(self, database):
        """Make an asynchronous call to delete an existing database
           within the specified container"""
        LOG.debug(_("Deleting database %s for Instance %s"), database, self.id)
        self._cast("delete_database", database=database)

    def enable_root(self):
        """Make a synchronous call to enable the root user for
           access from anywhere"""
        LOG.debug(_("Enable root user for Instance %s"), self.id)
        return self._call("enable_root", AGENT_LOW_TIMEOUT)

    def disable_root(self):
        """Make a synchronous call to disable the root user for
           access from anywhere"""
        LOG.debug(_("Disable root user for Instance %s"), self.id)
        return self._call("disable_root", AGENT_LOW_TIMEOUT)

    def is_root_enabled(self):
        """Make a synchronous call to check if root access is
           available for the container"""
        LOG.debug(_("Check root access for Instance %s"), self.id)
        return self._call("is_root_enabled", AGENT_LOW_TIMEOUT)

    def get_hwinfo(self):
        """Make a synchronous call to get hardware info for the container"""
        LOG.debug(_("Check hwinfo on Instance %s"), self.id)
        return self._call("get_hwinfo", AGENT_LOW_TIMEOUT)

    def get_diagnostics(self):
        """Make a synchronous call to get diagnostics for the container"""
        LOG.debug(_("Check diagnostics on Instance %s"), self.id)
        return self._call("get_diagnostics", AGENT_LOW_TIMEOUT)

    def prepare(self, memory_mb, databases, users,
                device_path='/dev/vdb', mount_point='/mnt/volume'):
        """Make an asynchronous call to prepare the guest
           as a database container"""
        LOG.debug(_("Sending the call to prepare the Guest"))
        self._cast_with_consumer(
            "prepare", databases=databases, memory_mb=memory_mb,
            users=users, device_path=device_path, mount_point=mount_point)

    def restart(self):
        """Restart the MySQL server."""
        LOG.debug(_("Sending the call to restart MySQL on the Guest."))
        self._call("restart", AGENT_HIGH_TIMEOUT)

    def start_mysql_with_conf_changes(self, updated_memory_size):
        """Start the MySQL server."""
        LOG.debug(_("Sending the call to start MySQL on the Guest."))
        self._call("start_mysql_with_conf_changes", AGENT_HIGH_TIMEOUT,
                   updated_memory_size=updated_memory_size)

    def stop_mysql(self, do_not_start_on_reboot=False):
        """Stop the MySQL server."""
        LOG.debug(_("Sending the call to stop MySQL on the Guest."))
        self._call("stop_mysql", AGENT_HIGH_TIMEOUT,
                   do_not_start_on_reboot=do_not_start_on_reboot)

    def upgrade(self):
        """Make an asynchronous call to self upgrade the guest agent"""
        LOG.debug(_("Sending an upgrade call to nova-guest"))
        self._cast_with_consumer("upgrade")

    def get_volume_info(self):
        """Make a synchronous call to get volume info for the container"""
        LOG.debug(_("Check Volume Info on Instance %s"), self.id)
        # self._check_for_hearbeat()
        return self._call("get_filesystem_stats", AGENT_LOW_TIMEOUT,
                          fs_path="/var/lib/mysql")

    def update_guest(self):
        """Make a synchronous call to update the guest agent."""
        self._call("update_guest", AGENT_HIGH_TIMEOUT)
