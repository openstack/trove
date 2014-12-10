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

import webob.exc

from trove.common import cfg
from trove.common import exception
from trove.common import pagination
from trove.common import utils
from trove.common import wsgi
from trove.extensions.mysql.common import populate_validated_databases
from trove.extensions.mysql.common import populate_users
from trove.instance import models, views
from trove.datastore import models as datastore_models
from trove.backup.models import Backup as backup_model
from trove.backup import views as backup_views
from trove.openstack.common import log as logging
from trove.common.i18n import _
from trove.common.i18n import _LI
import trove.common.apischema as apischema


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class InstanceController(wsgi.Controller):

    """Controller for instance functionality."""
    schemas = apischema.instance.copy()

    @classmethod
    def get_action_schema(cls, body, action_schema):
        action_type = body.keys()[0]
        action_schema = action_schema.get(action_type, {})
        if action_type == 'resize':
            # volume or flavorRef
            resize_action = body[action_type].keys()[0]
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
        could include 'resize', 'restart', 'reset_password'
        :param req: http request object
        :param body: deserialized body of the request as a dict
        :param tenant_id: the tenant id for whom owns the instance
        :param id: ???
        """
        LOG.debug("instance action req : '%s'\n\n", req)
        if not body:
            raise exception.BadRequest(_("Invalid request body."))
        context = req.environ[wsgi.CONTEXT_KEY]
        instance = models.Instance.load(context, id)
        _actions = {
            'restart': self._action_restart,
            'resize': self._action_resize,
            'reset_password': self._action_reset_password,
        }
        selected_action = None
        action_name = None
        for key in body:
            if key in _actions:
                selected_action = _actions[key]
                action_name = key
        LOG.info(_LI("Performing %(action_name)s action against "
                     "instance %(instance_id)s for tenant '%(tenant_id)s'"),
                 {'action_name': action_name, 'instance_id': id,
                  'tenant_id': tenant_id})
        return selected_action(instance, body)

    def _action_restart(self, instance, body):
        instance.restart()
        return wsgi.Result(None, 202)

    def _action_resize(self, instance, body):
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
        return selected_option(instance, args)

    def _action_resize_volume(self, instance, volume):
        instance.resize_volume(volume['size'])
        return wsgi.Result(None, 202)

    def _action_resize_flavor(self, instance, flavorRef):
        new_flavor_id = utils.get_id_from_href(flavorRef)
        instance.resize_flavor(new_flavor_id)
        return wsgi.Result(None, 202)

    def _action_reset_password(self, instance, body):
        raise webob.exc.HTTPNotImplemented()

    def index(self, req, tenant_id):
        """Return all instances."""
        LOG.info(_LI("Listing database instances for tenant '%s'"), tenant_id)
        LOG.debug("req : '%s'\n\n", req)
        context = req.environ[wsgi.CONTEXT_KEY]
        clustered_q = req.GET.get('include_clustered', '').lower()
        include_clustered = clustered_q == 'true'
        servers, marker = models.Instances.load(context, include_clustered)
        view = views.InstancesView(servers, req=req)
        paged = pagination.SimplePaginatedDataView(req.url, 'instances', view,
                                                   marker)
        return wsgi.Result(paged.data(), 200)

    def backups(self, req, tenant_id, id):
        """Return all backups for the specified instance."""
        LOG.info(_LI("Listing backups for instance '%s'"),
                 id)
        LOG.debug("req : '%s'\n\n", req)
        context = req.environ[wsgi.CONTEXT_KEY]
        backups, marker = backup_model.list_for_instance(context, id)
        view = backup_views.BackupViews(backups)
        paged = pagination.SimplePaginatedDataView(req.url, 'backups', view,
                                                   marker)
        return wsgi.Result(paged.data(), 200)

    def show(self, req, tenant_id, id):
        """Return a single instance."""
        LOG.info(_LI("Showing database instance '%(instance_id)s' for tenant "
                     "'%(tenant_id)s'"),
                 {'instance_id': id, 'tenant_id': tenant_id})
        LOG.debug("req : '%s'\n\n", req)

        context = req.environ[wsgi.CONTEXT_KEY]
        server = models.load_instance_with_guest(models.DetailInstance,
                                                 context, id)
        return wsgi.Result(views.InstanceDetailView(server,
                                                    req=req).data(), 200)

    def delete(self, req, tenant_id, id):
        """Delete a single instance."""
        LOG.info(_LI("Deleting database instance '%(instance_id)s' for tenant "
                     "'%(tenant_id)s'"),
                 {'instance_id': id, 'tenant_id': tenant_id})
        LOG.debug("req : '%s'\n\n", req)
        # TODO(hub-cap): turn this into middleware
        context = req.environ[wsgi.CONTEXT_KEY]
        instance = models.load_any_instance(context, id)
        instance.delete()
        # TODO(cp16net): need to set the return code correctly
        return wsgi.Result(None, 202)

    def create(self, req, body, tenant_id):
        # TODO(hub-cap): turn this into middleware
        LOG.info(_LI("Creating a database instance for tenant '%s'"),
                 tenant_id)
        LOG.debug(logging.mask_password("req : '%s'\n\n", req))
        LOG.debug(logging.mask_password("body : '%s'\n\n", body))
        context = req.environ[wsgi.CONTEXT_KEY]
        datastore_args = body['instance'].get('datastore', {})
        datastore, datastore_version = (
            datastore_models.get_datastore_version(**datastore_args))
        image_id = datastore_version.image_id
        name = body['instance']['name']
        flavor_ref = body['instance']['flavorRef']
        flavor_id = utils.get_id_from_href(flavor_ref)

        configuration = self._configuration_parse(context, body)
        databases = populate_validated_databases(
            body['instance'].get('databases', []))
        database_names = [database.get('_name', '') for database in databases]
        users = None
        try:
            users = populate_users(body['instance'].get('users', []),
                                   database_names)
        except ValueError as ve:
            raise exception.BadRequest(msg=ve)

        if 'volume' in body['instance']:
            volume_size = int(body['instance']['volume']['size'])
        else:
            volume_size = None

        if 'restorePoint' in body['instance']:
            backupRef = body['instance']['restorePoint']['backupRef']
            backup_id = utils.get_id_from_href(backupRef)
        else:
            backup_id = None

        availability_zone = body['instance'].get('availability_zone')
        nics = body['instance'].get('nics')

        slave_of_id = body['instance'].get('replica_of',
                                           # also check for older name
                                           body['instance'].get('slave_of'))

        instance = models.Instance.create(context, name, flavor_id,
                                          image_id, databases, users,
                                          datastore, datastore_version,
                                          volume_size, backup_id,
                                          availability_zone, nics,
                                          configuration, slave_of_id)

        view = views.InstanceDetailView(instance, req=req)
        return wsgi.Result(view.data(), 200)

    def _configuration_parse(self, context, body):
        if 'configuration' in body['instance']:
            configuration_ref = body['instance']['configuration']
            if configuration_ref:
                configuration_id = utils.get_id_from_href(configuration_ref)
                return configuration_id

    def update(self, req, id, body, tenant_id):
        """Updates the instance to attach/detach configuration."""
        LOG.info(_LI("Updating database instance '%(instance_id)s' for tenant "
                     "'%(tenant_id)s'"),
                 {'instance_id': id, 'tenant_id': tenant_id})
        LOG.debug("req: %s", req)
        LOG.debug("body: %s", body)
        context = req.environ[wsgi.CONTEXT_KEY]

        instance = models.Instance.load(context, id)

        # If configuration is set, then we will update the instance to use the
        # new configuration. If configuration is empty, we want to disassociate
        # the instance from the configuration group and remove the active
        # overrides file.

        update_args = {}
        configuration_id = self._configuration_parse(context, body)
        if configuration_id:
            instance.assign_configuration(configuration_id)
        else:
            instance.unassign_configuration()

        update_args['configuration_id'] = configuration_id
        instance.update_db(**update_args)
        return wsgi.Result(None, 202)

    def edit(self, req, id, body, tenant_id):
        """
        Updates the instance to set or unset one or more attributes.
        """
        LOG.info(_LI("Editing instance for tenant id %s."), tenant_id)
        LOG.debug(logging.mask_password("req: %s"), req)
        LOG.debug(logging.mask_password("body: %s"), body)
        context = req.environ[wsgi.CONTEXT_KEY]

        instance = models.Instance.load(context, id)

        if 'slave_of' in body['instance']:
            LOG.debug("Detaching replica from source.")
            instance.detach_replica()

        # If configuration is set, then we will update the instance to
        # use the new configuration. If configuration is empty, we
        # want to disassociate the instance from the configuration
        # group and remove the active overrides file.
        # If instance name is set, then we will update the instance name.

        edit_args = {}
        if 'configuration' in body['instance']:
            configuration_id = self._configuration_parse(context, body)
            if configuration_id:
                instance.assign_configuration(configuration_id)
            else:
                instance.unassign_configuration()
            edit_args['configuration_id'] = configuration_id

        if 'name' in body['instance']:
            edit_args['name'] = body['instance']['name']

        if edit_args:
            instance.update_db(**edit_args)

        return wsgi.Result(None, 202)

    def configuration(self, req, tenant_id, id):
        """
        Returns the default configuration template applied to the instance.
        """
        LOG.info(_LI("Getting default configuration for instance %s"), id)
        context = req.environ[wsgi.CONTEXT_KEY]
        instance = models.Instance.load(context, id)
        LOG.debug("Server: %s", instance)
        config = instance.get_default_configuration_template()
        LOG.debug("Default config for instance %(instance_id)s is %(config)s",
                  {'instance_id': id, 'config': config})
        return wsgi.Result(views.DefaultConfigurationView(
                           config).data(), 200)
