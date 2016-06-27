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

from oslo_config.cfg import NoSuchOptError
from oslo_log import log as logging

from trove.cluster import models
from trove.cluster import views
from trove.common import apischema
from trove.common import cfg
from trove.common import exception
from trove.common.i18n import _
from trove.common import notification
from trove.common.notification import StartNotification
from trove.common import pagination
from trove.common import policy
from trove.common import utils
from trove.common import wsgi
from trove.datastore import models as datastore_models


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class ClusterController(wsgi.Controller):

    """Controller for cluster functionality."""
    schemas = apischema.cluster.copy()

    @classmethod
    def authorize_cluster_action(cls, context, cluster_rule_name, cluster):
        policy.authorize_on_target(context, 'cluster:%s' % cluster_rule_name,
                                   {'tenant': cluster.tenant_id})

    @classmethod
    def get_action_schema(cls, body, action_schema):
        action_type = list(body.keys())[0]
        return action_schema.get(action_type, {})

    @classmethod
    def get_schema(cls, action, body):
        action_schema = super(ClusterController, cls).get_schema(action, body)
        if action == 'action':
            action_schema = cls.get_action_schema(body, action_schema)
        return action_schema

    def action(self, req, body, tenant_id, id):
        LOG.debug(("Committing Action Against Cluster for "
                   "Tenant '%(tenant_id)s'\n"
                   "req : '%(req)s'\n\nid : '%(id)s'\n\n") %
                  {"req": req, "id": id, "tenant_id": tenant_id})
        if not body:
            raise exception.BadRequest(_("Invalid request body."))

        if len(body) != 1:
            raise exception.BadRequest(_("Action request should have exactly"
                                         " one action specified in body"))
        context = req.environ[wsgi.CONTEXT_KEY]
        cluster = models.Cluster.load(context, id)
        if ('reset-status' in body and
                'force_delete' not in body['reset-status']):
            self.authorize_cluster_action(context, 'reset-status', cluster)
        elif ('reset-status' in body and
                'force_delete' in body['reset-status']):
            self.authorize_cluster_action(context, 'force_delete', cluster)
        else:
            self.authorize_cluster_action(context, 'action', cluster)
        cluster.action(context, req, *next(iter(body.items())))

        view = views.load_view(cluster, req=req, load_servers=False)
        wsgi_result = wsgi.Result(view.data(), 202)

        return wsgi_result

    def show(self, req, tenant_id, id):
        """Return a single cluster."""
        LOG.debug(("Showing a Cluster for Tenant '%(tenant_id)s'\n"
                   "req : '%(req)s'\n\nid : '%(id)s'\n\n") %
                  {"req": req, "id": id, "tenant_id": tenant_id})

        context = req.environ[wsgi.CONTEXT_KEY]
        cluster = models.Cluster.load(context, id)
        self.authorize_cluster_action(context, 'show', cluster)
        return wsgi.Result(views.load_view(cluster, req=req).data(), 200)

    def show_instance(self, req, tenant_id, cluster_id, instance_id):
        """Return a single instance belonging to a cluster."""
        LOG.debug(("Showing an Instance in a Cluster for Tenant "
                   "'%(tenant_id)s'\n"
                   "req : '%(req)s'\n\n"
                   "cluster_id : '%(cluster_id)s'\n\n"
                   "instance_id : '%(instance_id)s;\n\n") %
                  {"req": req, "tenant_id": tenant_id,
                   "cluster_id": cluster_id,
                   "instance_id": instance_id})

        context = req.environ[wsgi.CONTEXT_KEY]
        cluster = models.Cluster.load(context, cluster_id)
        self.authorize_cluster_action(context, 'show_instance', cluster)
        instance = models.Cluster.load_instance(context, cluster.id,
                                                instance_id)
        return wsgi.Result(views.ClusterInstanceDetailView(
            instance, req=req).data(), 200)

    def delete(self, req, tenant_id, id):
        """Delete a cluster."""
        LOG.debug(("Deleting a Cluster for Tenant '%(tenant_id)s'\n"
                   "req : '%(req)s'\n\nid : '%(id)s'\n\n") %
                  {"req": req, "id": id, "tenant_id": tenant_id})

        context = req.environ[wsgi.CONTEXT_KEY]
        cluster = models.Cluster.load(context, id)
        self.authorize_cluster_action(context, 'delete', cluster)
        context.notification = notification.DBaaSClusterDelete(context,
                                                               request=req)
        with StartNotification(context, cluster_id=id):
            cluster.delete()
        return wsgi.Result(None, 202)

    def index(self, req, tenant_id):
        """Return a list of clusters."""
        LOG.debug(("Showing a list of clusters for Tenant '%(tenant_id)s'\n"
                   "req : '%(req)s'\n\n") % {"req": req,
                                             "tenant_id": tenant_id})

        context = req.environ[wsgi.CONTEXT_KEY]

        # This theoretically allows the Admin tenant list clusters for
        # only one particular tenant as opposed to listing all clusters for
        # for all tenants.
        # * As far as I can tell this is the only call which actually uses the
        #   passed-in 'tenant_id' for anything.
        if not context.is_admin and context.tenant != tenant_id:
            raise exception.TroveOperationAuthError(tenant_id=context.tenant)

        # The rule checks that the currently authenticated tenant can perform
        # the 'cluster-list' action.
        policy.authorize_on_tenant(context, 'cluster:index')

        # load all clusters and instances for the tenant
        clusters, marker = models.Cluster.load_all(context, tenant_id)
        view = views.ClustersView(clusters, req=req)
        paged = pagination.SimplePaginatedDataView(req.url, 'clusters', view,
                                                   marker)
        return wsgi.Result(paged.data(), 200)

    def create(self, req, body, tenant_id):
        LOG.debug(("Creating a Cluster for Tenant '%(tenant_id)s'\n"
                   "req : '%(req)s'\n\nbody : '%(body)s'\n\n") %
                  {"tenant_id": tenant_id, "req": req, "body": body})

        context = req.environ[wsgi.CONTEXT_KEY]
        policy.authorize_on_tenant(context, 'cluster:create')

        name = body['cluster']['name']
        datastore_args = body['cluster'].get('datastore', {})
        datastore, datastore_version = (
            datastore_models.get_datastore_version(**datastore_args))

        # TODO(saurabhs): add extended_properties to apischema
        extended_properties = body['cluster'].get('extended_properties', {})

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
            volume_size = volume_type = nics = availability_zone = None
            modules = None
            if 'volume' in node:
                volume_size = int(node['volume']['size'])
                volume_type = node['volume'].get('type')
            if 'nics' in node:
                nics = node['nics']
            if 'availability_zone' in node:
                availability_zone = node['availability_zone']
            if 'modules' in node:
                modules = node['modules']

            instances.append({"flavor_id": flavor_id,
                              "volume_size": volume_size,
                              "volume_type": volume_type,
                              "nics": nics,
                              "availability_zone": availability_zone,
                              'region_name': node.get('region_name'),
                              "modules": modules})

        locality = body['cluster'].get('locality')
        if locality:
            locality_domain = ['affinity', 'anti-affinity']
            locality_domain_msg = ("Invalid locality '%s'. "
                                   "Must be one of ['%s']" %
                                   (locality,
                                    "', '".join(locality_domain)))
            if locality not in locality_domain:
                raise exception.BadRequest(msg=locality_domain_msg)

        context.notification = notification.DBaaSClusterCreate(context,
                                                               request=req)
        with StartNotification(context, name=name, datastore=datastore.name,
                               datastore_version=datastore_version.name):
            cluster = models.Cluster.create(context, name, datastore,
                                            datastore_version, instances,
                                            extended_properties,
                                            locality)
        cluster.locality = locality
        view = views.load_view(cluster, req=req, load_servers=False)
        return wsgi.Result(view.data(), 200)
