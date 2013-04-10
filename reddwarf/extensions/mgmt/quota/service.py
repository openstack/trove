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

from reddwarf.common import wsgi
from reddwarf.common import exception
from reddwarf.common.auth import admin_context
from reddwarf.extensions.mgmt.quota import views
from reddwarf.openstack.common import log as logging
from reddwarf.quota.quota import QUOTAS as quota_engine
from reddwarf.quota.models import Quota

LOG = logging.getLogger(__name__)


class QuotaController(wsgi.Controller):
    """Controller for quota  functionality"""

    @admin_context
    def show(self, req, tenant_id, id):
        """Return all quotas for this tenant."""
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("Indexing quota info for tenant '%s'") % id)
        quotas = quota_engine.get_all_quotas_by_tenant(id)
        return wsgi.Result(views.QuotaView(quotas).data(), 200)

    @admin_context
    def update(self, req, body, tenant_id, id):
        LOG.info("req : '%s'\n\n" % req)
        LOG.info("Updating quota limits for tenant '%s'" % id)
        if not body:
            raise exception.BadRequest(_("Invalid request body."))

        quotas = {}
        quota = None
        registered_resources = quota_engine.resources
        for resource, limit in body['quotas'].items():
            if limit is None:
                continue
            if resource == "xmlns":
                continue
            if resource not in registered_resources:
                raise exception.QuotaResourceUnknown(unknown=resource)
            try:
                quota = Quota.find_by(tenant_id=id, resource=resource)
                quota.hard_limit = limit
                quota.save()
            except exception.ModelNotFoundError:
                quota = Quota.create(tenant_id=id,
                                     resource=resource,
                                     hard_limit=limit)

            quotas[resource] = quota

        return wsgi.Result(views.QuotaView(quotas).data(), 200)
