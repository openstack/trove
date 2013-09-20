# vim: tabstop=4 shiftwidth=4 softtabstop=4

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
from trove.backup.models import Backup as backup_model
from trove.backup import views as backup_views
from trove.openstack.common import log as logging
from trove.openstack.common.gettextutils import _
import trove.common.apischema as apischema


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class InstanceController(wsgi.Controller):
    """Controller for instance functionality"""
    schemas = apischema.instance.copy()
    if not CONF.trove_volume_support:
        # see instance.models.create for further validation around this
        LOG.info("Removing volume attributes from schema")
        schemas['create']['properties']['instance']['required'].pop()

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
        LOG.info("req : '%s'\n\n" % req)
        LOG.info("Comitting an ACTION again instance %s for tenant '%s'"
                 % (id, tenant_id))
        if not body:
            raise exception.BadRequest(_("Invalid request body."))
        context = req.environ[wsgi.CONTEXT_KEY]
        instance = models.Instance.load(context, id)
        _actions = {
            'restart': self._action_restart,
            'resize': self._action_resize,
            'reset_password': self._action_reset_password
        }
        selected_action = None
        for key in body:
            if key in _actions:
                selected_action = _actions[key]
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
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("Indexing a database instance for tenant '%s'") % tenant_id)
        context = req.environ[wsgi.CONTEXT_KEY]
        servers, marker = models.Instances.load(context)
        view = views.InstancesView(servers, req=req)
        paged = pagination.SimplePaginatedDataView(req.url, 'instances', view,
                                                   marker)
        return wsgi.Result(paged.data(), 200)

    def backups(self, req, tenant_id, id):
        """Return all backups for the specified instance."""
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("Indexing backups for instance '%s'") %
                 id)

        backups = backup_model.list_for_instance(id)
        return wsgi.Result(backup_views.BackupViews(backups).data(), 200)

    def show(self, req, tenant_id, id):
        """Return a single instance."""
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("Showing a database instance for tenant '%s'") % tenant_id)
        LOG.info(_("id : '%s'\n\n") % id)

        context = req.environ[wsgi.CONTEXT_KEY]
        server = models.load_instance_with_guest(models.DetailInstance,
                                                 context, id)
        return wsgi.Result(views.InstanceDetailView(server,
                                                    req=req).data(), 200)

    def delete(self, req, tenant_id, id):
        """Delete a single instance."""
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("Deleting a database instance for tenant '%s'") % tenant_id)
        LOG.info(_("id : '%s'\n\n") % id)
        # TODO(hub-cap): turn this into middleware
        context = req.environ[wsgi.CONTEXT_KEY]
        instance = models.load_any_instance(context, id)
        instance.delete()
        # TODO(cp16net): need to set the return code correctly
        return wsgi.Result(None, 202)

    def create(self, req, body, tenant_id):
        # TODO(hub-cap): turn this into middleware
        LOG.info(_("Creating a database instance for tenant '%s'") % tenant_id)
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("body : '%s'\n\n") % body)
        context = req.environ[wsgi.CONTEXT_KEY]
        # Set the service type to mysql if its not in the request
        service_type = (body['instance'].get('service_type') or
                        CONF.service_type)
        service = models.ServiceImage.find_by(service_name=service_type)
        image_id = service['image_id']
        name = body['instance']['name']
        flavor_ref = body['instance']['flavorRef']
        flavor_id = utils.get_id_from_href(flavor_ref)
        databases = populate_validated_databases(
            body['instance'].get('databases', []))
        users = None
        try:
            users = populate_users(body['instance'].get('users', []))
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

        if 'availability_zone' in body['instance']:
            availability_zone = body['instance']['availability_zone']
        else:
            availability_zone = None

        instance = models.Instance.create(context, name, flavor_id,
                                          image_id, databases, users,
                                          service_type, volume_size,
                                          backup_id, availability_zone)

        view = views.InstanceDetailView(instance, req=req)
        return wsgi.Result(view.data(), 200)
