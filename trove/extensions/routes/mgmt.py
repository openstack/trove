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

from trove.common import extensions
from trove.extensions.mgmt.clusters.service import MgmtClusterController
from trove.extensions.mgmt.configuration import service as conf_service
from trove.extensions.mgmt.datastores.service import DatastoreVersionController
from trove.extensions.mgmt.instances.service import MgmtInstanceController
from trove.extensions.mgmt.quota.service import QuotaController
from trove.extensions.mgmt.upgrade.service import UpgradeController


class Mgmt(extensions.ExtensionDescriptor):

    def get_name(self):
        return "Mgmt"

    def get_description(self):
        return "MGMT services such as details diagnostics"

    def get_alias(self):
        return "Mgmt"

    def get_namespace(self):
        return "http://TBD"

    def get_updated(self):
        return "2011-01-22T13:25:27-06:00"

    def get_resources(self):
        resources = []

        instances = extensions.ResourceExtension(
            '{tenant_id}/mgmt/instances',
            MgmtInstanceController(),
            member_actions={'root': 'GET',
                            'diagnostics': 'GET',
                            'hwinfo': 'GET',
                            'rpc_ping': 'GET',
                            'action': 'POST'})
        resources.append(instances)

        clusters = extensions.ResourceExtension(
            '{tenant_id}/mgmt/clusters',
            MgmtClusterController(),
            member_actions={'action': 'POST'})
        resources.append(clusters)

        quota = extensions.ResourceExtension(
            '{tenant_id}/mgmt/quotas',
            QuotaController(),
            member_actions={})
        resources.append(quota)

        upgrade = extensions.ResourceExtension(
            '{tenant_id}/mgmt/instances/{instance_id}/upgrade',
            UpgradeController(),
            member_actions={})
        resources.append(upgrade)

        datastore_configuration_parameters = extensions.ResourceExtension(
            '{tenant_id}/mgmt/datastores/versions/{version_id}/parameters',
            conf_service.ConfigurationsParameterController(),
            member_actions={})
        resources.append(datastore_configuration_parameters)

        datastore_version = extensions.ResourceExtension(
            '{tenant_id}/mgmt/datastore-versions',
            DatastoreVersionController(),
            member_actions={})
        resources.append(datastore_version)

        return resources
