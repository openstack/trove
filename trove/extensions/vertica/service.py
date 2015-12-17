# Copyright [2015] Hewlett-Packard Development Company, L.P.
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

from trove.common.i18n import _LI
from trove.common import wsgi
from trove.extensions.common.service import BaseDatastoreRootController
from trove.extensions.common import views
from trove.extensions.vertica import models
from trove.instance.models import DBInstance

LOG = logging.getLogger(__name__)


class VerticaRootController(BaseDatastoreRootController):

    def root_index(self, req, tenant_id, instance_id, is_cluster):
        """Returns True if root is enabled; False otherwise."""
        if is_cluster:
            return self.cluster_root_index(req, tenant_id, instance_id)
        else:
            return self.instance_root_index(req, tenant_id, instance_id)

    def instance_root_index(self, req, tenant_id, instance_id):
        LOG.info(_LI("Getting root enabled for instance '%s'.") % instance_id)
        LOG.info(_LI("req : '%s'\n\n") % req)
        context = req.environ[wsgi.CONTEXT_KEY]
        is_root_enabled = models.VerticaRoot.load(context, instance_id)
        return wsgi.Result(views.RootEnabledView(is_root_enabled).data(), 200)

    def cluster_root_index(self, req, tenant_id, cluster_id):
        LOG.info(_LI("Getting root enabled for cluster '%s'.") % cluster_id)
        master_instance_id, cluster_instances = self._get_cluster_instance_id(
            tenant_id, cluster_id)
        return self.instance_root_index(req, tenant_id, master_instance_id)

    def root_create(self, req, body, tenant_id, instance_id, is_cluster):
        if is_cluster:
            return self.cluster_root_create(req, body, tenant_id, instance_id)
        else:
            return self.instance_root_create(req, body, instance_id)

    def instance_root_create(self, req, body, instance_id,
                             cluster_instances=None):
        LOG.info(_LI("Enabling root for instance '%s'.") % instance_id)
        LOG.info(_LI("req : '%s'\n\n") % req)
        context = req.environ[wsgi.CONTEXT_KEY]
        user_name = context.user
        if body:
            password = body['password'] if 'password' in body else None
        else:
            password = None
        root = models.VerticaRoot.create(context, instance_id, user_name,
                                         password, cluster_instances)
        return wsgi.Result(views.RootCreatedView(root).data(), 200)

    def cluster_root_create(self, req, body, tenant_id, cluster_id):
        LOG.info(_LI("Enabling root for cluster '%s'.") % cluster_id)
        master_instance_id, cluster_instances = self._get_cluster_instance_id(
            tenant_id, cluster_id)
        return self.instance_root_create(req, body, master_instance_id,
                                         cluster_instances)

    def _get_cluster_instance_id(self, tenant_id, cluster_id):
        args = {'tenant_id': tenant_id, 'cluster_id': cluster_id}
        cluster_instances = DBInstance.find_all(**args).all()
        instance_ids = [db_instance.id for db_instance in cluster_instances]
        args = {'tenant_id': tenant_id, 'cluster_id': cluster_id, 'type':
                'master'}
        master_instance = DBInstance.find_by(**args)
        master_instance_id = master_instance.id
        return master_instance_id, instance_ids
