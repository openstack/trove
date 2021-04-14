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
from trove.common.notification import NotificationCastWrapper
from trove import rpc

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class API(object):
    """API for interacting with the guest manager.

    API version history:
        * 1.0 - Initial version.
        * 1.1 - Added argement ds_version to prepare and
                start_db_with_conf_changes
              - Remove do_not_start_on_reboot from stop_db
              - Added online argument to resize_fs

    When updating this API, also update API_LATEST_VERSION
    """

    # API_LATEST_VERSION should bump the minor number each time
    # a method signature is added or changed
    API_LATEST_VERSION = '1.1'

    # API_BASE_VERSION should only change on major version upgrade
    API_BASE_VERSION = '1.0'

    VERSION_ALIASES = {
        'icehouse': '1.0',
        'juno': '1.0',
        'kilo': '1.0',
        'liberty': '1.0',
        'mitaka': '1.0',
        'newton': '1.0',
        'ussuri': '1.0',
        'victoria': '1.1',
        'wallaby': '1.1',
        'latest': API_LATEST_VERSION
    }

    def __init__(self, context, id):
        self.context = context
        self.id = id
        super(API, self).__init__()

        self.agent_low_timeout = CONF.agent_call_low_timeout
        self.agent_high_timeout = CONF.agent_call_high_timeout
        self.agent_snapshot_timeout = CONF.agent_replication_snapshot_timeout

        version_cap = self.VERSION_ALIASES.get(
            CONF.upgrade_levels.guestagent, CONF.upgrade_levels.guestagent)
        self.target = messaging.Target(topic=self._get_routing_key(),
                                       version=version_cap)

        self.client = self.get_client(self.target, version_cap)

    def get_client(self, target, version_cap, serializer=None):
        from trove.instance.models import get_instance_encryption_key

        instance_key = get_instance_encryption_key(self.id)
        return rpc.get_client(target, key=instance_key,
                              version_cap=version_cap,
                              serializer=serializer)

    def _call(self, method_name, timeout_sec, version, **kwargs):
        LOG.debug("Calling %(name)s with timeout %(timeout)s",
                  {'name': method_name, 'timeout': timeout_sec})
        try:
            cctxt = self.client.prepare(version=version, timeout=timeout_sec)
            result = cctxt.call(self.context, method_name, **kwargs)

            LOG.debug("Result is %s.", result)
            return result
        except RemoteError as r:
            LOG.exception("Error calling %s", method_name)
            raise exception.GuestError(original_message=r.value)
        except Exception as e:
            LOG.exception("Error calling %s", method_name)
            raise exception.GuestError(original_message=str(e))
        except Timeout:
            raise exception.GuestTimeout()

    def _cast(self, method_name, version, **kwargs):
        LOG.debug("Calling %s asynchronously", method_name)
        try:
            with NotificationCastWrapper(self.context, 'guest'):
                cctxt = self.client.prepare(version=version)
                cctxt.cast(self.context, method_name, **kwargs)
        except RemoteError as r:
            LOG.exception("Error calling %s", method_name)
            raise exception.GuestError(original_message=r.value)
        except Exception as e:
            LOG.exception("Error calling %s", method_name)
            raise exception.GuestError(original_message=str(e))

    def _get_routing_key(self):
        """Create the routing key based on the container id."""
        return "guestagent.%s" % self.id

    def change_passwords(self, users):
        """Make an asynchronous call to change the passwords of one or more
           users.
        """
        LOG.debug("Changing passwords for users on instance %s.", self.id)
        version = self.API_BASE_VERSION

        self._cast("change_passwords", version=version, users=users)

    def update_attributes(self, username, hostname, user_attrs):
        """Update user attributes."""
        LOG.debug("Changing user attributes on instance %s.", self.id)
        version = self.API_BASE_VERSION

        self._cast("update_attributes",
                   version=version, username=username,
                   hostname=hostname, user_attrs=user_attrs)

    def create_user(self, users):
        """Make an asynchronous call to create a new database user"""
        LOG.debug("Creating Users for instance %s.", self.id)
        version = self.API_BASE_VERSION

        self._cast("create_user", version=version, users=users)

    def get_user(self, username, hostname):
        """Make a synchronous call to get a single database user."""
        LOG.debug("Getting a user %(username)s on instance %(id)s.",
                  {'username': username, 'id': self.id})
        version = self.API_BASE_VERSION

        return self._call("get_user",
                          self.agent_low_timeout, version=version,
                          username=username, hostname=hostname)

    def list_access(self, username, hostname):
        """Show all the databases to which a user has more than USAGE."""
        LOG.debug("Showing user %(username)s grants on instance %(id)s.",
                  {'username': username, 'id': self.id})
        version = self.API_BASE_VERSION

        return self._call("list_access",
                          self.agent_low_timeout, version=version,
                          username=username, hostname=hostname)

    def grant_access(self, username, hostname, databases):
        """Grant a user permission to use a given database."""
        LOG.debug("Granting access to databases %(databases)s for user "
                  "%(username)s on instance %(id)s.", {'username': username,
                                                       'databases': databases,
                                                       'id': self.id})
        version = self.API_BASE_VERSION

        return self._call("grant_access",
                          self.agent_low_timeout, version=version,
                          username=username, hostname=hostname,
                          databases=databases)

    def revoke_access(self, username, hostname, database):
        """Remove a user's permission to use a given database."""
        LOG.debug("Revoking access from database %(database)s for user "
                  "%(username)s on instance %(id)s.", {'username': username,
                                                       'database': database,
                                                       'id': self.id})
        version = self.API_BASE_VERSION

        return self._call("revoke_access",
                          self.agent_low_timeout, version=version,
                          username=username, hostname=hostname,
                          database=database)

    def list_users(self, limit=None, marker=None, include_marker=False):
        """Make a synchronous call to list database users."""
        LOG.debug("Listing Users for instance %s.", self.id)
        version = self.API_BASE_VERSION

        return self._call("list_users",
                          self.agent_high_timeout, version=version,
                          limit=limit, marker=marker,
                          include_marker=include_marker)

    def delete_user(self, user):
        """Make an asynchronous call to delete an existing database user."""
        LOG.debug("Deleting user %(user)s for instance %(instance_id)s.",
                  {'user': user, 'instance_id': self.id})
        version = self.API_BASE_VERSION

        self._cast("delete_user", version=version, user=user)

    def create_database(self, databases):
        """Make an asynchronous call to create a new database
           within the specified container
        """
        LOG.debug("Creating databases for instance %s.", self.id)
        version = self.API_BASE_VERSION

        self._cast("create_database", version=version,
                   databases=databases)

    def list_databases(self, limit=None, marker=None, include_marker=False):
        """Make a synchronous call to list databases."""
        LOG.debug("Listing databases for instance %s.", self.id)
        version = self.API_BASE_VERSION

        return self._call("list_databases", self.agent_low_timeout,
                          version=version, limit=limit, marker=marker,
                          include_marker=include_marker)

    def delete_database(self, database):
        """Make an asynchronous call to delete an existing database
           within the specified container
        """
        LOG.debug("Deleting database %(database)s for "
                  "instance %(instance_id)s.", {'database': database,
                                                'instance_id': self.id})
        version = self.API_BASE_VERSION

        self._cast("delete_database", version=version, database=database)

    def get_root_password(self):
        """Make a synchronous call to get root password of instance.
        """
        LOG.debug("Get root password of instance %s.", self.id)
        version = self.API_BASE_VERSION

        return self._call("get_root_password", self.agent_high_timeout,
                          version=version)

    def enable_root(self):
        """Make a synchronous call to enable the root user for
           access from anywhere
        """
        LOG.debug("Enable root user for instance %s.", self.id)
        version = self.API_BASE_VERSION

        return self._call("enable_root", self.agent_high_timeout,
                          version=version)

    def enable_root_with_password(self, root_password=None):
        """Make a synchronous call to enable the root user for
           access from anywhere
        """
        LOG.debug("Enable root user for instance %s.", self.id)
        version = self.API_BASE_VERSION

        return self._call("enable_root_with_password",
                          self.agent_high_timeout,
                          version=version, root_password=root_password)

    def disable_root(self):
        """Make a synchronous call to disable the root user for
           access from anywhere
        """
        LOG.debug("Disable root user for instance %s.", self.id)
        version = self.API_BASE_VERSION

        return self._call("disable_root", self.agent_low_timeout,
                          version=version)

    def is_root_enabled(self):
        """Make a synchronous call to check if root access is
           available for the container
        """
        LOG.debug("Check root access for instance %s.", self.id)
        version = self.API_BASE_VERSION

        return self._call("is_root_enabled", self.agent_low_timeout,
                          version=version)

    def get_hwinfo(self):
        """Make a synchronous call to get hardware info for the container"""
        LOG.debug("Check hwinfo on instance %s.", self.id)
        version = self.API_BASE_VERSION

        return self._call("get_hwinfo", self.agent_low_timeout,
                          version=version)

    def get_diagnostics(self):
        """Make a synchronous call to get diagnostics for the container"""
        LOG.debug("Check diagnostics on instance %s.", self.id)
        version = self.API_BASE_VERSION

        return self._call("get_diagnostics",
                          self.agent_low_timeout, version=version)

    def rpc_ping(self):
        """Make a synchronous RPC call to check if we can ping the instance."""
        LOG.debug("Check RPC ping on instance %s.", self.id)
        version = self.API_BASE_VERSION

        return self._call("rpc_ping",
                          self.agent_low_timeout, version=version)

    def prepare(self, memory_mb, packages, databases, users,
                device_path='/dev/vdb', mount_point='/mnt/volume',
                backup_info=None, config_contents=None, root_password=None,
                overrides=None, cluster_config=None, snapshot=None,
                modules=None, ds_version=None):
        """Make an asynchronous call to prepare the guest
           as a database container optionally includes a backup id for restores
        """
        LOG.debug("Sending the call to prepare the Guest.")

        version = '1.1'

        # Taskmanager is a publisher, guestagent is a consumer. Usually
        # consumer creates a queue, but in this case we have to make sure
        # "prepare" doesn't get lost if for some reason guest was delayed and
        # didn't create a queue on time.
        self._create_guest_queue()

        packages = packages.split()

        prepare_args = dict(
            packages=packages, databases=databases, memory_mb=memory_mb,
            users=users, device_path=device_path, mount_point=mount_point,
            backup_info=backup_info, config_contents=config_contents,
            root_password=root_password, overrides=overrides,
            cluster_config=cluster_config, snapshot=snapshot, modules=modules,
            ds_version=ds_version)

        if not self.client.can_send_version(version):
            prepare_args.pop('ds_version')
            version = '1.0'
        self._cast("prepare", version=version, **prepare_args)

    def _create_guest_queue(self):
        """Call to construct, start and immediately stop rpc server in order
           to create a queue to communicate with the guestagent. This is
           method do nothing in case a queue is already created by
           the guest
        """
        from trove.instance.models import DBInstance
        server = None
        target = messaging.Target(topic=self._get_routing_key(),
                                  server=self.id,
                                  version=self.API_BASE_VERSION)
        try:
            instance = DBInstance.get_by(id=self.id)
            instance_key = instance.key if instance else None
            server = rpc.get_server(target, [], key=instance_key)
            server.start()
        finally:
            if server is not None:
                server.stop()
                server.wait()

    def pre_upgrade(self):
        """Prepare the guest for upgrade."""
        LOG.debug("Sending the call to prepare the guest for upgrade.")
        version = self.API_BASE_VERSION

        return self._call("pre_upgrade",
                          self.agent_high_timeout, version=version)

    def post_upgrade(self, upgrade_info):
        """Recover the guest after upgrading the guest's image."""
        LOG.debug("Recover the guest after upgrading the guest's image.")
        version = self.API_BASE_VERSION
        LOG.debug("Recycling the client ...")
        version_cap = self.VERSION_ALIASES.get(
            CONF.upgrade_levels.guestagent, CONF.upgrade_levels.guestagent)
        self.client = self.get_client(self.target, version_cap)

        self._call("post_upgrade",
                   self.agent_high_timeout, version=version,
                   upgrade_info=upgrade_info)

    def upgrade(self, upgrade_info):
        """Upgrade database service."""
        LOG.debug("Sending the call to upgrade database service.")
        version = self.API_BASE_VERSION

        return self._cast("upgrade", version=version,
                          upgrade_info=upgrade_info)

    def restart(self):
        """Restart the database server."""
        LOG.debug("Sending the call to restart the database process "
                  "on the Guest.")
        version = self.API_BASE_VERSION

        self._call("restart", self.agent_high_timeout, version=version)

    def start_db_with_conf_changes(self, config_contents, ds_version):
        """Start the database server."""
        LOG.debug("Sending the call to start the database process on "
                  "the Guest with a timeout of %s.",
                  self.agent_high_timeout)
        start_args = dict(config_contents=config_contents,
                          ds_version=ds_version)

        version = '1.1'
        if not self.client.can_send_version(version):
            start_args.pop('ds_version')
            version = '1.0'

        self._call("start_db_with_conf_changes", self.agent_high_timeout,
                   version=version, **start_args)

    def reset_configuration(self, configuration):
        """Ignore running state of the database server; just change
           the config file to a new flavor.
        """
        LOG.debug("Sending the call to change the database conf file on the "
                  "Guest with a timeout of %s.",
                  self.agent_high_timeout)
        version = self.API_BASE_VERSION

        self._call("reset_configuration", self.agent_high_timeout,
                   version=version, configuration=configuration)

    def stop_db(self, do_not_start_on_reboot=False):
        """Stop the database server."""
        LOG.debug("Sending the call to stop the database process "
                  "on the Guest.")

        version = '1.1'
        stop_args = {}
        if not self.client.can_send_version(version):
            stop_args['do_not_start_on_reboot'] = do_not_start_on_reboot
            version = '1.0'

        self._call("stop_db", self.agent_low_timeout,
                   version=version, **stop_args)

    def get_volume_info(self):
        """Make a synchronous call to get volume info for the container."""
        LOG.debug("Check Volume Info on instance %s.", self.id)
        version = self.API_BASE_VERSION

        return self._call("get_filesystem_stats", self.agent_low_timeout,
                          version=version, fs_path=None)

    def update_guest(self):
        """Make a synchronous call to update the guest agent."""
        LOG.debug("Updating guest agent on instance %s.", self.id)
        version = self.API_BASE_VERSION

        self._call("update_guest",
                   self.agent_high_timeout, version=version)

    def create_backup(self, backup_info):
        """Make async call to create a full backup of this instance."""
        LOG.debug("Create Backup %(backup_id)s "
                  "for instance %(instance_id)s.",
                  {'backup_id': backup_info['id'], 'instance_id': self.id})
        version = self.API_BASE_VERSION

        self._cast("create_backup", version=version,
                   backup_info=backup_info)

    def mount_volume(self, device_path=None, mount_point=None):
        """Mount the volume."""
        LOG.debug("Mount volume %(mount)s on instance %(id)s.", {
            'mount': mount_point, 'id': self.id})
        version = self.API_BASE_VERSION

        self._call("mount_volume",
                   self.agent_low_timeout, version=version,
                   device_path=device_path, mount_point=mount_point)

    def unmount_volume(self, device_path=None, mount_point=None):
        """Unmount the volume."""
        LOG.debug("Unmount volume %(device)s on instance %(id)s.", {
            'device': device_path, 'id': self.id})
        version = self.API_BASE_VERSION

        self._call("unmount_volume",
                   self.agent_low_timeout, version=version,
                   device_path=device_path, mount_point=mount_point)

    def resize_fs(self, device_path=None, mount_point=None, online=False):
        """Resize the filesystem."""
        LOG.debug("Resize device %(device)s on instance %(id)s.", {
            'device': device_path, 'id': self.id})

        resize_args = dict(device_path=device_path,
                           mount_point=mount_point,
                           online=online)

        version = '1.1'
        if not self.client.can_send_version(version):
            resize_args.pop('online')
            version = '1.0'

        self._call("resize_fs",
                   self.agent_high_timeout, version=version, **resize_args)

    def update_overrides(self, overrides, remove=False):
        """Update the overrides."""
        LOG.debug("Updating overrides values %(overrides)s on instance "
                  "%(id)s.", {'overrides': overrides, 'id': self.id})
        version = self.API_BASE_VERSION

        self._call("update_overrides", self.agent_high_timeout,
                   version=version, overrides=overrides, remove=remove)

    def apply_overrides(self, overrides):
        LOG.debug("Applying overrides values %(overrides)s on instance "
                  "%(id)s.", {'overrides': overrides, 'id': self.id})
        version = self.API_BASE_VERSION

        self._call("apply_overrides", self.agent_high_timeout,
                   version=version, overrides=overrides)

    def backup_required_for_replication(self):
        LOG.debug("Checking backup requirement for replication")
        version = self.API_BASE_VERSION

        return self._call("backup_required_for_replication",
                          self.agent_low_timeout,
                          version=version)

    def get_replication_snapshot(self, snapshot_info=None,
                                 replica_source_config=None):
        LOG.debug("Retrieving replication snapshot from instance %s.", self.id)
        version = self.API_BASE_VERSION

        return self._call("get_replication_snapshot",
                          self.agent_snapshot_timeout,
                          version=version, snapshot_info=snapshot_info,
                          replica_source_config=replica_source_config)

    def attach_replication_slave(self, snapshot, replica_config=None):
        LOG.debug("Configuring instance %s to replicate from %s.",
                  self.id, snapshot.get('master').get('id'))
        version = self.API_BASE_VERSION

        self._cast("attach_replication_slave", version=version,
                   snapshot=snapshot, slave_config=replica_config)

    def detach_replica(self, for_failover=False):
        LOG.debug("Detaching replica %s from its replication source.", self.id)
        version = self.API_BASE_VERSION

        return self._call("detach_replica", self.agent_high_timeout,
                          version=version, for_failover=for_failover)

    def get_replica_context(self):
        LOG.debug("Getting replica context.")
        version = self.API_BASE_VERSION

        return self._call("get_replica_context",
                          self.agent_high_timeout, version=version)

    def attach_replica(self, replica_info, slave_config, restart=False):
        LOG.debug("Attaching replica %s.", replica_info)
        version = self.API_BASE_VERSION

        self._call("attach_replica",
                   self.agent_high_timeout, version=version,
                   replica_info=replica_info, slave_config=slave_config,
                   restart=restart)

    def make_read_only(self, read_only):
        LOG.debug("Executing make_read_only(%s)", read_only)
        version = self.API_BASE_VERSION

        self._call("make_read_only",
                   self.agent_high_timeout, version=version,
                   read_only=read_only)

    def enable_as_master(self, replica_source_config):
        LOG.debug("Executing enable_as_master")
        version = self.API_BASE_VERSION

        self._call("enable_as_master", self.agent_high_timeout,
                   version=version,
                   replica_source_config=replica_source_config)

    # DEPRECATED: Maintain for API Compatibility
    def get_txn_count(self):
        LOG.debug("Executing get_txn_count.")
        version = self.API_BASE_VERSION

        return self._call("get_txn_count",
                          self.agent_high_timeout, version=version)

    def get_last_txn(self):
        LOG.debug("Executing get_last_txn.")
        version = self.API_BASE_VERSION

        return self._call("get_last_txn",
                          self.agent_high_timeout, version=version)

    def get_latest_txn_id(self):
        LOG.debug("Executing get_latest_txn_id.")
        version = self.API_BASE_VERSION

        return self._call("get_latest_txn_id",
                          self.agent_high_timeout, version=version)

    def wait_for_txn(self, txn):
        LOG.debug("Executing wait_for_txn.")
        version = self.API_BASE_VERSION

        self._call("wait_for_txn",
                   self.agent_high_timeout, version=version, txn=txn)

    def cleanup_source_on_replica_detach(self, replica_info):
        LOG.debug("Cleaning up master %s on detach of replica.", self.id)
        version = self.API_BASE_VERSION

        self._call("cleanup_source_on_replica_detach",
                   self.agent_high_timeout,
                   version=version, replica_info=replica_info)

    def demote_replication_master(self):
        LOG.debug("Demoting instance %s to non-master.", self.id)
        version = self.API_BASE_VERSION

        self._call("demote_replication_master", self.agent_high_timeout,
                   version=version)

    def guest_log_list(self):
        LOG.debug("Retrieving guest log list for %s.", self.id)
        version = self.API_BASE_VERSION

        result = self._call("guest_log_list", self.agent_high_timeout,
                            version=version)
        LOG.debug("guest_log_list returns %s", result)
        return result

    def guest_log_action(self, log_name, enable, disable, publish, discard):
        LOG.debug("Processing guest log '%s' for %s.", log_name, self.id)
        version = self.API_BASE_VERSION

        return self._call("guest_log_action", self.agent_high_timeout,
                          version=version, log_name=log_name,
                          enable=enable, disable=disable,
                          publish=publish, discard=discard)

    def module_list(self, include_contents):
        LOG.debug("Querying modules on %s (contents: %s).",
                  self.id, include_contents)
        version = self.API_BASE_VERSION

        result = self._call("module_list", self.agent_high_timeout,
                            version=version,
                            include_contents=include_contents)
        return result

    def module_apply(self, modules):
        LOG.debug("Applying modules to %s.", self.id)
        version = self.API_BASE_VERSION

        return self._call("module_apply", self.agent_high_timeout,
                          version=version, modules=modules)

    def module_remove(self, module):
        LOG.debug("Removing modules from %s.", self.id)
        version = self.API_BASE_VERSION

        return self._call("module_remove", self.agent_high_timeout,
                          version=version, module=module)

    def rebuild(self, ds_version, config_contents=None, config_overrides=None):
        """Make an asynchronous call to rebuild the database service."""
        LOG.debug("Sending the call to rebuild database service in the guest.")
        version = self.API_BASE_VERSION

        # Taskmanager is a publisher, guestagent is a consumer. Usually
        # consumer creates a queue, but in this case we have to make sure
        # "prepare" doesn't get lost if for some reason guest was delayed and
        # didn't create a queue on time.
        self._create_guest_queue()

        self._cast("rebuild", version=version,
                   ds_version=ds_version, config_contents=config_contents,
                   config_overrides=config_overrides)
