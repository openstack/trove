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


from trove.cluster.service import ClusterController
from trove.common import exception
from trove.common import wsgi
from trove.common.auth import admin_context
from trove.extensions.mgmt.clusters import models
from trove.extensions.mgmt.clusters import views
from trove.openstack.common import log as logging
from trove.openstack.common.gettextutils import _
import trove.common.apischema as apischema

LOG = logging.getLogger(__name__)


class ClusterController(ClusterController):
    """Controller for cluster functionality."""
    schemas = apischema.mgmt_cluster

    @classmethod
    def get_action_schema(cls, body, action_schema):
        action_type = body.keys()[0]
        return action_schema.get(action_type, {})

    @admin_context
    def index(self, req, tenant_id):
        """Return a list of clusters."""
        LOG.debug("Showing a list of clusters for tenant '%s'." % tenant_id)
        LOG.info(_("req : '%s'\n\n") % req)
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
        LOG.debug("Showing cluster for tenant '%s'." % tenant_id)
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("id : '%s'\n\n") % id)
        context = req.environ[wsgi.CONTEXT_KEY]
        cluster = models.MgmtCluster.load(context, id)
        return wsgi.Result(
            views.load_mgmt_view(cluster, req=req).data(),
            200)

    @admin_context
    def action(self, req, body, tenant_id, id):
        LOG.debug("Committing an action against cluster %(cluster)s for "
                  "tenant '%(tenant)s'." % {'cluster': id,
                                            'tenant': tenant_id})
        LOG.info(_("req : '%s'\n\n") % req)
        if not body:
            raise exception.BadRequest(_("Invalid request body."))
        context = req.environ[wsgi.CONTEXT_KEY]
        cluster = models.MgmtCluster.load(context=context, id=id)
        _actions = {
            'reset-task': self._action_reset_task
        }
        selected_action = None
        for key in body:
            if key in _actions:
                if selected_action is not None:
                    msg = _("Only one action can be specified per request.")
                    raise exception.BadRequest(msg)
                selected_action = _actions[key]
            else:
                msg = _("Invalid cluster action: %s.") % key
                raise exception.BadRequest(msg)

        if selected_action:
            return selected_action(context, cluster, body)
        else:
            raise exception.BadRequest(_("Invalid request body."))

    def _action_reset_task(self, context, cluster, body):
        cluster.reset_task()
        return wsgi.Result(None, 202)
