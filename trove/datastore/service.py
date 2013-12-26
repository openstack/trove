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

from trove.common import wsgi
from trove.datastore import models, views


class DatastoreController(wsgi.Controller):

    def show(self, req, tenant_id, id):
        datastore = models.Datastore.load(id)
        return wsgi.Result(views.
                           DatastoreView(datastore, req).data(), 200)

    def index(self, req, tenant_id):
        datastores = models.Datastores.load()
        return wsgi.Result(views.
                           DatastoresView(datastores, req).data(),
                           200)

    def version_show(self, req, tenant_id, datastore, id):
        datastore = models.Datastore.load(datastore)
        datastore_version = models.DatastoreVersion.load(datastore, id)
        return wsgi.Result(views.DatastoreVersionView(datastore_version,
                                                      req).data(), 200)

    def version_show_by_uuid(self, req, tenant_id, uuid):
        datastore_version = models.DatastoreVersion.load_by_uuid(uuid)
        return wsgi.Result(views.DatastoreVersionView(datastore_version,
                                                      req).data(), 200)

    def version_index(self, req, tenant_id, datastore):
        context = req.environ[wsgi.CONTEXT_KEY]
        only_active = True
        if context.is_admin:
            only_active = False
        datastore_versions = models.DatastoreVersions.load(datastore,
                                                           only_active)
        return wsgi.Result(views.
                           DatastoreVersionsView(datastore_versions,
                                                 req).data(), 200)
