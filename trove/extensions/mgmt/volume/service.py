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


from trove.common import wsgi
from trove.common.auth import admin_context
from trove.extensions.mgmt.volume import models
from trove.extensions.mgmt.volume import views
from trove.openstack.common import log as logging
from trove.openstack.common.gettextutils import _

LOG = logging.getLogger(__name__)


class StorageController(wsgi.Controller):
    """Controller for storage device functionality"""

    @admin_context
    def index(self, req, tenant_id):
        """Return all storage devices."""
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("Indexing storage info for tenant '%s'") % tenant_id)
        context = req.environ[wsgi.CONTEXT_KEY]
        storages = models.StorageDevices.load(context)
        return wsgi.Result(views.StoragesView(storages).data(), 200)
