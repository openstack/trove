# Copyright 2013 OpenStack Foundation
# Copyright 2013 Rackspace Hosting
# Copyright 2013 Hewlett-Packard Development Company, L.P.
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
#
from oslo_log import log as logging

from trove.common import exception
from trove.common import policy
from trove.common import wsgi
from trove.datastore import models, views
from trove.flavor import views as flavor_views
from trove.volume_type import views as volume_type_view

LOG = logging.getLogger(__name__)


class DatastoreController(wsgi.Controller):

    @classmethod
    def authorize_request(cls, req, rule_name):
        """Datastores are not owned by any particular tenant so we only check
        the current tenant is allowed to perform the action.
        """
        context = req.environ[wsgi.CONTEXT_KEY]
        policy.authorize_on_tenant(context, 'datastore:%s' % rule_name)

    def show(self, req, tenant_id, id):
        self.authorize_request(req, 'show')
        datastore = models.Datastore.load(id)
        datastore_versions = (models.DatastoreVersions.load(datastore.id))
        return wsgi.Result(views.
                           DatastoreView(datastore, datastore_versions,
                                         req).data(), 200)

    def index(self, req, tenant_id):
        self.authorize_request(req, 'index')
        context = req.environ[wsgi.CONTEXT_KEY]
        only_active = True
        if context.is_admin:
            only_active = False
        datastores = models.Datastores.load(only_active)
        datastores_versions = models.DatastoreVersions.load_all(only_active)
        return wsgi.Result(views.
                           DatastoresView(datastores, datastores_versions,
                                          req).data(), 200)

    def version_show(self, req, tenant_id, datastore, id):
        self.authorize_request(req, 'version_show')
        datastore = models.Datastore.load(datastore)
        datastore_version = models.DatastoreVersion.load(datastore, id)
        return wsgi.Result(views.DatastoreVersionView(datastore_version,
                                                      req).data(), 200)

    def version_show_by_uuid(self, req, tenant_id, uuid):
        self.authorize_request(req, 'version_show_by_uuid')
        datastore_version = models.DatastoreVersion.load_by_uuid(uuid)
        return wsgi.Result(views.DatastoreVersionView(datastore_version,
                                                      req).data(), 200)

    def version_index(self, req, tenant_id, datastore):
        self.authorize_request(req, 'version_index')
        context = req.environ[wsgi.CONTEXT_KEY]
        only_active = True
        if context.is_admin:
            only_active = False
        datastore_versions = models.DatastoreVersions.load(datastore,
                                                           only_active)
        return wsgi.Result(views.
                           DatastoreVersionsView(datastore_versions,
                                                 req).data(), 200)

    def list_associated_flavors(self, req, tenant_id, datastore,
                                version_id):
        """
        All nova flavors are returned for a datastore-version unless
        one or more entries are found in datastore_version_metadata,
        in which case only those are returned.
        """
        self.authorize_request(req, 'list_associated_flavors')
        context = req.environ[wsgi.CONTEXT_KEY]
        flavors = (models.DatastoreVersionMetadata.
                   list_datastore_version_flavor_associations(
                       context, datastore, version_id))
        return wsgi.Result(flavor_views.FlavorsView(flavors, req).data(), 200)

    def list_associated_volume_types(self, req, tenant_id, datastore,
                                     version_id):
        """
        Return all known volume types if no restrictions have been
        established in datastore_version_metadata, otherwise return
        that restricted set.
        """
        context = req.environ[wsgi.CONTEXT_KEY]
        volume_types = (models.DatastoreVersionMetadata.
                        allowed_datastore_version_volume_types(
                            context, datastore, version_id))
        return wsgi.Result(volume_type_view.VolumeTypesView(
            volume_types, req).data(), 200)

    def delete(self, req, tenant_id, id):
        """Remove an existing datastore."""
        self.authorize_request(req, 'delete')

        ds_versions = models.DatastoreVersions.load(id, only_active=False)
        if len(ds_versions.db_info.all()) > 0:
            raise exception.DatastoreVersionsExist(datastore=id)

        LOG.info("Deleting datastore %s", id)

        datastore = models.Datastore.load(id)
        datastore.delete()
        return wsgi.Result(None, 202)
