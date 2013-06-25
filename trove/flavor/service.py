# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2012 OpenStack Foundation
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

import routes
import webob.exc

from trove.common import exception
from trove.common import utils
from trove.common import wsgi
from trove.flavor import models
from trove.flavor import views


class FlavorController(wsgi.Controller):
    """Controller for flavor functionality"""

    def show(self, req, tenant_id, id):
        """Return a single flavor."""
        context = req.environ[wsgi.CONTEXT_KEY]
        self._validate_flavor_id(id)
        flavor = models.Flavor(context=context, flavor_id=int(id))
        # Pass in the request to build accurate links.
        return wsgi.Result(views.FlavorView(flavor, req).data(), 200)

    def index(self, req, tenant_id):
        """Return all flavors."""
        context = req.environ[wsgi.CONTEXT_KEY]
        flavors = models.Flavors(context=context)
        return wsgi.Result(views.FlavorsView(flavors, req).data(), 200)

    def _validate_flavor_id(self, id):
        try:
            if int(id) != float(id):
                raise exception.NotFound(uuid=id)
        except ValueError:
            raise exception.NotFound(uuid=id)
