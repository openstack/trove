# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2013 OpenStack Foundation
# Copyright 2013 Hewlett-Packard Development Company, L.P.
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

from trove.backup import views
from trove.backup.models import Backup
from trove.common import apischema
from trove.common import cfg
from trove.common import pagination
from trove.common import wsgi
from trove.openstack.common import log as logging
from trove.openstack.common.gettextutils import _

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class BackupController(wsgi.Controller):
    """
    Controller for accessing backups in the OpenStack API.
    """
    schemas = apischema.backup

    def index(self, req, tenant_id):
        """
        Return all backups information for a tenant ID.
        """
        LOG.debug("Listing Backups for tenant '%s'" % tenant_id)
        context = req.environ[wsgi.CONTEXT_KEY]
        backups, marker = Backup.list(context)
        view = views.BackupViews(backups)
        paged = pagination.SimplePaginatedDataView(req.url, 'backups', view,
                                                   marker)
        return wsgi.Result(paged.data(), 200)

    def show(self, req, tenant_id, id):
        """Return a single backup."""
        LOG.info(_("Showing a backup for tenant '%s'") % tenant_id)
        LOG.info(_("id : '%s'\n\n") % id)
        context = req.environ[wsgi.CONTEXT_KEY]
        backup = Backup.get_by_id(context, id)
        return wsgi.Result(views.BackupView(backup).data(), 200)

    def create(self, req, body, tenant_id):
        LOG.debug("Creating a Backup for tenant '%s'" % tenant_id)
        context = req.environ[wsgi.CONTEXT_KEY]
        data = body['backup']
        instance = data['instance']
        name = data['name']
        desc = data.get('description')
        backup = Backup.create(context, instance, name, desc)
        return wsgi.Result(views.BackupView(backup).data(), 202)

    def delete(self, req, tenant_id, id):
        LOG.debug("Delete Backup for tenant: %s, ID: %s" % (tenant_id, id))
        context = req.environ[wsgi.CONTEXT_KEY]
        Backup.delete(context, id)
        return wsgi.Result(None, 202)
