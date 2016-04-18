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

from trove.datastore import models as datastore_models
from trove.module import models


class ModuleView(object):

    def __init__(self, module):
        self.module = module

    def data(self):
        module_dict = dict(
            id=self.module.id,
            name=self.module.name,
            type=self.module.type,
            description=self.module.description,
            tenant_id=self.module.tenant_id,
            datastore_id=self.module.datastore_id,
            datastore_version_id=self.module.datastore_version_id,
            auto_apply=self.module.auto_apply,
            priority_apply=self.module.priority_apply,
            apply_order=self.module.apply_order,
            is_admin=self.module.is_admin,
            md5=self.module.md5,
            visible=self.module.visible,
            created=self.module.created,
            updated=self.module.updated)
        # add extra data to make results more legible
        if self.module.tenant_id:
            # This should be the tenant name, but until we figure out where
            # to get it from, use the tenant_id
            tenant = self.module.tenant_id
        else:
            tenant = models.Modules.MATCH_ALL_NAME
        module_dict["tenant"] = tenant
        datastore = self.module.datastore_id
        datastore_version = self.module.datastore_version_id
        if datastore:
            if datastore_version:
                ds, ds_ver = (
                    datastore_models.get_datastore_version(
                        type=datastore, version=datastore_version))
                datastore = ds.name
                datastore_version = ds_ver.name
            else:
                ds = datastore_models.Datastore.load(datastore)
                datastore = ds.name
                datastore_version = models.Modules.MATCH_ALL_NAME
        else:
            datastore = models.Modules.MATCH_ALL_NAME
            datastore_version = models.Modules.MATCH_ALL_NAME
        module_dict["datastore"] = datastore
        module_dict["datastore_version"] = datastore_version

        return {"module": module_dict}


class ModulesView(object):

    def __init__(self, modules):
        self.modules = modules

    def data(self):
        data = []

        for module in self.modules:
            data.append(self.data_for_module(module))

        return {"modules": data}

    def data_for_module(self, module):
        view = ModuleView(module)
        return view.data()['module']


class DetailedModuleView(ModuleView):

    def __init__(self, module):
        super(DetailedModuleView, self).__init__(module)

    def data(self, include_contents=False):
        return_value = super(DetailedModuleView, self).data()
        module_dict = return_value["module"]
        module_dict["live_update"] = self.module.live_update
        if hasattr(self.module, 'instance_count'):
            module_dict["instance_count"] = self.module.instance_count
        if include_contents:
            if not hasattr(self.module, 'encrypted_contents'):
                self.module.encrypted_contents = self.module.contents
                self.module.contents = models.Module.deprocess_contents(
                    self.module.contents)
            module_dict['contents'] = self.module.contents
        return {"module": module_dict}


def get_module_list(modules):
    module_list = []
    for module in modules:
        module_info = DetailedModuleView(module).data(
            include_contents=True)
        module_list.append(module_info)
    return module_list
