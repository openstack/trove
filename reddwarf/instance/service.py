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
from reddwarf.common import context as rd_context
from reddwarf.common import exception
from reddwarf.common import utils
from reddwarf.common import wsgi
from reddwarf.instance import models, views
from reddwarf.common import exception as rd_exceptions

CONFIG = config.Config
LOG = logging.getLogger(__name__)


class BaseController(wsgi.Controller):
    """Base controller class."""

    exclude_attr = []
    exception_map = {
        webob.exc.HTTPUnprocessableEntity: [
            ],
        webob.exc.HTTPBadRequest: [
            models.InvalidModelError,
            exception.BadRequest,
            ],
        webob.exc.HTTPNotFound: [
            exception.NotFound,
            models.ModelNotFoundError,
            ],
        webob.exc.HTTPConflict: [
            ],
        }

    def __init__(self):
        pass

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

    def detail(self, req, tenant_id):
        """Return all instances."""
        LOG.info("req : '%s'\n\n" % req)
        LOG.info("Detailing a database instance for tenant '%s'" % tenant_id)
        #TODO(cp16net) return a detailed list instead of index
        return self.index(req, tenant_id)

    def index(self, req, tenant_id):
        """Return all instances."""
        LOG.info("req : '%s'\n\n" % req)
        LOG.info("Indexing a database instance for tenant '%s'" % tenant_id)
        # TODO(hub-cap): turn this into middleware
        context = rd_context.ReddwarfContext(
                          auth_tok=req.headers["X-Auth-Token"],
                          tenant=tenant_id)
        servers = models.Instances.load(context)
        # TODO(cp16net): need to set the return code correctly
        return wsgi.Result(views.InstancesView(servers).data(), 201)

    def show(self, req, tenant_id, id):
        """Return a single instance."""
        LOG.info("req : '%s'\n\n" % req)
        LOG.info("Showing a database instance for tenant '%s'" % tenant_id)
        LOG.info("id : '%s'\n\n" % id)
        # TODO(hub-cap): turn this into middleware
        context = rd_context.ReddwarfContext(
                          auth_tok=req.headers["X-Auth-Token"],
                          tenant=tenant_id)
        try:
            # TODO(hub-cap): start testing the failure cases here
            server = models.Instance.load(context=context, uuid=id)
        except exception.ReddwarfError, e:
            # TODO(hub-cap): come up with a better way than
            #    this to get the message
            LOG.error(e)
            return wsgi.Result(str(e), 404)
        # TODO(cp16net): need to set the return code correctly
        return wsgi.Result(views.InstanceView(server).data(), 201)

    def delete(self, req, tenant_id, id):
        """Delete a single instance."""
        LOG.info("req : '%s'\n\n" % req)
        LOG.info("Deleting a database instance for tenant '%s'" % tenant_id)
        LOG.info("id : '%s'\n\n" % id)
        # TODO(hub-cap): turn this into middleware
        context = rd_context.ReddwarfContext(
                          auth_tok=req.headers["X-Auth-Token"],
                          tenant=tenant_id)
        models.Instance.delete(context=context, uuid=id)
        # TODO(cp16net): need to set the return code correctly
        return wsgi.Result(202)

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
        LOG.info("Creating a database instance for tenant '%s'" % tenant_id)
        LOG.info("req : '%s'\n\n" % req)
        LOG.info("body : '%s'\n\n" % body)
        context = rd_context.ReddwarfContext(
                          auth_tok=req.headers["X-Auth-Token"],
                          tenant=tenant_id)
        database = models.ServiceImage.find_by(service_name="database")
        image_id = database['image_id']
        name = body['instance']['name']
        flavor_ref = body['instance']['flavorRef']
        instance = models.Instance.create(context, name, flavor_ref, image_id)

        #TODO(cp16net): need to set the return code correctly
        return wsgi.Result(views.InstanceView(instance).data(), 201)

    @staticmethod
    def _validate_empty_body(body):
        """Check that the body is not empty"""
        if not body:
            msg = "The request contains an empty body"
            raise rd_exceptions.ReddwarfError(msg)

    @staticmethod
    def _validate_volume_size(size):
        """Validate the various possible errors for volume size"""
        try:
            volume_size = float(size)
        except (ValueError, TypeError) as err:
            LOG.error(err)
            msg = ("Required element/key - instance volume"
                   "'size' was not specified as a number")
            raise rd_exceptions.ReddwarfError(msg)
        if int(volume_size) != volume_size or int(volume_size) < 1:
            msg = ("Volume 'size' needs to be a positive "
                   "integer value, %s cannot be accepted."
                   % volume_size)
            raise rd_exceptions.ReddwarfError(msg)
        #TODO(cp16net) add in the volume validation when volumes are supported
#        max_size = FLAGS.reddwarf_max_accepted_volume_size
#        if int(volume_size) > max_size:
#            msg = ("Volume 'size' cannot exceed maximum "
#                   "of %d Gb, %s cannot be accepted."
#                   % (max_size, volume_size))
#            raise rd_exceptions.ReddwarfError(msg)

    @staticmethod
    def _validate(body):
        """Validate that the request has all the required parameters"""
        InstanceController._validate_empty_body(body)
        try:
            body['instance']
            body['instance']['flavorRef']
            # TODO(cp16net) add in volume to the mix
#            volume_size = body['instance']['volume']['size']
        except KeyError as e:
            LOG.error("Create Instance Required field(s) - %s" % e)
            raise rd_exceptions.ReddwarfError("Required element/key - %s "
                                       "was not specified" % e)
#        Instance._validate_volume_size(volume_size)

    @staticmethod
    def _validate_resize_instance(body):
        """ Validate that the resize body has the attributes for flavorRef """
        try:
            body['resize']
            body['resize']['flavorRef']
        except KeyError as e:
            LOG.error("Resize Instance Required field(s) - %s" % e)
            raise rd_exceptions.ReddwarfError("Required element/key - %s "
                                       "was not specified" % e)

    @staticmethod
    def _validate_single_resize_in_body(body):
        # Validate body resize does not have both volume and flavorRef
        try:
            resize = body['resize']
            if 'volume' in resize and 'flavorRef' in resize:
                msg = ("Not allowed to resize volume "
                       "and flavor at the same time")
                LOG.error(msg)
                raise rd_exceptions.ReddwarfError(msg)
        except KeyError as e:
            LOG.error("Resize Instance Required field(s) - %s" % e)
            raise rd_exceptions.ReddwarfError("Required element/key - %s "
                                              "was not specified" % e)

    @staticmethod
    def _validate_resize(body, old_volume_size):
        """
        We are going to check that volume resizing data is present.
        """
        InstanceController._validate_empty_body(body)
        try:
            body['resize']
            body['resize']['volume']
            new_volume_size = body['resize']['volume']['size']
        except KeyError as e:
            LOG.error("Resize Instance Required field(s) - %s" % e)
            raise rd_exceptions.ReddwarfError("Required element/key - %s "
                                       "was not specified" % e)
        Instance._validate_volume_size(new_volume_size)
        if int(new_volume_size) <= old_volume_size:
            raise rd_exceptions.ReddwarfError("The new volume 'size' cannot "
                                       "be less than the current volume size "
                                       "of '%s'" % old_volume_size)


class API(wsgi.Router):
    """API"""
    def __init__(self):
        mapper = routes.Mapper()
        super(API, self).__init__(mapper)
        self._instance_router(mapper)

    def _instance_router(self, mapper):
        instance_resource = InstanceController().create_resource()
        path = "/{tenant_id}/instances"
        mapper.resource("instance", path, controller=instance_resource)


def app_factory(global_conf, **local_conf):
    return API()
