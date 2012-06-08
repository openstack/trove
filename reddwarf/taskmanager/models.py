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

from novaclient import exceptions as nova_exceptions
from reddwarf.common import config
from reddwarf.common import remote
from reddwarf.common import utils
from reddwarf.common.exception import PollTimeOut
from reddwarf.common.exception import VolumeCreationFailure
from reddwarf.common.exception import NotFound
from reddwarf.common.exception import ReddwarfError
from reddwarf.common.remote import create_dns_client
from reddwarf.common.remote import create_nova_client
from reddwarf.common.remote import create_nova_volume_client
from reddwarf.common.remote import create_guest_client
from reddwarf.common.utils import poll_until
from reddwarf.instance import models as inst_models
from reddwarf.instance.models import DBInstance
from reddwarf.instance.models import InstanceStatus
from reddwarf.instance.models import InstanceServiceStatus
from reddwarf.instance.models import populate_databases
from reddwarf.instance.models import ServiceStatuses
from reddwarf.instance.views import get_ip_address


LOG = logging.getLogger(__name__)


class InstanceTasks:
    """
    Performs the various asynchronous instance related tasks.
    """

    def __init__(self, context, db_info=None, server=None, volumes=None,
                 nova_client=None, volume_client=None, guest=None):
        self.context = context
        self.db_info = db_info
        self.server = server
        self.volumes = volumes
        self.nova_client = nova_client
        self.volume_client = volume_client
        self.guest = guest

    @property
    def volume_id(self):
        return self.volumes[0]['id']

    @property
    def volume_mountpoint(self):
        mountpoint = self.volumes[0]['mountpoint']
        if mountpoint[0] is not "/":
            return "/%s" % mountpoint
        else:
            return mountpoint

    @staticmethod
    def load(context, id):
        if context is None:
            raise TypeError("Argument context not defined.")
        elif id is None:
            raise TypeError("Argument id not defined.")
        try:
            db_info = inst_models.DBInstance.find_by(id=id)
        except NotFound:
            raise NotFound(uuid=id)
        server, volumes = inst_models.load_server_with_volumes(context,
                                                db_info.id,
                                                db_info.compute_instance_id)
        nova_client = remote.create_nova_client(context)
        volume_client = remote.create_nova_volume_client(context)
        guest = remote.create_guest_client(context, id)
        return InstanceTasks(context, db_info, server, volumes,
                             nova_client=nova_client,
                             volume_client=volume_client, guest=guest)

    def delete_instance(self):
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
                      % self.db_info.id )
            LOG.error(ex)

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
            self.nova_client.volumes.rescan_server_volume(self.server,
                                                          self.volume_id)
            self.guest.resize_fs(self.volume_mountpoint)
        except PollTimeOut as pto:
            LOG.error("Timeout trying to rescan or resize the attached volume "
                      "filesystem for volume: %s" % self.volume_id)
        except Exception as e:
            LOG.error("Error encountered trying to rescan or resize the "
                      "attached volume filesystem for volume: %s"
                      % self.volume_id)
        finally:
            self.db_info.task_status = inst_models.InstanceTasks.NONE
            self.db_info.save()

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
                if self.server.status != "RESIZE" and\
                   self.server.status != "VERIFY_RESIZE":
                    raise ReddwarfError("Unexpected status after " \
                            "call to resize! : %s" % resize_status_msg())

                # Wait for the flavor to change.
                utils.poll_until(
                    lambda: self.nova_client.servers.get(self.server.id),
                    lambda server: server.status != 'RESIZE',
                    sleep_time=2,
                    time_out=60 * 2)

                # Do check to make sure the status and flavor id are correct.
                if (str(self.server.flavor['id']) != str(new_flavor_id) or
                    self.server.status != "VERIFY_RESIZE"):
                    raise ReddwarfError("Assertion failed! flavor_id=%s "
                                        "and not %s"
                    % (self.server.status, str(self.server.flavor['id'])))

                # Confirm the resize with Nova.
                LOG.debug("Instance %s calling Compute confirm resize..."
                          % self.db_info.id)
                self.server.confirm_resize()
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
            self.db_info.task_status = inst_models.InstanceTasks.NONE
            self.db_info.save()

    def create_instance(self, instance_id, name, flavor_ref,
                            image_id, databases, service_type, volume_size):
        LOG.info("Entering create_instance")
        try:
            db_info = DBInstance.find_by(id=instance_id)
            volume_info = self._create_volume(instance_id,
                                              volume_size)
            block_device_mapping = volume_info['block_device']
            server = self._create_server(instance_id, name,
                    flavor_ref, image_id, service_type, block_device_mapping)
            LOG.info("server id: %s" % server)
            server_id = server.id
            self._create_dns_entry(instance_id, server_id)
            LOG.info("volume_info %s " % volume_info)
            self._guest_prepare(server, db_info, volume_info, databases)
        except Exception, e:
            LOG.error(e)
            self._log_service_status(instance_id, ServiceStatuses.UNKNOWN)

    def _create_volume(self, instance_id, volume_size):
        LOG.info("Entering create_volume")
        LOG.debug(_("Starting to create the volume for the instance"))

        volume_support = config.Config.get("reddwarf_volume_support", 'False')
        LOG.debug(_("reddwarf volume support = %s") % volume_support)
        if volume_size is None or \
           utils.bool_from_string(volume_support) is False:
            volume_info = {'block_device': None,
                           'device_path': None,
                           'mount_point': None,
                           'volumes': None}
            return volume_info

        db_info = DBInstance.find_by(id=instance_id)

        volume_client = create_nova_volume_client(self.context)
        volume_desc = ("mysql volume for %s" % instance_id)
        volume_ref = volume_client.volumes.create(
                        volume_size,
                        display_name="mysql-%s" % db_info.id,
                        display_description=volume_desc)

        # Record the volume ID in case something goes wrong.
        db_info.volume_id = volume_ref.id
        db_info.save()

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

    def _create_server(self, instance_id, name, flavor_ref, image_id,
                       service_type, block_device_mapping):
        nova_client = create_nova_client(self.context)
        files = {"/etc/guest_info": "guest_id=%s\nservice_type=%s\n" %
                                    (instance_id, service_type)}
        server = nova_client.servers.create(name, image_id, flavor_ref,
                        files=files, block_device_mapping=block_device_mapping)
        LOG.debug(_("Created new compute instance %s.") % server.id)
        return server

    def _guest_prepare(self, server, db_info, volume_info, databases):
        LOG.info("Entering guest_prepare")
        db_info.compute_instance_id = server.id
        db_info.save()
        self._log_service_status(db_info, ServiceStatuses.NEW)

        # Now wait for the response from the create to do additional work
        guest = create_guest_client(self.context, db_info.id)

        # populate the databases
        model_schemas = populate_databases(databases)
        guest.prepare(512, model_schemas, users=[],
                      device_path=volume_info['device_path'],
                      mount_point=volume_info['mount_point'])

    def _create_dns_entry(self, instance_id, server_id):
        LOG.debug("%s: Creating dns entry for instance: %s"
                  % (greenthread.getcurrent(), instance_id))
        dns_client = create_dns_client(self.context)
        dns_support = config.Config.get("reddwarf_dns_support", 'False')
        LOG.debug(_("reddwarf dns support = %s") % dns_support)

        nova_client = create_nova_client(self.context)
        if utils.bool_from_string(dns_support):
            def get_server():
                return nova_client.servers.get(server_id)

            def ip_is_available(server):
                LOG.info("Polling for ip addresses: $%s " % server.addresses)
                if server.addresses != {}:
                    return True
                elif server.addresses == {} and\
                     server.status != InstanceStatus.ERROR:
                    return False
                elif server.addresses == {} and\
                     server.status == InstanceStatus.ERROR:
                    LOG.error(_("Instance IP not available, instance (%s): "
                                "server had status (%s).")
                    % (instance_id, server.status))
                    raise ReddwarfError(status=server.status)
            poll_until(get_server, ip_is_available,
                       sleep_time=1, time_out=60 * 2)
            server = nova_client.servers.get(server_id)
            LOG.info("Creating dns entry...")
            dns_client.create_instance_entry(instance_id,
                                             get_ip_address(server.addresses))

    def _log_service_status(self, instance_id, status):
        LOG.info("Saving service status %s for instance %s "
                  % (status, instance_id))
        service_status = InstanceServiceStatus.get_by(instance_id=instance_id)
        if service_status:
            service_status.status = status
            service_status.save()
        else:
            InstanceServiceStatus.create(instance_id=instance_id,
                                         status=status)

    def _refresh_compute_server_info(self):
        """Refreshes the compute server field."""
        server = self.nova_client.servers.get(self.server.id)
        self.server = server
