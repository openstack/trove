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


from trove.common import wsgi
from trove.common.auth import admin_context
from trove.extensions.mgmt.host import models
from trove.extensions.mgmt.host import views
from trove.instance.service import InstanceController
from trove.openstack.common import log as logging
from trove.openstack.common.gettextutils import _

LOG = logging.getLogger(__name__)


class HostController(InstanceController):
    """Controller for instance functionality"""

    @admin_context
    def index(self, req, tenant_id, detailed=False):
        """Return all hosts."""
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("Indexing a host for tenant '%s'") % tenant_id)
        context = req.environ[wsgi.CONTEXT_KEY]
        hosts = models.SimpleHost.load_all(context)
        return wsgi.Result(views.HostsView(hosts).data(), 200)

    @admin_context
    def show(self, req, tenant_id, id):
        """Return a single host."""
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("Showing a host for tenant '%s'") % tenant_id)
        LOG.info(_("id : '%s'\n\n") % id)
        context = req.environ[wsgi.CONTEXT_KEY]
        host = models.DetailedHost.load(context, id)
        return wsgi.Result(views.HostDetailedView(host).data(), 200)
