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

import logging
import routes
import webob.exc

from reddwarf.common import BaseController
from reddwarf.common import config
from reddwarf.common import context as rd_context
from reddwarf.common import exception
from reddwarf.common import wsgi

CONFIG = config.Config
LOG = logging.getLogger(__name__)


class FlavorController(BaseController):
    """Controller for flavor functionality"""

    def show(self, req, tenant_id, id):
        """Return a single flavor."""
        context = rd_context.ReddwarfContext(
                          auth_tok=req.headers["X-Auth-Token"],
                          tenant=tenant_id)
        try:
            flavor = flavormodels.Flavor(context=context, flavor_id=id).data()
            print "Flavor in show: %s" % flavor
        except exception.ReddwarfError, e:
            return wsgi.Result(str(e), 404)
        return wsgi.Result(flavorviews.FlavorView(flavor).data(), 201)

    def detail(self, req, tenant_id):
        """Return a list of flavors, with additional data about each flavor."""
        context = rd_context.ReddwarfContext(
                          auth_tok=req.headers["X-Auth-Token"],
                          tenant=tenant_id)
        try:
            flavors = flavormodels.Flavors(context=context)
        except exception.ReddwarfError, e:
            return wsgi.Result(str(e), 404)
        return wsgi.Result(flavorviews.FlavorsView(flavors).data(), 201)

    def index(self, req, tenant_id):
        """Return all flavors."""
        context = rd_context.ReddwarfContext(
                          auth_tok=req.headers["X-Auth-Token"],
                          tenant=tenant_id)
        flavors = flavormodels.Flavors(context)
        return wsgi.Result(flavorviews.FlavorsView(flavors).data(), 201)


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
                        collection={'detail': 'GET'})


def app_factory(global_conf, **local_conf):
    return API()
