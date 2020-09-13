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

from oslo_log import log as logging
from oslo_utils import strutils

from trove.backup import views
from trove.backup.models import Backup
from trove.backup.models import BackupStrategy
from trove.common import apischema
from trove.common import exception
from trove.common import notification
from trove.common import pagination
from trove.common import policy
from trove.common import utils
from trove.common import wsgi
from trove.common.notification import StartNotification

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
        LOG.debug("Listing backups for tenant %s", tenant_id)
        datastore = req.GET.get('datastore')
        instance_id = req.GET.get('instance_id')
        project_id = req.GET.get('project_id')
        all_projects = strutils.bool_from_string(req.GET.get('all_projects'))
        context = req.environ[wsgi.CONTEXT_KEY]

        if project_id or all_projects:
            policy.authorize_on_tenant(context, 'backup:index:all_projects')
        else:
            policy.authorize_on_tenant(context, 'backup:index')

        backups, marker = Backup.list(
            context,
            datastore=datastore,
            instance_id=instance_id,
            project_id=project_id,
            all_projects=all_projects
        )
        view = views.BackupViews(backups)
        paged = pagination.SimplePaginatedDataView(req.url, 'backups', view,
                                                   marker)
        return wsgi.Result(paged.data(), 200)

    def show(self, req, tenant_id, id):
        """Return a single backup."""
        LOG.debug("Showing a backup for tenant %(tenant_id)s ID: '%(id)s'",
                  {'tenant_id': tenant_id, 'id': id})
        context = req.environ[wsgi.CONTEXT_KEY]
        backup = Backup.get_by_id(context, id)
        policy.authorize_on_target(context, 'backup:show',
                                   {'tenant': backup.tenant_id})
        return wsgi.Result(views.BackupView(backup).data(), 200)

    def create(self, req, body, tenant_id):
        LOG.info("Creating a backup for tenant %s", tenant_id)
        context = req.environ[wsgi.CONTEXT_KEY]
        policy.authorize_on_tenant(context, 'backup:create')
        data = body['backup']
        instance = data['instance']
        name = data['name']
        desc = data.get('description')
        parent = data.get('parent_id')
        incremental = data.get('incremental')
        swift_container = data.get('swift_container')

        context.notification = notification.DBaaSBackupCreate(context,
                                                              request=req)

        if not swift_container:
            instance_id = utils.get_id_from_href(instance)
            backup_strategy = BackupStrategy.get(context, instance_id)
            if backup_strategy:
                swift_container = backup_strategy.swift_container

        with StartNotification(context, name=name, instance_id=instance,
                               description=desc, parent_id=parent):
            backup = Backup.create(context, instance, name, desc,
                                   parent_id=parent, incremental=incremental,
                                   swift_container=swift_container)

        return wsgi.Result(views.BackupView(backup).data(), 202)

    def delete(self, req, tenant_id, id):
        LOG.info('Deleting backup for tenant %(tenant_id)s '
                 'ID: %(backup_id)s',
                 {'tenant_id': tenant_id, 'backup_id': id})
        context = req.environ[wsgi.CONTEXT_KEY]
        backup = Backup.get_by_id(context, id)
        policy.authorize_on_target(context, 'backup:delete',
                                   {'tenant': backup.tenant_id})
        context.notification = notification.DBaaSBackupDelete(context,
                                                              request=req)
        with StartNotification(context, backup_id=id):
            Backup.delete(context, id)
        return wsgi.Result(None, 202)


class BackupStrategyController(wsgi.Controller):
    schemas = apischema.backup_strategy

    def create(self, req, body, tenant_id):
        LOG.info("Creating or updating a backup strategy for tenant %s, "
                 "body: %s", tenant_id, body)
        context = req.environ[wsgi.CONTEXT_KEY]
        policy.authorize_on_tenant(context, 'backup_strategy:create')
        data = body['backup_strategy']

        instance_id = data.get('instance_id', '')
        swift_container = data.get('swift_container')

        backup_strategy = BackupStrategy.create(context, instance_id,
                                                swift_container)
        return wsgi.Result(
            views.BackupStrategyView(backup_strategy).data(), 202)

    def index(self, req, tenant_id):
        context = req.environ[wsgi.CONTEXT_KEY]
        instance_id = req.GET.get('instance_id')
        tenant_id = req.GET.get('project_id', context.project_id)
        LOG.info("Listing backup strateies for tenant %s", tenant_id)

        if tenant_id != context.project_id and not context.is_admin:
            raise exception.TroveOperationAuthError(
                tenant_id=context.project_id
            )
        policy.authorize_on_tenant(context, 'backup_strategy:index')

        result = BackupStrategy.list(context, tenant_id,
                                     instance_id=instance_id)
        view = views.BackupStrategiesView(result)
        return wsgi.Result(view.data(), 200)

    def delete(self, req, tenant_id):
        context = req.environ[wsgi.CONTEXT_KEY]
        instance_id = req.GET.get('instance_id', '')
        tenant_id = req.GET.get('project_id', context.project_id)
        LOG.info('Deleting backup strategies for tenant %s, instance_id=%s',
                 tenant_id, instance_id)

        if tenant_id != context.project_id and not context.is_admin:
            raise exception.TroveOperationAuthError(
                tenant_id=context.project_id
            )
        policy.authorize_on_tenant(context, 'backup_strategy:delete')

        BackupStrategy.delete(context, tenant_id, instance_id)

        return wsgi.Result(None, 202)
