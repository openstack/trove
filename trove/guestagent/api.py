# Copyright (c) 2011 OpenStack Foundation
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

from trove.common import cfg
from trove.common import exception
from trove.common import rpc as rd_rpc
from trove.guestagent import models as agent_models
from trove.openstack.common import rpc
from trove.openstack.common import log as logging
from trove.openstack.common.rpc import proxy
from trove.openstack.common.rpc import common

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
        LOG.debug("Calling %s with timeout %s" % (method_name, timeout_sec))
        try:
            result = self.call(self.context,
                               self.make_msg(method_name, **kwargs),
                               timeout=timeout_sec)

            LOG.debug("Result is %s" % result)
            return result
        except common.RemoteError as r:
            LOG.error(r)
            raise exception.GuestError(original_message=r.value)
        except Exception as e:
            LOG.error(e)
            raise exception.GuestError(original_message=str(e))
        except Timeout:
            raise exception.GuestTimeout()

    def _cast(self, method_name, **kwargs):
        LOG.debug("Casting %s" % method_name)
        try:
            self.cast(self.context, self.make_msg(method_name, **kwargs),
                      topic=kwargs.get('topic'),
                      version=kwargs.get('version'))
        except common.RemoteError as r:
            LOG.error(r)
            raise exception.GuestError(original_message=r.value)
        except Exception as e:
            LOG.error(e)
            raise exception.GuestError(original_message=str(e))

    def _cast_with_consumer(self, method_name, **kwargs):
        conn = None
        try:
            conn = rpc.create_connection(new=True)
            conn.create_consumer(self._get_routing_key(), None, fanout=False)
        except common.RemoteError as r:
            LOG.error(r)
            raise exception.GuestError(original_message=r.value)
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
        topic = self._get_routing_key()
        LOG.debug("Deleting queue with name %s." % topic)
        rd_rpc.delete_queue(self.context, topic)

    def _get_routing_key(self):
        """Create the routing key based on the container id."""
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
           users.
        """
        LOG.debug("Changing passwords for users on Instance %s", self.id)
        self._cast("change_passwords", users=users)

    def update_attributes(self, username, hostname, user_attrs):
        """Update user attributes."""
        LOG.debug("Changing user attributes on Instance %s", self.id)
        self._cast("update_attributes", username=username, hostname=hostname,
                   user_attrs=user_attrs)

    def create_user(self, users):
        """Make an asynchronous call to create a new database user"""
        LOG.debug("Creating Users for Instance %s", self.id)
        self._cast("create_user", users=users)

    def get_user(self, username, hostname):
        """Make an asynchronous call to get a single database user."""
        LOG.debug("Getting a user on Instance %s", self.id)
        LOG.debug("User name is %s" % username)
        return self._call("get_user", AGENT_LOW_TIMEOUT,
                          username=username, hostname=hostname)

    def list_access(self, username, hostname):
        """Show all the databases to which a user has more than USAGE."""
        LOG.debug("Showing user grants on Instance %s", self.id)
        LOG.debug("User name is %s" % username)
        return self._call("list_access", AGENT_LOW_TIMEOUT,
                          username=username, hostname=hostname)

    def grant_access(self, username, hostname, databases):
        """Grant a user permission to use a given database."""
        return self._call("grant_access", AGENT_LOW_TIMEOUT,
                          username=username, hostname=hostname,
                          databases=databases)

    def revoke_access(self, username, hostname, database):
        """Remove a user's permission to use a given database."""
        return self._call("revoke_access", AGENT_LOW_TIMEOUT,
                          username=username, hostname=hostname,
                          database=database)

    def list_users(self, limit=None, marker=None, include_marker=False):
        """Make an asynchronous call to list database users."""
        LOG.debug("Listing Users for Instance %s", self.id)
        return self._call("list_users", AGENT_LOW_TIMEOUT, limit=limit,
                          marker=marker, include_marker=include_marker)

    def delete_user(self, user):
        """Make an asynchronous call to delete an existing database user."""
        LOG.debug("Deleting user %(user)s for Instance %(instance_id)s" %
                  {'user': user, 'instance_id': self.id})
        self._cast("delete_user", user=user)

    def create_database(self, databases):
        """Make an asynchronous call to create a new database
           within the specified container
        """
        LOG.debug("Creating databases for Instance %s", self.id)
        self._cast("create_database", databases=databases)

    def list_databases(self, limit=None, marker=None, include_marker=False):
        """Make an asynchronous call to list databases."""
        LOG.debug("Listing databases for Instance %s", self.id)
        return self._call("list_databases", AGENT_LOW_TIMEOUT, limit=limit,
                          marker=marker, include_marker=include_marker)

    def delete_database(self, database):
        """Make an asynchronous call to delete an existing database
           within the specified container
        """
        LOG.debug("Deleting database %(database)s for "
                  "Instance %(instance_id)s" % {'database': database,
                                                'instance_id': self.id})
        self._cast("delete_database", database=database)

    def enable_root(self):
        """Make a synchronous call to enable the root user for
           access from anywhere
        """
        LOG.debug("Enable root user for Instance %s", self.id)
        return self._call("enable_root", AGENT_HIGH_TIMEOUT)

    def disable_root(self):
        """Make a synchronous call to disable the root user for
           access from anywhere
        """
        LOG.debug("Disable root user for Instance %s", self.id)
        return self._call("disable_root", AGENT_LOW_TIMEOUT)

    def is_root_enabled(self):
        """Make a synchronous call to check if root access is
           available for the container
        """
        LOG.debug("Check root access for Instance %s", self.id)
        return self._call("is_root_enabled", AGENT_LOW_TIMEOUT)

    def get_hwinfo(self):
        """Make a synchronous call to get hardware info for the container"""
        LOG.debug("Check hwinfo on Instance %s", self.id)
        return self._call("get_hwinfo", AGENT_LOW_TIMEOUT)

    def get_diagnostics(self):
        """Make a synchronous call to get diagnostics for the container"""
        LOG.debug("Check diagnostics on Instance %s", self.id)
        return self._call("get_diagnostics", AGENT_LOW_TIMEOUT)

    def prepare(self, memory_mb, packages, databases, users,
                device_path='/dev/vdb', mount_point='/mnt/volume',
                backup_info=None, config_contents=None, root_password=None,
                overrides=None):
        """Make an asynchronous call to prepare the guest
           as a database container optionally includes a backup id for restores
        """
        LOG.debug("Sending the call to prepare the Guest")
        self._cast_with_consumer(
            "prepare", packages=packages, databases=databases,
            memory_mb=memory_mb, users=users, device_path=device_path,
            mount_point=mount_point, backup_info=backup_info,
            config_contents=config_contents, root_password=root_password,
            overrides=overrides)

    def restart(self):
        """Restart the MySQL server."""
        LOG.debug("Sending the call to restart MySQL on the Guest.")
        self._call("restart", AGENT_HIGH_TIMEOUT)

    def start_db_with_conf_changes(self, config_contents):
        """Start the MySQL server."""
        LOG.debug("Sending the call to start MySQL on the Guest with "
                  "a timeout of %s." % AGENT_HIGH_TIMEOUT)
        self._call("start_db_with_conf_changes", AGENT_HIGH_TIMEOUT,
                   config_contents=config_contents)

    def reset_configuration(self, configuration):
        """Ignore running state of MySQL, and just change the config file
           to a new flavor.
        """
        LOG.debug("Sending the call to change MySQL conf file on the Guest "
                  "with a timeout of %s." % AGENT_HIGH_TIMEOUT)
        self._call("reset_configuration", AGENT_HIGH_TIMEOUT,
                   configuration=configuration)

    def stop_db(self, do_not_start_on_reboot=False):
        """Stop the MySQL server."""
        LOG.debug("Sending the call to stop MySQL on the Guest.")
        self._call("stop_db", AGENT_HIGH_TIMEOUT,
                   do_not_start_on_reboot=do_not_start_on_reboot)

    def upgrade(self):
        """Make an asynchronous call to self upgrade the guest agent."""
        LOG.debug("Sending an upgrade call to nova-guest")
        self._cast_with_consumer("upgrade")

    def get_volume_info(self):
        """Make a synchronous call to get volume info for the container."""
        LOG.debug("Check Volume Info on Instance %s", self.id)
        # self._check_for_hearbeat()
        return self._call("get_filesystem_stats", AGENT_LOW_TIMEOUT,
                          fs_path=None)

    def update_guest(self):
        """Make a synchronous call to update the guest agent."""
        self._call("update_guest", AGENT_HIGH_TIMEOUT)

    def create_backup(self, backup_info):
        """Make async call to create a full backup of this instance."""
        LOG.debug("Create Backup %(backup_id)s "
                  "for Instance %(instance_id)s" %
                  {'backup_id': backup_info['id'], 'instance_id': self.id})
        self._cast("create_backup", backup_info=backup_info)

    def mount_volume(self, device_path=None, mount_point=None):
        """Mount the volume."""
        LOG.debug("Mount volume %(mount)s on instance %(id)s" % {
            'mount': mount_point, 'id': self.id})
        self._call("mount_volume", AGENT_LOW_TIMEOUT,
                   device_path=device_path, mount_point=mount_point)

    def unmount_volume(self, device_path=None, mount_point=None):
        """Unmount the volume."""
        LOG.debug("Unmount volume %(device)s on instance %(id)s" % {
            'device': device_path, 'id': self.id})
        self._call("unmount_volume", AGENT_LOW_TIMEOUT,
                   device_path=device_path, mount_point=mount_point)

    def resize_fs(self, device_path=None, mount_point=None):
        """Resize the filesystem."""
        LOG.debug("Resize device %(device)s on instance %(id)s" % {
            'device': device_path, 'id': self.id})
        self._call("resize_fs", AGENT_HIGH_TIMEOUT, device_path=device_path,
                   mount_point=mount_point)

    def update_overrides(self, overrides, remove=False):
        """Update the overrides."""
        LOG.debug("Updating overrides on Instance %s", self.id)
        LOG.debug("Updating overrides values %s" % overrides)
        self._cast("update_overrides", overrides=overrides, remove=remove)

    def apply_overrides(self, overrides):
        LOG.debug("Applying overrides on Instance %s", self.id)
        LOG.debug("Applying overrides values %s" % overrides)
        self._cast("apply_overrides", overrides=overrides)

    def get_replication_snapshot(self, master_config=None):
        LOG.debug("Retrieving replication snapshot from instance %s", self.id)
        self._call("get_replication_snapshot", AGENT_HIGH_TIMEOUT,
                   master_config=master_config)

    def attach_replication_slave(self, snapshot, slave_config=None):
        LOG.debug("Configuring instance %s to replicate from %s",
                  self.id, snapshot.get('master').get('id'))
        self._cast("attach_replication_slave", snapshot=snapshot,
                   slave_config=slave_config)

    def detach_replication_slave(self):
        LOG.debug("Detaching slave %s from its master", self.id)
        self._call("detach_replication_slave", AGENT_LOW_TIMEOUT)

    def demote_replication_master(self):
        LOG.debug("Demoting instance %s to non-master", self.id)
        self._call("demote_replication_master", AGENT_LOW_TIMEOUT)
