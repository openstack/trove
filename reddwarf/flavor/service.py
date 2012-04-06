# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2012 OpenStack LLC.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http: //www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import routes
import webob.exc

from reddwarf.common import exception
from reddwarf.common import utils
from reddwarf.common import wsgi
from reddwarf.flavor import models
from reddwarf.flavor import views


class BaseController(wsgi.Controller):
    """Base controller class."""

    exclude_attr = []
    exception_map = {
        webob.exc.HTTPUnprocessableEntity: [
            ],
        webob.exc.HTTPBadRequest: [
            exception.BadRequest,
            ],
        webob.exc.HTTPNotFound: [
            exception.NotFound,
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


class FlavorController(BaseController):
    """Controller for flavor functionality"""

    def show(self, req, tenant_id, id):
        """Return a single flavor."""
        context = req.environ[wsgi.CONTEXT_KEY]
        flavor = models.Flavor(context=context, flavor_id=id)
        # Pass in the request to build accurate links.
        return wsgi.Result(views.FlavorDetailView(flavor, req).data(), 200)

    def detail(self, req, tenant_id):
        """Return a list of flavors, with additional data about each flavor."""
        context = req.environ[wsgi.CONTEXT_KEY]
        flavors = models.Flavors(context=context)
        return wsgi.Result(views.FlavorsDetailView(flavors, req).data(), 200)

    def index(self, req, tenant_id):
        """Return all flavors."""
        context = req.environ[wsgi.CONTEXT_KEY]
        flavors = models.Flavors(context=context)
        return wsgi.Result(views.FlavorsView(flavors, req).data(), 200)


class API(wsgi.Router):
    """API"""
    def __init__(self):
        mapper = routes.Mapper()
        super(API, self).__init__(mapper)
        self._flavor_router(mapper)

    def _flavor_router(self, mapper):
        flavor_resource = FlavorController().create_resource()
        path = "/{tenant_id}/flavors"
        mapper.resource("flavor", path, controller=flavor_resource,
                        collection={'detail': 'GET', '': 'GET'})


def app_factory(global_conf, **local_conf):
    return API()
