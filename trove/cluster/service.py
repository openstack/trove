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

from oslo.config.cfg import NoSuchOptError

from trove.cluster import models
from trove.cluster import views
from trove.common import cfg
from trove.common import exception
from trove.common import pagination
from trove.common import apischema
from trove.common import utils
from trove.common import wsgi
from trove.common.strategies.cluster import strategy
from trove.datastore import models as datastore_models
from trove.openstack.common import log as logging
from trove.common.i18n import _


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class ClusterController(wsgi.Controller):

    """Controller for cluster functionality."""
    schemas = apischema.cluster.copy()

    @classmethod
    def get_action_schema(cls, body, action_schema):
        action_type = body.keys()[0]
        return action_schema.get(action_type, {})

    @classmethod
    def get_schema(cls, action, body):
        action_schema = super(ClusterController, cls).get_schema(action, body)
        if action == 'action':
            action_schema = cls.get_action_schema(body, action_schema)
        return action_schema

    def action(self, req, body, tenant_id, id):
        LOG.debug("Committing Action Against Cluster for "
                  "Tenant '%s'" % tenant_id)
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("id : '%s'\n\n") % id)
        if not body:
            raise exception.BadRequest(_("Invalid request body."))
        context = req.environ[wsgi.CONTEXT_KEY]
        cluster = models.Cluster.load(context, id)
        manager = cluster.datastore_version.manager
        api_strategy = strategy.load_api_strategy(manager)
        _actions = api_strategy.cluster_controller_actions
        selected_action = None
        for key in body:
            if key in _actions:
                selected_action = _actions[key]
                break
        else:
            message = _("No action '%(action)s' supplied "
                        "by strategy for manager '%(manager)s'") % (
                            {'action': key, 'manager': manager})
            raise exception.TroveError(message)
        return selected_action(cluster, body)

    def show(self, req, tenant_id, id):
        """Return a single cluster."""
        LOG.debug("Showing a Cluster for Tenant '%s'" % tenant_id)
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("id : '%s'\n\n") % id)

        context = req.environ[wsgi.CONTEXT_KEY]
        cluster = models.Cluster.load(context, id)
        return wsgi.Result(views.load_view(cluster, req=req).data(), 200)

    def show_instance(self, req, tenant_id, cluster_id, instance_id):
        """Return a single instance belonging to a cluster."""
        LOG.debug("Showing an Instance in a Cluster for Tenant '%s'"
                  % tenant_id)
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("cluster_id : '%s'\n\n") % cluster_id)
        LOG.info(_("instance_id : '%s'\n\n") % instance_id)

        context = req.environ[wsgi.CONTEXT_KEY]
        cluster = models.Cluster.load(context, cluster_id)
        instance = models.Cluster.load_instance(context, cluster.id,
                                                instance_id)
        return wsgi.Result(views.ClusterInstanceDetailView(
            instance, req=req).data(), 200)

    def delete(self, req, tenant_id, id):
        """Delete a cluster."""
        LOG.debug("Deleting a Cluster for Tenant '%s'" % tenant_id)
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("id : '%s'\n\n") % id)

        context = req.environ[wsgi.CONTEXT_KEY]
        cluster = models.Cluster.load(context, id)
        cluster.delete()
        return wsgi.Result(None, 202)

    def index(self, req, tenant_id):
        """Return a list of clusters."""
        LOG.debug("Showing a list of clusters for Tenant '%s'" % tenant_id)
        LOG.info(_("req : '%s'\n\n") % req)

        context = req.environ[wsgi.CONTEXT_KEY]
        if not context.is_admin and context.tenant != tenant_id:
            raise exception.TroveOperationAuthError(tenant_id=context.tenant)

        # load all clusters and instances for the tenant
        clusters, marker = models.Cluster.load_all(context, tenant_id)
        view = views.ClustersView(clusters, req=req)
        paged = pagination.SimplePaginatedDataView(req.url, 'clusters', view,
                                                   marker)
        return wsgi.Result(paged.data(), 200)

    def create(self, req, body, tenant_id):
        LOG.debug("Creating a Cluster for Tenant '%s'" % tenant_id)
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("body : '%s'\n\n") % body)

        context = req.environ[wsgi.CONTEXT_KEY]
        name = body['cluster']['name']
        datastore_args = body['cluster'].get('datastore', {})
        datastore, datastore_version = (
            datastore_models.get_datastore_version(**datastore_args))

        try:
            clusters_enabled = (CONF.get(datastore_version.manager)
                                .get('cluster_support'))
        except NoSuchOptError:
            clusters_enabled = False

        if not clusters_enabled:
            raise exception.ClusterDatastoreNotSupported(
                datastore=datastore.name,
                datastore_version=datastore_version.name)

        nodes = body['cluster']['instances']
        instances = []
        for node in nodes:
            flavor_id = utils.get_id_from_href(node['flavorRef'])
            volume_size = nics = availability_zone = None
            if 'volume' in node:
                volume_size = int(node['volume']['size'])
            if 'nics' in node:
                nics = node['nics']
            if 'availability_zone' in node:
                availability_zone = node['availability_zone']

            instances.append({"flavor_id": flavor_id,
                              "volume_size": volume_size,
                              "nics": nics,
                              "availability_zone": availability_zone})

        cluster = models.Cluster.create(context, name, datastore,
                                        datastore_version, instances)
        view = views.load_view(cluster, req=req, load_servers=False)
        return wsgi.Result(view.data(), 200)
