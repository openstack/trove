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

from oslo_log import log as logging

from trove.backup import models as backup_model
from trove.common import apischema
from trove.common import clients
from trove.common import exception
from trove.common import glance as common_glance
from trove.common import utils
from trove.common import wsgi
from trove.common.auth import admin_context
from trove.configuration import models as config_model
from trove.datastore import models
from trove.extensions.mgmt.datastores import views
from trove.instance import models as instance_model

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
        image_id = body['version'].get('image')
        image_tags = body['version'].get('image_tags')
        packages = body['version'].get('packages')
        if type(packages) is list:
            packages = ','.join(packages)
        active = body['version']['active']
        default = body['version'].get('default', False)
        # For backward compatibility, use name as default value for version if
        # not specified
        version_str = body['version'].get('version', version_name)

        LOG.info("Tenant: '%(tenant)s' is adding the datastore "
                 "version: '%(version)s' to datastore: '%(datastore)s'",
                 {'tenant': tenant_id, 'version': version_name,
                  'datastore': datastore_name})

        if not image_id and not image_tags:
            raise exception.BadRequest("Image must be specified.")

        client = clients.create_glance_client(context)
        common_glance.get_image_id(client, image_id, image_tags)

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
            models.DatastoreVersion.load(datastore, version_name,
                                         version=version_str)
            raise exception.DatastoreVersionAlreadyExists(
                name=version_name, version=version_str)
        except exception.DatastoreVersionNotFound:
            models.update_datastore_version(datastore.name, version_name,
                                            manager, image_id, image_tags,
                                            packages, active,
                                            version=version_str)

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
                 "version: '%(id)s' for datastore: '%(datastore)s'",
                 {'tenant': tenant_id, 'id': id,
                  'datastore': datastore_version.datastore_name})

        name = body.get('name', datastore_version.name)
        manager = body.get('datastore_manager', datastore_version.manager)
        image_id = body.get('image')
        image_tags = body.get('image_tags')
        active = body.get('active', datastore_version.active)
        default = body.get('default', None)
        packages = body.get('packages', datastore_version.packages)
        if type(packages) is list:
            packages = ','.join(packages)

        if image_id or image_tags:
            client = clients.create_glance_client(context)
            common_glance.get_image_id(client, image_id, image_tags)

        if not image_id and image_tags:
            # Remove the image ID from the datastore version.
            image_id = ""

        if image_id is None:
            image_id = datastore_version.image_id
        if image_tags is None:
            image_tags = datastore_version.image_tags
            if type(image_tags) is str:
                image_tags = image_tags.split(',')

        if not image_id and not image_tags:
            raise exception.BadRequest("Image must be specified.")

        models.update_datastore_version(datastore_version.datastore_name,
                                        datastore_version.name,
                                        manager, image_id, image_tags,
                                        packages, active,
                                        version=datastore_version.version,
                                        new_name=name)

        if default:
            models.update_datastore(datastore_version.datastore_name,
                                    datastore_version.name)
        elif (default is False and datastore_version.default is True):
            models.update_datastore(datastore_version.datastore_name, None)

        return wsgi.Result(None, 202)

    @admin_context
    def delete(self, req, tenant_id, id):
        """Remove an existing datastore version."""
        instances = instance_model.DBInstance.find_all(
            datastore_version_id=id, deleted=0).all()
        if len(instances) > 0:
            raise exception.DatastoreVersionsInUse(resource='instance')

        backups = backup_model.DBBackup.find_all(
            datastore_version_id=id, deleted=0).all()
        if len(backups) > 0:
            raise exception.DatastoreVersionsInUse(resource='backup')

        configs = config_model.DBConfiguration.find_all(
            datastore_version_id=id, deleted=0).all()
        if len(configs) > 0:
            raise exception.DatastoreVersionsInUse(resource='configuration')

        datastore_version = models.DatastoreVersion.load_by_uuid(id)
        datastore = models.Datastore.load(datastore_version.datastore_id)

        LOG.info("Tenant: '%(tenant)s' is removing the datastore "
                 "version: '%(version)s' for datastore: '%(datastore)s'",
                 {'tenant': tenant_id, 'version': datastore_version.name,
                  'datastore': datastore.name})

        # Remove the config parameters associated with the datastore version
        LOG.debug(f"Deleting config parameters for datastore version {id}")
        db_params = config_model.DatastoreConfigurationParameters. \
            load_parameters(id)
        for db_param in db_params:
            db_param.delete()

        if datastore.default_version_id == datastore_version.id:
            models.update_datastore(datastore.name, None)
        datastore_version.delete()
        return wsgi.Result(None, 202)
