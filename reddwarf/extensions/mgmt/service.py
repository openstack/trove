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
import webob.exc

from reddwarf.common import exception
from reddwarf.common import wsgi
from reddwarf.instance import models as instance_models
from reddwarf.extensions.mgmt import views
from reddwarf.instance.service import InstanceController

LOG = logging.getLogger(__name__)


class MgmtInstanceController(InstanceController):
    """Controller for instance functionality"""

    def index(self, req, tenant_id, detailed=False):
        """Return all instances."""
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("Indexing a database instance for tenant '%s'") % tenant_id)
        # TODO(sacharya): Load all servers from nova?
        context = req.environ[wsgi.CONTEXT_KEY]
        servers = instance_models.Instances.load(context)

        view_cls = views.InstancesView
        return wsgi.Result(view_cls(servers,
            add_addresses=self.add_addresses).data(), 200)

    def show(self, req, tenant_id, id):
        """Return a single instance."""
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("Showing a database instance for tenant '%s'") % tenant_id)
        LOG.info(_("id : '%s'\n\n") % id)

        context = req.environ[wsgi.CONTEXT_KEY]
        try:
            server = instance_models.Instance.load(context=context, id=id)
        except exception.ReddwarfError, e:
            LOG.error(e)
            return wsgi.Result(str(e), 404)
        return wsgi.Result(views.InstanceView(server,
            add_addresses=self.add_addresses).data(), 200)

