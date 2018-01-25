# Copyright 2014 eBay Software Foundation
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


from oslo_log import log as logging

from trove.cluster.service import ClusterController
import trove.common.apischema as apischema
from trove.common.auth import admin_context
from trove.common import exception
from trove.common.i18n import _
from trove.common import wsgi
from trove.extensions.mgmt.clusters import models
from trove.extensions.mgmt.clusters import views

LOG = logging.getLogger(__name__)


class MgmtClusterController(ClusterController):
    """Controller for cluster functionality."""
    schemas = apischema.mgmt_cluster

    @classmethod
    def get_action_schema(cls, body, action_schema):
        action_type = list(body.keys())[0]
        return action_schema.get(action_type, {})

    @admin_context
    def index(self, req, tenant_id):
        """Return a list of clusters."""
        LOG.debug("Showing a list of clusters for tenant '%s'.", tenant_id)
        LOG.info("req : '%s'\n\n", req)
        context = req.environ[wsgi.CONTEXT_KEY]
        deleted = None
        deleted_q = req.GET.get('deleted', '').lower()
        if deleted_q in ['true']:
            deleted = True
        elif deleted_q in ['false']:
            deleted = False
        clusters = models.MgmtCluster.load_all(context, deleted=deleted)
        view_cls = views.MgmtClustersView
        return wsgi.Result(view_cls(clusters, req=req).data(), 200)

    @admin_context
    def show(self, req, tenant_id, id):
        """Return a single cluster."""
        LOG.info("Showing cluster for tenant '%(tenant_id)s'.\n"
                 "req : '%(req)s'\n"
                 "id : '%(id)s'", {
                     "tenant_id": tenant_id, "req": req, "id": id})

        context = req.environ[wsgi.CONTEXT_KEY]
        cluster = models.MgmtCluster.load(context, id)
        return wsgi.Result(
            views.load_mgmt_view(cluster, req=req).data(),
            200)

    @admin_context
    def action(self, req, body, tenant_id, id):
        LOG.debug("Committing an action against cluster %(cluster)s for "
                  "tenant '%(tenant)s'.", {'cluster': id,
                                           'tenant': tenant_id})
        LOG.info("req : '%s'\n\n", req)
        if not body:
            raise exception.BadRequest(_("Invalid request body."))
        context = req.environ[wsgi.CONTEXT_KEY]
        cluster = models.MgmtCluster.load(context=context, id=id)

        if 'reset-task' in body:
            return self._action_reset_task(context, cluster, body)
        else:
            msg = _("Invalid cluster action requested.")
            raise exception.BadRequest(msg)

    def _action_reset_task(self, context, cluster, body):
        cluster.reset_task()
        return wsgi.Result(None, 202)
