#    Copyright 2012 OpenStack Foundation
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

import traceback

from eventlet import greenthread
from novaclient import exceptions as nova_exceptions
from trove.common import cfg
from trove.common import utils
from trove.common.exception import GuestError
from trove.common.exception import PollTimeOut
from trove.common.exception import VolumeCreationFailure
from trove.common.exception import TroveError
from trove.common.remote import create_dns_client
from trove.common.remote import create_nova_client
from trove.common.remote import create_nova_volume_client
from swiftclient.client import ClientException
from trove.common.utils import poll_until
from trove.instance import models as inst_models
from trove.instance.models import BuiltInstance
from trove.instance.models import FreshInstance
from trove.instance.models import InstanceStatus
from trove.instance.models import InstanceServiceStatus
from trove.instance.models import ServiceStatuses
from trove.instance.views import get_ip_address
from trove.openstack.common import log as logging
from trove.openstack.common.gettextutils import _
from trove.openstack.common.notifier import api as notifier
from trove.openstack.common import timeutils
import trove.common.remote as remote
import trove.backup.models

LOG = logging.getLogger(__name__)
CONF = cfg.CONF
VOLUME_TIME_OUT = CONF.volume_time_out  # seconds.
DNS_TIME_OUT = CONF.dns_time_out  # seconds.
RESIZE_TIME_OUT = CONF.resize_time_out  # seconds.
REVERT_TIME_OUT = CONF.revert_time_out  # seconds.
USAGE_SLEEP_TIME = CONF.usage_sleep_time  # seconds.
USAGE_TIMEOUT = CONF.usage_timeout  # seconds.

use_nova_server_volume = CONF.use_nova_server_volume


class NotifyMixin(object):
    """Notification Mixin

    This adds the ability to send usage events to an Instance object.
    """

    def send_usage_event(self, event_type, **kwargs):
        event_type = 'trove.instance.%s' % event_type
        publisher_id = CONF.host

        # Grab the instance size from the kwargs or from the nova client
        instance_size = kwargs.pop('instance_size', None)
        flavor = self.nova_client.flavors.get(self.flavor_id)
        server = kwargs.pop('server', None)
        if server is None:
            server = self.nova_client.servers.get(self.server_id)
        az = getattr(server, 'OS-EXT-AZ:availability_zone', None)

        # Default payload
        created_time = timeutils.isotime(self.db_info.created)
        payload = {
            'availability_zone': az,
            'created_at': created_time,
            'display_name': self.name,
            'instance_id': self.id,
            'instance_name': self.name,
            'instance_size': instance_size or flavor.ram,
            'instance_type': flavor.name,
            'instance_type_id': flavor.id,
            'launched_at': created_time,
            'nova_instance_id': self.server_id,
            'region': CONF.region,
            'state_description': self.status,
            'state': self.status,
            'tenant_id': self.tenant_id,
            'user_id': self.context.user,
        }

        if CONF.trove_volume_support:
            payload.update({
                'volume_size': self.volume_size,
                'nova_volume_id': self.volume_id
            })

        # Update payload with all other kwargs
        payload.update(kwargs)
        LOG.debug('Sending event: %s, %s' % (event_type, payload))
        notifier.notify(self.context, publisher_id, event_type, 'INFO',
                        payload)


class FreshInstanceTasks(FreshInstance, NotifyMixin):

    def create_instance(self, flavor_id, flavor_ram, image_id,
                        databases, users, service_type, volume_size,
                        security_groups, backup_id):
        if use_nova_server_volume:
            server, volume_info = self._create_server_volume(
                flavor_id,
                image_id,
                security_groups,
                service_type,
                volume_size)
        else:
            server, volume_info = self._create_server_volume_individually(
                flavor_id,
                image_id,
                security_groups,
                service_type,
                volume_size)
        try:
            self._create_dns_entry()
        except Exception as e:
            msg = "Error creating DNS entry for instance: %s" % self.id
            err = inst_models.InstanceTasks.BUILDING_ERROR_DNS
            self._log_and_raise(e, msg, err)

        if server:
            self._guest_prepare(server, flavor_ram, volume_info,
                                databases, users, backup_id)

        if not self.db_info.task_status.is_error:
            self.update_db(task_status=inst_models.InstanceTasks.NONE)

        # Make sure the service becomes active before sending a usage
        # record to avoid over billing a customer for an instance that
        # fails to build properly.
        try:
            utils.poll_until(self._service_is_active,
                             sleep_time=USAGE_SLEEP_TIME,
                             time_out=USAGE_TIMEOUT)
            self.send_usage_event('create', instance_size=flavor_ram)
        except PollTimeOut:
            LOG.error("Timeout for service changing to active. "
                      "No usage create-event sent.")
        except Exception:
            LOG.exception("Error during create-event call.")

    def _service_is_active(self):
        """
        Check that the database guest is active.

        This function is meant to be called with poll_until to check that
        the guest is alive before sending a 'create' message. This prevents
        over billing a customer for a instance that they can never use.

        Returns: boolean if the service is active.
        Raises: TroveError if the service is in a failure state.
        """
        service = InstanceServiceStatus.find_by(instance_id=self.id)
        status = service.get_status()
        if status == ServiceStatuses.RUNNING:
            return True
        elif status not in [ServiceStatuses.NEW,
                            ServiceStatuses.BUILDING]:
            raise TroveError("Service not active, status: %s" % status)

        c_id = self.db_info.compute_instance_id
        nova_status = self.nova_client.servers.get(c_id).status
        if nova_status in [InstanceStatus.ERROR,
                           InstanceStatus.FAILED]:
            raise TroveError("Server not active, status: %s" % nova_status)
        return False

    def _create_server_volume(self, flavor_id, image_id, security_groups,
                              service_type, volume_size):
        server = None
        try:
            nova_client = create_nova_client(self.context)
            files = {"/etc/guest_info": ("[DEFAULT]\n--guest_id="
                                         "%s\n--service_type=%s\n" %
                                         (self.id, service_type))}
            name = self.hostname or self.name
            volume_desc = ("mysql volume for %s" % self.id)
            volume_name = ("mysql-%s" % self.id)
            volume_ref = {'size': volume_size, 'name': volume_name,
                          'description': volume_desc}

            server = nova_client.servers.create(
                name, image_id, flavor_id,
                files=files, volume=volume_ref,
                security_groups=security_groups)
            LOG.debug(_("Created new compute instance %s.") % server.id)

            server_dict = server._info
            LOG.debug("Server response: %s" % server_dict)
            volume_id = None
            for volume in server_dict.get('os:volumes', []):
                volume_id = volume.get('id')

            # Record the server ID and volume ID in case something goes wrong.
            self.update_db(compute_instance_id=server.id, volume_id=volume_id)
        except Exception as e:
            msg = "Error creating server and volume for instance."
            err = inst_models.InstanceTasks.BUILDING_ERROR_SERVER
            self._log_and_raise(e, msg, err)

        device_path = CONF.device_path
        mount_point = CONF.mount_point
        volume_info = {'device_path': device_path, 'mount_point': mount_point}

        return server, volume_info

    def _create_server_volume_individually(self, flavor_id, image_id,
                                           security_groups, service_type,
                                           volume_size):
        server = None
        volume_info = self._build_volume_info(volume_size)
        block_device_mapping = volume_info['block_device']
        try:
            server = self._create_server(flavor_id, image_id, security_groups,
                                         service_type, block_device_mapping)
            server_id = server.id
            # Save server ID.
            self.update_db(compute_instance_id=server_id)
        except Exception as e:
            msg = "Error creating server for instance."
            err = inst_models.InstanceTasks.BUILDING_ERROR_SERVER
            self._log_and_raise(e, msg, err)
        return server, volume_info

    def _build_volume_info(self, volume_size=None):
        volume_info = None
        volume_support = CONF.trove_volume_support
        LOG.debug(_("trove volume support = %s") % volume_support)
        if volume_support:
            try:
                volume_info = self._create_volume(volume_size)
            except Exception as e:
                msg = "Error provisioning volume for instance."
                err = inst_models.InstanceTasks.BUILDING_ERROR_VOLUME
                self._log_and_raise(e, msg, err)
        else:
            LOG.debug(_("device_path = %s") % CONF.device_path)
            LOG.debug(_("mount_point = %s") % CONF.mount_point)
            volume_info = {
                'block_device': None,
                'device_path': CONF.device_path,
                'mount_point': CONF.mount_point,
                'volumes': None,
            }
        return volume_info

    def _log_and_raise(self, exc, message, task_status):
        LOG.error(message)
        LOG.error(exc)
        LOG.error(traceback.format_exc())
        self.update_db(task_status=task_status)
        raise TroveError(message=message)

    def _create_volume(self, volume_size):
        LOG.info("Entering create_volume")
        LOG.debug(_("Starting to create the volume for the instance"))

        volume_client = create_nova_volume_client(self.context)
        volume_desc = ("mysql volume for %s" % self.id)
        volume_ref = volume_client.volumes.create(
            volume_size,
            display_name="mysql-%s" % self.id,
            display_description=volume_desc)

        # Record the volume ID in case something goes wrong.
        self.update_db(volume_id=volume_ref.id)

        utils.poll_until(
            lambda: volume_client.volumes.get(volume_ref.id),
            lambda v_ref: v_ref.status in ['available', 'error'],
            sleep_time=2,
            time_out=VOLUME_TIME_OUT)

        v_ref = volume_client.volumes.get(volume_ref.id)
        if v_ref.status in ['error']:
            raise VolumeCreationFailure()
        LOG.debug(_("Created volume %s") % v_ref)
        # The mapping is in the format:
        # <id>:[<type>]:[<size(GB)>]:[<delete_on_terminate>]
        # setting the delete_on_terminate instance to true=1
        mapping = "%s:%s:%s:%s" % (v_ref.id, '', v_ref.size, 1)
        bdm = CONF.block_device_mapping
        block_device = {bdm: mapping}
        volumes = [{'id': v_ref.id,
                    'size': v_ref.size}]
        LOG.debug("block_device = %s" % block_device)
        LOG.debug("volume = %s" % volumes)

        device_path = CONF.device_path
        mount_point = CONF.mount_point
        LOG.debug(_("device_path = %s") % device_path)
        LOG.debug(_("mount_point = %s") % mount_point)

        volume_info = {'block_device': block_device,
                       'device_path': device_path,
                       'mount_point': mount_point,
                       'volumes': volumes}
        return volume_info

    def _create_server(self, flavor_id, image_id, security_groups,
                       service_type, block_device_mapping):
        nova_client = create_nova_client(self.context)
        files = {"/etc/guest_info": ("[DEFAULT]\nguest_id=%s\n"
                                     "service_type=%s\n" %
                                     (self.id, service_type))}
        name = self.hostname or self.name
        bdmap = block_device_mapping
        server = nova_client.servers.create(name, image_id, flavor_id,
                                            files=files,
                                            security_groups=security_groups,
                                            block_device_mapping=bdmap)
        LOG.debug(_("Created new compute instance %s.") % server.id)
        return server

    def _guest_prepare(self, server, flavor_ram, volume_info,
                       databases, users, backup_id=None):
        LOG.info("Entering guest_prepare.")
        # Now wait for the response from the create to do additional work
        self.guest.prepare(flavor_ram, databases, users,
                           device_path=volume_info['device_path'],
                           mount_point=volume_info['mount_point'],
                           backup_id=backup_id)

    def _create_dns_entry(self):
        LOG.debug("%s: Creating dns entry for instance: %s" %
                  (greenthread.getcurrent(), self.id))
        dns_support = CONF.trove_dns_support
        LOG.debug(_("trove dns support = %s") % dns_support)

        if dns_support:
            nova_client = create_nova_client(self.context)
            dns_client = create_dns_client(self.context)

            def get_server():
                c_id = self.db_info.compute_instance_id
                return nova_client.servers.get(c_id)

            def ip_is_available(server):
                LOG.info("Polling for ip addresses: $%s " % server.addresses)
                if server.addresses != {}:
                    return True
                elif (server.addresses == {} and
                      server.status != InstanceStatus.ERROR):
                    return False
                elif (server.addresses == {} and
                      server.status == InstanceStatus.ERROR):
                    msg = _("Instance IP not available, instance (%s): "
                            "server had status (%s).")
                    LOG.error(msg % (self.id, server.status))
                    raise TroveError(status=server.status)
            poll_until(get_server, ip_is_available,
                       sleep_time=1, time_out=DNS_TIME_OUT)
            server = nova_client.servers.get(self.db_info.compute_instance_id)
            LOG.info("Creating dns entry...")
            dns_client.create_instance_entry(self.id,
                                             get_ip_address(server.addresses))
        else:
            LOG.debug("%s: DNS not enabled for instance: %s" %
                      (greenthread.getcurrent(), self.id))


class BuiltInstanceTasks(BuiltInstance, NotifyMixin):
    """
    Performs the various asynchronous instance related tasks.
    """

    def get_volume_mountpoint(self):
        volume = create_nova_volume_client(self.context).volumes.get(volume_id)
        mountpoint = volume.attachments[0]['device']
        if mountpoint[0] is not "/":
            return "/%s" % mountpoint
        else:
            return mountpoint

    def _delete_resources(self):
        server_id = self.db_info.compute_instance_id
        old_server = self.nova_client.servers.get(server_id)
        try:
            self.server.delete()
        except Exception as ex:
            LOG.error("Error during delete compute server %s "
                      % self.server.id)
            LOG.error(ex)
        try:
            dns_support = CONF.trove_dns_support
            LOG.debug(_("trove dns support = %s") % dns_support)
            if dns_support:
                dns_api = create_dns_client(self.context)
                dns_api.delete_instance_entry(instance_id=self.db_info.id)
        except Exception as ex:
            LOG.error("Error during dns entry for instance %s "
                      % self.db_info.id)
            LOG.error(ex)
        # Poll until the server is gone.

        def server_is_finished():
            try:
                server = self.nova_client.servers.get(server_id)
                if server.status not in ['SHUTDOWN', 'ACTIVE']:
                    msg = "Server %s got into ERROR status during delete " \
                          "of instance %s!" % (server.id, self.id)
                    LOG.error(msg)
                return False
            except nova_exceptions.NotFound:
                return True

        poll_until(server_is_finished, sleep_time=2,
                   time_out=CONF.server_delete_time_out)
        self.send_usage_event('delete', deleted_at=timeutils.isotime(),
                              server=old_server)

    def resize_volume(self, new_size):
        old_volume_size = self.volume_size
        new_size = int(new_size)
        LOG.debug("%s: Resizing volume for instance: %s from %s to %r GB"
                  % (greenthread.getcurrent(), self.server.id,
                     old_volume_size, new_size))
        self.volume_client.volumes.resize(self.volume_id, new_size)
        try:
            utils.poll_until(
                lambda: self.volume_client.volumes.get(self.volume_id),
                lambda volume: volume.status == 'in-use',
                sleep_time=2,
                time_out=CONF.volume_time_out)
            volume = self.volume_client.volumes.get(self.volume_id)
            self.update_db(volume_size=volume.size)
            self.nova_client.volumes.rescan_server_volume(self.server,
                                                          self.volume_id)
            self.send_usage_event('modify_volume',
                                  old_volume_size=old_volume_size,
                                  launched_at=timeutils.isotime(),
                                  modify_at=timeutils.isotime(),
                                  volume_size=new_size)
        except PollTimeOut as pto:
            LOG.error("Timeout trying to rescan or resize the attached volume "
                      "filesystem for volume: %s" % self.volume_id)
        except Exception as e:
            LOG.error(e)
            LOG.error("Error encountered trying to rescan or resize the "
                      "attached volume filesystem for volume: %s"
                      % self.volume_id)
        finally:
            self.update_db(task_status=inst_models.InstanceTasks.NONE)

    def resize_flavor(self, new_flavor_id, old_memory_size,
                      new_memory_size):
        action = ResizeAction(self, new_flavor_id,
                              new_memory_size, old_memory_size)
        action.execute()

    def migrate(self):
        action = MigrateAction(self)
        action.execute()

    def create_backup(self, backup_id):
        LOG.debug("Calling create_backup  %s " % self.id)
        self.guest.create_backup(backup_id)

    def reboot(self):
        try:
            LOG.debug("Instance %s calling stop_db..." % self.id)
            self.guest.stop_db()
            LOG.debug("Rebooting instance %s" % self.id)
            self.server.reboot()

            # Poll nova until instance is active
            reboot_time_out = CONF.reboot_time_out

            def update_server_info():
                self._refresh_compute_server_info()
                return self.server.status == 'ACTIVE'
            utils.poll_until(
                update_server_info,
                sleep_time=2,
                time_out=reboot_time_out)

            # Set the status to PAUSED. The guest agent will reset the status
            # when the reboot completes and MySQL is running.
            self._set_service_status_to_paused()
            LOG.debug("Successfully rebooted instance %s" % self.id)
        except Exception, e:
            LOG.error("Failed to reboot instance %s: %s" % (self.id, str(e)))
        finally:
            LOG.debug("Rebooting FINALLY  %s" % self.id)
            self.update_db(task_status=inst_models.InstanceTasks.NONE)

    def restart(self):
        LOG.debug("Restarting MySQL on instance %s " % self.id)
        try:
            self.guest.restart()
            LOG.debug("Restarting MySQL successful  %s " % self.id)
        except GuestError:
            LOG.error("Failure to restart MySQL for instance %s." % self.id)
        finally:
            LOG.debug("Restarting FINALLY  %s " % self.id)
            self.update_db(task_status=inst_models.InstanceTasks.NONE)

    def _refresh_compute_server_info(self):
        """Refreshes the compute server field."""
        server = self.nova_client.servers.get(self.server.id)
        self.server = server

    def _refresh_compute_service_status(self):
        """Refreshes the service status info for an instance."""
        service = InstanceServiceStatus.find_by(instance_id=self.id)
        self.service_status = service.get_status()

    def _set_service_status_to_paused(self):
        status = InstanceServiceStatus.find_by(instance_id=self.id)
        status.set_status(inst_models.ServiceStatuses.PAUSED)
        status.save()


class BackupTasks(object):

    @classmethod
    def delete_files_from_swift(cls, context, filename):
        client = remote.create_swift_client(context)
        # Delete the manifest
        if client.head_object(CONF.backup_swift_container, filename):
            client.delete_object(CONF.backup_swift_container, filename)

        # Delete the segments
        if client.head_container(filename + "_segments"):

            for obj in client.get_container(filename + "_segments")[1]:
                client.delete_object(filename + "_segments", obj['name'])

            # Delete the segments container
            client.delete_container(filename + "_segments")

    @classmethod
    def delete_backup(cls, context, backup_id):
        #delete backup from swift
        backup = trove.backup.models.Backup.get_by_id(backup_id)
        try:
            filename = backup.filename
            if filename:
                BackupTasks.delete_files_from_swift(context, filename)

        except (ClientException, ValueError) as e:
            LOG.exception("Exception deleting from swift. Details: %s" % e)
            LOG.error("Failed to delete swift objects")
            backup.state = trove.backup.models.BackupState.FAILED

        else:
            backup.delete()


class ResizeActionBase(object):
    """Base class for executing a resize action."""

    def __init__(self, instance):
        self.instance = instance

    def _assert_guest_is_ok(self):
        # The guest will never set the status to PAUSED.
        self.instance._set_service_status_to_paused()
        # Now we wait until it sets it to anything at all,
        # so we know it's alive.
        utils.poll_until(
            self._guest_is_awake,
            sleep_time=2,
            time_out=RESIZE_TIME_OUT)

    def _assert_nova_status_is_ok(self):
        # Make sure Nova thinks things went well.
        if self.instance.server.status != "VERIFY_RESIZE":
            msg = "Migration failed! status=%s and not %s" \
                  % (self.instance.server.status, 'VERIFY_RESIZE')
            raise TroveError(msg)

    def _assert_mysql_is_ok(self):
        # Tell the guest to turn on MySQL, and ensure the status becomes
        # ACTIVE.
        self._start_mysql()
        # The guest should do this for us... but sometimes it walks funny.
        self.instance._refresh_compute_service_status()
        if self.instance.service_status != ServiceStatuses.RUNNING:
            raise Exception("Migration failed! Service status was %s."
                            % self.instance.service_status)

    def _assert_processes_are_ok(self):
        """Checks the procs; if anything is wrong, reverts the operation."""
        # Tell the guest to turn back on, and make sure it can start.
        self._assert_guest_is_ok()
        LOG.debug("Nova guest is fine.")
        self._assert_mysql_is_ok()
        LOG.debug("Mysql is good, too.")

    def _confirm_nova_action(self):
        LOG.debug("Instance %s calling Compute confirm resize..."
                  % self.instance.id)
        self.instance.server.confirm_resize()

    def _revert_nova_action(self):
        LOG.debug("Instance %s calling Compute revert resize..."
                  % self.instance.id)
        self.instance.server.revert_resize()

    def execute(self):
        """Initiates the action."""
        try:
            LOG.debug("Instance %s calling stop_db..."
                      % self.instance.id)
            self.instance.guest.stop_db(do_not_start_on_reboot=True)
            self._perform_nova_action()
        finally:
            self.instance.update_db(task_status=inst_models.InstanceTasks.NONE)

    def _guest_is_awake(self):
        self.instance._refresh_compute_service_status()
        return self.instance.service_status != ServiceStatuses.PAUSED

    def _perform_nova_action(self):
        """Calls Nova to resize or migrate an instance, and confirms."""
        need_to_revert = False
        try:
            LOG.debug("Initiating nova action")
            self._initiate_nova_action()
            LOG.debug("Waiting for nova action")
            self._wait_for_nova_action()
            LOG.debug("Asserting nova status is ok")
            self._assert_nova_status_is_ok()
            need_to_revert = True
            LOG.debug("* * * REVERT BARRIER PASSED * * *")
            LOG.debug("Asserting nova action success")
            self._assert_nova_action_was_successful()
            LOG.debug("Asserting processes are OK")
            self._assert_processes_are_ok()
            LOG.debug("Confirming nova action")
            self._confirm_nova_action()
        except Exception as ex:
            LOG.exception("Exception during nova action.")
            if need_to_revert:
                LOG.error("Reverting action for instance %s" %
                          self.instance.id)
                self._revert_nova_action()
                self._wait_for_revert_nova_action()

            if self.instance.server.status == 'ACTIVE':
                LOG.error("Restarting MySQL.")
                self.instance.guest.restart()
            else:
                LOG.error("Can not restart MySQL because "
                          "Nova server status is not ACTIVE")

            LOG.error("Error resizing instance %s." % self.instance.id)
            raise ex

        LOG.debug("Recording success")
        self._record_action_success()

    def _wait_for_nova_action(self):
        # Wait for the flavor to change.
        def update_server_info():
            self.instance._refresh_compute_server_info()
            return self.instance.server.status != 'RESIZE'
        utils.poll_until(
            update_server_info,
            sleep_time=2,
            time_out=RESIZE_TIME_OUT)

    def _wait_for_revert_nova_action(self):
        # Wait for the server to return to ACTIVE after revert.
        def update_server_info():
            self.instance._refresh_compute_server_info()
            return self.instance.server.status == 'ACTIVE'
        utils.poll_until(
            update_server_info,
            sleep_time=2,
            time_out=REVERT_TIME_OUT)


class ResizeAction(ResizeActionBase):

    def __init__(self, instance, new_flavor_id=None,
                 new_memory_size=None, old_memory_size=None):
        self.instance = instance
        self.old_memory_size = old_memory_size
        self.new_flavor_id = new_flavor_id
        self.new_memory_size = new_memory_size

    def _assert_nova_action_was_successful(self):
        # Do check to make sure the status and flavor id are correct.
        if str(self.instance.server.flavor['id']) != str(self.new_flavor_id):
            msg = "Assertion failed! flavor_id=%s and not %s" \
                  % (self.instance.server.flavor['id'], self.new_flavor_id)
            raise TroveError(msg)

    def _initiate_nova_action(self):
        self.instance.server.resize(self.new_flavor_id)

    def _revert_nova_action(self):
        LOG.debug("Instance %s calling Compute revert resize..."
                  % self.instance.id)
        LOG.debug("Repairing config.")
        try:
            config = {'memory_mb': self.old_memory_size}
            self.instance.guest.reset_configuration(config)
        except GuestTimeout as gt:
            LOG.exception("Error sending reset_configuration call.")
        LOG.debug("Reverting resize.")
        super(ResizeAction, self)._revert_nova_action()

    def _record_action_success(self):
        LOG.debug("Updating instance %s to flavor_id %s."
                  % (self.instance.id, self.new_flavor_id))
        self.instance.update_db(flavor_id=self.new_flavor_id)
        self.instance.send_usage_event('modify_flavor',
                                       old_instance_size=self.old_memory_size,
                                       instance_size=self.new_memory_size,
                                       launched_at=timeutils.isotime(),
                                       modify_at=timeutils.isotime())

    def _start_mysql(self):
        self.instance.guest.start_db_with_conf_changes(self.new_memory_size)


class MigrateAction(ResizeActionBase):

    def _assert_nova_action_was_successful(self):
        LOG.debug("Currently no assertions for a Migrate Action")

    def _initiate_nova_action(self):
        LOG.debug("Migrating instance %s without flavor change ..."
                  % self.instance.id)
        self.instance.server.migrate()

    def _record_action_success(self):
        LOG.debug("Successfully finished Migration to %s: %s" %
                  (self.instance.hostname, self.instance.id))

    def _start_mysql(self):
        self.instance.guest.restart()
