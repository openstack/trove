#    Copyright 2012 OpenStack Foundation
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

import routes

from trove.backup.service import BackupController
from trove.cluster.service import ClusterController
from trove.common import wsgi
from trove.configuration.service import ConfigurationsController
from trove.configuration.service import ParametersController
from trove.datastore.service import DatastoreController
from trove.flavor.service import FlavorController
from trove.instance.service import InstanceController
from trove.limits.service import LimitsController
from trove.module.service import ModuleController
from trove.versions import VersionsController
from trove.volume_type.service import VolumeTypesController


class API(wsgi.Router):
    """Defines the API routes."""
    def __init__(self):
        mapper = routes.Mapper()
        super(API, self).__init__(mapper)
        self._instance_router(mapper)
        self._cluster_router(mapper)
        self._datastore_router(mapper)
        self._flavor_router(mapper)
        self._volume_type_router(mapper)
        self._versions_router(mapper)
        self._limits_router(mapper)
        self._backups_router(mapper)
        self._configurations_router(mapper)
        self._modules_router(mapper)

    def _versions_router(self, mapper):
        versions_resource = VersionsController().create_resource()
        mapper.connect("/",
                       controller=versions_resource,
                       action="show",
                       conditions={'method': ['GET']})

    def _datastore_router(self, mapper):
        datastore_resource = DatastoreController().create_resource()
        mapper.resource("datastore", "/{tenant_id}/datastores",
                        controller=datastore_resource)
        mapper.connect("/{tenant_id}/datastores/{datastore}/versions",
                       controller=datastore_resource,
                       action="version_index")
        mapper.connect("/{tenant_id}/datastores/{datastore}/versions/{id}",
                       controller=datastore_resource,
                       action="version_show")
        mapper.connect(
            "/{tenant_id}/datastores/{datastore}/versions/"
            "{version_id}/flavors",
            controller=datastore_resource,
            action="list_associated_flavors",
            conditions={'method': ['GET']}
        )
        mapper.connect(
            "/{tenant_id}/datastores/{datastore}/versions/"
            "{version_id}/volume-types",
            controller=datastore_resource,
            action="list_associated_volume_types",
            conditions={'method': ['GET']}
        )
        mapper.connect("/{tenant_id}/datastores/versions/{uuid}",
                       controller=datastore_resource,
                       action="version_show_by_uuid")

    def _instance_router(self, mapper):
        instance_resource = InstanceController().create_resource()
        mapper.connect("/{tenant_id}/instances",
                       controller=instance_resource,
                       action="index",
                       conditions={'method': ['GET']})
        mapper.connect("/{tenant_id}/instances",
                       controller=instance_resource,
                       action="create",
                       conditions={'method': ['POST']})
        mapper.connect("/{tenant_id}/instances/{id}",
                       controller=instance_resource,
                       action="show",
                       conditions={'method': ['GET']})
        mapper.connect("/{tenant_id}/instances/{id}/action",
                       controller=instance_resource,
                       action="action",
                       conditions={'method': ['POST']})
        mapper.connect("/{tenant_id}/instances/{id}",
                       controller=instance_resource,
                       action="update",
                       conditions={'method': ['PUT']})
        mapper.connect("/{tenant_id}/instances/{id}",
                       controller=instance_resource,
                       action="edit",
                       conditions={'method': ['PATCH']})
        mapper.connect("/{tenant_id}/instances/{id}",
                       controller=instance_resource,
                       action="delete",
                       conditions={'method': ['DELETE']})
        mapper.connect("/{tenant_id}/instances/{id}/backups",
                       controller=instance_resource,
                       action="backups",
                       conditions={'method': ['GET']})
        mapper.connect("/{tenant_id}/instances/{id}/configuration",
                       controller=instance_resource,
                       action="configuration",
                       conditions={'method': ['GET']})
        mapper.connect("/{tenant_id}/instances/{id}/log",
                       controller=instance_resource,
                       action="guest_log_list",
                       conditions={'method': ['GET']})
        mapper.connect("/{tenant_id}/instances/{id}/log",
                       controller=instance_resource,
                       action="guest_log_action",
                       conditions={'method': ['POST']})
        mapper.connect("/{tenant_id}/instances/{id}/modules",
                       controller=instance_resource,
                       action="module_list",
                       conditions={'method': ['GET']})
        mapper.connect("/{tenant_id}/instances/{id}/modules",
                       controller=instance_resource,
                       action="module_apply",
                       conditions={'method': ['POST']})
        mapper.connect("/{tenant_id}/instances/{id}/modules/{module_id}",
                       controller=instance_resource,
                       action="module_remove",
                       conditions={'method': ['DELETE']})

    def _cluster_router(self, mapper):
        cluster_resource = ClusterController().create_resource()
        mapper.connect("/{tenant_id}/clusters",
                       controller=cluster_resource,
                       action="index",
                       conditions={'method': ['GET']})
        mapper.connect("/{tenant_id}/clusters/{id}",
                       controller=cluster_resource,
                       action="show",
                       conditions={'method': ['GET']})
        mapper.connect("/{tenant_id}/clusters",
                       controller=cluster_resource,
                       action="create",
                       conditions={'method': ['POST']})
        mapper.connect("/{tenant_id}/clusters/{id}",
                       controller=cluster_resource,
                       action="action",
                       conditions={'method': ['POST']})
        mapper.connect("/{tenant_id}/clusters/{cluster_id}/instances/"
                       "{instance_id}",
                       controller=cluster_resource,
                       action="show_instance",
                       conditions={'method': ['GET']})
        mapper.connect("/{tenant_id}/clusters/{id}",
                       controller=cluster_resource,
                       action="delete",
                       conditions={'method': ['DELETE']})

    def _flavor_router(self, mapper):
        flavor_resource = FlavorController().create_resource()
        mapper.connect("/{tenant_id}/flavors",
                       controller=flavor_resource,
                       action="index",
                       conditions={'method': ['GET']})
        mapper.connect("/{tenant_id}/flavors/{id}",
                       controller=flavor_resource,
                       action="show",
                       conditions={'method': ['GET']})

    def _volume_type_router(self, mapper):
        volume_type_resource = VolumeTypesController().create_resource()
        mapper.connect("/{tenant_id}/volume-types",
                       controller=volume_type_resource,
                       action="index",
                       conditions={'method': ['GET']})
        mapper.connect("/{tenant_id}/volume-types/{id}",
                       controller=volume_type_resource,
                       action="show",
                       conditions={'method': ['GET']})

    def _limits_router(self, mapper):
        limits_resource = LimitsController().create_resource()
        mapper.connect("/{tenant_id}/limits",
                       controller=limits_resource,
                       action="index",
                       conditions={'method': ['GET']})

    def _backups_router(self, mapper):
        backups_resource = BackupController().create_resource()
        mapper.connect("/{tenant_id}/backups",
                       controller=backups_resource,
                       action="index",
                       conditions={'method': ['GET']})
        mapper.connect("/{tenant_id}/backups",
                       controller=backups_resource,
                       action="create",
                       conditions={'method': ['POST']})
        mapper.connect("/{tenant_id}/backups/{id}",
                       controller=backups_resource,
                       action="show",
                       conditions={'method': ['GET']})
        mapper.connect("/{tenant_id}/backups/{id}",
                       controller=backups_resource,
                       action="action",
                       conditions={'method': ['POST']})
        mapper.connect("/{tenant_id}/backups/{id}",
                       controller=backups_resource,
                       action="delete",
                       conditions={'method': ['DELETE']})

    def _modules_router(self, mapper):

        modules_resource = ModuleController().create_resource()
        mapper.resource("modules", "/{tenant_id}/modules",
                        controller=modules_resource)
        mapper.connect("/{tenant_id}/modules",
                       controller=modules_resource,
                       action="index",
                       conditions={'method': ['GET']})
        mapper.connect("/{tenant_id}/modules",
                       controller=modules_resource,
                       action="create",
                       conditions={'method': ['POST']})
        mapper.connect("/{tenant_id}/modules/{id}",
                       controller=modules_resource,
                       action="show",
                       conditions={'method': ['GET']})
        mapper.connect("/{tenant_id}/modules/{id}",
                       controller=modules_resource,
                       action="update",
                       conditions={'method': ['PUT']})
        mapper.connect("/{tenant_id}/modules/{id}",
                       controller=modules_resource,
                       action="delete",
                       conditions={'method': ['DELETE']})
        mapper.connect("/{tenant_id}/modules/{id}/instances",
                       controller=modules_resource,
                       action="instances",
                       conditions={'method': ['GET']})
        mapper.connect("/{tenant_id}/modules/{id}/instances",
                       controller=modules_resource,
                       action="reapply",
                       conditions={'method': ['PUT']})

    def _configurations_router(self, mapper):
        parameters_resource = ParametersController().create_resource()
        path = '/{tenant_id}/datastores/versions/{version}/parameters'
        mapper.connect(path,
                       controller=parameters_resource,
                       action='index_by_version',
                       conditions={'method': ['GET']})
        path = '/{tenant_id}/datastores/versions/{version}/parameters/{name}'
        mapper.connect(path,
                       controller=parameters_resource,
                       action='show_by_version',
                       conditions={'method': ['GET']})

        path = '/{tenant_id}/datastores/{datastore}/versions/{id}'
        mapper.connect(path + '/parameters',
                       controller=parameters_resource,
                       action='index',
                       conditions={'method': ['GET']})
        mapper.connect(path + '/parameters/{name}',
                       controller=parameters_resource,
                       action='show',
                       conditions={'method': ['GET']})

        configuration_resource = ConfigurationsController().create_resource()
        mapper.connect('/{tenant_id}/configurations',
                       controller=configuration_resource,
                       action='index',
                       conditions={'method': ['GET']})
        mapper.connect('/{tenant_id}/configurations',
                       controller=configuration_resource,
                       action='create',
                       conditions={'method': ['POST']})
        mapper.connect('/{tenant_id}/configurations/{id}',
                       controller=configuration_resource,
                       action='show',
                       conditions={'method': ['GET']})
        mapper.connect('/{tenant_id}/configurations/{id}/instances',
                       controller=configuration_resource,
                       action='instances',
                       conditions={'method': ['GET']})
        mapper.connect('/{tenant_id}/configurations/{id}',
                       controller=configuration_resource,
                       action='edit',
                       conditions={'method': ['PATCH']})
        mapper.connect('/{tenant_id}/configurations/{id}',
                       controller=configuration_resource,
                       action='update',
                       conditions={'method': ['PUT']})
        mapper.connect('/{tenant_id}/configurations/{id}',
                       controller=configuration_resource,
                       action='delete',
                       conditions={'method': ['DELETE']})


def app_factory(global_conf, **local_conf):
    return API()
