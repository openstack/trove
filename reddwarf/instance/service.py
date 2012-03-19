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


class InstanceController(BaseController):
    """Controller for instance functionality"""

    def detail(self, req, tenant_id):
        """Return all instances."""
        LOG.info("req : '%s'\n\n" % req)
        LOG.info("Creating a database instance for tenant '%s'" % tenant_id)
        return self.index(req, tenant_id)

    def index(self, req, tenant_id):
        """Return all instances."""
        LOG.info("req : '%s'\n\n" % req)
        LOG.info("Creating a database instance for tenant '%s'" % tenant_id)
        # TODO(hub-cap): turn this into middleware
        context = rd_context.ReddwarfContext(
                          auth_tok=req.headers["X-Auth-Token"],
                          tenant=tenant_id)
        servers = models.Instances(context).data()
        # TODO(cp16net): need to set the return code correctly
        return wsgi.Result(views.InstancesView(servers).data(), 201)

    def show(self, req, tenant_id, id):
        """Return a single instance."""
        LOG.info("req : '%s'\n\n" % req)
        LOG.info("Creating a database instance for tenant '%s'" % tenant_id)
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
            return wsgi.Result(str(e), 404)
        # TODO(cp16net): need to set the return code correctly
        return wsgi.Result(views.InstanceView(server), 201)

    def delete(self, req, tenant_id, id):
        """Delete a single instance."""
        LOG.info("req : '%s'\n\n" % req)
        LOG.info("Creating a database instance for tenant '%s'" % tenant_id)
        LOG.info("id : '%s'\n\n" % id)
        # TODO(hub-cap): turn this into middleware
        context = rd_context.ReddwarfContext(
                          auth_tok=req.headers["X-Auth-Token"],
                          tenant=tenant_id)
        # TODO(cp16net) : need to handle exceptions here if the delete fails
        models.Instance.delete(context=context, uuid=id)

        # TODO(cp16net): need to set the return code correctly
        return wsgi.Result(202)

    def create(self, req, body, tenant_id):
        # find the service id (cant be done yet at startup due to
        # inconsitencies w/ the load app paste
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

        # Now wait for the response from the create to do additional work
        #TODO(cp16net): need to set the return code correctly
        return wsgi.Result(views.InstanceView(instance).data(), 201)


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
