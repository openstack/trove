# Copyright [2016] Hewlett-Packard Development Company, L.P.
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

from trove.common import cfg
from trove.common import exception
from trove.extensions.common.service import ClusterRootController

CONF = cfg.CONF
MANAGER = CONF.datastore_manager if CONF.datastore_manager else 'pxc'


class PxcRootController(ClusterRootController):

    def root_delete(self, req, tenant_id, instance_id, is_cluster):
        raise exception.DatastoreOperationNotSupported(
            operation='disable_root', datastore=MANAGER)
