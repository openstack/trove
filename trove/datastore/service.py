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
        datastore, datastore_version = models.get_datastore_version(datastore,
                                                                    id)
        return wsgi.Result(views.DatastoreVersionView(datastore_version,
                                                      req).data(), 200)

    def version_index(self, req, tenant_id, datastore):
        datastore_versions = models.DatastoreVersions.load(datastore)
        return wsgi.Result(views.
                           DatastoreVersionsView(datastore_versions,
                                                 req).data(), 200)
