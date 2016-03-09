# Copyright 2015 Tesora Inc.
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

from trove.common import cfg
from trove.common import exception
from trove.extensions.common.service import ClusterRootController
from trove.instance.models import DBInstance

LOG = logging.getLogger(__name__)
CONF = cfg.CONF
MANAGER = CONF.datastore_manager if CONF.datastore_manager else 'mongodb'


class MongoDBRootController(ClusterRootController):

    def delete(self, req, tenant_id, instance_id):
        raise exception.DatastoreOperationNotSupported(
            operation='disable_root', datastore=MANAGER)

    def _block_cluster_instance_actions(self):
        return True

    def _find_query_router_ids(self, tenant_id, cluster_id):
        args = {'tenant_id': tenant_id, 'cluster_id': cluster_id,
                'type': 'query_router'}
        query_router_instances = DBInstance.find_all(**args).all()
        return [db_instance.id for db_instance in query_router_instances]

    def _get_cluster_instance_id(self, tenant_id, cluster_id):
        instance_ids = self._find_cluster_node_ids(tenant_id, cluster_id)
        single_instance_id = self._find_query_router_ids(tenant_id,
                                                         cluster_id)[0]
        return single_instance_id, instance_ids
