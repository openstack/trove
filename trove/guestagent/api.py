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
from oslo_log import log as logging
import oslo_messaging as messaging
from oslo_messaging.rpc.client import RemoteError

from trove.common import cfg
from trove.common import exception
from trove.common.i18n import _
import trove.common.rpc.version as rpc_version
from trove import rpc

CONF = cfg.CONF
LOG = logging.getLogger(__name__)
AGENT_LOW_TIMEOUT = CONF.agent_call_low_timeout
AGENT_HIGH_TIMEOUT = CONF.agent_call_high_timeout
AGENT_SNAPSHOT_TIMEOUT = CONF.agent_replication_snapshot_timeout


class API(object):
    """API for interacting with the guest manager."""

    def __init__(self, context, id):
        self.context = context
        self.id = id
        super(API, self).__init__()

        target = messaging.Target(topic=self._get_routing_key(),
                                  version=rpc_version.RPC_API_VERSION)

        self.version_cap = rpc_version.VERSION_ALIASES.get(
            CONF.upgrade_levels.guestagent)
        self.client = self.get_client(target, self.version_cap)

    def get_client(self, target, version_cap, serializer=None):
        return rpc.get_client(target,
                              version_cap=version_cap,
                              serializer=serializer)

    def _call(self, method_name, timeout_sec, version, **kwargs):
        LOG.debug("Calling %s with timeout %s" % (method_name, timeout_sec))
        try:
            cctxt = self.client.prepare(version=version, timeout=timeout_sec)
            result = cctxt.call(self.context, method_name, **kwargs)

            LOG.debug("Result is %s." % result)
            return result
        except RemoteError as r:
            LOG.exception(_("Error calling %s") % method_name)
            raise exception.GuestError(original_message=r.value)
        except Exception as e:
            LOG.exception(_("Error calling %s") % method_name)
            raise exception.GuestError(original_message=str(e))
        except Timeout:
            raise exception.GuestTimeout()

    def _cast(self, method_name, version, **kwargs):
        LOG.debug("Casting %s" % method_name)
        try:
            cctxt = self.client.prepare(version=version)
            cctxt.cast(self.context, method_name, **kwargs)
        except RemoteError as r:
            LOG.exception(_("Error calling %s") % method_name)
            raise exception.GuestError(original_message=r.value)
        except Exception as e:
            LOG.exception(_("Error calling %s") % method_name)
            raise exception.GuestError(original_message=str(e))

    def _get_routing_key(self):
        """Create the routing key based on the container id."""
        return "guestagent.%s" % self.id

    def change_passwords(self, users):
        """Make an asynchronous call to change the passwords of one or more
           users.
        """
        LOG.debug("Changing passwords for users on instance %s.", self.id)
        self._cast("change_passwords", self.version_cap, users=users)

    def update_attributes(self, username, hostname, user_attrs):
        """Update user attributes."""
        LOG.debug("Changing user attributes on instance %s.", self.id)
        self._cast("update_attributes", self.version_cap, username=username,
                   hostname=hostname, user_attrs=user_attrs)

    def create_user(self, users):
        """Make an asynchronous call to create a new database user"""
        LOG.debug("Creating Users for instance %s.", self.id)
        self._cast("create_user", self.version_cap, users=users)

    def get_user(self, username, hostname):
        """Make an asynchronous call to get a single database user."""
        LOG.debug("Getting a user %(username)s on instance %(id)s.",
                  {'username': username, 'id': self.id})
        return self._call("get_user", AGENT_LOW_TIMEOUT, self.version_cap,
                          username=username, hostname=hostname)

    def list_access(self, username, hostname):
        """Show all the databases to which a user has more than USAGE."""
        LOG.debug("Showing user %(username)s grants on instance %(id)s.",
                  {'username': username, 'id': self.id})
        return self._call("list_access", AGENT_LOW_TIMEOUT, self.version_cap,
                          username=username, hostname=hostname)

    def grant_access(self, username, hostname, databases):
        """Grant a user permission to use a given database."""
        LOG.debug("Granting access to databases %(databases)s for user "
                  "%(username)s on instance %(id)s.", {'username': username,
                                                       'databases': databases,
                                                       'id': self.id})
        return self._call("grant_access", AGENT_LOW_TIMEOUT, self.version_cap,
                          username=username, hostname=hostname,
                          databases=databases)

    def revoke_access(self, username, hostname, database):
        """Remove a user's permission to use a given database."""
        LOG.debug("Revoking access from database %(database)s for user "
                  "%(username)s on instance %(id)s.", {'username': username,
                                                       'database': database,
                                                       'id': self.id})
        return self._call("revoke_access", AGENT_LOW_TIMEOUT, self.version_cap,
                          username=username, hostname=hostname,
                          database=database)

    def list_users(self, limit=None, marker=None, include_marker=False):
        """Make an asynchronous call to list database users."""
        LOG.debug("Listing Users for instance %s.", self.id)
        return self._call("list_users", AGENT_HIGH_TIMEOUT, self.version_cap,
                          limit=limit, marker=marker,
                          include_marker=include_marker)

    def delete_user(self, user):
        """Make an asynchronous call to delete an existing database user."""
        LOG.debug("Deleting user %(user)s for instance %(instance_id)s." %
                  {'user': user, 'instance_id': self.id})
        self._cast("delete_user", self.version_cap, user=user)

    def create_database(self, databases):
        """Make an asynchronous call to create a new database
           within the specified container
        """
        LOG.debug("Creating databases for instance %s.", self.id)
        self._cast("create_database", self.version_cap, databases=databases)

    def list_databases(self, limit=None, marker=None, include_marker=False):
        """Make an asynchronous call to list databases."""
        LOG.debug("Listing databases for instance %s.", self.id)
        return self._call("list_databases", AGENT_LOW_TIMEOUT,
                          self.version_cap, limit=limit, marker=marker,
                          include_marker=include_marker)

    def delete_database(self, database):
        """Make an asynchronous call to delete an existing database
           within the specified container
        """
        LOG.debug("Deleting database %(database)s for "
                  "instance %(instance_id)s." % {'database': database,
                                                 'instance_id': self.id})
        self._cast("delete_database", self.version_cap, database=database)

    def enable_root(self):
        """Make a synchronous call to enable the root user for
           access from anywhere
        """
        LOG.debug("Enable root user for instance %s.", self.id)
        return self._call("enable_root", AGENT_HIGH_TIMEOUT, self.version_cap)

    def disable_root(self):
        """Make a synchronous call to disable the root user for
           access from anywhere
        """
        LOG.debug("Disable root user for instance %s.", self.id)
        return self._call("disable_root", AGENT_LOW_TIMEOUT, self.version_cap)

    def is_root_enabled(self):
        """Make a synchronous call to check if root access is
           available for the container
        """
        LOG.debug("Check root access for instance %s.", self.id)
        return self._call("is_root_enabled", AGENT_LOW_TIMEOUT,
                          self.version_cap)

    def get_hwinfo(self):
        """Make a synchronous call to get hardware info for the container"""
        LOG.debug("Check hwinfo on instance %s.", self.id)
        return self._call("get_hwinfo", AGENT_LOW_TIMEOUT, self.version_cap)

    def get_diagnostics(self):
        """Make a synchronous call to get diagnostics for the container"""
        LOG.debug("Check diagnostics on instance %s.", self.id)
        return self._call("get_diagnostics", AGENT_LOW_TIMEOUT,
                          self.version_cap)

    def rpc_ping(self):
        """Make a synchronous RPC call to check if we can ping the instance."""
        LOG.debug("Check RPC ping on instance %s.", self.id)
        return self._call("rpc_ping", AGENT_LOW_TIMEOUT, self.version_cap)

    def prepare(self, memory_mb, packages, databases, users,
                device_path='/dev/vdb', mount_point='/mnt/volume',
                backup_info=None, config_contents=None, root_password=None,
                overrides=None, cluster_config=None, snapshot=None):
        """Make an asynchronous call to prepare the guest
           as a database container optionally includes a backup id for restores
        """
        LOG.debug("Sending the call to prepare the Guest.")

        # Taskmanager is a publisher, guestagent is a consumer. Usually
        # consumer creates a queue, but in this case we have to make sure
        # "prepare" doesn't get lost if for some reason guest was delayed and
        # didn't create a queue on time.
        self._create_guest_queue()

        packages = packages.split()
        self._cast(
            "prepare", self.version_cap, packages=packages,
            databases=databases, memory_mb=memory_mb, users=users,
            device_path=device_path, mount_point=mount_point,
            backup_info=backup_info, config_contents=config_contents,
            root_password=root_password, overrides=overrides,
            cluster_config=cluster_config, snapshot=snapshot)

    def _create_guest_queue(self):
        """Call to construct, start and immediately stop rpc server in order
           to create a queue to communicate with the guestagent. This is
           method do nothing in case a queue is already created by
           the guest
        """
        server = None
        target = messaging.Target(topic=self._get_routing_key(),
                                  server=self.id,
                                  version=rpc_version.RPC_API_VERSION)
        try:
            server = rpc.get_server(target, [])
            server.start()
        finally:
            if server is not None:
                server.stop()

    def restart(self):
        """Restart the database server."""
        LOG.debug("Sending the call to restart the database process "
                  "on the Guest.")
        self._call("restart", AGENT_HIGH_TIMEOUT, self.version_cap)

    def start_db_with_conf_changes(self, config_contents):
        """Start the database server."""
        LOG.debug("Sending the call to start the database process on "
                  "the Guest with a timeout of %s." % AGENT_HIGH_TIMEOUT)
        self._call("start_db_with_conf_changes", AGENT_HIGH_TIMEOUT,
                   self.version_cap, config_contents=config_contents)

    def reset_configuration(self, configuration):
        """Ignore running state of the database server; just change
           the config file to a new flavor.
        """
        LOG.debug("Sending the call to change the database conf file on the "
                  "Guest with a timeout of %s." % AGENT_HIGH_TIMEOUT)
        self._call("reset_configuration", AGENT_HIGH_TIMEOUT,
                   self.version_cap, configuration=configuration)

    def stop_db(self, do_not_start_on_reboot=False):
        """Stop the database server."""
        LOG.debug("Sending the call to stop the database process "
                  "on the Guest.")
        self._call("stop_db", AGENT_HIGH_TIMEOUT, self.version_cap,
                   do_not_start_on_reboot=do_not_start_on_reboot)

    def upgrade(self, instance_version, location, metadata=None):
        """Make an asynchronous call to self upgrade the guest agent."""
        LOG.debug("Sending an upgrade call to nova-guest.")
        self._cast("upgrade", self.version_cap,
                   instance_version=instance_version,
                   location=location,
                   metadata=metadata)

    def get_volume_info(self):
        """Make a synchronous call to get volume info for the container."""
        LOG.debug("Check Volume Info on instance %s.", self.id)
        return self._call("get_filesystem_stats", AGENT_LOW_TIMEOUT,
                          self.version_cap, fs_path=None)

    def update_guest(self):
        """Make a synchronous call to update the guest agent."""
        LOG.debug("Updating guest agent on instance %s.", self.id)
        self._call("update_guest", AGENT_HIGH_TIMEOUT, self.version_cap)

    def create_backup(self, backup_info):
        """Make async call to create a full backup of this instance."""
        LOG.debug("Create Backup %(backup_id)s "
                  "for instance %(instance_id)s." %
                  {'backup_id': backup_info['id'], 'instance_id': self.id})
        self._cast("create_backup", self.version_cap, backup_info=backup_info)

    def mount_volume(self, device_path=None, mount_point=None):
        """Mount the volume."""
        LOG.debug("Mount volume %(mount)s on instance %(id)s." % {
            'mount': mount_point, 'id': self.id})
        self._call("mount_volume", AGENT_LOW_TIMEOUT, self.version_cap,
                   device_path=device_path, mount_point=mount_point)

    def unmount_volume(self, device_path=None, mount_point=None):
        """Unmount the volume."""
        LOG.debug("Unmount volume %(device)s on instance %(id)s." % {
            'device': device_path, 'id': self.id})
        self._call("unmount_volume", AGENT_LOW_TIMEOUT, self.version_cap,
                   device_path=device_path, mount_point=mount_point)

    def resize_fs(self, device_path=None, mount_point=None):
        """Resize the filesystem."""
        LOG.debug("Resize device %(device)s on instance %(id)s." % {
            'device': device_path, 'id': self.id})
        self._call("resize_fs", AGENT_HIGH_TIMEOUT, self.version_cap,
                   device_path=device_path, mount_point=mount_point)

    def update_overrides(self, overrides, remove=False):
        """Update the overrides."""
        LOG.debug("Updating overrides values %(overrides)s on instance "
                  "%(id)s.", {'overrides': overrides, 'id': self.id})
        self._cast("update_overrides", self.version_cap, overrides=overrides,
                   remove=remove)

    def apply_overrides(self, overrides):
        LOG.debug("Applying overrides values %(overrides)s on instance "
                  "%(id)s.", {'overrides': overrides, 'id': self.id})
        self._cast("apply_overrides", self.version_cap, overrides=overrides)

    def get_replication_snapshot(self, snapshot_info=None,
                                 replica_source_config=None):
        LOG.debug("Retrieving replication snapshot from instance %s.", self.id)
        return self._call("get_replication_snapshot", AGENT_SNAPSHOT_TIMEOUT,
                          self.version_cap, snapshot_info=snapshot_info,
                          replica_source_config=replica_source_config)

    def attach_replication_slave(self, snapshot, replica_config=None):
        LOG.debug("Configuring instance %s to replicate from %s.",
                  self.id, snapshot.get('master').get('id'))
        self._cast("attach_replication_slave", self.version_cap,
                   snapshot=snapshot, slave_config=replica_config)

    def detach_replica(self, for_failover=False):
        LOG.debug("Detaching replica %s from its replication source.", self.id)
        return self._call("detach_replica", AGENT_HIGH_TIMEOUT,
                          self.version_cap, for_failover=for_failover)

    def get_replica_context(self):
        LOG.debug("Getting replica context.")
        return self._call("get_replica_context",
                          AGENT_HIGH_TIMEOUT, self.version_cap)

    def attach_replica(self, replica_info, slave_config):
        LOG.debug("Attaching replica %s." % replica_info)
        self._call("attach_replica", AGENT_HIGH_TIMEOUT, self.version_cap,
                   replica_info=replica_info, slave_config=slave_config)

    def make_read_only(self, read_only):
        LOG.debug("Executing make_read_only(%s)" % read_only)
        self._call("make_read_only", AGENT_HIGH_TIMEOUT, self.version_cap,
                   read_only=read_only)

    def enable_as_master(self, replica_source_config):
        LOG.debug("Executing enable_as_master")
        self._call("enable_as_master", AGENT_HIGH_TIMEOUT, self.version_cap,
                   replica_source_config=replica_source_config)

    # DEPRECATED: Maintain for API Compatibility
    def get_txn_count(self):
        LOG.debug("Executing get_txn_count.")
        return self._call("get_txn_count",
                          AGENT_HIGH_TIMEOUT, self.version_cap)

    def get_last_txn(self):
        LOG.debug("Executing get_last_txn.")
        return self._call("get_last_txn",
                          AGENT_HIGH_TIMEOUT, self.version_cap)

    def get_latest_txn_id(self):
        LOG.debug("Executing get_latest_txn_id.")
        return self._call("get_latest_txn_id",
                          AGENT_HIGH_TIMEOUT, self.version_cap)

    def wait_for_txn(self, txn):
        LOG.debug("Executing wait_for_txn.")
        self._call("wait_for_txn", AGENT_HIGH_TIMEOUT, self.version_cap,
                   txn=txn)

    def cleanup_source_on_replica_detach(self, replica_info):
        LOG.debug("Cleaning up master %s on detach of replica.", self.id)
        self._call("cleanup_source_on_replica_detach", AGENT_HIGH_TIMEOUT,
                   self.version_cap, replica_info=replica_info)

    def demote_replication_master(self):
        LOG.debug("Demoting instance %s to non-master.", self.id)
        self._call("demote_replication_master", AGENT_HIGH_TIMEOUT,
                   self.version_cap)
