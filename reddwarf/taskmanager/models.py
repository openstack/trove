#    Copyright 2012 OpenStack LLC
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

import time
from eventlet import greenthread
from datetime import datetime
import traceback
from novaclient import exceptions as nova_exceptions
from reddwarf.common import cfg
from reddwarf.common import remote
from reddwarf.common import utils
from reddwarf.common.exception import GuestError
from reddwarf.common.exception import PollTimeOut
from reddwarf.common.exception import VolumeCreationFailure
from reddwarf.common.exception import NotFound
from reddwarf.common.exception import ReddwarfError
from reddwarf.common.remote import create_dns_client
from reddwarf.common.remote import create_nova_client
from reddwarf.common.remote import create_nova_volume_client
from reddwarf.common.remote import create_guest_client
from reddwarf.common.utils import poll_until
from reddwarf.extensions.mysql.common import populate_databases
from reddwarf.extensions.mysql.common import populate_users
from reddwarf.instance import models as inst_models
from reddwarf.instance.models import DBInstance
from reddwarf.instance.models import BuiltInstance
from reddwarf.instance.models import FreshInstance
from reddwarf.instance.models import InstanceStatus
from reddwarf.instance.models import InstanceServiceStatus
from reddwarf.instance.models import ServiceStatuses
from reddwarf.instance.tasks import InstanceTasks
from reddwarf.instance.views import get_ip_address
from reddwarf.openstack.common import log as logging
from reddwarf.openstack.common.gettextutils import _


LOG = logging.getLogger(__name__)
CONF = cfg.CONF
VOLUME_TIME_OUT = CONF.volume_time_out  # seconds.
DNS_TIME_OUT = CONF.dns_time_out  # seconds.
RESIZE_TIME_OUT = CONF.resize_time_out  # seconds.
REVERT_TIME_OUT = CONF.revert_time_out  # seconds.

use_nova_server_volume = CONF.use_nova_server_volume


class FreshInstanceTasks(FreshInstance):

    def create_instance(self, flavor_id, flavor_ram, image_id,
                        databases, users, service_type, volume_size):
        if use_nova_server_volume:
            server, volume_info = self._create_server_volume(
                flavor_id,
                image_id,
                service_type,
                volume_size)
        else:
            server, volume_info = self._create_server_volume_individually(
                flavor_id,
                image_id,
                service_type,
                volume_size)
        try:
            self._create_dns_entry()
        except Exception as e:
            msg = "Error creating DNS entry for instance."
            err = inst_models.InstanceTasks.BUILDING_ERROR_DNS
            self._log_and_raise(e, msg, err)

        if server:
            self._guest_prepare(server, flavor_ram, volume_info,
                                databases, users)

        if not self.db_info.task_status.is_error:
            self.update_db(task_status=inst_models.InstanceTasks.NONE)

    def _create_server_volume(self, flavor_id, image_id, service_type,
                              volume_size):
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

            server = nova_client.servers.create(name, image_id, flavor_id,
                                                files=files, volume=volume_ref)
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
                                           service_type, volume_size):
        volume_info = None
        block_device_mapping = None
        server = None
        try:
            volume_info = self._create_volume(volume_size)
            block_device_mapping = volume_info['block_device']
        except Exception as e:
            msg = "Error provisioning volume for instance."
            err = inst_models.InstanceTasks.BUILDING_ERROR_VOLUME
            self._log_and_raise(e, msg, err)

        try:
            server = self._create_server(flavor_id, image_id, service_type,
                                         block_device_mapping)
            server_id = server.id
            # Save server ID.
            self.update_db(compute_instance_id=server_id)
        except Exception as e:
            msg = "Error creating server for instance."
            err = inst_models.InstanceTasks.BUILDING_ERROR_SERVER
            self._log_and_raise(e, msg, err)
        return server, volume_info

    def _log_and_raise(self, exc, message, task_status):
        LOG.error(message)
        LOG.error(exc)
        LOG.error(traceback.format_exc())
        self.update_db(task_status=task_status)
        raise ReddwarfError(message=message)

    def _create_volume(self, volume_size):
        LOG.info("Entering create_volume")
        LOG.debug(_("Starting to create the volume for the instance"))

        volume_support = CONF.reddwarf_volume_support
        LOG.debug(_("reddwarf volume support = %s") % volume_support)
        if (volume_size is None or
                volume_support is False):
            volume_info = {
                'block_device': None,
                'device_path': None,
                'mount_point': None,
                'volumes': None,
            }
            return volume_info

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

    def _create_server(self, flavor_id, image_id,
                       service_type, block_device_mapping):
        nova_client = create_nova_client(self.context)
        files = {"/etc/guest_info": ("[DEFAULT]\nguest_id=%s\n"
                                     "service_type=%s\n" %
                                     (self.id, service_type))}
        name = self.hostname or self.name
        bdmap = block_device_mapping
        server = nova_client.servers.create(name, image_id, flavor_id,
                                            files=files,
                                            block_device_mapping=bdmap)
        LOG.debug(_("Created new compute instance %s.") % server.id)
        return server

    def _guest_prepare(self, server, flavor_ram, volume_info,
                       databases, users):
        LOG.info("Entering guest_prepare.")
        # Now wait for the response from the create to do additional work
        self.guest.prepare(flavor_ram, databases, users,
                           device_path=volume_info['device_path'],
                           mount_point=volume_info['mount_point'])

    def _create_dns_entry(self):
        LOG.debug("%s: Creating dns entry for instance: %s" %
                  (greenthread.getcurrent(), self.id))
        dns_support = CONF.reddwarf_dns_support
        LOG.debug(_("reddwarf dns support = %s") % dns_support)

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
                    raise ReddwarfError(status=server.status)
            poll_until(get_server, ip_is_available,
                       sleep_time=1, time_out=DNS_TIME_OUT)
            server = nova_client.servers.get(self.db_info.compute_instance_id)
            LOG.info("Creating dns entry...")
            dns_client.create_instance_entry(self.id,
                                             get_ip_address(server.addresses))
        else:
            LOG.debug("%s: DNS not enabled for instance: %s" %
                      (greenthread.getcurrent(), self.id))


class BuiltInstanceTasks(BuiltInstance):
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
        try:
            self.server.delete()
        except Exception as ex:
            LOG.error("Error during delete compute server %s "
                      % self.server.id)
            LOG.error(ex)
        try:
            dns_support = CONF.reddwarf_dns_support
            LOG.debug(_("reddwarf dns support = %s") % dns_support)
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
                server_id = self.db_info.compute_instance_id
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

    def resize_volume(self, new_size):
        LOG.debug("%s: Resizing volume for instance: %s to %r GB"
                  % (greenthread.getcurrent(), self.server.id, new_size))
        self.volume_client.volumes.resize(self.volume_id, int(new_size))
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
        action = ResizeAction(self, new_flavor_id, new_memory_size)
        action.execute()

    def migrate(self):
        action = MigrateAction(self)
        action.execute()

    def reboot(self):
        try:
            LOG.debug("Instance %s calling stop_mysql..." % self.id)
            self.guest.stop_mysql()
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
            raise ReddwarfError(msg)

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
            LOG.debug("Instance %s calling stop_mysql..."
                      % self.instance.id)
            self.instance.guest.stop_mysql(do_not_start_on_reboot=True)
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

    def __init__(self, instance, new_flavor_id=None, new_memory_size=None):
        self.instance = instance
        self.new_flavor_id = new_flavor_id
        self.new_memory_size = new_memory_size

    def _assert_nova_action_was_successful(self):
        # Do check to make sure the status and flavor id are correct.
        if str(self.instance.server.flavor['id']) != str(self.new_flavor_id):
            msg = "Assertion failed! flavor_id=%s and not %s" \
                  % (self.instance.server.flavor['id'], self.new_flavor_id)
            raise ReddwarfError(msg)

    def _initiate_nova_action(self):
        self.instance.server.resize(self.new_flavor_id)

    def _record_action_success(self):
        LOG.debug("Updating instance %s to flavor_id %s."
                  % (self.instance.id, self.new_flavor_id))
        self.instance.update_db(flavor_id=self.new_flavor_id)

    def _start_mysql(self):
        self.instance.guest.start_mysql_with_conf_changes(self.new_memory_size)


class MigrateAction(ResizeActionBase):

    def _assert_nova_action_was_successful(self):
        LOG.debug("Currently no assertions for a Migrate Action")

    def _initiate_nova_action(self):
        LOG.debug("Migrating instance %s without flavor change ..."
                  % self.instance.id)
        self.instance.server.migrate()

    def _record_action_success(self):
        LOG.debug("Successfully finished Migration to %s: %s" %
                  (self.hostname, self.instance.id))

    def _start_mysql(self):
        self.instance.guest.restart()
