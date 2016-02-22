# Copyright 2016 Tesora, Inc.
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

import copy

from oslo_log import log as logging

import trove.common.apischema as apischema
from trove.common import cfg
from trove.common.i18n import _
from trove.common import pagination
from trove.common import wsgi
from trove.module import models
from trove.module import views


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class ModuleController(wsgi.Controller):

    schemas = apischema.module

    def index(self, req, tenant_id):
        context = req.environ[wsgi.CONTEXT_KEY]
        modules, marker = models.Modules.load(context)
        view = views.ModulesView(modules)
        paged = pagination.SimplePaginatedDataView(req.url, 'modules',
                                                   view, marker)
        return wsgi.Result(paged.data(), 200)

    def show(self, req, tenant_id, id):
        LOG.info(_("Showing module %s") % id)

        context = req.environ[wsgi.CONTEXT_KEY]
        module = models.Module.load(context, id)
        module.instance_count = models.DBInstanceModules.find_all(
            id=module.id, md5=module.md5,
            deleted=False).count()

        return wsgi.Result(
            views.DetailedModuleView(module).data(), 200)

    def create(self, req, body, tenant_id):

        name = body['module']['name']
        LOG.info(_("Creating module '%s'") % name)

        context = req.environ[wsgi.CONTEXT_KEY]
        module_type = body['module']['module_type']
        contents = body['module']['contents']

        description = body['module'].get('description')
        all_tenants = body['module'].get('all_tenants', 0)
        module_tenant_id = None if all_tenants else tenant_id
        datastore = body['module'].get('datastore', {}).get('type', None)
        ds_version = body['module'].get('datastore', {}).get('version', None)
        auto_apply = body['module'].get('auto_apply', 0)
        visible = body['module'].get('visible', 1)
        live_update = body['module'].get('live_update', 0)

        module = models.Module.create(
            context, name, module_type, contents,
            description, module_tenant_id, datastore, ds_version,
            auto_apply, visible, live_update)
        view_data = views.DetailedModuleView(module)
        return wsgi.Result(view_data.data(), 200)

    def delete(self, req, tenant_id, id):
        LOG.info(_("Deleting module %s") % id)

        context = req.environ[wsgi.CONTEXT_KEY]
        module = models.Module.load(context, id)
        models.Module.delete(context, module)
        return wsgi.Result(None, 200)

    def update(self, req, body, tenant_id, id):
        LOG.info(_("Updating module %s") % id)

        context = req.environ[wsgi.CONTEXT_KEY]
        module = models.Module.load(context, id)
        original_module = copy.deepcopy(module)
        if 'name' in body['module']:
            module.name = body['module']['name']
        if 'module_type' in body['module']:
            module.type = body['module']['module_type']
        if 'contents' in body['module']:
            module.contents = body['module']['contents']
        if 'description' in body['module']:
            module.description = body['module']['description']
        if 'all_tenants' in body['module']:
            module.tenant_id = (None if body['module']['all_tenants']
                                else tenant_id)
        if 'datastore' in body['module']:
            if 'type' in body['module']['datastore']:
                module.datastore_id = body['module']['datastore']['type']
            if 'version' in body['module']['datastore']:
                module.datastore_version_id = (
                    body['module']['datastore']['version'])
        if 'auto_apply' in body['module']:
            module.auto_apply = body['module']['auto_apply']
        if 'visible' in body['module']:
            module.visible = body['module']['visible']
        if 'live_update' in body['module']:
            module.live_update = body['module']['live_update']

        models.Module.update(context, module, original_module)
        view_data = views.DetailedModuleView(module)
        return wsgi.Result(view_data.data(), 200)
