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
import os.path

from heatclient import exc as heat_exceptions
from cinderclient import exceptions as cinder_exceptions
from eventlet import greenthread
from novaclient import exceptions as nova_exceptions
from trove.backup import models as bkup_models
from trove.common import cfg
from trove.common import template
from trove.common import utils
from trove.common.exception import GuestError
from trove.common.exception import GuestTimeout
from trove.common.exception import PollTimeOut
from trove.common.exception import VolumeCreationFailure
from trove.common.exception import TroveError
from trove.common.instance import ServiceStatuses
from trove.common import instance as rd_instance
from trove.common.remote import create_dns_client
from trove.common.remote import create_heat_client
from trove.common.remote import create_cinder_client
from trove.extensions.mysql import models as mysql_models
from trove.extensions.security_group.models import SecurityGroup
from trove.extensions.security_group.models import SecurityGroupRule
from swiftclient.client import ClientException
from trove.instance import models as inst_models
from trove.instance.models import BuiltInstance
from trove.instance.models import DBInstance
from trove.instance.models import FreshInstance
from trove.instance.tasks import InstanceTasks
from trove.instance.models import InstanceStatus
from trove.instance.models import InstanceServiceStatus
from trove.instance.views import get_ip_address
from trove.openstack.common import log as logging
from trove.openstack.common.gettextutils import _
from trove.openstack.common.notifier import api as notifier
from trove.openstack.common import timeutils
import trove.common.remote as remote

LOG = logging.getLogger(__name__)
CONF = cfg.CONF
VOLUME_TIME_OUT = CONF.volume_time_out  # seconds.
DNS_TIME_OUT = CONF.dns_time_out  # seconds.
RESIZE_TIME_OUT = CONF.resize_time_out  # seconds.
REVERT_TIME_OUT = CONF.revert_time_out  # seconds.
HEAT_TIME_OUT = CONF.heat_time_out  # seconds.
USAGE_SLEEP_TIME = CONF.usage_sleep_time  # seconds.
USAGE_TIMEOUT = CONF.usage_timeout  # seconds.
HEAT_STACK_SUCCESSFUL_STATUSES = [('CREATE', 'CREATE_COMPLETE')]
HEAT_RESOURCE_SUCCESSFUL_STATE = 'CREATE_COMPLETE'

use_nova_server_volume = CONF.use_nova_server_volume
use_heat = CONF.use_heat


class NotifyMixin(object):
    """Notification Mixin

    This adds the ability to send usage events to an Instance object.
    """

    def _get_service_id(self, datastore_manager, id_map):
        if datastore_manager in id_map:
            datastore_manager_id = id_map[datastore_manager]
        else:
            datastore_manager_id = cfg.UNKNOWN_SERVICE_ID
            LOG.error("Datastore ID for Manager (%s) is not configured"
                      % datastore_manager)
        return datastore_manager_id

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
            'name': self.name,
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

        payload['service_id'] = self._get_service_id(
            self.datastore_version.manager, CONF.notification_service_id)

        # Update payload with all other kwargs
        payload.update(kwargs)
        LOG.debug(_('Sending event: %(event_type)s, %(payload)s') %
                  {'event_type': event_type, 'payload': payload})
        notifier.notify(self.context, publisher_id, event_type, 'INFO',
                        payload)


class ConfigurationMixin(object):
    """Configuration Mixin

    Configuration related tasks for instances and resizes.
    """

    def _render_config(self, datastore_manager, flavor, instance_id):
        config = template.SingleInstanceConfigTemplate(
            datastore_manager, flavor, instance_id)
        config.render()
        return config


class FreshInstanceTasks(FreshInstance, NotifyMixin, ConfigurationMixin):
    def create_instance(self, flavor, image_id, databases, users,
                        datastore_manager, packages, volume_size,
                        backup_id, availability_zone, root_password, nics):

        LOG.debug(_("begin create_instance for id: %s") % self.id)
        security_groups = None

        # If security group support is enabled and heat based instance
        # orchestration is disabled, create a security group.
        #
        # Heat based orchestration handles security group(resource)
        # in the template definition.
        if CONF.trove_security_groups_support and not use_heat:
            try:
                security_groups = self._create_secgroup()
            except Exception as e:
                msg = (_("Error creating security group for instance: %s") %
                       self.id)
                err = inst_models.InstanceTasks.BUILDING_ERROR_SEC_GROUP
                self._log_and_raise(e, msg, err)
            else:
                LOG.debug(_("Successfully created security group for "
                            "instance: %s") % self.id)

        if use_heat:
            volume_info = self._create_server_volume_heat(
                flavor,
                image_id,
                datastore_manager,
                volume_size,
                availability_zone,
                nics)
        elif use_nova_server_volume:
            volume_info = self._create_server_volume(
                flavor['id'],
                image_id,
                security_groups,
                datastore_manager,
                volume_size,
                availability_zone,
                nics)
        else:
            volume_info = self._create_server_volume_individually(
                flavor['id'],
                image_id,
                security_groups,
                datastore_manager,
                volume_size,
                availability_zone,
                nics)

        config = self._render_config(datastore_manager, flavor, self.id)

        backup_info = None
        if backup_id is not None:
                backup = bkup_models.Backup.get_by_id(self.context, backup_id)
                backup_info = {'id': backup_id,
                               'location': backup.location,
                               'type': backup.backup_type,
                               'checksum': backup.checksum,
                               }
        self._guest_prepare(flavor['ram'], volume_info,
                            packages, databases, users, backup_info,
                            config.config_contents, root_password)

        if root_password:
            self.report_root_enabled()

        if not self.db_info.task_status.is_error:
            self.update_db(task_status=inst_models.InstanceTasks.NONE)

        # when DNS is supported, we attempt to add this after the
        # instance is prepared.  Otherwise, if DNS fails, instances
        # end up in a poorer state and there's no tooling around
        # re-sending the prepare call; retrying DNS is much easier.
        try:
            self._create_dns_entry()
        except Exception as e:
            msg = _("Error creating DNS entry for instance: %s") % self.id
            err = inst_models.InstanceTasks.BUILDING_ERROR_DNS
            self._log_and_raise(e, msg, err)
        else:
            LOG.debug(_("Successfully created DNS entry for instance: %s") %
                      self.id)

        # Make sure the service becomes active before sending a usage
        # record to avoid over billing a customer for an instance that
        # fails to build properly.
        try:
            utils.poll_until(self._service_is_active,
                             sleep_time=USAGE_SLEEP_TIME,
                             time_out=USAGE_TIMEOUT)
            self.send_usage_event('create', instance_size=flavor['ram'])
        except PollTimeOut:
            LOG.error(_("Timeout for service changing to active. "
                      "No usage create-event sent."))
            self.update_statuses_on_time_out()

        except Exception:
            LOG.exception(_("Error during create-event call."))

        LOG.debug(_("end create_instance for id: %s") % self.id)

    def report_root_enabled(self):
        mysql_models.RootHistory.create(self.context, self.id, 'root')

    def update_statuses_on_time_out(self):

        if CONF.update_status_on_fail:
            #Updating service status
            service = InstanceServiceStatus.find_by(instance_id=self.id)
            service.set_status(ServiceStatuses.
                               FAILED_TIMEOUT_GUESTAGENT)
            service.save()
            LOG.error(_("Service status: %(status)s") %
                      {'status': ServiceStatuses.
                       FAILED_TIMEOUT_GUESTAGENT.api_status})
            LOG.error(_("Service error description: %(desc)s") %
                      {'desc': ServiceStatuses.
                       FAILED_TIMEOUT_GUESTAGENT.description})
            #Updating instance status
            db_info = DBInstance.find_by(name=self.name)
            db_info.set_task_status(InstanceTasks.
                                    BUILDING_ERROR_TIMEOUT_GA)
            db_info.save()
            LOG.error(_("Trove instance status: %(action)s") %
                      {'action': InstanceTasks.
                       BUILDING_ERROR_TIMEOUT_GA.action})
            LOG.error(_("Trove instance status description: %(text)s") %
                      {'text': InstanceTasks.
                       BUILDING_ERROR_TIMEOUT_GA.db_text})

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
        if status == rd_instance.ServiceStatuses.RUNNING:
            return True
        elif status not in [rd_instance.ServiceStatuses.NEW,
                            rd_instance.ServiceStatuses.BUILDING]:
            raise TroveError(_("Service not active, status: %s") % status)

        c_id = self.db_info.compute_instance_id
        nova_status = self.nova_client.servers.get(c_id).status
        if nova_status in [InstanceStatus.ERROR,
                           InstanceStatus.FAILED]:
            raise TroveError(_("Server not active, status: %s") % nova_status)
        return False

    def _create_server_volume(self, flavor_id, image_id, security_groups,
                              datastore_manager, volume_size,
                              availability_zone, nics):
        LOG.debug(_("begin _create_server_volume for id: %s") % self.id)
        server = None
        try:
            files = {"/etc/guest_info": ("[DEFAULT]\n--guest_id="
                                         "%s\n--datastore_manager=%s\n"
                                         "--tenant_id=%s\n" %
                                         (self.id, datastore_manager,
                                          self.tenant_id))}
            name = self.hostname or self.name
            volume_desc = ("mysql volume for %s" % self.id)
            volume_name = ("mysql-%s" % self.id)
            volume_ref = {'size': volume_size, 'name': volume_name,
                          'description': volume_desc}

            server = self.nova_client.servers.create(
                name, image_id, flavor_id,
                files=files, volume=volume_ref,
                security_groups=security_groups,
                availability_zone=availability_zone, nics=nics)
            LOG.debug(_("Created new compute instance %(server_id)s "
                        "for id: %(id)s") %
                      {'server_id': server.id, 'id': self.id})

            server_dict = server._info
            LOG.debug(_("Server response: %s") % server_dict)
            volume_id = None
            for volume in server_dict.get('os:volumes', []):
                volume_id = volume.get('id')

            # Record the server ID and volume ID in case something goes wrong.
            self.update_db(compute_instance_id=server.id, volume_id=volume_id)
        except Exception as e:
            msg = _("Error creating server and volume for "
                    "instance %s") % self.id
            LOG.debug(_("end _create_server_volume for id: %s") % self.id)
            err = inst_models.InstanceTasks.BUILDING_ERROR_SERVER
            self._log_and_raise(e, msg, err)

        device_path = CONF.device_path
        mount_point = CONF.mount_point
        volume_info = {'device_path': device_path, 'mount_point': mount_point}
        LOG.debug(_("end _create_server_volume for id: %s") % self.id)
        return volume_info

    def _create_server_volume_heat(self, flavor, image_id,
                                   datastore_manager,
                                   volume_size, availability_zone, nics):
        LOG.debug(_("begin _create_server_volume_heat for id: %s") % self.id)
        try:
            client = create_heat_client(self.context)

            ifaces, ports = self._build_heat_nics(nics)
            template_obj = template.load_heat_template(datastore_manager)
            heat_template_unicode = template_obj.render(
                volume_support=CONF.trove_volume_support,
                ifaces=ifaces, ports=ports)
            try:
                heat_template = heat_template_unicode.encode('utf-8')
            except UnicodeEncodeError:
                LOG.error(_("heat template ascii encode issue"))
                raise TroveError("heat template ascii encode issue")

            parameters = {"Flavor": flavor["name"],
                          "VolumeSize": volume_size,
                          "InstanceId": self.id,
                          "ImageId": image_id,
                          "DatastoreManager": datastore_manager,
                          "AvailabilityZone": availability_zone,
                          "TenantId": self.tenant_id}
            stack_name = 'trove-%s' % self.id
            client.stacks.create(stack_name=stack_name,
                                 template=heat_template,
                                 parameters=parameters)
            try:
                utils.poll_until(
                    lambda: client.stacks.get(stack_name),
                    lambda stack: stack.stack_status in ['CREATE_COMPLETE',
                                                         'CREATE_FAILED'],
                    sleep_time=USAGE_SLEEP_TIME,
                    time_out=HEAT_TIME_OUT)
            except PollTimeOut:
                LOG.error(_("Timeout during stack status tracing"))
                raise TroveError("Timeout occured in tracking stack status")

            stack = client.stacks.get(stack_name)
            if ((stack.action, stack.stack_status)
                    not in HEAT_STACK_SUCCESSFUL_STATUSES):
                raise TroveError("Heat Stack Create Failed.")

            resource = client.resources.get(stack.id, 'BaseInstance')
            if resource.resource_status != HEAT_RESOURCE_SUCCESSFUL_STATE:
                raise TroveError("Heat Resource Provisioning Failed.")
            instance_id = resource.physical_resource_id

            if CONF.trove_volume_support:
                resource = client.resources.get(stack.id, 'DataVolume')
                if resource.resource_status != HEAT_RESOURCE_SUCCESSFUL_STATE:
                    raise TroveError("Heat Resource Provisioning Failed.")
                volume_id = resource.physical_resource_id
                self.update_db(compute_instance_id=instance_id,
                               volume_id=volume_id)
            else:
                self.update_db(compute_instance_id=instance_id)

        except (TroveError, heat_exceptions.HTTPNotFound) as e:
            msg = _("Error during creating stack for instance %s") % self.id
            LOG.debug(msg)
            err = inst_models.InstanceTasks.BUILDING_ERROR_SERVER
            self._log_and_raise(e, msg, err)

        device_path = CONF.device_path
        mount_point = CONF.mount_point
        volume_info = {'device_path': device_path, 'mount_point': mount_point}

        LOG.debug(_("end _create_server_volume_heat for id: %s") % self.id)
        return volume_info

    def _create_server_volume_individually(self, flavor_id, image_id,
                                           security_groups, datastore_manager,
                                           volume_size,
                                           availability_zone, nics):
        LOG.debug(_("begin _create_server_volume_individually for id: %s") %
                  self.id)
        server = None
        volume_info = self._build_volume_info(volume_size)
        block_device_mapping = volume_info['block_device']
        try:
            server = self._create_server(flavor_id, image_id, security_groups,
                                         datastore_manager,
                                         block_device_mapping,
                                         availability_zone, nics)
            server_id = server.id
            # Save server ID.
            self.update_db(compute_instance_id=server_id)
        except Exception as e:
            msg = _("Error creating server for instance %s") % self.id
            err = inst_models.InstanceTasks.BUILDING_ERROR_SERVER
            self._log_and_raise(e, msg, err)
        LOG.debug(_("end _create_server_volume_individually for id: %s") %
                  self.id)
        return volume_info

    def _build_volume_info(self, volume_size=None):
        volume_info = None
        volume_support = CONF.trove_volume_support
        LOG.debug(_("trove volume support = %s") % volume_support)
        if volume_support:
            try:
                volume_info = self._create_volume(volume_size)
            except Exception as e:
                msg = _("Error provisioning volume for instance: %s") % self.id
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
        LOG.debug(_("begin _create_volume for id: %s") % self.id)
        volume_client = create_cinder_client(self.context)
        volume_desc = ("mysql volume for %s" % self.id)
        volume_ref = volume_client.volumes.create(
            volume_size, name="mysql-%s" % self.id, description=volume_desc)

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
        LOG.debug(_("end _create_volume for id: %s") % self.id)
        return self._build_volume(v_ref)

    def _build_volume(self, v_ref):
        LOG.debug(_("Created volume %s") % v_ref)
        # The mapping is in the format:
        # <id>:[<type>]:[<size(GB)>]:[<delete_on_terminate>]
        # setting the delete_on_terminate instance to true=1
        mapping = "%s:%s:%s:%s" % (v_ref.id, '', v_ref.size, 1)
        bdm = CONF.block_device_mapping
        block_device = {bdm: mapping}
        created_volumes = [{'id': v_ref.id,
                            'size': v_ref.size}]
        LOG.debug("block_device = %s" % block_device)
        LOG.debug("volume = %s" % created_volumes)

        device_path = CONF.device_path
        mount_point = CONF.mount_point
        LOG.debug(_("device_path = %s") % device_path)
        LOG.debug(_("mount_point = %s") % mount_point)

        volume_info = {'block_device': block_device,
                       'device_path': device_path,
                       'mount_point': mount_point,
                       'volumes': created_volumes}
        return volume_info

    def _create_server(self, flavor_id, image_id, security_groups,
                       datastore_manager, block_device_mapping,
                       availability_zone, nics):
        files = {"/etc/guest_info": ("[DEFAULT]\nguest_id=%s\n"
                                     "datastore_manager=%s\n"
                                     "tenant_id=%s\n" %
                                     (self.id, datastore_manager,
                                      self.tenant_id))}
        if os.path.isfile(CONF.get('guest_config')):
            with open(CONF.get('guest_config'), "r") as f:
                files["/etc/trove-guestagent.conf"] = f.read()
        userdata = None
        cloudinit = os.path.join(CONF.get('cloudinit_location'),
                                 "%s.cloudinit" % datastore_manager)
        if os.path.isfile(cloudinit):
            with open(cloudinit, "r") as f:
                userdata = f.read()
        name = self.hostname or self.name
        bdmap = block_device_mapping
        server = self.nova_client.servers.create(
            name, image_id, flavor_id, files=files, userdata=userdata,
            security_groups=security_groups, block_device_mapping=bdmap,
            availability_zone=availability_zone, nics=nics)
        LOG.debug(_("Created new compute instance %(server_id)s "
                    "for id: %(id)s") %
                  {'server_id': server.id, 'id': self.id})
        return server

    def _guest_prepare(self, flavor_ram, volume_info,
                       packages, databases, users, backup_info=None,
                       config_contents=None, root_password=None):
        LOG.info(_("Entering guest_prepare"))
        # Now wait for the response from the create to do additional work
        self.guest.prepare(flavor_ram, packages, databases, users,
                           device_path=volume_info['device_path'],
                           mount_point=volume_info['mount_point'],
                           backup_info=backup_info,
                           config_contents=config_contents,
                           root_password=root_password)

    def _create_dns_entry(self):
        LOG.debug(_("%(gt)s: Creating dns entry for instance: %(id)s") %
                  {'gt': greenthread.getcurrent(), 'id': self.id})
        dns_support = CONF.trove_dns_support
        LOG.debug(_("trove dns support = %s") % dns_support)

        if dns_support:
            dns_client = create_dns_client(self.context)

            def get_server():
                c_id = self.db_info.compute_instance_id
                return self.nova_client.servers.get(c_id)

            def ip_is_available(server):
                LOG.info(_("Polling for ip addresses: $%s ") %
                         server.addresses)
                if server.addresses != {}:
                    return True
                elif (server.addresses == {} and
                        server.status != InstanceStatus.ERROR):
                    return False
                elif (server.addresses == {} and
                        server.status == InstanceStatus.ERROR):
                    LOG.error(_("Instance IP not available, "
                                "instance (%(instance)s): "
                                "server had status (%(status)s).") %
                              {'instance': self.id, 'status': server.status})
                    raise TroveError(status=server.status)

            utils.poll_until(get_server, ip_is_available,
                             sleep_time=1, time_out=DNS_TIME_OUT)
            server = self.nova_client.servers.get(
                self.db_info.compute_instance_id)
            LOG.info(_("Creating dns entry..."))
            ip = get_ip_address(server.addresses)
            if not ip:
                raise TroveError('Error creating DNS. No IP available.')
            dns_client.create_instance_entry(self.id, ip.pop)
        else:
            LOG.debug(_("%(gt)s: DNS not enabled for instance: %(id)s") %
                      {'gt': greenthread.getcurrent(), 'id': self.id})

    def _create_secgroup(self):
        security_group = SecurityGroup.create_for_instance(self.id,
                                                           self.context)
        if CONF.trove_security_groups_rules_support:
            SecurityGroupRule.create_sec_group_rule(
                security_group,
                CONF.trove_security_group_rule_protocol,
                CONF.trove_security_group_rule_port,
                CONF.trove_security_group_rule_port,
                CONF.trove_security_group_rule_cidr,
                self.context
            )
        return [security_group["name"]]

    def _build_heat_nics(self, nics):
        ifaces = []
        ports = []
        if nics:
            for idx, nic in enumerate(nics):
                iface_id = nic.get('port-id')
                if iface_id:
                    ifaces.append(iface_id)
                    continue
                net_id = nic.get('net-id')
                if net_id:
                    port = {}
                    port['name'] = "Port%s" % idx
                    port['net_id'] = net_id
                    fixed_ip = nic.get('v4-fixed-ip')
                    if fixed_ip:
                        port['fixed_ip'] = fixed_ip
                    ports.append(port)
                    ifaces.append("{Ref: Port%s}" % idx)
        return ifaces, ports


class BuiltInstanceTasks(BuiltInstance, NotifyMixin, ConfigurationMixin):
    """
    Performs the various asynchronous instance related tasks.
    """

    def _delete_resources(self, deleted_at):
        LOG.debug(_("begin _delete_resources for id: %s") % self.id)
        server_id = self.db_info.compute_instance_id
        old_server = self.nova_client.servers.get(server_id)
        try:
            if use_heat:
                # Delete the server via heat
                heatclient = create_heat_client(self.context)
                name = 'trove-%s' % self.id
                heatclient.stacks.delete(name)
            else:
                self.server.delete()
        except Exception as ex:
            LOG.exception(_("Error during delete compute server %s")
                          % self.server.id)
        try:
            dns_support = CONF.trove_dns_support
            LOG.debug(_("trove dns support = %s") % dns_support)
            if dns_support:
                dns_api = create_dns_client(self.context)
                dns_api.delete_instance_entry(instance_id=self.db_info.id)
        except Exception as ex:
            LOG.exception(_("Error during dns entry of instance %(id)s: "
                            "%(ex)s") % {'id': self.db_info.id, 'ex': ex})

            # Poll until the server is gone.
        def server_is_finished():
            try:
                server = self.nova_client.servers.get(server_id)
                if server.status not in ['SHUTDOWN', 'ACTIVE']:
                    LOG.error(_("Server %(server_id)s got into ERROR status "
                                "during delete of instance %(instance_id)s!") %
                              {'server_id': server.id, 'instance_id': self.id})
                return False
            except nova_exceptions.NotFound:
                return True

        try:
            utils.poll_until(server_is_finished, sleep_time=2,
                             time_out=CONF.server_delete_time_out)
        except PollTimeOut:
            LOG.exception(_("Timout during nova server delete of server: %s") %
                          server_id)
        self.send_usage_event('delete',
                              deleted_at=timeutils.isotime(deleted_at),
                              server=old_server)
        LOG.debug(_("end _delete_resources for id: %s") % self.id)

    def _resize_active_volume(self, new_size):
        try:
            LOG.debug(_("Instance %s calling stop_db...") % self.server.id)
            self.guest.stop_db()

            LOG.debug(_("Detach volume %(vol_id)s from instance %(id)s") %
                      {'vol_id': self.volume_id, 'id': self.server.id})
            self.volume_client.volumes.detach(self.volume_id)

            utils.poll_until(
                lambda: self.volume_client.volumes.get(self.volume_id),
                lambda volume: volume.status == 'available',
                sleep_time=2,
                time_out=CONF.volume_time_out)

            LOG.debug(_("Successfully detach volume %s") % self.volume_id)
        except Exception as e:
            LOG.debug(_("end _resize_active_volume for id: %s") %
                      self.server.id)
            LOG.exception(_("Failed to detach volume %(volume_id)s "
                          "instance %(id)s: %(e)s") %
                          {'volume_id': self.volume_id, 'id':
                           self.server.id, 'e': str(e)})
            self.restart()
            raise

        self._do_resize(new_size)
        self.volume_client.volumes.attach(self.server.id, self.volume_id)
        LOG.debug(_("end _resize_active_volume for id: %s") % self.server.id)
        self.restart()

    def _do_resize(self, new_size):
        try:
            self.volume_client.volumes.extend(self.volume_id, new_size)
        except cinder_exceptions.ClientException:
            LOG.exception(_("Error encountered trying to rescan or resize the "
                            "attached volume filesystem for volume: "
                            "%s") % self.volume_id)
            raise

        try:
            volume = self.volume_client.volumes.get(self.volume_id)
            if not volume:
                raise (cinder_exceptions.
                       ClientException(_('Failed to get volume with '
                                       'id: %(id)s') %
                                       {'id': self.volume_id}))
            utils.poll_until(
                lambda: self.volume_client.volumes.get(self.volume_id),
                lambda volume: volume.size == int(new_size),
                sleep_time=2,
                time_out=CONF.volume_time_out)
            self.update_db(volume_size=new_size)
        except PollTimeOut:
            LOG.error(_("Timeout trying to rescan or resize the attached "
                      "volume filesystem for volume %(vol_id)s of "
                      "instance: %(id)s") %
                      {'vol_id': self.volume_id, 'id': self.id})
        except Exception as e:
            LOG.exception(_("Error encountered trying to rescan or resize the "
                          "attached volume filesystem of volume %(vol_id)s of "
                          "instance %(id)s: %(e)s") %
                          {'vol_id': self.volume_id, 'id': self.id, 'e': e})
        finally:
            self.update_db(task_status=inst_models.InstanceTasks.NONE)

    def resize_volume(self, new_size):
        LOG.debug(_("begin resize_volume for id: %s") % self.id)
        old_volume_size = self.volume_size
        new_size = int(new_size)
        LOG.debug(_("%(gt)s: Resizing instance %(instance_id)s volume for "
                    "server %(server_id)s from %(old_volume_size)s to "
                    "%(new_size)r GB")
                  % {'gt': greenthread.getcurrent(),
                     'instance_id': self.id,
                     'server_id': self.server.id,
                     'old_volume_size': old_volume_size,
                     'new_size': new_size})

        if self.server.status == 'active':
            self._resize_active_volume(new_size)
        else:
            self._do_resize(new_size)

        self.send_usage_event('modify_volume', old_volume_size=old_volume_size,
                              launched_at=timeutils.isotime(self.updated),
                              modify_at=timeutils.isotime(self.updated),
                              volume_size=new_size)
        LOG.debug(_("end resize_volume for id: %s") % self.id)

    def resize_flavor(self, old_flavor, new_flavor):
        action = ResizeAction(self, old_flavor, new_flavor)
        action.execute()

    def migrate(self, host):
        LOG.debug(_("Calling migrate with host(%s)...") % host)
        action = MigrateAction(self, host)
        action.execute()

    def create_backup(self, backup_info):
        LOG.debug(_("Calling create_backup  %s ") % self.id)
        self.guest.create_backup(backup_info)

    def reboot(self):
        try:
            LOG.debug(_("Instance %s calling stop_db...") % self.id)
            self.guest.stop_db()
            LOG.debug(_("Rebooting instance %s") % self.id)
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
            LOG.debug(_("Successfully rebooted instance %s") % self.id)
        except Exception as e:
            LOG.error(_("Failed to reboot instance %(id)s: %(e)s") %
                      {'id': self.id, 'e': str(e)})
        finally:
            LOG.debug(_("Rebooting FINALLY  %s") % self.id)
            self.update_db(task_status=inst_models.InstanceTasks.NONE)

    def restart(self):
        LOG.debug(_("Restarting MySQL on instance %s ") % self.id)
        try:
            self.guest.restart()
            LOG.debug(_("Restarting MySQL successful  %s ") % self.id)
        except GuestError:
            LOG.error(_("Failure to restart MySQL for instance %s.") % self.id)
        finally:
            LOG.debug(_("Restarting FINALLY  %s ") % self.id)
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
        status.set_status(rd_instance.ServiceStatuses.PAUSED)
        status.save()


class BackupTasks(object):
    @classmethod
    def _parse_manifest(cls, manifest):
        # manifest is in the format 'container/prefix'
        # where prefix can be 'path' or 'lots/of/paths'
        try:
            container_index = manifest.index('/')
            prefix_index = container_index + 1
        except ValueError:
            return None, None
        container = manifest[:container_index]
        prefix = manifest[prefix_index:]
        return container, prefix

    @classmethod
    def delete_files_from_swift(cls, context, filename):
        container = CONF.backup_swift_container
        client = remote.create_swift_client(context)
        obj = client.head_object(container, filename)
        manifest = obj.get('x-object-manifest', '')
        cont, prefix = cls._parse_manifest(manifest)
        if all([cont, prefix]):
            # This is a manifest file, first delete all segments.
            LOG.info(_("Deleting files with prefix: %(cont)s/%(prefix)s") %
                     {'cont': cont, 'prefix': prefix})
            # list files from container/prefix specified by manifest
            headers, segments = client.get_container(cont, prefix=prefix)
            LOG.debug(headers)
            for segment in segments:
                name = segment.get('name')
                if name:
                    LOG.info(_("Deleting file: %(cont)s/%(name)s") %
                             {'cont': cont, 'name': name})
                    client.delete_object(cont, name)
        # Delete the manifest file
        LOG.info(_("Deleting file: %(cont)s/%(filename)s") %
                 {'cont': cont, 'filename': filename})
        client.delete_object(container, filename)

    @classmethod
    def delete_backup(cls, context, backup_id):
        #delete backup from swift
        backup = bkup_models.Backup.get_by_id(context, backup_id)
        try:
            filename = backup.filename
            if filename:
                BackupTasks.delete_files_from_swift(context, filename)
        except ValueError:
            backup.delete()
        except ClientException as e:
            if e.http_status == 404:
                # Backup already deleted in swift
                backup.delete()
            else:
                LOG.exception(_("Exception deleting from swift. "
                                "Details: %s") % e)
                backup.state = bkup_models.BackupState.DELETE_FAILED
                backup.save()
                raise TroveError("Failed to delete swift objects")
        else:
            backup.delete()


class ResizeActionBase(ConfigurationMixin):
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
            msg = "Migration failed! status=%s and not %s" % \
                (self.instance.server.status, 'VERIFY_RESIZE')
            raise TroveError(msg)

    def _assert_mysql_is_ok(self):
        # Tell the guest to turn on MySQL, and ensure the status becomes
        # ACTIVE.
        self._start_mysql()
        # The guest should do this for us... but sometimes it walks funny.
        self.instance._refresh_compute_service_status()
        if self.instance.service_status != rd_instance.ServiceStatuses.RUNNING:
            raise Exception("Migration failed! Service status was %s."
                            % self.instance.service_status)

    def _assert_processes_are_ok(self):
        """Checks the procs; if anything is wrong, reverts the operation."""
        # Tell the guest to turn back on, and make sure it can start.
        self._assert_guest_is_ok()
        LOG.debug(_("Nova guest is fine."))
        self._assert_mysql_is_ok()
        LOG.debug(_("Mysql is good, too."))

    def _confirm_nova_action(self):
        LOG.debug(_("Instance %s calling Compute confirm resize...")
                  % self.instance.id)
        self.instance.server.confirm_resize()

    def _revert_nova_action(self):
        LOG.debug(_("Instance %s calling Compute revert resize...")
                  % self.instance.id)
        self.instance.server.revert_resize()

    def execute(self):
        """Initiates the action."""
        try:
            LOG.debug(_("Instance %s calling stop_db...")
                      % self.instance.id)
            self.instance.guest.stop_db(do_not_start_on_reboot=True)
            self._perform_nova_action()
        finally:
            self.instance.update_db(task_status=inst_models.InstanceTasks.NONE)

    def _guest_is_awake(self):
        self.instance._refresh_compute_service_status()
        return (self.instance.service_status !=
                rd_instance.ServiceStatuses.PAUSED)

    def _perform_nova_action(self):
        """Calls Nova to resize or migrate an instance, and confirms."""
        LOG.debug(_("begin resize method _perform_nova_action instance: %s") %
                  self.instance.id)
        need_to_revert = False
        try:
            LOG.debug(_("Initiating nova action"))
            self._initiate_nova_action()
            LOG.debug(_("Waiting for nova action"))
            self._wait_for_nova_action()
            LOG.debug(_("Asserting nova status is ok"))
            self._assert_nova_status_is_ok()
            need_to_revert = True
            LOG.debug(_("* * * REVERT BARRIER PASSED * * *"))
            LOG.debug(_("Asserting nova action success"))
            self._assert_nova_action_was_successful()
            LOG.debug(_("Asserting processes are OK"))
            self._assert_processes_are_ok()
            LOG.debug(_("Confirming nova action"))
            self._confirm_nova_action()
        except Exception as ex:
            LOG.exception(_("Exception during nova action."))
            if need_to_revert:
                LOG.error(_("Reverting action for instance %s") %
                          self.instance.id)
                self._revert_nova_action()
                self._wait_for_revert_nova_action()

            if self.instance.server.status == 'ACTIVE':
                LOG.error(_("Restarting MySQL."))
                self.instance.guest.restart()
            else:
                LOG.error(_("Can not restart MySQL because "
                            "Nova server status is not ACTIVE"))

            LOG.error(_("Error resizing instance %s.") % self.instance.id)
            raise ex

        LOG.debug(_("Recording success"))
        self._record_action_success()
        LOG.debug(_("end resize method _perform_nova_action instance: %s") %
                  self.instance.id)

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
    def __init__(self, instance, old_flavor, new_flavor):
        self.instance = instance
        self.old_flavor = old_flavor
        self.new_flavor = new_flavor
        self.new_flavor_id = new_flavor['id']

    def _assert_nova_action_was_successful(self):
        # Do check to make sure the status and flavor id are correct.
        if str(self.instance.server.flavor['id']) != str(self.new_flavor_id):
            msg = "Assertion failed! flavor_id=%s and not %s" \
                  % (self.instance.server.flavor['id'], self.new_flavor_id)
            raise TroveError(msg)

    def _initiate_nova_action(self):
        self.instance.server.resize(self.new_flavor_id)

    def _revert_nova_action(self):
        LOG.debug(_("Instance %s calling Compute revert resize...")
                  % self.instance.id)
        LOG.debug(_("Repairing config."))
        try:
            config = self._render_config(
                self.instance.datastore_version.manager,
                self.old_flavor,
                self.instance.id
            )
            config = {'config_contents': config.config_contents}
            self.instance.guest.reset_configuration(config)
        except GuestTimeout:
            LOG.exception(_("Error sending reset_configuration call."))
        LOG.debug(_("Reverting resize."))
        super(ResizeAction, self)._revert_nova_action()

    def _record_action_success(self):
        LOG.debug(_("Updating instance %(id)s to flavor_id %(flavor_id)s.")
                  % {'id': self.instance.id, 'flavor_id': self.new_flavor_id})
        self.instance.update_db(flavor_id=self.new_flavor_id)
        self.instance.send_usage_event(
            'modify_flavor',
            old_instance_size=self.old_flavor['ram'],
            instance_size=self.new_flavor['ram'],
            launched_at=timeutils.isotime(self.instance.updated),
            modify_at=timeutils.isotime(self.instance.updated))

    def _start_mysql(self):
        config = self._render_config(self.instance.datastore_version.manager,
                                     self.new_flavor, self.instance.id)
        self.instance.guest.start_db_with_conf_changes(config.config_contents)


class MigrateAction(ResizeActionBase):
    def __init__(self, instance, host=None):
        self.instance = instance
        self.host = host

    def _assert_nova_action_was_successful(self):
        LOG.debug(_("Currently no assertions for a Migrate Action"))

    def _initiate_nova_action(self):
        LOG.debug(_("Migrating instance %s without flavor change ...")
                  % self.instance.id)
        LOG.debug(_("Forcing migration to host(%s)") % self.host)
        self.instance.server.migrate(force_host=self.host)

    def _record_action_success(self):
        LOG.debug(_("Successfully finished Migration to "
                    "%(hostname)s: %(id)s") %
                  {'hostname': self.instance.hostname,
                   'id': self.instance.id})

    def _start_mysql(self):
        self.instance.guest.restart()
