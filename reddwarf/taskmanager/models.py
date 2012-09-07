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

import logging

from eventlet import greenthread
from datetime import datetime
import traceback
from novaclient import exceptions as nova_exceptions
from reddwarf.common import config
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


LOG = logging.getLogger(__name__)

use_nova_server_volume = config.Config.get_bool('use_nova_server_volume',
                                                default=False)


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
            files = {"/etc/guest_info": "--guest_id=%s\n--service_type=%s\n" %
                                        (self.id, service_type)}
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

        device_path = config.Config.get('device_path', '/dev/vdb')
        mount_point = config.Config.get('mount_point', '/var/lib/mysql')
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
        tb = traceback.format_exc()
        for line in tb:
            LOG.error(line)
        LOG.error(traceback.format_exc())
        self.update_db(task_status=task_status)
        raise ReddwarfError(message=message)

    def _create_volume(self, volume_size):
        LOG.info("Entering create_volume")
        LOG.debug(_("Starting to create the volume for the instance"))

        volume_support = config.Config.get("reddwarf_volume_support", 'False')
        LOG.debug(_("reddwarf volume support = %s") % volume_support)
        if (volume_size is None or
                utils.bool_from_string(volume_support) is False):
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
            time_out=2 * 60)

        v_ref = volume_client.volumes.get(volume_ref.id)
        if v_ref.status in ['error']:
            raise VolumeCreationFailure()
        LOG.debug(_("Created volume %s") % v_ref)
        # The mapping is in the format:
        # <id>:[<type>]:[<size(GB)>]:[<delete_on_terminate>]
        # setting the delete_on_terminate instance to true=1
        mapping = "%s:%s:%s:%s" % (v_ref.id, '', v_ref.size, 1)
        bdm = config.Config.get('block_device_mapping', 'vdb')
        block_device = {bdm: mapping}
        volumes = [{'id': v_ref.id,
                    'size': v_ref.size}]
        LOG.debug("block_device = %s" % block_device)
        LOG.debug("volume = %s" % volumes)

        device_path = config.Config.get('device_path', '/dev/vdb')
        mount_point = config.Config.get('mount_point', '/var/lib/mysql')
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
        files = {"/etc/guest_info": "guest_id=%s\nservice_type=%s\n" %
                                    (self.id, service_type)}
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
        LOG.debug("%s: Creating dns entry for instance: %s"
                  % (greenthread.getcurrent(), self.id))
        dns_client = create_dns_client(self.context)
        dns_support = config.Config.get("reddwarf_dns_support", 'False')
        LOG.debug(_("reddwarf dns support = %s") % dns_support)

        nova_client = create_nova_client(self.context)
        if utils.bool_from_string(dns_support):

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
                       sleep_time=1, time_out=60 * 2)
            server = nova_client.servers.get(self.db_info.compute_instance_id)
            LOG.info("Creating dns entry...")
            dns_client.create_instance_entry(self.id,
                                             get_ip_address(server.addresses))


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
            dns_support = config.Config.get("reddwarf_dns_support", 'False')
            LOG.debug(_("reddwarf dns support = %s") % dns_support)
            if utils.bool_from_string(dns_support):
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
                   time_out=int(config.Config.get('server_delete_time_out')))

    def resize_volume(self, new_size):
        LOG.debug("%s: Resizing volume for instance: %s to %r GB"
                  % (greenthread.getcurrent(), self.server.id, new_size))
        self.volume_client.volumes.resize(self.volume_id, int(new_size))
        try:
            utils.poll_until(
                lambda: self.volume_client.volumes.get(self.volume_id),
                lambda volume: volume.status == 'in-use',
                sleep_time=2,
                time_out=int(config.Config.get('volume_time_out')))
            volume = self.volume_client.volumes.get(self.volume_id)
            self.update_db(volume_size=volume.size)
            self.nova_client.volumes.rescan_server_volume(self.server,
                                                          self.volume_id)
            self.guest.resize_fs(self.get_volume_mountpoint())
        except PollTimeOut as pto:
            LOG.error("Timeout trying to rescan or resize the attached volume "
                      "filesystem for volume: %s" % self.volume_id)
        except Exception as e:
            LOG.error("Error encountered trying to rescan or resize the "
                      "attached volume filesystem for volume: %s"
                      % self.volume_id)
        finally:
            self.update_db(task_status=inst_models.InstanceTasks.NONE)

    def resize_flavor(self, new_flavor_id, old_memory_size,
                      new_memory_size):
        def resize_status_msg():
            return "instance_id=%s, status=%s, flavor_id=%s, "\
                   "dest. flavor id=%s)" % (self.db_info.id,
                                            self.server.status,
                                            str(self.flavor['id']),
                                            str(new_flavor_id))

        try:
            LOG.debug("Instance %s calling stop_mysql..." % self.db_info.id)
            self.guest.stop_mysql()
            try:
                LOG.debug("Instance %s calling Compute resize..."
                          % self.db_info.id)
                self.server.resize(new_flavor_id)

                # Do initial check and confirm the status is appropriate.
                self._refresh_compute_server_info()
                if (self.server.status != "RESIZE" and
                        self.server.status != "VERIFY_RESIZE"):
                    msg = "Unexpected status after call to resize! : %s"
                    raise ReddwarfError(msg % resize_status_msg())

                # Wait for the flavor to change.
                def update_server_info():
                    self._refresh_compute_server_info()
                    return self.server.status != 'RESIZE'

                utils.poll_until(
                    update_server_info,
                    sleep_time=2,
                    time_out=60 * 2)

                # Do check to make sure the status and flavor id are correct.
                if (str(self.server.flavor['id']) != str(new_flavor_id) or
                        self.server.status != "VERIFY_RESIZE"):
                    msg = "Assertion failed! flavor_id=%s and not %s"
                    actual_flavor = self.server.flavor['id']
                    expected_flavor = new_flavor_id
                    raise ReddwarfError(msg % (actual_flavor, expected_flavor))

                # Confirm the resize with Nova.
                LOG.debug("Instance %s calling Compute confirm resize..."
                          % self.db_info.id)
                self.server.confirm_resize()
                # Record the new flavor_id in our database.
                LOG.debug("Updating instance %s to flavor_id %s."
                          % (self.id, new_flavor_id))
                self.update_db(flavor_id=new_flavor_id)
            except PollTimeOut as pto:
                LOG.error("Timeout trying to resize the flavor for instance "
                          " %s" % self.db_info.id)
            except Exception as ex:
                new_memory_size = old_memory_size
                LOG.error("Error during resize compute! Aborting action.")
                LOG.error(ex)
            finally:
                # Tell the guest to restart MySQL with the new RAM size.
                # This is in the finally because we have to call this, or
                # else MySQL could stay turned off on an otherwise usable
                # instance.
                LOG.debug("Instance %s starting mysql..." % self.db_info.id)
                self.guest.start_mysql_with_conf_changes(new_memory_size)
        finally:
            self.update_db(task_status=inst_models.InstanceTasks.NONE)

    def reboot(self):
        try:
            LOG.debug("Instance %s calling stop_mysql..." % self.id)
            self.guest.stop_mysql()
            LOG.debug("Rebooting instance %s" % self.id)
            self.server.reboot()

            # Poll nova until instance is active
            reboot_time_out = int(config.Config.get("reboot_time_out", 60 * 2))

            def update_server_info():
                self._refresh_compute_server_info()
                return self.server.status == 'ACTIVE'
            utils.poll_until(
                update_server_info,
                sleep_time=2,
                time_out=reboot_time_out)

            # Set the status to PAUSED. The guest agent will reset the status
            # when the reboot completes and MySQL is running.
            status = InstanceServiceStatus.find_by(instance_id=self.id)
            status.set_status(inst_models.ServiceStatuses.PAUSED)
            status.save()
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
