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
from trove.common import exception
from trove.common.i18n import _
from trove.common import pagination
from trove.common import policy
from trove.common import wsgi
from trove.datastore import models as datastore_models
from trove.instance import models as instance_models
from trove.instance import views as instance_views
from trove.module import models
from trove.module import views


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class ModuleController(wsgi.Controller):

    schemas = apischema.module

    @classmethod
    def authorize_module_action(cls, context, module_rule_name, module):
        """If a module is not owned by any particular tenant just check
        that the current tenant is allowed to perform the action.
        """
        if module.tenant_id is not None:
            policy.authorize_on_target(context, 'module:%s' % module_rule_name,
                                       {'tenant': module.tenant_id})
        else:
            policy.authorize_on_tenant(context, 'module:%s' % module_rule_name)

    def index(self, req, tenant_id):
        context = req.environ[wsgi.CONTEXT_KEY]
        policy.authorize_on_tenant(context, 'module:index')
        datastore = req.GET.get('datastore', '')
        if datastore and datastore.lower() != models.Modules.MATCH_ALL_NAME:
            ds, ds_ver = datastore_models.get_datastore_version(
                type=datastore)
            datastore = ds.id
        modules = models.Modules.load(context, datastore=datastore)
        view = views.ModulesView(modules)
        return wsgi.Result(view.data(), 200)

    def show(self, req, tenant_id, id):
        LOG.info(_("Showing module %s.") % id)

        context = req.environ[wsgi.CONTEXT_KEY]
        module = models.Module.load(context, id)
        self.authorize_module_action(context, 'show', module)
        module.instance_count = len(models.InstanceModules.load(
            context, module_id=module.id, md5=module.md5))

        return wsgi.Result(
            views.DetailedModuleView(module).data(), 200)

    def create(self, req, body, tenant_id):

        name = body['module']['name']
        LOG.info(_("Creating module '%s'") % name)

        context = req.environ[wsgi.CONTEXT_KEY]
        policy.authorize_on_tenant(context, 'module:create')
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
        priority_apply = body['module'].get('priority_apply', 0)
        apply_order = body['module'].get('apply_order', 5)
        full_access = body['module'].get('full_access', None)

        module = models.Module.create(
            context, name, module_type, contents,
            description, module_tenant_id, datastore, ds_version,
            auto_apply, visible, live_update, priority_apply,
            apply_order, full_access)
        view_data = views.DetailedModuleView(module)
        return wsgi.Result(view_data.data(), 200)

    def delete(self, req, tenant_id, id):
        LOG.info(_("Deleting module %s.") % id)

        context = req.environ[wsgi.CONTEXT_KEY]
        module = models.Module.load(context, id)
        self.authorize_module_action(context, 'delete', module)
        models.Module.delete(context, module)
        return wsgi.Result(None, 200)

    def update(self, req, body, tenant_id, id):
        LOG.info(_("Updating module %s.") % id)

        context = req.environ[wsgi.CONTEXT_KEY]
        module = models.Module.load(context, id)
        self.authorize_module_action(context, 'update', module)
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
        ds_changed = False
        ds_ver_changed = False
        if 'datastore' in body['module']:
            if 'type' in body['module']['datastore']:
                module.datastore_id = body['module']['datastore']['type']
                ds_changed = True
            if 'version' in body['module']['datastore']:
                module.datastore_version_id = (
                    body['module']['datastore']['version'])
                ds_ver_changed = True
        if 'all_datastores' in body['module']:
            if ds_changed:
                raise exception.ModuleInvalid(
                    reason=_('You cannot set a datastore and specify '
                             '--all_datastores'))
            module.datastore_id = None
        if 'all_datastore_versions' in body['module']:
            if ds_ver_changed:
                raise exception.ModuleInvalid(
                    reason=_('You cannot set a datastore version and specify '
                             '--all_datastore_versions'))
            module.datastore_version_id = None
        if 'auto_apply' in body['module']:
            module.auto_apply = body['module']['auto_apply']
        if 'visible' in body['module']:
            module.visible = body['module']['visible']
        if 'live_update' in body['module']:
            module.live_update = body['module']['live_update']
        if 'priority_apply' in body['module']:
            module.priority_apply = body['module']['priority_apply']
        if 'apply_order' in body['module']:
            module.apply_order = body['module']['apply_order']
        full_access = None
        if 'full_access' in body['module']:
            full_access = body['module']['full_access']

        models.Module.update(context, module, original_module, full_access)
        view_data = views.DetailedModuleView(module)
        return wsgi.Result(view_data.data(), 200)

    def instances(self, req, tenant_id, id):
        LOG.info(_("Getting instances for module %s.") % id)

        context = req.environ[wsgi.CONTEXT_KEY]

        module = models.Module.load(context, id)
        self.authorize_module_action(context, 'instances', module)

        count_only = req.GET.get('count_only', '').lower() == 'true'
        include_clustered = (
            req.GET.get('include_clustered', '').lower() == 'true')
        if count_only:
            instance_count = instance_models.module_instance_count(
                context, id, include_clustered=include_clustered)
            result_list = {
                'instances':
                instance_views.convert_instance_count_to_list(instance_count)}
        else:
            instance_modules, marker = models.InstanceModules.load(
                context, module_id=id)
            if instance_modules:
                instance_ids = [inst_mod.instance_id
                                for inst_mod in instance_modules]
                instances, marker = instance_models.Instances.load(
                    context, include_clustered, instance_ids=instance_ids)
            else:
                instances = []
                marker = None
            view = instance_views.InstancesView(instances, req=req)
            result_list = pagination.SimplePaginatedDataView(
                req.url, 'instances', view, marker).data()
        return wsgi.Result(result_list, 200)

    def reapply(self, req, body, tenant_id, id):
        LOG.info(_("Reapplying module %s to all instances.") % id)

        context = req.environ[wsgi.CONTEXT_KEY]
        md5 = None
        if 'md5' in body['reapply']:
            md5 = body['reapply']['md5']
        include_clustered = None
        if 'include_clustered' in body['reapply']:
            include_clustered = body['reapply']['include_clustered']
        if 'batch_size' in body['reapply']:
            batch_size = body['reapply']['batch_size']
        else:
            batch_size = CONF.module_reapply_max_batch_size
        if 'batch_delay' in body['reapply']:
            batch_delay = body['reapply']['batch_delay']
        else:
            batch_delay = CONF.module_reapply_min_batch_delay
        force = None
        if 'force' in body['reapply']:
            force = body['reapply']['force']
        module = models.Module.load(context, id)
        self.authorize_module_action(context, 'reapply', module)
        models.Module.reapply(context, id, md5, include_clustered,
                              batch_size, batch_delay, force)
        return wsgi.Result(None, 202)
