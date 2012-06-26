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

from novaclient import exceptions as nova_exceptions

from reddwarf.common import exception
from reddwarf.common import wsgi
from reddwarf.extensions.mgmt.instances import models
from reddwarf.extensions.mgmt.instances.views import DiagnosticsView
from reddwarf.instance import models as instance_models
from reddwarf.extensions.mgmt.instances import views
from reddwarf.extensions.mysql import models as mysql_models
from reddwarf.instance.service import InstanceController
from reddwarf.common.auth import admin_context
from reddwarf.common.remote import create_nova_client


LOG = logging.getLogger(__name__)


class MgmtInstanceController(InstanceController):
    """Controller for instance functionality"""

    @admin_context
    def index(self, req, tenant_id, detailed=False):
        """Return all instances."""
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("Indexing a database instance for tenant '%s'") % tenant_id)
        context = req.environ[wsgi.CONTEXT_KEY]
        try:
            instances = models.load_mgmt_instances(context)
        except nova_exceptions.ClientException, e:
            LOG.error(e)
            return wsgi.Result(str(e), 403)

        view_cls = views.MgmtInstancesView
        return wsgi.Result(view_cls(instances, req=req,
                                    add_addresses=self.add_addresses,
                                    add_volumes=self.add_volumes).data(), 200)

    @admin_context
    def show(self, req, tenant_id, id):
        """Return a single instance."""
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("Showing a database instance for tenant '%s'") % tenant_id)
        LOG.info(_("id : '%s'\n\n") % id)

        context = req.environ[wsgi.CONTEXT_KEY]
        try:
            server = models.SimpleMgmtInstance.load(context, id)
            root_history = mysql_models.RootHistory.load(context=context,
                                                         instance_id=id)
        except exception.ReddwarfError, e:
            LOG.error(e)
            return wsgi.Result(str(e), 404)
        return wsgi.Result(views.MgmtInstanceDetailView(server, req=req,
                                        add_addresses=self.add_addresses,
                                        add_volumes=self.add_volumes,
                                        root_history=root_history).data(), 200)

    @admin_context
    def root(self, req, tenant_id, id):
        """Return the date and time root was enabled on an instance,
        if ever."""
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("Showing root history for tenant '%s'") % tenant_id)
        LOG.info(_("id : '%s'\n\n") % id)
        context = req.environ[wsgi.CONTEXT_KEY]
        try:
            server = instance_models.Instance.load(context=context, id=id)
        except exception.ReddwarfError, e:
            LOG.error(e)
            return wsgi.Result(str(e), 404)
        reh = mysql_models.RootHistory.load(context=context, instance_id=id)
        rhv = None
        if reh:
            rhv = views.RootHistoryView(reh.id, enabled=reh.created,
                                        user_id=reh.user)
        else:
            rhv = views.RootHistoryView(id)
        return wsgi.Result(rhv.data(), 200)

    @admin_context
    def diagnostics(self, req, tenant_id, id):
        """Return a single instance diagnostics."""
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("Showing a instance diagnostics for instance '%s'") % id)
        LOG.info(_("id : '%s'\n\n") % id)

        context = req.environ[wsgi.CONTEXT_KEY]
        try:
            instance = models.MgmtInstance.load(context=context, id=id)
            diagnostics = instance.get_diagnostics()
        except exception.ReddwarfError, e:
            LOG.error(e)
            return wsgi.Result(str(e), 404)
        return wsgi.Result(DiagnosticsView(id, diagnostics), 200)
