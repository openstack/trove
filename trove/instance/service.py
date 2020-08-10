# Copyright 2011 OpenStack Foundation
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

import ipaddress

from oslo_log import log as logging
from oslo_utils import strutils

from trove.backup.models import Backup as backup_model
from trove.backup import views as backup_views
import trove.common.apischema as apischema
from trove.common import cfg
from trove.common import clients
from trove.common import exception
from trove.common.i18n import _
from trove.common import neutron
from trove.common import notification
from trove.common.notification import StartNotification
from trove.common import pagination
from trove.common import policy
from trove.common import utils
from trove.common import wsgi
from trove.datastore import models as ds_models
from trove.extensions.mysql.common import populate_users
from trove.extensions.mysql.common import populate_validated_databases
from trove.instance import models, views
from trove.module import models as module_models
from trove.module import views as module_views

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class InstanceController(wsgi.Controller):
    """Controller for instance functionality."""
    schemas = apischema.instance.copy()

    @classmethod
    def authorize_instance_action(cls, context, instance_rule_name, instance):
        policy.authorize_on_target(context, 'instance:%s' % instance_rule_name,
                                   {'tenant': instance.tenant_id})

    @classmethod
    def get_action_schema(cls, body, action_schema):
        action_type = list(body.keys())[0]
        action_schema = action_schema.get(action_type, {})
        if action_type == 'resize':
            # volume or flavorRef
            resize_action = list(body[action_type].keys())[0]
            action_schema = action_schema.get(resize_action, {})
        return action_schema

    @classmethod
    def get_schema(cls, action, body):
        action_schema = super(InstanceController, cls).get_schema(action, body)
        if action == 'action':
            # resize or restart
            action_schema = cls.get_action_schema(body, action_schema)
        return action_schema

    def action(self, req, body, tenant_id, id):
        """
        Handles requests that modify existing instances in some manner. Actions
        could include 'resize', 'restart'
        :param req: http request object
        :param body: deserialized body of the request as a dict
        :param tenant_id: the tenant id for whom owns the instance
        :param id: instance id
        """
        LOG.debug("instance action req : '%s'\n\n", req)
        if not body:
            raise exception.BadRequest(_("Invalid request body."))
        context = req.environ[wsgi.CONTEXT_KEY]
        _actions = {
            'restart': self._action_restart,
            'resize': self._action_resize,
            'promote_to_replica_source':
                self._action_promote_to_replica_source,
            'eject_replica_source': self._action_eject_replica_source,
            'reset_status': self._action_reset_status,
        }
        selected_action = None
        action_name = None
        for key in body:
            if key in _actions:
                selected_action = _actions[key]
                action_name = key
        LOG.info("Performing %(action_name)s action against "
                 "instance %(instance_id)s for tenant %(tenant_id)s, "
                 "body: %(body)s",
                 {'action_name': action_name, 'instance_id': id,
                  'tenant_id': tenant_id, 'body': body})
        needs_server = True
        if action_name in ['reset_status']:
            needs_server = False
        instance = models.Instance.load(context, id, needs_server=needs_server)
        return selected_action(context, req, instance, body)

    def _action_restart(self, context, req, instance, body):
        context.notification = notification.DBaaSInstanceRestart(context,
                                                                 request=req)
        self.authorize_instance_action(context, 'restart', instance)
        with StartNotification(context, instance_id=instance.id):
            instance.restart()
        return wsgi.Result(None, 202)

    def _action_resize(self, context, req, instance, body):
        """
        Handles 2 cases
        1. resize volume
            body only contains {volume: {size: x}}
        2. resize instance
            body only contains {flavorRef: http.../2}

        If the body has both we will throw back an error.
        """
        options = {
            'volume': self._action_resize_volume,
            'flavorRef': self._action_resize_flavor
        }
        selected_option = None
        args = None
        for key in options:
            if key in body['resize']:
                selected_option = options[key]
                args = body['resize'][key]
                break
        return selected_option(context, req, instance, args)

    def _action_resize_volume(self, context, req, instance, volume):
        context.notification = notification.DBaaSInstanceResizeVolume(
            context, request=req)
        self.authorize_instance_action(context, 'resize_volume', instance)

        with StartNotification(context, instance_id=instance.id,
                               new_size=volume['size']):
            instance.resize_volume(volume['size'])
        return wsgi.Result(None, 202)

    def _action_resize_flavor(self, context, req, instance, flavorRef):
        context.notification = notification.DBaaSInstanceResizeInstance(
            context, request=req)
        self.authorize_instance_action(context, 'resize_flavor', instance)

        new_flavor_id = utils.get_id_from_href(flavorRef)
        with StartNotification(context, instance_id=instance.id,
                               new_flavor_id=new_flavor_id):
            instance.resize_flavor(new_flavor_id)
        return wsgi.Result(None, 202)

    def _action_promote_to_replica_source(self, context, req, instance, body):
        self.authorize_instance_action(
            context, 'promote_to_replica_source', instance)
        context.notification = notification.DBaaSInstanceEject(context,
                                                               request=req)
        with StartNotification(context, instance_id=instance.id):
            instance.promote_to_replica_source()
        return wsgi.Result(None, 202)

    def _action_eject_replica_source(self, context, req, instance, body):
        self.authorize_instance_action(
            context, 'eject_replica_source', instance)
        context.notification = notification.DBaaSInstancePromote(context,
                                                                 request=req)
        with StartNotification(context, instance_id=instance.id):
            instance.eject_replica_source()
        return wsgi.Result(None, 202)

    def _action_reset_status(self, context, req, instance, body):
        if 'force_delete' in body['reset_status']:
            self.authorize_instance_action(context, 'force_delete', instance)
        else:
            self.authorize_instance_action(
                context, 'reset_status', instance)
        context.notification = notification.DBaaSInstanceResetStatus(
            context, request=req)
        with StartNotification(context, instance_id=instance.id):
            instance.reset_status()

            LOG.debug("Failing backups for instance %s.", instance.id)
            backup_model.fail_for_instance(instance.id)

        return wsgi.Result(None, 202)

    def index(self, req, tenant_id):
        """Return all instances."""
        LOG.info("Listing database instances for tenant '%s'", tenant_id)
        LOG.debug("req : '%s'\n\n", req)
        context = req.environ[wsgi.CONTEXT_KEY]
        policy.authorize_on_tenant(context, 'instance:index')
        instances = self._get_instances(req, instance_view=views.InstanceView)
        return wsgi.Result(instances, 200)

    def detail(self, req, tenant_id):
        """Return all instances with details."""
        LOG.info("Listing database instances with details for tenant '%s'",
                 tenant_id)
        LOG.debug("req : '%s'\n\n", req)
        context = req.environ[wsgi.CONTEXT_KEY]
        policy.authorize_on_tenant(context, 'instance:detail')
        instances = self._get_instances(req,
                                        instance_view=views.InstanceDetailView)
        return wsgi.Result(instances, 200)

    def _get_instances(self, req, instance_view):
        context = req.environ[wsgi.CONTEXT_KEY]
        clustered_q = req.GET.get('include_clustered', '').lower()
        include_clustered = clustered_q == 'true'
        instances, marker = models.Instances.load(context, include_clustered)
        view = views.InstancesView(instances,
                                   item_view=instance_view,
                                   req=req)
        paged = pagination.SimplePaginatedDataView(req.url, 'instances', view,
                                                   marker)
        return paged.data()

    def backups(self, req, tenant_id, id):
        """Return all backups for the specified instance."""
        LOG.info("Listing backups for instance '%s'",
                 id)
        LOG.debug("req : '%s'\n\n", req)
        context = req.environ[wsgi.CONTEXT_KEY]

        instance = models.Instance.load(context, id)
        self.authorize_instance_action(context, 'backups', instance)

        backups, marker = backup_model.list_for_instance(context, id)
        view = backup_views.BackupViews(backups)
        paged = pagination.SimplePaginatedDataView(req.url, 'backups', view,
                                                   marker)
        return wsgi.Result(paged.data(), 200)

    def show(self, req, tenant_id, id):
        """Return a single instance."""
        LOG.info("Showing database instance '%(instance_id)s' for tenant "
                 "'%(tenant_id)s'",
                 {'instance_id': id, 'tenant_id': tenant_id})
        LOG.debug("req : '%s'\n\n", req)

        context = req.environ[wsgi.CONTEXT_KEY]
        instance = models.load_instance_with_info(models.DetailInstance,
                                                  context, id)
        self.authorize_instance_action(context, 'show', instance)
        return wsgi.Result(
            views.InstanceDetailView(instance, req=req).data(), 200
        )

    def delete(self, req, tenant_id, id):
        """Delete a single instance."""
        LOG.info("Deleting database instance '%(instance_id)s' for tenant "
                 "'%(tenant_id)s'",
                 {'instance_id': id, 'tenant_id': tenant_id})
        LOG.debug("req : '%s'\n\n", req)
        context = req.environ[wsgi.CONTEXT_KEY]
        instance = models.load_any_instance(context, id)
        self.authorize_instance_action(context, 'delete', instance)
        context.notification = notification.DBaaSInstanceDelete(
            context, request=req)
        with StartNotification(context, instance_id=instance.id):
            marker = 'foo'
            while marker:
                instance_modules, marker = module_models.InstanceModules.load(
                    context, instance_id=id)
                for instance_module in instance_modules:
                    instance_module = module_models.InstanceModule.load(
                        context, instance_module['instance_id'],
                        instance_module['module_id'])
                    module_models.InstanceModule.delete(
                        context, instance_module)
            instance.delete()
        return wsgi.Result(None, 202)

    def _check_nic(self, context, nic):
        """Check user provided nic.

        :param context: User context.
        :param nic: A dict may contain network_id(net-id), subnet_id or
            ip_address.
        """
        neutron_client = clients.create_neutron_client(context)
        network_id = nic.get('network_id', nic.get('net-id'))
        subnet_id = nic.get('subnet_id')
        ip_address = nic.get('ip_address')

        if not network_id and not subnet_id:
            raise exception.NetworkNotProvided(resource='network or subnet')

        if not subnet_id and ip_address:
            raise exception.NetworkNotProvided(resource='subnet')

        if subnet_id:
            actual_network = neutron_client.show_subnet(
                subnet_id)['subnet']['network_id']
            if network_id and actual_network != network_id:
                raise exception.SubnetNotFound(subnet_id=subnet_id,
                                               network_id=network_id)
            network_id = actual_network

        nic['network_id'] = network_id
        nic.pop('net-id', None)

        self._check_network_overlap(context, network_id, subnet_id)

    def _check_network_overlap(self, context, user_network=None,
                               user_subnet=None):
        """Check if the network contains IP address belongs to reserved
        network.

        :param context: User context.
        :param user_network: Network ID.
        :param user_subnet: Subnet ID.
        """
        neutron_client = clients.create_neutron_client(context)
        user_cidrs = neutron.get_subnet_cidrs(neutron_client, user_network,
                                              user_subnet)

        reserved_cidrs = CONF.reserved_network_cidrs
        mgmt_cidrs = neutron.get_mamangement_subnet_cidrs(neutron_client)
        reserved_cidrs.extend(mgmt_cidrs)

        LOG.debug("Cidrs of the user network: %s, cidrs of the reserved "
                  "network: %s", user_cidrs, reserved_cidrs)

        for user_cidr in user_cidrs:
            user_net = ipaddress.ip_network(user_cidr)
            for reserved_cidr in reserved_cidrs:
                res_net = ipaddress.ip_network(reserved_cidr)
                if user_net.overlaps(res_net):
                    raise exception.NetworkConflict()

    def create(self, req, body, tenant_id):
        LOG.info("Creating a database instance for tenant '%s'",
                 tenant_id)
        LOG.debug("req : '%s'\n\n", strutils.mask_password(req))
        LOG.debug("body : '%s'\n\n", strutils.mask_password(body))
        context = req.environ[wsgi.CONTEXT_KEY]
        policy.authorize_on_tenant(context, 'instance:create')
        context.notification = notification.DBaaSInstanceCreate(
            context, request=req)

        name = body['instance']['name']
        slave_of_id = body['instance'].get('replica_of')
        replica_count = body['instance'].get('replica_count')
        flavor_ref = body['instance'].get('flavorRef')
        datastore_args = body['instance'].get('datastore', {})
        volume_info = body['instance'].get('volume', {})
        availability_zone = body['instance'].get('availability_zone')
        nics = body['instance'].get('nics', [])
        locality = body['instance'].get('locality')
        region_name = body['instance'].get(
            'region_name', CONF.service_credentials.region_name
        )
        access = body['instance'].get('access', None)

        if slave_of_id:
            if flavor_ref:
                msg = 'Cannot specify flavor when creating replicas.'
                raise exception.BadRequest(message=msg)
            if datastore_args:
                msg = 'Cannot specify datastore when creating replicas.'
                raise exception.BadRequest(message=msg)
            if volume_info:
                msg = 'Cannot specify volume when creating replicas.'
                raise exception.BadRequest(message=msg)
            if locality:
                msg = 'Cannot specify locality when creating replicas.'
                raise exception.BadRequest(message=msg)
            backup_model.verify_swift_auth_token(context)
        else:
            if replica_count and replica_count > 1:
                msg = (f"Replica count only valid when creating replicas. "
                       f"Cannot create {replica_count} instances.")
                raise exception.BadRequest(message=msg)

        flavor_id = utils.get_id_from_href(flavor_ref)

        if volume_info:
            volume_size = int(volume_info.get('size'))
            volume_type = volume_info.get('type')
        else:
            volume_size = None
            volume_type = None

        if slave_of_id:
            try:
                replica_source = models.DBInstance.find_by(
                    context, id=slave_of_id, deleted=False)
                flavor_id = replica_source.flavor_id
            except exception.ModelNotFoundError:
                LOG.error(f"Cannot create a replica of {slave_of_id} as that "
                          f"instance could not be found.")
                raise exception.NotFound(uuid=slave_of_id)
            if replica_source.slave_of_id:
                raise exception.Forbidden(
                    f"Cannot create a replica of a replica {slave_of_id}")

            datastore_version = ds_models.DatastoreVersion.load_by_uuid(
                replica_source.datastore_version_id)
            datastore = ds_models.Datastore.load(
                datastore_version.datastore_id)
        else:
            datastore, datastore_version = ds_models.get_datastore_version(
                **datastore_args)

        image_id = datastore_version.image_id

        databases = populate_validated_databases(
            body['instance'].get('databases', []))
        database_names = [database.get('_name', '') for database in databases]
        users = None
        try:
            users = populate_users(body['instance'].get('users', []),
                                   database_names)
        except ValueError as ve:
            raise exception.BadRequest(message=ve)
        if slave_of_id and (databases or users):
            raise exception.ReplicaCreateWithUsersDatabasesError()

        configuration = self._configuration_parse(context, body)
        modules = body['instance'].get('modules')

        # The following operations have their own API calls.
        # We need to make sure the same policies are enforced when
        # creating an instance.
        # i.e. if attaching configuration group to an existing instance is not
        # allowed, it should not be possible to create a new instance with the
        # group attached either
        if configuration:
            policy.authorize_on_tenant(context, 'instance:update')
        if modules:
            policy.authorize_on_tenant(context, 'instance:module_apply')
        if users:
            policy.authorize_on_tenant(
                context, 'instance:extension:user:create')
        if databases:
            policy.authorize_on_tenant(
                context, 'instance:extension:database:create')

        if 'restorePoint' in body['instance']:
            backupRef = body['instance']['restorePoint']['backupRef']
            backup_id = utils.get_id_from_href(backupRef)
        else:
            backup_id = None

        # Only 1 nic is allowed as defined in API jsonschema.
        # Use list just for backward compatibility.
        if len(nics) > 0:
            nic = nics[0]
            LOG.info('Checking user provided instance network %s', nic)
            if slave_of_id and nic.get('ip_address'):
                msg = "Cannot specify IP address when creating replicas."
                raise exception.BadRequest(message=msg)
            self._check_nic(context, nic)

        if locality:
            locality_domain = ['affinity', 'anti-affinity']
            locality_domain_msg = ("Invalid locality '%s'. "
                                   "Must be one of ['%s']" %
                                   (locality,
                                    "', '".join(locality_domain)))
            if locality not in locality_domain:
                raise exception.BadRequest(message=locality_domain_msg)

        instance = models.Instance.create(context, name, flavor_id,
                                          image_id, databases, users,
                                          datastore, datastore_version,
                                          volume_size, backup_id,
                                          availability_zone, nics,
                                          configuration, slave_of_id,
                                          replica_count=replica_count,
                                          volume_type=volume_type,
                                          modules=modules,
                                          locality=locality,
                                          region_name=region_name,
                                          access=access)

        view = views.InstanceDetailView(instance, req=req)
        return wsgi.Result(view.data(), 200)

    def _configuration_parse(self, context, body):
        if 'configuration' in body['instance']:
            configuration_ref = body['instance']['configuration']
            if configuration_ref:
                configuration_id = utils.get_id_from_href(configuration_ref)
                return configuration_id

    def _modify_instance(self, context, req, instance, **kwargs):
        if 'detach_replica' in kwargs and kwargs['detach_replica']:
            context.notification = notification.DBaaSInstanceDetach(
                context, request=req)
            with StartNotification(context, instance_id=instance.id):
                instance.detach_replica()
        if 'configuration_id' in kwargs:
            if kwargs['configuration_id']:
                context.notification = (
                    notification.DBaaSInstanceAttachConfiguration(context,
                                                                  request=req))
                configuration_id = kwargs['configuration_id']
                with StartNotification(context, instance_id=instance.id,
                                       configuration_id=configuration_id):
                    instance.attach_configuration(configuration_id)
            else:
                context.notification = (
                    notification.DBaaSInstanceDetachConfiguration(context,
                                                                  request=req))
                with StartNotification(context, instance_id=instance.id):
                    instance.detach_configuration()
        if 'datastore_version' in kwargs:
            datastore_version = ds_models.DatastoreVersion.load(
                instance.datastore, kwargs['datastore_version'])
            context.notification = (
                notification.DBaaSInstanceUpgrade(context, request=req))
            with StartNotification(context, instance_id=instance.id,
                                   datastore_version_id=datastore_version.id):
                instance.upgrade(datastore_version)
        if kwargs:
            instance.update_db(**kwargs)

    def update(self, req, id, body, tenant_id):
        """Updates the instance to attach/detach configuration."""
        LOG.info("Updating database instance '%(instance_id)s' for tenant "
                 "'%(tenant_id)s'",
                 {'instance_id': id, 'tenant_id': tenant_id})
        LOG.debug("req: %s", req)
        LOG.debug("body: %s", body)
        context = req.environ[wsgi.CONTEXT_KEY]

        instance = models.Instance.load(context, id)
        self.authorize_instance_action(context, 'update', instance)

        # Make sure args contains a 'configuration_id' argument,
        args = {}
        args['configuration_id'] = self._configuration_parse(context, body)
        self._modify_instance(context, req, instance, **args)
        return wsgi.Result(None, 202)

    def edit(self, req, id, body, tenant_id):
        """
        Updates the instance to set or unset one or more attributes.
        """
        LOG.info("Editing instance for tenant id %s.", tenant_id)
        LOG.debug("req: %s", strutils.mask_password(req))
        LOG.debug("body: %s", strutils.mask_password(body))
        context = req.environ[wsgi.CONTEXT_KEY]

        instance = models.Instance.load(context, id)
        self.authorize_instance_action(context, 'edit', instance)

        args = {}
        args['detach_replica'] = ('replica_of' in body['instance'] or
                                  'slave_of' in body['instance'])

        if 'name' in body['instance']:
            args['name'] = body['instance']['name']
        if 'configuration' in body['instance']:
            args['configuration_id'] = self._configuration_parse(context, body)
        if 'datastore_version' in body['instance']:
            args['datastore_version'] = body['instance'].get(
                'datastore_version')

        self._modify_instance(context, req, instance, **args)
        return wsgi.Result(None, 202)

    def configuration(self, req, tenant_id, id):
        """
        Returns the default configuration template applied to the instance.
        """
        LOG.info("Getting default configuration for instance %s", id)
        context = req.environ[wsgi.CONTEXT_KEY]
        instance = models.Instance.load(context, id)
        self.authorize_instance_action(context, 'configuration', instance)

        LOG.debug("Server: %s", instance)
        config = instance.get_default_configuration_template()
        LOG.debug("Default config for instance %(instance_id)s is %(config)s",
                  {'instance_id': id, 'config': config})
        return wsgi.Result(views.DefaultConfigurationView(
            config).data(), 200)

    def guest_log_list(self, req, tenant_id, id):
        """Return all information about all logs for an instance."""
        LOG.debug("Listing logs for tenant %s", tenant_id)
        context = req.environ[wsgi.CONTEXT_KEY]

        try:
            backup_model.verify_swift_auth_token(context)
        except exception.SwiftNotFound:
            raise exception.LogsNotAvailable()

        instance = models.Instance.load(context, id)
        if not instance:
            raise exception.NotFound(uuid=id)
        self.authorize_instance_action(context, 'guest_log_list', instance)
        client = clients.create_guest_client(context, id)
        guest_log_list = client.guest_log_list()
        return wsgi.Result({'logs': guest_log_list}, 200)

    def guest_log_action(self, req, body, tenant_id, id):
        """Processes a guest log."""
        LOG.info("Processing log for tenant %s", tenant_id)
        context = req.environ[wsgi.CONTEXT_KEY]

        try:
            backup_model.verify_swift_auth_token(context)
        except exception.SwiftNotFound:
            raise exception.LogsNotAvailable()

        instance = models.Instance.load(context, id)
        if not instance:
            raise exception.NotFound(uuid=id)
        log_name = body['name']
        enable = body.get('enable', None)
        disable = body.get('disable', None)
        publish = body.get('publish', None)
        discard = body.get('discard', None)
        if enable and disable:
            raise exception.BadRequest(_("Cannot enable and disable log."))
        client = clients.create_guest_client(context, id)
        guest_log = client.guest_log_action(log_name, enable, disable,
                                            publish, discard)
        return wsgi.Result({'log': guest_log}, 200)

    def module_list(self, req, tenant_id, id):
        """Return information about modules on an instance."""
        context = req.environ[wsgi.CONTEXT_KEY]
        instance = models.Instance.load(context, id)
        if not instance:
            raise exception.NotFound(uuid=id)
        self.authorize_instance_action(context, 'module_list', instance)
        from_guest = bool(req.GET.get('from_guest', '').lower())
        include_contents = bool(req.GET.get('include_contents', '').lower())
        if from_guest:
            return self._module_list_guest(
                context, id, include_contents=include_contents)
        else:
            return self._module_list(
                context, id, include_contents=include_contents)

    def _module_list_guest(self, context, id, include_contents):
        """Return information about modules on an instance."""
        client = clients.create_guest_client(context, id)
        result_list = client.module_list(include_contents)
        return wsgi.Result({'modules': result_list}, 200)

    def _module_list(self, context, id, include_contents):
        """Return information about instance modules."""
        client = clients.create_guest_client(context, id)
        result_list = client.module_list(include_contents)
        return wsgi.Result({'modules': result_list}, 200)

    def module_apply(self, req, body, tenant_id, id):
        """Apply modules to an instance."""
        context = req.environ[wsgi.CONTEXT_KEY]
        instance = models.Instance.load(context, id)
        if not instance:
            raise exception.NotFound(uuid=id)
        self.authorize_instance_action(context, 'module_apply', instance)
        module_ids = [mod['id'] for mod in body.get('modules', [])]
        modules = module_models.Modules.load_by_ids(context, module_ids)
        module_models.Modules.validate(
            modules, instance.datastore.id, instance.datastore_version.id)
        module_list = module_views.convert_modules_to_list(modules)
        client = clients.create_guest_client(context, id)
        result_list = client.module_apply(module_list)
        models.Instance.add_instance_modules(context, id, modules)
        return wsgi.Result({'modules': result_list}, 200)

    def module_remove(self, req, tenant_id, id, module_id):
        """Remove module from an instance."""
        context = req.environ[wsgi.CONTEXT_KEY]
        instance = models.Instance.load(context, id)
        if not instance:
            raise exception.NotFound(uuid=id)
        self.authorize_instance_action(context, 'module_remove', instance)
        module = module_models.Module.load(context, module_id)
        module_info = module_views.DetailedModuleView(module).data()
        client = clients.create_guest_client(context, id)
        client.module_remove(module_info)
        instance_modules = module_models.InstanceModules.load_all(
            context, instance_id=id, module_id=module_id)
        for instance_module in instance_modules:
            module_models.InstanceModule.delete(context, instance_module)
            LOG.debug("Deleted IM record %(instance_module_id)s "
                      "(instance %(id)s, module %(module_id)s).",
                      {'instance_module_id': instance_module.id, 'id': id,
                       'module_id': module_id})
        return wsgi.Result(None, 200)
