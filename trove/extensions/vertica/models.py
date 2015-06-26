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

from trove.extensions.common.models import Root
from trove.extensions.common.models import RootHistory

LOG = logging.getLogger(__name__)


class VerticaRoot(Root):

    @classmethod
    def create(cls, context, instance_id, user, root_password,
               cluster_instances_list=None):
        root_user = super(VerticaRoot, cls).create(context, instance_id,
                                                   user, root_password,
                                                   cluster_instances_list=None)

        if cluster_instances_list:
            for instance in cluster_instances_list:
                RootHistory.create(context, instance, user)

        return root_user
