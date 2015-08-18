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

import re
import traceback
import os.path

from heatclient import exc as heat_exceptions
from cinderclient import exceptions as cinder_exceptions
from eventlet import greenthread
from novaclient import exceptions as nova_exceptions

from oslo.utils import timeutils

from trove.backup import models as bkup_models
from trove.backup.models import Backup
from trove.backup.models import DBBackup
from trove.backup.state import BackupState
from trove.cluster.models import Cluster
from trove.cluster.models import DBCluster
from trove.cluster import tasks
from trove.common import cfg
from trove.common import exception
from trove.common import template
from trove.common import utils
from trove.common.utils import try_recover
from trove.common.exception import BackupCreationError
from trove.common.exception import GuestError
from trove.common.exception import GuestTimeout
from trove.common.exception import InvalidModelError
from trove.common.exception import MalformedSecurityGroupRuleError
from trove.common.exception import PollTimeOut
from trove.common.exception import TroveError
from trove.common.exception import VolumeCreationFailure
from trove.common.instance import ServiceStatuses
from trove.common import instance as rd_instance
from trove.common.strategies.cluster import strategy
from trove.common.remote import create_dns_client
from trove.common.remote import create_heat_client
from trove.common.remote import create_cinder_client
from trove.extensions.mysql import models as mysql_models
from trove.configuration.models import Configuration
from trove.extensions.security_group.models import SecurityGroup
from trove.extensions.security_group.models import SecurityGroupRule
from trove.extensions.security_group.models import (
    SecurityGroupInstanceAssociation)
from swiftclient.client import ClientException
from trove.instance import models as inst_models
from trove.instance.models import BuiltInstance
from trove.instance.models import DBInstance
from trove.instance.models import FreshInstance
from trove.instance.tasks import InstanceTasks
from trove.instance.models import InstanceStatus
from trove.instance.models import InstanceServiceStatus
from trove.openstack.common import log as logging
from trove.common.i18n import _
from trove.quota.quota import run_with_quotas
import trove.common.remote as remote
from trove import rpc

LOG = logging.getLogger(__name__)
CONF = cfg.CONF
VOLUME_TIME_OUT = CONF.volume_time_out  # seconds.
DNS_TIME_OUT = CONF.dns_time_out  # seconds.
RESIZE_TIME_OUT = CONF.resize_time_out  # seconds.
REVERT_TIME_OUT = CONF.revert_time_out  # seconds.
HEAT_TIME_OUT = CONF.heat_time_out  # seconds.
USAGE_SLEEP_TIME = CONF.usage_sleep_time  # seconds.
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

        if CONF.get(self.datastore_version.manager).volume_support:
            payload.update({
                'volume_size': self.volume_size,
                'nova_volume_id': self.volume_id
            })

        payload['service_id'] = self._get_service_id(
            self.datastore_version.manager, CONF.notification_service_id)

        # Update payload with all other kwargs
        payload.update(kwargs)
        LOG.debug('Sending event: %(event_type)s, %(payload)s' %
                  {'event_type': event_type, 'payload': payload})

        notifier = rpc.get_notifier(
            service="taskmanager", publisher_id=publisher_id)

        notifier.info(self.context, event_type, payload)


class ConfigurationMixin(object):
    """Configuration Mixin

    Configuration related tasks for instances and resizes.
    """

    def _render_config(self, flavor):
        config = template.SingleInstanceConfigTemplate(
            self.datastore_version, flavor, self.id)
        config.render()
        return config

    def _render_override_config(self, flavor, overrides=None):
        config = template.OverrideConfigTemplate(
            self.datastore_version, flavor, self.id)
        config.render(overrides=overrides)
        return config

    def _render_replica_source_config(self, flavor):
        config = template.ReplicaSourceConfigTemplate(
            self.datastore_version, flavor, self.id)
        config.render()
        return config

    def _render_replica_config(self, flavor):
        config = template.ReplicaConfigTemplate(
            self.datastore_version, flavor, self.id)
        config.render()
        return config

    def _render_config_dict(self, flavor):
        config = template.SingleInstanceConfigTemplate(
            self.datastore_version, flavor, self.id)
        ret = config.render_dict()
        LOG.debug("the default template dict of mysqld section: %s" % ret)
        return ret


class ClusterTasks(Cluster):

    def delete_cluster(self, context, cluster_id):

        LOG.debug("begin delete_cluster for id: %s" % cluster_id)

        def all_instances_marked_deleted():
            db_instances = DBInstance.find_all(cluster_id=cluster_id,
                                               deleted=False).all()
            return len(db_instances) == 0

        try:
            utils.poll_until(all_instances_marked_deleted,
                             sleep_time=2,
                             time_out=CONF.cluster_delete_time_out)
        except PollTimeOut:
            LOG.error(_("timeout for instances to be marked as deleted."))
            return

        LOG.debug("setting cluster %s as deleted." % cluster_id)
        cluster = DBCluster.find_by(id=cluster_id)
        cluster.deleted = True
        cluster.deleted_at = utils.utcnow()
        cluster.task_status = tasks.ClusterTasks.NONE
        cluster.save()
        LOG.debug("end delete_cluster for id: %s" % cluster_id)


class FreshInstanceTasks(FreshInstance, NotifyMixin, ConfigurationMixin):

    def _get_injected_files(self, datastore_manager):
        injected_config_location = CONF.get('injected_config_location')
        guest_info = CONF.get('guest_info')

        if ('/' in guest_info):
            # Set guest_info_file to exactly guest_info from the conf file.
            # This should be /etc/guest_info for pre-Kilo compatibility.
            guest_info_file = guest_info
        else:
            guest_info_file = os.path.join(injected_config_location,
                                           guest_info)

        files = {guest_info_file: (
            "[DEFAULT]\n"
            "guest_id=%s\n"
            "datastore_manager=%s\n"
            "tenant_id=%s\n"
            % (self.id, datastore_manager, self.tenant_id))}

        if os.path.isfile(CONF.get('guest_config')):
            with open(CONF.get('guest_config'), "r") as f:
                files[os.path.join(injected_config_location,
                                   "trove-guestagent.conf")] = f.read()

        return files

    def wait_for_instance(self, timeout, flavor):
        # Make sure the service becomes active before sending a usage
        # record to avoid over billing a customer for an instance that
        # fails to build properly.
        try:
            utils.poll_until(self._service_is_active,
                             sleep_time=USAGE_SLEEP_TIME,
                             time_out=timeout)
            LOG.info(_("Created instance %s successfully.") % self.id)
            self.send_usage_event('create', instance_size=flavor['ram'])
        except PollTimeOut:
            LOG.error(_("Failed to create instance %s. "
                        "Timeout waiting for instance to become active. "
                        "No usage create-event was sent.") % self.id)
            self.update_statuses_on_time_out()
        except Exception:
            LOG.exception(_("Failed to send usage create-event for "
                            "instance %s.") % self.id)

    def create_instance(self, flavor, image_id, databases, users,
                        datastore_manager, packages, volume_size,
                        backup_id, availability_zone, root_password, nics,
                        overrides, cluster_config, snapshot=None):
        # It is the caller's responsibility to ensure that
        # FreshInstanceTasks.wait_for_instance is called after
        # create_instance to ensure that the proper usage event gets sent

        LOG.info(_("Creating instance %s.") % self.id)
        security_groups = None

        # If security group support is enabled and heat based instance
        # orchestration is disabled, create a security group.
        #
        # Heat based orchestration handles security group(resource)
        # in the template definition.
        if CONF.trove_security_groups_support and not use_heat:
            try:
                security_groups = self._create_secgroup(datastore_manager)
            except Exception as e:
                msg = (_("Error creating security group for instance: %s") %
                       self.id)
                err = inst_models.InstanceTasks.BUILDING_ERROR_SEC_GROUP
                self._log_and_raise(e, msg, err)
            else:
                LOG.debug("Successfully created security group for "
                          "instance: %s" % self.id)

        files = self._get_injected_files(datastore_manager)

        if use_heat:
            volume_info = self._create_server_volume_heat(
                flavor,
                image_id,
                datastore_manager,
                volume_size,
                availability_zone,
                nics,
                files)
        elif use_nova_server_volume:
            volume_info = self._create_server_volume(
                flavor['id'],
                image_id,
                security_groups,
                datastore_manager,
                volume_size,
                availability_zone,
                nics,
                files)
        else:
            volume_info = self._create_server_volume_individually(
                flavor['id'],
                image_id,
                security_groups,
                datastore_manager,
                volume_size,
                availability_zone,
                nics,
                files)

        config = self._render_config(flavor)
        config_overrides = self._render_override_config(flavor,
                                                        overrides=overrides)

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
                            config.config_contents, root_password,
                            config_overrides.config_contents,
                            cluster_config, snapshot)

        if root_password:
            self.report_root_enabled()

        if not self.db_info.task_status.is_error:
            self.reset_task_status()

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
            LOG.debug("Successfully created DNS entry for instance: %s" %
                      self.id)

    def attach_replication_slave(self, snapshot, flavor):
        LOG.debug("Calling attach_replication_slave for %s.", self.id)
        try:
            replica_config = self._render_replica_config(flavor)
            self.guest.attach_replication_slave(snapshot,
                                                replica_config.config_contents)
        except GuestError as e:
            msg = (_("Error attaching instance %s "
                     "as replica.") % self.id)
            err = inst_models.InstanceTasks.BUILDING_ERROR_REPLICA
            self._log_and_raise(e, msg, err)

    def get_replication_master_snapshot(self, context, slave_of_id, flavor,
                                        backup_id=None, replica_number=1):
        # if we aren't passed in a backup id, look it up to possibly do
        # an incremental backup, thus saving time
        if not backup_id:
            backup = Backup.get_last_completed(
                context, slave_of_id, include_incremental=True)
            if backup:
                backup_id = backup.id
        snapshot_info = {
            'name': "Replication snapshot for %s" % self.id,
            'description': "Backup image used to initialize "
                           "replication slave",
            'instance_id': slave_of_id,
            'parent_id': backup_id,
            'tenant_id': self.tenant_id,
            'state': BackupState.NEW,
            'datastore_version_id': self.datastore_version.id,
            'deleted': False,
            'replica_number': replica_number,
        }

        # Only do a backup if it's the first replica
        if replica_number == 1:
            try:
                db_info = DBBackup.create(**snapshot_info)
                replica_backup_id = db_info.id
            except InvalidModelError:
                msg = (_("Unable to create replication snapshot record for "
                         "instance: %s") % self.id)
                LOG.exception(msg)
                raise BackupCreationError(msg)
            if backup_id:
                # Look up the parent backup  info or fail early if not found or
                # if the user does not have access to the parent.
                _parent = Backup.get_by_id(context, backup_id)
                parent = {
                    'location': _parent.location,
                    'checksum': _parent.checksum,
                }
                snapshot_info.update({
                    'parent': parent,
                })
        else:
            # we've been passed in the actual replica backup id, so just use it
            replica_backup_id = backup_id

        try:
            master = BuiltInstanceTasks.load(context, slave_of_id)
            snapshot_info.update({
                'id': replica_backup_id,
                'datastore': master.datastore.name,
                'datastore_version': master.datastore_version.name,
            })
            snapshot = master.get_replication_snapshot(
                snapshot_info, flavor=master.flavor_id)
            snapshot.update({
                'config': self._render_replica_config(flavor).config_contents
            })
            return snapshot
        except Exception as e_create:
            msg_create = (
                _("Error creating replication snapshot from "
                  "instance %(source)s for new replica %(replica)s.") %
                {'source': slave_of_id, 'replica': self.id})
            err = inst_models.InstanceTasks.BUILDING_ERROR_REPLICA
            # if the delete of the 'bad' backup fails, it'll mask the
            # create exception, so we trap it here
            try:
                # Only try to delete the backup if it's the first replica
                if replica_number == 1:
                    Backup.delete(context, replica_backup_id)
            except Exception as e_delete:
                LOG.error(msg_create)
                # Make sure we log any unexpected errors from the create
                if not isinstance(e_create, TroveError):
                    LOG.error(e_create)
                msg_delete = (
                    _("An error occurred while deleting a bad "
                      "replication snapshot from instance %(source)s.") %
                    {'source': slave_of_id})
                # we've already logged the create exception, so we'll raise
                # the delete (otherwise the create will be logged twice)
                self._log_and_raise(e_delete, msg_delete, err)

            # the delete worked, so just log the original problem with create
            self._log_and_raise(e_create, msg_create, err)

    def report_root_enabled(self):
        mysql_models.RootHistory.create(self.context, self.id, 'root')

    def update_statuses_on_time_out(self):

        if CONF.update_status_on_fail:
            # Updating service status
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
            # Updating instance status
            db_info = DBInstance.find_by(id=self.id, deleted=False)
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
        if (status == rd_instance.ServiceStatuses.RUNNING or
           status == rd_instance.ServiceStatuses.BUILD_PENDING):
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
                              availability_zone, nics, files):
        LOG.debug("Begin _create_server_volume for id: %s" % self.id)
        try:
            userdata = self._prepare_userdata(datastore_manager)
            name = self.hostname or self.name
            volume_desc = ("datastore volume for %s" % self.id)
            volume_name = ("datastore-%s" % self.id)
            volume_ref = {'size': volume_size, 'name': volume_name,
                          'description': volume_desc}
            config_drive = CONF.use_nova_server_config_drive
            server = self.nova_client.servers.create(
                name, image_id, flavor_id,
                files=files, volume=volume_ref,
                security_groups=security_groups,
                availability_zone=availability_zone,
                nics=nics, config_drive=config_drive,
                userdata=userdata)
            LOG.debug("Created new compute instance %(server_id)s "
                      "for id: %(id)s" %
                      {'server_id': server.id, 'id': self.id})

            server_dict = server._info
            LOG.debug("Server response: %s" % server_dict)
            volume_id = None
            for volume in server_dict.get('os:volumes', []):
                volume_id = volume.get('id')

            # Record the server ID and volume ID in case something goes wrong.
            self.update_db(compute_instance_id=server.id, volume_id=volume_id)
        except Exception as e:
            msg = _("Error creating server and volume for "
                    "instance %s") % self.id
            LOG.debug("End _create_server_volume for id: %s" % self.id)
            err = inst_models.InstanceTasks.BUILDING_ERROR_SERVER
            self._log_and_raise(e, msg, err)

        device_path = self.device_path
        mount_point = CONF.get(datastore_manager).mount_point
        volume_info = {'device_path': device_path, 'mount_point': mount_point}
        LOG.debug("End _create_server_volume for id: %s" % self.id)
        return volume_info

    def _build_sg_rules_mapping(self, rule_ports):
        final = []
        cidr = CONF.trove_security_group_rule_cidr
        for port_or_range in set(rule_ports):
            from_, to_ = utils.gen_ports(port_or_range)
            final.append({'cidr': cidr,
                          'from_': str(from_),
                          'to_': str(to_)})
        return final

    def _create_server_volume_heat(self, flavor, image_id,
                                   datastore_manager, volume_size,
                                   availability_zone, nics, files):
        LOG.debug("Begin _create_server_volume_heat for id: %s" % self.id)
        try:
            client = create_heat_client(self.context)
            tcp_rules_mapping_list = self._build_sg_rules_mapping(CONF.get(
                datastore_manager).tcp_ports)
            udp_ports_mapping_list = self._build_sg_rules_mapping(CONF.get(
                datastore_manager).udp_ports)

            ifaces, ports = self._build_heat_nics(nics)
            template_obj = template.load_heat_template(datastore_manager)
            heat_template_unicode = template_obj.render(
                volume_support=self.volume_support,
                ifaces=ifaces, ports=ports,
                tcp_rules=tcp_rules_mapping_list,
                udp_rules=udp_ports_mapping_list,
                datastore_manager=datastore_manager,
                files=files)
            try:
                heat_template = heat_template_unicode.encode('utf-8')
            except UnicodeEncodeError:
                raise TroveError("Failed to utf-8 encode Heat template.")

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
                raise TroveError("Failed to obtain Heat stack status. "
                                 "Timeout occurred.")

            stack = client.stacks.get(stack_name)
            if ((stack.action, stack.stack_status)
                    not in HEAT_STACK_SUCCESSFUL_STATUSES):
                raise TroveError("Failed to create Heat stack.")

            resource = client.resources.get(stack.id, 'BaseInstance')
            if resource.resource_status != HEAT_RESOURCE_SUCCESSFUL_STATE:
                raise TroveError("Failed to provision Heat base instance.")
            instance_id = resource.physical_resource_id

            if self.volume_support:
                resource = client.resources.get(stack.id, 'DataVolume')
                if resource.resource_status != HEAT_RESOURCE_SUCCESSFUL_STATE:
                    raise TroveError("Failed to provision Heat data volume.")
                volume_id = resource.physical_resource_id
                self.update_db(compute_instance_id=instance_id,
                               volume_id=volume_id)
            else:
                self.update_db(compute_instance_id=instance_id)

            if CONF.trove_security_groups_support:
                resource = client.resources.get(stack.id, 'DatastoreSG')
                name = "%s_%s" % (
                    CONF.trove_security_group_name_prefix, self.id)
                description = _("Security Group for %s") % self.id
                SecurityGroup.create(
                    id=resource.physical_resource_id,
                    name=name, description=description,
                    user=self.context.user,
                    tenant_id=self.context.tenant)
                SecurityGroupInstanceAssociation.create(
                    security_group_id=resource.physical_resource_id,
                    instance_id=self.id)

        except (TroveError, heat_exceptions.HTTPNotFound,
                heat_exceptions.HTTPException) as e:
            msg = _("Error occurred during Heat stack creation for "
                    "instance %s.") % self.id
            err = inst_models.InstanceTasks.BUILDING_ERROR_SERVER
            self._log_and_raise(e, msg, err)

        device_path = self.device_path
        mount_point = CONF.get(datastore_manager).mount_point
        volume_info = {'device_path': device_path, 'mount_point': mount_point}

        LOG.debug("End _create_server_volume_heat for id: %s" % self.id)
        return volume_info

    def _create_server_volume_individually(self, flavor_id, image_id,
                                           security_groups, datastore_manager,
                                           volume_size, availability_zone,
                                           nics, files):
        LOG.debug("Begin _create_server_volume_individually for id: %s" %
                  self.id)
        server = None
        volume_info = self._build_volume_info(datastore_manager,
                                              volume_size=volume_size)
        block_device_mapping = volume_info['block_device']
        try:
            server = self._create_server(flavor_id, image_id, security_groups,
                                         datastore_manager,
                                         block_device_mapping,
                                         availability_zone, nics, files)
            server_id = server.id
            # Save server ID.
            self.update_db(compute_instance_id=server_id)
        except Exception as e:
            msg = _("Failed to create server for instance %s") % self.id
            err = inst_models.InstanceTasks.BUILDING_ERROR_SERVER
            self._log_and_raise(e, msg, err)
        LOG.debug("End _create_server_volume_individually for id: %s" %
                  self.id)
        return volume_info

    def _build_volume_info(self, datastore_manager, volume_size=None):
        volume_info = None
        volume_support = self.volume_support
        device_path = self.device_path
        mount_point = CONF.get(datastore_manager).mount_point
        LOG.debug("trove volume support = %s" % volume_support)
        if volume_support:
            try:
                volume_info = self._create_volume(
                    volume_size, datastore_manager)
            except Exception as e:
                msg = _("Failed to create volume for instance %s") % self.id
                err = inst_models.InstanceTasks.BUILDING_ERROR_VOLUME
                self._log_and_raise(e, msg, err)
        else:
            LOG.debug("device_path = %s" % device_path)
            LOG.debug("mount_point = %s" % mount_point)
            volume_info = {
                'block_device': None,
                'device_path': device_path,
                'mount_point': mount_point,
                'volumes': None,
            }
        return volume_info

    def _log_and_raise(self, exc, message, task_status):
        LOG.error(message)
        LOG.error(exc)
        LOG.error(traceback.format_exc())
        self.update_db(task_status=task_status)
        raise TroveError(message=message)

    def _create_volume(self, volume_size, datastore_manager):
        LOG.debug("Begin _create_volume for id: %s" % self.id)
        volume_client = create_cinder_client(self.context)
        volume_desc = ("datastore volume for %s" % self.id)
        volume_ref = volume_client.volumes.create(
            volume_size, name="datastore-%s" % self.id,
            description=volume_desc, volume_type=CONF.cinder_volume_type)

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
        LOG.debug("End _create_volume for id: %s" % self.id)
        return self._build_volume(v_ref, datastore_manager)

    def _build_volume(self, v_ref, datastore_manager):
        LOG.debug("Created volume %s" % v_ref)
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

        device_path = self.device_path
        mount_point = CONF.get(datastore_manager).mount_point
        LOG.debug("device_path = %s" % device_path)
        LOG.debug("mount_point = %s" % mount_point)

        volume_info = {'block_device': block_device,
                       'device_path': device_path,
                       'mount_point': mount_point,
                       'volumes': created_volumes}
        return volume_info

    def _prepare_userdata(self, datastore_manager):
        userdata = None
        cloudinit = os.path.join(CONF.get('cloudinit_location'),
                                 "%s.cloudinit" % datastore_manager)
        if os.path.isfile(cloudinit):
            with open(cloudinit, "r") as f:
                userdata = f.read()
        return userdata

    def _create_server(self, flavor_id, image_id, security_groups,
                       datastore_manager, block_device_mapping,
                       availability_zone, nics, files={}):
        userdata = self._prepare_userdata(datastore_manager)
        name = self.hostname or self.name
        bdmap = block_device_mapping
        config_drive = CONF.use_nova_server_config_drive

        server = self.nova_client.servers.create(
            name, image_id, flavor_id, files=files, userdata=userdata,
            security_groups=security_groups, block_device_mapping=bdmap,
            availability_zone=availability_zone, nics=nics,
            config_drive=config_drive)
        LOG.debug("Created new compute instance %(server_id)s "
                  "for instance %(id)s" %
                  {'server_id': server.id, 'id': self.id})
        return server

    def _guest_prepare(self, flavor_ram, volume_info,
                       packages, databases, users, backup_info=None,
                       config_contents=None, root_password=None,
                       overrides=None, cluster_config=None, snapshot=None):
        LOG.debug("Entering guest_prepare")
        # Now wait for the response from the create to do additional work
        self.guest.prepare(flavor_ram, packages, databases, users,
                           device_path=volume_info['device_path'],
                           mount_point=volume_info['mount_point'],
                           backup_info=backup_info,
                           config_contents=config_contents,
                           root_password=root_password,
                           overrides=overrides,
                           cluster_config=cluster_config,
                           snapshot=snapshot)

    def _create_dns_entry(self):
        dns_support = CONF.trove_dns_support
        LOG.debug("trove dns support = %s" % dns_support)

        if dns_support:
            LOG.debug("%(gt)s: Creating dns entry for instance: %(id)s" %
                      {'gt': greenthread.getcurrent(), 'id': self.id})
            dns_client = create_dns_client(self.context)

            def get_server():
                c_id = self.db_info.compute_instance_id
                return self.nova_client.servers.get(c_id)

            def ip_is_available(server):
                LOG.debug("Polling for ip addresses: $%s " % server.addresses)
                if server.addresses != {}:
                    return True
                elif (server.addresses == {} and
                      server.status != InstanceStatus.ERROR):
                    return False
                elif (server.addresses == {} and
                      server.status == InstanceStatus.ERROR):
                    LOG.error(_("Failed to create DNS entry for instance "
                                "%(instance)s. Server status was "
                                "%(status)s).") %
                              {'instance': self.id, 'status': server.status})
                    raise TroveError(status=server.status)

            utils.poll_until(get_server, ip_is_available,
                             sleep_time=1, time_out=DNS_TIME_OUT)
            server = self.nova_client.servers.get(
                self.db_info.compute_instance_id)
            self.db_info.addresses = server.addresses
            LOG.debug(_("Creating dns entry..."))
            ip = self.dns_ip_address
            if not ip:
                raise TroveError("Failed to create DNS entry for instance %s. "
                                 "No IP available." % self.id)
            dns_client.create_instance_entry(self.id, ip)
        else:
            LOG.debug("%(gt)s: DNS not enabled for instance: %(id)s" %
                      {'gt': greenthread.getcurrent(), 'id': self.id})

    def _create_secgroup(self, datastore_manager):
        security_group = SecurityGroup.create_for_instance(
            self.id, self.context)
        tcp_ports = CONF.get(datastore_manager).tcp_ports
        udp_ports = CONF.get(datastore_manager).udp_ports
        self._create_rules(security_group, tcp_ports, 'tcp')
        self._create_rules(security_group, udp_ports, 'udp')
        return [security_group["name"]]

    def _create_rules(self, s_group, ports, protocol):
        err = inst_models.InstanceTasks.BUILDING_ERROR_SEC_GROUP
        err_msg = _("Failed to create security group rules for instance "
                    "%(instance_id)s: Invalid port format - "
                    "FromPort = %(from)s, ToPort = %(to)s")

        def set_error_and_raise(port_or_range):
            from_port, to_port = port_or_range
            self.update_db(task_status=err)
            msg = err_msg % {'instance_id': self.id, 'from': from_port,
                             'to': to_port}
            raise MalformedSecurityGroupRuleError(message=msg)

        for port_or_range in set(ports):
            try:
                from_, to_ = (None, None)
                from_, to_ = utils.gen_ports(port_or_range)
                cidr = CONF.trove_security_group_rule_cidr
                SecurityGroupRule.create_sec_group_rule(
                    s_group, protocol, int(from_), int(to_),
                    cidr, self.context)
            except (ValueError, TroveError):
                set_error_and_raise([from_, to_])

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
        LOG.debug("Begin _delete_resources for instance %s" % self.id)
        server_id = self.db_info.compute_instance_id
        old_server = self.nova_client.servers.get(server_id)
        LOG.debug("Stopping datastore on instance %s before deleting any "
                  "resources." % self.id)
        try:
            self.guest.stop_db()
        except Exception:
            LOG.exception(_("Error stopping the datastore before attempting "
                            "to delete instance id %s.") % self.id)
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
            LOG.debug("trove dns support = %s" % dns_support)
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
                if not self.server_status_matches(['SHUTDOWN', 'ACTIVE'],
                                                  server=server):
                    LOG.error(_("Server %(server_id)s entered ERROR status "
                                "when deleting instance %(instance_id)s!") %
                              {'server_id': server.id, 'instance_id': self.id})
                return False
            except nova_exceptions.NotFound:
                return True

        try:
            utils.poll_until(server_is_finished, sleep_time=2,
                             time_out=CONF.server_delete_time_out)
        except PollTimeOut:
            LOG.exception(_("Failed to delete instance %(instance_id)s: "
                            "Timeout deleting compute server %(server_id)s") %
                          {'instance_id': self.id, 'server_id': server_id})

        # If volume has been resized it must be manually removed in cinder
        try:
            if self.volume_id:
                volume_client = create_cinder_client(self.context)
                volume = volume_client.volumes.get(self.volume_id)
                if volume.status == "available":
                    LOG.info(_("Deleting volume %(v)s for instance: %(i)s.")
                             % {'v': self.volume_id, 'i': self.id})
                    volume.delete()
        except Exception:
            LOG.exception(_("Error deleting volume of instance %(id)s.") %
                          {'id': self.db_info.id})

        self.send_usage_event('delete',
                              deleted_at=timeutils.isotime(deleted_at),
                              server=old_server)
        LOG.debug("End _delete_resources for instance %s" % self.id)

    def server_status_matches(self, expected_status, server=None):
        if not server:
            server = self.server
        return server.status.upper() in (
            status.upper() for status in expected_status)

    def resize_volume(self, new_size):
        LOG.info(_("Resizing volume for instance %(instance_id)s from "
                 "%(old_size)s GB to %(new_size)s GB.") %
                 {'instance_id': self.id, 'old_size': self.volume_size,
                  'new_size': new_size})
        action = ResizeVolumeAction(self, self.volume_size, new_size)
        action.execute()
        LOG.info(_("Resized volume for instance %s successfully.") % self.id)

    def resize_flavor(self, old_flavor, new_flavor):
        LOG.info(_("Resizing instance %(instance_id)s from flavor "
                   "%(old_flavor)s to %(new_flavor)s.") %
                 {'instance_id': self.id, 'old_flavor': old_flavor['id'],
                  'new_flavor': new_flavor['id']})
        action = ResizeAction(self, old_flavor, new_flavor)
        action.execute()
        LOG.info(_("Resized instance %s successfully.") % self.id)

    def migrate(self, host):
        LOG.info(_("Initiating migration to host %s.") % host)
        action = MigrateAction(self, host)
        action.execute()

    def create_backup(self, backup_info):
        LOG.info(_("Initiating backup for instance %s.") % self.id)
        self.guest.create_backup(backup_info)

    def get_replication_snapshot(self, snapshot_info, flavor):

        def _get_replication_snapshot():
            LOG.debug("Calling get_replication_snapshot on %s.", self.id)
            try:
                rep_source_config = self._render_replica_source_config(flavor)
                result = self.guest.get_replication_snapshot(
                    snapshot_info, rep_source_config.config_contents)
                LOG.debug("Got replication snapshot from guest successfully.")
                return result
            except Exception:
                LOG.exception(_("Failed to get replication snapshot from %s.")
                              % self.id)
                raise

        return run_with_quotas(self.context.tenant, {'backups': 1},
                               _get_replication_snapshot)

    def detach_replica(self, master, for_failover=False):
        LOG.debug("Calling detach_replica on %s" % self.id)
        try:
            self.guest.detach_replica(for_failover)
            self.update_db(slave_of_id=None)
            self.slave_list = None
        except (GuestError, GuestTimeout):
            LOG.exception(_("Failed to detach replica %s.") % self.id)
            raise

    def attach_replica(self, master):
        LOG.debug("Calling attach_replica on %s" % self.id)
        try:
            replica_info = master.guest.get_replica_context()
            flavor = self.nova_client.flavors.get(self.flavor_id)
            slave_config = self._render_replica_config(flavor).config_contents
            self.guest.attach_replica(replica_info, slave_config)
            self.update_db(slave_of_id=master.id)
            self.slave_list = None
        except (GuestError, GuestTimeout):
            LOG.exception(_("Failed to attach replica %s.") % self.id)
            raise

    def make_read_only(self, read_only):
        LOG.debug("Calling make_read_only on %s" % self.id)
        self.guest.make_read_only(read_only)

    def _get_floating_ips(self):
        """Returns floating ips as a dict indexed by the ip."""
        floating_ips = {}
        for ip in self.nova_client.floating_ips.list():
            floating_ips.update({ip.ip: ip})
        return floating_ips

    def detach_public_ips(self):
        LOG.debug("Begin detach_public_ips for instance %s" % self.id)
        removed_ips = []
        server_id = self.db_info.compute_instance_id
        nova_instance = self.nova_client.servers.get(server_id)
        floating_ips = self._get_floating_ips()
        for ip in self.get_visible_ip_addresses():
            if ip in floating_ips:
                nova_instance.remove_floating_ip(ip)
                removed_ips.append(ip)
        return removed_ips

    def attach_public_ips(self, ips):
        LOG.debug("Begin attach_public_ips for instance %s" % self.id)
        server_id = self.db_info.compute_instance_id
        nova_instance = self.nova_client.servers.get(server_id)
        for ip in ips:
            nova_instance.add_floating_ip(ip)

    def enable_as_master(self):
        LOG.debug("Calling enable_as_master on %s" % self.id)
        flavor = self.nova_client.flavors.get(self.flavor_id)
        replica_source_config = self._render_replica_source_config(flavor)
        self.update_db(slave_of_id=None)
        self.slave_list = None
        self.guest.enable_as_master(replica_source_config.config_contents)

    def get_last_txn(self):
        LOG.debug("Calling get_last_txn on %s" % self.id)
        return self.guest.get_last_txn()

    def get_latest_txn_id(self):
        LOG.debug("Calling get_latest_txn_id on %s" % self.id)
        return self.guest.get_latest_txn_id()

    def wait_for_txn(self, txn):
        LOG.debug("Calling wait_for_txn on %s" % self.id)
        if txn:
            self.guest.wait_for_txn(txn)

    def switch_master(self, new_master):
        LOG.debug("calling switch_master on %s" % self.id)

        self.guest.switch_master(new_master)
        self.update_db(slave_of_id=new_master.id)
        self.slave_list = None

    def cleanup_source_on_replica_detach(self, replica_info):
        LOG.debug("Calling cleanup_source_on_replica_detach on %s" % self.id)
        self.guest.cleanup_source_on_replica_detach(replica_info)

    def demote_replication_master(self):
        LOG.debug("Calling demote_replication_master on %s" % self.id)
        self.guest.demote_replication_master()

    def reboot(self):
        try:
            # Issue a guest stop db call to shutdown the db if running
            LOG.debug("Stopping datastore on instance %s." % self.id)
            try:
                self.guest.stop_db()
            except (exception.GuestError, exception.GuestTimeout) as e:
                # Acceptable to be here if db was already in crashed state
                # Also we check guest state before issuing reboot
                LOG.debug(str(e))

            self._refresh_datastore_status()
            if not (self.datastore_status_matches(
                    rd_instance.ServiceStatuses.SHUTDOWN) or
                    self.datastore_status_matches(
                    rd_instance.ServiceStatuses.CRASHED)):
                # We will bail if db did not get stopped or is blocked
                LOG.error(_("Cannot reboot instance. DB status is %s.")
                          % self.datastore_status.status)
                return
            LOG.debug("The guest service status is %s."
                      % self.datastore_status.status)

            LOG.info(_("Rebooting instance %s.") % self.id)
            self.server.reboot()
            # Poll nova until instance is active
            reboot_time_out = CONF.reboot_time_out

            def update_server_info():
                self.refresh_compute_server_info()
                return self.server_status_matches(['ACTIVE'])

            utils.poll_until(
                update_server_info,
                sleep_time=2,
                time_out=reboot_time_out)

            # Set the status to PAUSED. The guest agent will reset the status
            # when the reboot completes and MySQL is running.
            self.set_datastore_status_to_paused()
            LOG.info(_("Rebooted instance %s successfully.") % self.id)
        except Exception as e:
            LOG.error(_("Failed to reboot instance %(id)s: %(e)s") %
                      {'id': self.id, 'e': str(e)})
        finally:
            LOG.debug("Rebooting FINALLY %s" % self.id)
            self.reset_task_status()

    def restart(self):
        LOG.info(_("Initiating datastore restart on instance %s.") % self.id)
        try:
            self.guest.restart()
        except GuestError:
            LOG.error(_("Failed to initiate datastore restart on instance "
                        "%s.") % self.id)
        finally:
            self.reset_task_status()

    def update_overrides(self, overrides, remove=False):
        LOG.info(_("Initiating datastore configurations update on instance "
                   "%s.") % self.id)
        LOG.debug("overrides: %s" % overrides)
        LOG.debug("self.ds_version: %s" % self.ds_version.__dict__)

        flavor = self.nova_client.flavors.get(self.flavor_id)
        config_overrides = self._render_override_config(
            flavor,
            overrides=overrides)
        try:
            self.guest.update_overrides(config_overrides.config_contents,
                                        remove=remove)
            self.guest.apply_overrides(overrides)
        except GuestError:
            LOG.error(_("Failed to initiate datastore configurations update "
                      "on instance %s.") % self.id)

    def unassign_configuration(self, flavor, configuration_id):
        LOG.info(_("Initiating configuration group %(config_id)s removal from "
                 "instance %(instance_id)s.")
                 % {'config_id': configuration_id,
                    'instance_id': self.id})

        def _find_item(items, item_name):
            LOG.debug("Searching for %(item_name)s in %(items)s" %
                      {'item_name': item_name, 'items': items})
            # find the item in the list
            for i in items:
                if i[0] == item_name:
                    return i

        def _convert_value(value):
            # split the value and the size e.g. 512M=['512','M']
            pattern = re.compile('(\d+)(\w+)')
            split = pattern.findall(value)
            if len(split) < 2:
                return value
            digits, size = split
            conversions = {
                'K': 1024,
                'M': 1024 ** 2,
                'G': 1024 ** 3,
            }
            return str(int(digits) * conversions[size])

        default_config = self._render_config_dict(flavor)
        args = {
            "ds_manager": self.ds_version.manager,
            "config": default_config,
        }
        LOG.debug("default %(ds_manager)s section: %(config)s" % args)
        LOG.debug("self.configuration: %s" % self.configuration.__dict__)

        overrides = {}
        config_items = Configuration.load_items(self.context, configuration_id)
        for item in config_items:
            LOG.debug("finding item(%s)" % item.__dict__)
            try:
                key, val = _find_item(default_config, item.configuration_key)
            except TypeError:
                val = None
                restart_required = inst_models.InstanceTasks.RESTART_REQUIRED
                self.update_db(task_status=restart_required)
            if val:
                overrides[item.configuration_key] = _convert_value(val)
        LOG.debug("setting the default variables in dict: %s" % overrides)
        self.update_db(configuration_id=None)
        self.update_overrides(overrides, remove=True)

    def refresh_compute_server_info(self):
        """Refreshes the compute server field."""
        server = self.nova_client.servers.get(self.server.id)
        self.server = server

    def _refresh_datastore_status(self):
        """
        Gets the latest instance service status from datastore and updates
        the reference on this BuiltInstanceTask reference
        """
        self.datastore_status = InstanceServiceStatus.find_by(
            instance_id=self.id)

    def set_datastore_status_to_paused(self):
        """
        Updates the InstanceServiceStatus for this BuiltInstance to PAUSED.
        This does not change the reference for this BuiltInstanceTask
        """
        datastore_status = InstanceServiceStatus.find_by(instance_id=self.id)
        datastore_status.status = rd_instance.ServiceStatuses.PAUSED
        datastore_status.save()


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
            LOG.debug("Deleting files with prefix: %(cont)s/%(prefix)s" %
                      {'cont': cont, 'prefix': prefix})
            # list files from container/prefix specified by manifest
            headers, segments = client.get_container(cont, prefix=prefix)
            LOG.debug(headers)
            for segment in segments:
                name = segment.get('name')
                if name:
                    LOG.debug("Deleting file: %(cont)s/%(name)s" %
                              {'cont': cont, 'name': name})
                    client.delete_object(cont, name)
        # Delete the manifest file
        LOG.debug("Deleting file: %(cont)s/%(filename)s" %
                  {'cont': cont, 'filename': filename})
        client.delete_object(container, filename)

    @classmethod
    def delete_backup(cls, context, backup_id):
        #delete backup from swift
        LOG.info(_("Deleting backup %s.") % backup_id)
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
                LOG.exception(_("Error occurred when deleting from swift. "
                                "Details: %s") % e)
                backup.state = bkup_models.BackupState.DELETE_FAILED
                backup.save()
                raise TroveError("Failed to delete swift object for backup %s."
                                 % backup_id)
        else:
            backup.delete()
        LOG.info(_("Deleted backup %s successfully.") % backup_id)


class ResizeVolumeAction(object):
    """Performs volume resize action."""

    def __init__(self, instance, old_size, new_size):
        self.instance = instance
        self.old_size = int(old_size)
        self.new_size = int(new_size)

    def get_mount_point(self):
        mount_point = CONF.get(
            self.instance.datastore_version.manager).mount_point
        return mount_point

    def get_device_path(self):
        return self.instance.device_path

    def _fail(self, orig_func):
        LOG.exception(_("%(func)s encountered an error when attempting to "
                      "resize the volume for instance %(id)s. Setting service "
                      "status to failed.") % {'func': orig_func.__name__,
                      'id': self.instance.id})
        service = InstanceServiceStatus.find_by(instance_id=self.instance.id)
        service.set_status(ServiceStatuses.FAILED)
        service.save()

    def _recover_restart(self, orig_func):
        LOG.exception(_("%(func)s encountered an error when attempting to "
                      "resize the volume for instance %(id)s. Trying to "
                      "recover by restarting the guest.") % {
                      'func': orig_func.__name__,
                      'id': self.instance.id})
        self.instance.restart()

    def _recover_mount_restart(self, orig_func):
        LOG.exception(_("%(func)s encountered an error when attempting to "
                      "resize the volume for instance %(id)s. Trying to "
                      "recover by mounting the volume and then restarting the "
                      "guest.") % {'func': orig_func.__name__,
                      'id': self.instance.id})
        self._mount_volume()
        self.instance.restart()

    def _recover_full(self, orig_func):
        LOG.exception(_("%(func)s encountered an error when attempting to "
                      "resize the volume for instance %(id)s. Trying to "
                      "recover by attaching and mounting the volume and then "
                      "restarting the guest.") % {'func': orig_func.__name__,
                      'id': self.instance.id})
        self._attach_volume()
        self._mount_volume()
        self.instance.restart()

    def _stop_db(self):
        LOG.debug("Instance %s calling stop_db." % self.instance.id)
        self.instance.guest.stop_db()

    @try_recover
    def _unmount_volume(self):
        LOG.debug("Unmounting the volume on instance %(id)s" % {
                  'id': self.instance.id})
        mount_point = self.get_mount_point()
        device_path = self.get_device_path()
        self.instance.guest.unmount_volume(device_path=device_path,
                                           mount_point=mount_point)
        LOG.debug("Successfully unmounted the volume %(vol_id)s for "
                  "instance %(id)s" % {'vol_id': self.instance.volume_id,
                  'id': self.instance.id})

    @try_recover
    def _detach_volume(self):
        LOG.debug("Detach volume %(vol_id)s from instance %(id)s" % {
                  'vol_id': self.instance.volume_id,
                  'id': self.instance.id})
        self.instance.nova_client.volumes.delete_server_volume(
            self.instance.server.id, self.instance.volume_id)

        def volume_available():
            volume = self.instance.volume_client.volumes.get(
                self.instance.volume_id)
            return volume.status == 'available'
        utils.poll_until(volume_available,
                         sleep_time=2,
                         time_out=CONF.volume_time_out)

        LOG.debug("Successfully detached volume %(vol_id)s from instance "
                  "%(id)s" % {'vol_id': self.instance.volume_id,
                              'id': self.instance.id})

    @try_recover
    def _attach_volume(self):
        device_path = self.get_device_path()
        LOG.debug("Attach volume %(vol_id)s to instance %(id)s at "
                  "%(dev)s" % {'vol_id': self.instance.volume_id,
                  'id': self.instance.id, 'dev': device_path})
        self.instance.nova_client.volumes.create_server_volume(
            self.instance.server.id, self.instance.volume_id, device_path)

        def volume_in_use():
            volume = self.instance.volume_client.volumes.get(
                self.instance.volume_id)
            return volume.status == 'in-use'
        utils.poll_until(volume_in_use,
                         sleep_time=2,
                         time_out=CONF.volume_time_out)

        LOG.debug("Successfully attached volume %(vol_id)s to instance "
                  "%(id)s" % {'vol_id': self.instance.volume_id,
                  'id': self.instance.id})

    @try_recover
    def _resize_fs(self):
        LOG.debug("Resizing the filesystem for instance %(id)s" % {
                  'id': self.instance.id})
        mount_point = self.get_mount_point()
        device_path = self.get_device_path()
        self.instance.guest.resize_fs(device_path=device_path,
                                      mount_point=mount_point)
        LOG.debug("Successfully resized volume %(vol_id)s filesystem for "
                  "instance %(id)s" % {'vol_id': self.instance.volume_id,
                  'id': self.instance.id})

    @try_recover
    def _mount_volume(self):
        LOG.debug("Mount the volume on instance %(id)s" % {
                  'id': self.instance.id})
        mount_point = self.get_mount_point()
        device_path = self.get_device_path()
        self.instance.guest.mount_volume(device_path=device_path,
                                         mount_point=mount_point)
        LOG.debug("Successfully mounted the volume %(vol_id)s on instance "
                  "%(id)s" % {'vol_id': self.instance.volume_id,
                  'id': self.instance.id})

    @try_recover
    def _extend(self):
        LOG.debug("Extending volume %(vol_id)s for instance %(id)s to "
                  "size %(size)s" % {'vol_id': self.instance.volume_id,
                  'id': self.instance.id, 'size': self.new_size})
        self.instance.volume_client.volumes.extend(self.instance.volume_id,
                                                   self.new_size)
        LOG.debug("Successfully extended the volume %(vol_id)s for instance "
                  "%(id)s" % {'vol_id': self.instance.volume_id,
                  'id': self.instance.id})

    def _verify_extend(self):
        try:
            volume = self.instance.volume_client.volumes.get(
                self.instance.volume_id)
            if not volume:
                msg = (_('Failed to get volume %(vol_id)s') % {
                       'vol_id': self.instance.volume_id})
                raise cinder_exceptions.ClientException(msg)

            def volume_is_new_size():
                volume = self.instance.volume_client.volumes.get(
                    self.instance.volume_id)
                return volume.size == self.new_size
            utils.poll_until(volume_is_new_size,
                             sleep_time=2,
                             time_out=CONF.volume_time_out)

            self.instance.update_db(volume_size=self.new_size)
        except PollTimeOut:
            LOG.exception(_("Timeout trying to extend the volume %(vol_id)s "
                          "for instance %(id)s") % {
                          'vol_id': self.instance.volume_id,
                          'id': self.instance.id})
            volume = self.instance.volume_client.volumes.get(
                self.instance.volume_id)
            if volume.status == 'extending':
                self._fail(self._verify_extend)
            elif volume.size != self.new_size:
                self.instance.update_db(volume_size=volume.size)
                self._recover_full(self._verify_extend)
            raise
        except Exception:
            LOG.exception(_("Error encountered trying to verify extend for "
                          "the volume %(vol_id)s for instance %(id)s") % {
                          'vol_id': self.instance.volume_id,
                          'id': self.instance.id})
            self._recover_full(self._verify_extend)
            raise

    def _resize_active_volume(self):
        LOG.debug("Begin _resize_active_volume for id: %(id)s" % {
                  'id': self.instance.id})
        self._stop_db()
        self._unmount_volume(recover_func=self._recover_restart)
        self._detach_volume(recover_func=self._recover_mount_restart)
        self._extend(recover_func=self._recover_full)
        self._verify_extend()
        # if anything fails after this point, recovery is futile
        self._attach_volume(recover_func=self._fail)
        self._resize_fs(recover_func=self._fail)
        self._mount_volume(recover_func=self._fail)
        self.instance.restart()
        LOG.debug("End _resize_active_volume for id: %(id)s" % {
                  'id': self.instance.id})

    def execute(self):
        LOG.debug("%(gt)s: Resizing instance %(id)s volume for server "
                  "%(server_id)s from %(old_volume_size)s to "
                  "%(new_size)r GB" % {'gt': greenthread.getcurrent(),
                  'id': self.instance.id,
                  'server_id': self.instance.server.id,
                  'old_volume_size': self.old_size,
                  'new_size': self.new_size})

        if self.instance.server.status == InstanceStatus.ACTIVE:
            self._resize_active_volume()
            self.instance.reset_task_status()
            # send usage event for size reported by cinder
            volume = self.instance.volume_client.volumes.get(
                self.instance.volume_id)
            launched_time = timeutils.isotime(self.instance.updated)
            modified_time = timeutils.isotime(self.instance.updated)
            self.instance.send_usage_event('modify_volume',
                                           old_volume_size=self.old_size,
                                           launched_at=launched_time,
                                           modify_at=modified_time,
                                           volume_size=volume.size)
        else:
            self.instance.reset_task_status()
            msg = _("Failed to resize instance %(id)s volume for server "
                    "%(server_id)s. The instance must be in state %(state)s "
                    "not %(inst_state)s.") % {
                        'id': self.instance.id,
                        'server_id': self.instance.server.id,
                        'state': InstanceStatus.ACTIVE,
                        'inst_state': self.instance.server.status}
            raise TroveError(msg)


class ResizeActionBase(object):
    """Base class for executing a resize action."""

    def __init__(self, instance):
        """
        Creates a new resize action for a given instance
        :param instance: reference to existing instance that will be resized
        :type instance: trove.taskmanager.models.BuiltInstanceTasks
        """
        self.instance = instance

    def _assert_guest_is_ok(self):
        # The guest will never set the status to PAUSED.
        self.instance.set_datastore_status_to_paused()
        # Now we wait until it sets it to anything at all,
        # so we know it's alive.
        utils.poll_until(
            self._guest_is_awake,
            sleep_time=2,
            time_out=RESIZE_TIME_OUT)

    def _assert_nova_status_is_ok(self):
        # Make sure Nova thinks things went well.
        if not self.instance.server_status_matches(["VERIFY_RESIZE"]):
            msg = "Migration failed! status=%(act_status)s and " \
                  "not %(exp_status)s" % {
                      "act_status": self.instance.server.status,
                      "exp_status": 'VERIFY_RESIZE'}
            raise TroveError(msg)

    def _assert_datastore_is_ok(self):
        # Tell the guest to turn on datastore, and ensure the status becomes
        # RUNNING.
        self._start_datastore()
        utils.poll_until(
            self._datastore_is_online,
            sleep_time=2,
            time_out=RESIZE_TIME_OUT)

    def _assert_datastore_is_offline(self):
        # Tell the guest to turn off MySQL, and ensure the status becomes
        # SHUTDOWN.
        self.instance.guest.stop_db(do_not_start_on_reboot=True)
        utils.poll_until(
            self._datastore_is_offline,
            sleep_time=2,
            time_out=RESIZE_TIME_OUT)

    def _assert_processes_are_ok(self):
        """Checks the procs; if anything is wrong, reverts the operation."""
        # Tell the guest to turn back on, and make sure it can start.
        self._assert_guest_is_ok()
        LOG.debug("Nova guest is ok.")
        self._assert_datastore_is_ok()
        LOG.debug("Datastore is ok.")

    def _confirm_nova_action(self):
        LOG.debug("Instance %s calling Compute confirm resize..."
                  % self.instance.id)
        self.instance.server.confirm_resize()

    def _datastore_is_online(self):
        self.instance._refresh_datastore_status()
        return self.instance.is_datastore_running

    def _datastore_is_offline(self):
        self.instance._refresh_datastore_status()
        return (self.instance.datastore_status_matches(
                rd_instance.ServiceStatuses.SHUTDOWN))

    def _revert_nova_action(self):
        LOG.debug("Instance %s calling Compute revert resize..."
                  % self.instance.id)
        self.instance.server.revert_resize()

    def execute(self):
        """Initiates the action."""
        try:
            LOG.debug("Instance %s calling stop_db..."
                      % self.instance.id)
            self._assert_datastore_is_offline()
            self._perform_nova_action()
        finally:
            if self.instance.db_info.task_status != (
                    inst_models.InstanceTasks.NONE):
                self.instance.reset_task_status()

    def _guest_is_awake(self):
        self.instance._refresh_datastore_status()
        return not self.instance.datastore_status_matches(
            rd_instance.ServiceStatuses.PAUSED)

    def _perform_nova_action(self):
        """Calls Nova to resize or migrate an instance, and confirms."""
        LOG.debug("Begin resize method _perform_nova_action instance: %s" %
                  self.instance.id)
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
            LOG.exception(_("Exception during nova action."))
            if need_to_revert:
                LOG.error(_("Reverting action for instance %s") %
                          self.instance.id)
                self._revert_nova_action()
                self._wait_for_revert_nova_action()

            if self.instance.server_status_matches(['ACTIVE']):
                LOG.error(_("Restarting datastore."))
                self.instance.guest.restart()
            else:
                LOG.error(_("Cannot restart datastore because "
                            "Nova server status is not ACTIVE"))

            LOG.error(_("Error resizing instance %s.") % self.instance.id)
            raise ex

        LOG.debug("Recording success")
        self._record_action_success()
        LOG.debug("End resize method _perform_nova_action instance: %s" %
                  self.instance.id)

    def _wait_for_nova_action(self):
        # Wait for the flavor to change.
        def update_server_info():
            self.instance.refresh_compute_server_info()
            return not self.instance.server_status_matches(['RESIZE'])

        utils.poll_until(
            update_server_info,
            sleep_time=2,
            time_out=RESIZE_TIME_OUT)

    def _wait_for_revert_nova_action(self):
        # Wait for the server to return to ACTIVE after revert.
        def update_server_info():
            self.instance.refresh_compute_server_info()
            return self.instance.server_status_matches(['ACTIVE'])

        utils.poll_until(
            update_server_info,
            sleep_time=2,
            time_out=REVERT_TIME_OUT)


class ResizeAction(ResizeActionBase):
    def __init__(self, instance, old_flavor, new_flavor):
        """
        :type instance: trove.taskmanager.models.BuiltInstanceTasks
        :type old_flavor: dict
        :type new_flavor: dict
        """
        super(ResizeAction, self).__init__(instance)
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
        LOG.debug("Instance %s calling Compute revert resize..."
                  % self.instance.id)
        LOG.debug("Repairing config.")
        try:
            config = self.instance._render_config(self.old_flavor)
            config = {'config_contents': config.config_contents}
            self.instance.guest.reset_configuration(config)
        except GuestTimeout:
            LOG.exception(_("Error sending reset_configuration call."))
        LOG.debug("Reverting resize.")
        super(ResizeAction, self)._revert_nova_action()

    def _record_action_success(self):
        LOG.debug("Updating instance %(id)s to flavor_id %(flavor_id)s."
                  % {'id': self.instance.id, 'flavor_id': self.new_flavor_id})
        self.instance.update_db(flavor_id=self.new_flavor_id,
                                task_status=inst_models.InstanceTasks.NONE)
        self.instance.send_usage_event(
            'modify_flavor',
            old_instance_size=self.old_flavor['ram'],
            instance_size=self.new_flavor['ram'],
            launched_at=timeutils.isotime(self.instance.updated),
            modify_at=timeutils.isotime(self.instance.updated),
            server=self.instance.server)

    def _start_datastore(self):
        config = self.instance._render_config(self.new_flavor)
        self.instance.guest.start_db_with_conf_changes(config.config_contents)


class MigrateAction(ResizeActionBase):
    def __init__(self, instance, host=None):
        super(MigrateAction, self).__init__(instance)
        self.instance = instance
        self.host = host

    def _assert_nova_action_was_successful(self):
        LOG.debug("Currently no assertions for a Migrate Action")

    def _initiate_nova_action(self):
        LOG.debug("Migrating instance %s without flavor change ..."
                  % self.instance.id)
        LOG.debug("Forcing migration to host(%s)" % self.host)
        self.instance.server.migrate(force_host=self.host)

    def _record_action_success(self):
        LOG.debug("Successfully finished Migration to "
                  "%(hostname)s: %(id)s" %
                  {'hostname': self.instance.hostname,
                   'id': self.instance.id})

    def _start_datastore(self):
        self.instance.guest.restart()


def load_cluster_tasks(context, cluster_id):
    manager = Cluster.manager_from_cluster_id(context, cluster_id)
    strat = strategy.load_taskmanager_strategy(manager)
    task_manager_cluster_tasks_class = strat.task_manager_cluster_tasks_class
    return ClusterTasks.load(context, cluster_id,
                             task_manager_cluster_tasks_class)
