# Copyright [2015] Hewlett-Packard Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from glanceclient import exc as glance_exceptions
from oslo_log import log as logging

from trove.common import apischema
from trove.common.auth import admin_context
from trove.common import clients
from trove.common import exception
from trove.common import utils
from trove.common import wsgi
from trove.datastore import models
from trove.extensions.mgmt.datastores import views

LOG = logging.getLogger(__name__)


class DatastoreVersionController(wsgi.Controller):
    """Controller for datastore version registration functionality."""

    schemas = apischema.mgmt_datastore_version

    @admin_context
    def create(self, req, body, tenant_id):
        """Adds a new datastore version."""
        context = req.environ[wsgi.CONTEXT_KEY]
        datastore_name = body['version']['datastore_name']
        version_name = body['version']['name']
        manager = body['version']['datastore_manager']
        image_id = body['version']['image']
        packages = body['version']['packages']
        if type(packages) is list:
            packages = ','.join(packages)
        active = body['version']['active']
        default = body['version']['default']

        LOG.info("Tenant: '%(tenant)s' is adding the datastore "
                 "version: '%(version)s' to datastore: '%(datastore)s'",
                 {'tenant': tenant_id, 'version': version_name,
                  'datastore': datastore_name})

        client = clients.create_glance_client(context)
        try:
            client.images.get(image_id)
        except glance_exceptions.HTTPNotFound:
            raise exception.ImageNotFound(uuid=image_id)

        try:
            datastore = models.Datastore.load(datastore_name)
        except exception.DatastoreNotFound:
            # Create the datastore if datastore_name does not exists.
            LOG.info("Creating datastore %s", datastore_name)
            datastore = models.DBDatastore()
            datastore.id = utils.generate_uuid()
            datastore.name = datastore_name
            datastore.save()

        try:
            models.DatastoreVersion.load(datastore, version_name)
            raise exception.DatastoreVersionAlreadyExists(name=version_name)
        except exception.DatastoreVersionNotFound:
            models.update_datastore_version(datastore.name, version_name,
                                            manager, image_id, packages,
                                            active)

        if default:
            models.update_datastore(datastore.name, version_name)

        return wsgi.Result(None, 202)

    @admin_context
    def index(self, req, tenant_id):
        """Lists all datastore-versions for given datastore."""
        db_ds_versions = models.DatastoreVersions.load_all(only_active=False)
        datastore_versions = [models.DatastoreVersion.load_by_uuid(
            ds_version.id) for ds_version in db_ds_versions]

        return wsgi.Result(
            views.DatastoreVersionsView(datastore_versions).data(), 200)

    @admin_context
    def show(self, req, tenant_id, id):
        """Lists details of a datastore-version for given datastore."""
        datastore_version = models.DatastoreVersion.load_by_uuid(id)
        return wsgi.Result(
            views.DatastoreVersionView(datastore_version).data(),
            200)

    @admin_context
    def edit(self, req, body, tenant_id, id):
        """Updates the attributes of a datastore version."""
        context = req.environ[wsgi.CONTEXT_KEY]
        datastore_version = models.DatastoreVersion.load_by_uuid(id)

        LOG.info("Tenant: '%(tenant)s' is updating the datastore "
                 "version: '%(version)s' for datastore: '%(datastore)s'",
                 {'tenant': tenant_id, 'version': datastore_version.name,
                  'datastore': datastore_version.datastore_name})

        manager = body.get('datastore_manager', datastore_version.manager)
        image_id = body.get('image', datastore_version.image_id)
        active = body.get('active', datastore_version.active)
        default = body.get('default', None)
        packages = body.get('packages', datastore_version.packages)
        if type(packages) is list:
            packages = ','.join(packages)

        client = clients.create_glance_client(context)
        try:
            client.images.get(image_id)
        except glance_exceptions.HTTPNotFound:
            raise exception.ImageNotFound(uuid=image_id)

        models.update_datastore_version(datastore_version.datastore_name,
                                        datastore_version.name,
                                        manager, image_id, packages,
                                        active)

        if default:
            models.update_datastore(datastore_version.datastore_name,
                                    datastore_version.name)
        elif (default is False and datastore_version.default is True):
            models.update_datastore(datastore_version.datastore_name, None)

        return wsgi.Result(None, 202)

    @admin_context
    def delete(self, req, tenant_id, id):
        """Remove an existing datastore version."""
        datastore_version = models.DatastoreVersion.load_by_uuid(id)
        datastore = models.Datastore.load(datastore_version.datastore_id)

        LOG.info("Tenant: '%(tenant)s' is removing the datastore "
                 "version: '%(version)s' for datastore: '%(datastore)s'",
                 {'tenant': tenant_id, 'version': datastore_version.name,
                  'datastore': datastore.name})

        if datastore.default_version_id == datastore_version.id:
            models.update_datastore(datastore.name, None)
        datastore_version.delete()
        return wsgi.Result(None, 202)
