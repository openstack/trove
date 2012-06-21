# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack LLC.
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

import logging
import routes
import webob.exc

from reddwarf.common import config
from reddwarf.common import exception
from reddwarf.common import pagination
from reddwarf.common import utils
from reddwarf.common import wsgi
from reddwarf.extensions.mysql.common import populate_databases
from reddwarf.extensions.mysql.common import populate_users
from reddwarf.instance import models, views


CONFIG = config.Config
LOG = logging.getLogger(__name__)


class BaseController(wsgi.Controller):
    """Base controller class."""

    exclude_attr = []
    exception_map = {
        webob.exc.HTTPUnprocessableEntity: [
            exception.UnprocessableEntity,
            ],
        webob.exc.HTTPBadRequest: [
            exception.InvalidModelError,
            exception.BadRequest,
            exception.CannotResizeToSameSize,
            exception.BadValue
            ],
        webob.exc.HTTPNotFound: [
            exception.NotFound,
            exception.ComputeInstanceNotFound,
            exception.ModelNotFoundError,
            ],
        webob.exc.HTTPConflict: [
            ],
        webob.exc.HTTPRequestEntityTooLarge: [
            exception.OverLimit,
            exception.QuotaExceeded,
            exception.VolumeQuotaExceeded,
            ],
        webob.exc.HTTPServerError: [
            exception.VolumeCreationFailure
            ]
        }

    def __init__(self):
        self.add_addresses = utils.bool_from_string(
                        config.Config.get('add_addresses', 'False'))
        self.add_volumes = utils.bool_from_string(
                        config.Config.get('reddwarf_volume_support', 'False'))
        pass

    def _extract_limits(self, params):
        return dict([(key, params[key]) for key in params.keys()
                     if key in ["limit", "marker"]])

    def _extract_required_params(self, params, model_name):
        params = params or {}
        model_params = params.get(model_name, {})
        return utils.stringify_keys(utils.exclude(model_params,
                                                  *self.exclude_attr))


class api_validation:
    """ api validation wrapper """
    def __init__(self, action=None):
        self.action = action

    def __call__(self, f):
        """
        Apply validation of the api body
        """
        def wrapper(*args, **kwargs):
            body = kwargs['body']
            if self.action == 'create':
                InstanceController._validate(body)
            return f(*args, **kwargs)
        return wrapper


class InstanceController(BaseController):
    """Controller for instance functionality"""

    def action(self, req, body, tenant_id, id):
        LOG.info("req : '%s'\n\n" % req)
        LOG.info("Comitting an ACTION again instance %s for tenant '%s'"
                 % (id, tenant_id))
        if not body:
            raise exception.BadRequest(_("Invalid request body."))
        context = req.environ[wsgi.CONTEXT_KEY]
        instance = models.Instance.load(context, id)
        _actions = {
            'restart': self._action_restart,
            'resize': self._action_resize
            }
        selected_action = None
        for key in body:
            if key in _actions:
                if selected_action is not None:
                    msg = _("Only one action can be specified per request.")
                    raise exception.BadRequest(msg)
                selected_action = _actions[key]
            else:
                msg = _("Invalid instance action: %s") % key
                raise exception.BadRequest(msg)

        if selected_action:
            return selected_action(instance, body)
        else:
            raise exception.BadRequest(_("Invalid request body."))

    def _action_restart(self, instance, body):
        instance.validate_can_perform_restart_or_reboot()
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
        instance.validate_can_perform_resize()
        options = {
            'volume': self._action_resize_volume,
            'flavorRef': self._action_resize_flavor
        }
        selected_option = None
        args = None
        for key in options:
            if key in body['resize']:
                if selected_option is not None:
                    msg = _("Not allowed to resize volume and flavor at the "
                            "same time.")
                    raise exception.BadRequest(msg)
                selected_option = options[key]
                args = body['resize'][key]

        if selected_option:
            return selected_option(instance, args)
        else:
            raise exception.BadRequest(_("Missing resize arguments."))

    def _action_resize_volume(self, instance, volume):
        InstanceController._validate_resize_volume(volume)
        instance.resize_volume(volume['size'])
        return wsgi.Result(None, 202)

    def _action_resize_flavor(self, instance, flavorRef):
        new_flavor_id = utils.get_id_from_href(flavorRef)
        instance.resize_flavor(new_flavor_id)
        return wsgi.Result(None, 202)

    def index(self, req, tenant_id):
        """Return all instances."""
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("Indexing a database instance for tenant '%s'") % tenant_id)
        context = req.environ[wsgi.CONTEXT_KEY]
        servers, marker = models.Instances.load(context)
        view = views.InstancesView(servers, req=req,
                                   add_volumes=self.add_volumes)
        paged = pagination.SimplePaginatedDataView(req.url, 'instances', view,
                                                   marker)
        return wsgi.Result(paged.data(), 200)

    def show(self, req, tenant_id, id):
        """Return a single instance."""
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("Showing a database instance for tenant '%s'") % tenant_id)
        LOG.info(_("id : '%s'\n\n") % id)

        context = req.environ[wsgi.CONTEXT_KEY]
        server = models.load_instance_with_guest(models.DetailInstance,
                                                 context, id)
        return wsgi.Result(views.InstanceDetailView(server, req=req,
                           add_addresses=self.add_addresses,
                           add_volumes=self.add_volumes).data(), 200)

    def delete(self, req, tenant_id, id):
        """Delete a single instance."""
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("Deleting a database instance for tenant '%s'") % tenant_id)
        LOG.info(_("id : '%s'\n\n") % id)
        # TODO(hub-cap): turn this into middleware
        context = req.environ[wsgi.CONTEXT_KEY]
        instance = models.Instance.load(context=context, id=id)
        instance.delete()
        # TODO(cp16net): need to set the return code correctly
        return wsgi.Result(None, 202)

    @api_validation(action="create")
    def create(self, req, body, tenant_id):
        # find the service id (cant be done yet at startup due to
        # inconsistencies w/ the load app paste
        # TODO(hub-cap): figure out how to get this to work in __init__ time
        # TODO(hub-cap): The problem with this in __init__ is that the paste
        #   config is generated w/ the same config file as the db flags that
        #   are needed for init. These need to be split so the db can be init'd
        #   w/o the paste stuff. Since the paste stuff inits the
        #   database.service module, it is a chicken before the egg problem.
        #   Simple refactor will fix it and we can move this into the __init__
        #   code. Or maybe we shouldnt due to the nature of changing images.
        #   This needs discussion.
        # TODO(hub-cap): turn this into middleware
        LOG.info(_("Creating a database instance for tenant '%s'") % tenant_id)
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("body : '%s'\n\n") % body)
        context = req.environ[wsgi.CONTEXT_KEY]
        service_type = body['instance'].get('service_type')
        if service_type is None:
            service_type = 'mysql'
        service = models.ServiceImage.find_by(service_name=service_type)
        image_id = service['image_id']
        name = body['instance']['name']
        flavor_ref = body['instance']['flavorRef']
        flavor_id = utils.get_id_from_href(flavor_ref)
        databases = populate_databases(body['instance'].get('databases', []))
        users = populate_users(body['instance'].get('users', []))
        if body['instance'].get('volume', None) is not None:
            try:
                volume_size = int(body['instance']['volume']['size'])
            except ValueError as e:
                raise exception.BadValue(msg=e)
        else:
            volume_size = None

        instance_max = int(config.Config.get('max_instances_per_user', 5))
        number_instances = models.DBInstance.find_all(tenant_id=tenant_id,
                                                      deleted=False).count()

        if number_instances >= instance_max:
            # That's too many, pal. Got to cut you off.
            LOG.error(_("New instance would exceed user instance quota."))
            msg = "User instance quota of %d would be exceeded."
            raise exception.QuotaExceeded(msg % instance_max)

        instance = models.Instance.create(context, name, flavor_id,
                                          image_id, databases, users,
                                          service_type, volume_size)

        return wsgi.Result(views.InstanceDetailView(instance, req=req,
                                  add_volumes=self.add_volumes).data(), 200)

    @staticmethod
    def _validate_body_not_empty(body):
        """Check that the body is not empty"""
        if not body:
            msg = "The request contains an empty body"
            raise exception.ReddwarfError(msg)

    @staticmethod
    def _validate_resize_volume(volume):
        """
        We are going to check that volume resizing data is present.
        """
        if 'size' not in volume:
            raise exception.BadRequest(
                "Missing 'size' property of 'volume' in request body.")
        InstanceController._validate_volume_size(volume['size'])

    @staticmethod
    def _validate_volume_size(size):
        """Validate the various possible errors for volume size"""
        try:
            volume_size = float(size)
        except (ValueError, TypeError) as err:
            LOG.error(err)
            msg = ("Required element/key - instance volume 'size' was not "
                   "specified as a number (value was %s)." % size)
            raise exception.ReddwarfError(msg)
        if int(volume_size) != volume_size or int(volume_size) < 1:
            msg = ("Volume 'size' needs to be a positive "
                   "integer value, %s cannot be accepted."
                   % volume_size)
            raise exception.ReddwarfError(msg)
        max_size = int(config.Config.get('max_accepted_volume_size', 1))
        if int(volume_size) > max_size:
            msg = ("Volume 'size' cannot exceed maximum "
                   "of %d Gb, %s cannot be accepted."
                   % (max_size, volume_size))
            raise exception.VolumeQuotaExceeded(msg)

    @staticmethod
    def _validate(body):
        """Validate that the request has all the required parameters"""
        InstanceController._validate_body_not_empty(body)

        try:
            body['instance']
            body['instance']['flavorRef']
            vol_enabled = utils.bool_from_string(
                                config.Config.get('reddwarf_volume_support',
                                                  'True'))
            must_have_vol = utils.bool_from_string(
                                config.Config.get('reddwarf_must_use_volume',
                                                  'False'))
            if vol_enabled:
                if body['instance'].get('volume', None):
                    if body['instance']['volume'].get('size', None):
                        volume_size = body['instance']['volume']['size']
                        InstanceController._validate_volume_size(volume_size)
                    elif must_have_vol:
                        raise exception.MissingKey(key="size")
                elif must_have_vol:
                    raise exception.MissingKey(key="volume")

        except KeyError as e:
            LOG.error(_("Create Instance Required field(s) - %s") % e)
            raise exception.ReddwarfError("Required element/key - %s "
                                       "was not specified" % e)
