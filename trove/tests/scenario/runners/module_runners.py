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

import Crypto.Random
from proboscis import SkipTest
import re
import tempfile
import time

from troveclient.compat import exceptions

from trove.common import exception
from trove.common.utils import poll_until
from trove.guestagent.common import guestagent_utils
from trove.guestagent.common import operating_system
from trove.module import models
from trove.tests.scenario.runners.test_runners import TestRunner


class ModuleRunner(TestRunner):

    def __init__(self):
        super(ModuleRunner, self).__init__()

        self.MODULE_CONTENTS_PATTERN = 'Message=%s\n'
        self.MODULE_MESSAGE_PATTERN = 'Hello World from: %s'
        self.MODULE_NAME = 'test_module_1'
        self.MODULE_DESC = 'test description'
        self.MODULE_NEG_CONTENTS = 'contents for negative tests'
        self.MODULE_BINARY_SUFFIX = '_bin_auto'
        self.MODULE_BINARY_SUFFIX2 = self.MODULE_BINARY_SUFFIX + '_2'
        self.MODULE_BINARY_CONTENTS = Crypto.Random.new().read(20)
        self.MODULE_BINARY_CONTENTS2 = '\x00\xFF\xea\x9c\x11\xfeok\xb1\x8ax'

        self.module_name_order = [
            {'suffix': self.MODULE_BINARY_SUFFIX,
             'priority': True, 'order': 1},
            {'suffix': self.MODULE_BINARY_SUFFIX2,
             'priority': True, 'order': 2},
            {'suffix': '_hidden_all_tenant_auto_priority',
             'priority': True, 'order': 3},
            {'suffix': '_hidden', 'priority': True, 'order': 4},
            {'suffix': '_auto', 'priority': True, 'order': 5},
            {'suffix': '_live', 'priority': True, 'order': 6},
            {'suffix': '_priority', 'priority': True, 'order': 7},
            {'suffix': '_ds', 'priority': False, 'order': 1},
            {'suffix': '_ds_ver', 'priority': False, 'order': 2},
            {'suffix': '_all_tenant_ds_ver', 'priority': False, 'order': 3},
            {'suffix': '', 'priority': False, 'order': 4},
            {'suffix': '_ds_diff', 'priority': False, 'order': 5},
            {'suffix': '_diff_tenant', 'priority': False, 'order': 6},
            {'suffix': '_full_access', 'priority': False, 'order': 7},
            {'suffix': '_for_update', 'priority': False, 'order': 8},
            {'suffix': '_updated', 'priority': False, 'order': 8},
        ]

        self.apply_count = 0
        self.mod_inst_id = None
        self.mod_inst_apply_count = 0
        self.temp_module = None
        self.live_update_orig_md5 = None
        self.reapply_max_upd_date = None
        self._module_type = None

        self.test_modules = []
        self.module_count_prior_to_create = 0
        self.module_ds_count_prior_to_create = 0
        self.module_ds_all_count_prior_to_create = 0
        self.module_all_tenant_count_prior_to_create = 0
        self.module_auto_apply_count_prior_to_create = 0
        self.module_admin_count_prior_to_create = 0
        self.module_other_count_prior_to_create = 0

        self.module_create_count = 0
        self.module_ds_create_count = 0
        self.module_ds_all_create_count = 0
        self.module_all_tenant_create_count = 0
        self.module_auto_apply_create_count = 0
        self.module_admin_create_count = 0
        self.module_other_create_count = 0

    @property
    def module_type(self):
        if not self._module_type:
            self._module_type = self.test_helper.get_valid_module_type()
        return self._module_type

    def _get_test_module(self, index):
        if not self.test_modules or len(self.test_modules) < (index + 1):
            raise SkipTest("Requested module not created")
        return self.test_modules[index]

    @property
    def main_test_module(self):
        return self._get_test_module(0)

    @property
    def update_test_module(self):
        return self._get_test_module(1)

    @property
    def live_update_test_module(self):
        return self._find_live_update_module()

    def build_module_args(self, name_order=None):
        suffix = "_unknown"
        priority = False
        order = 5
        if name_order is not None:
            name_rec = self.module_name_order[name_order]
            suffix = name_rec['suffix']
            priority = name_rec['priority']
            order = name_rec['order']
        name = self.MODULE_NAME + suffix
        description = self.MODULE_DESC + suffix.replace('_', ' ')
        contents = self.get_module_contents(name)
        return name, description, contents, priority, order

    def get_module_contents(self, name=None):
        message = self.get_module_message(name=name)
        return self.MODULE_CONTENTS_PATTERN % message

    def get_module_message(self, name=None):
        name = name or self.MODULE_NAME
        return self.MODULE_MESSAGE_PATTERN % name

    def _find_invisible_module(self):
        def _match(mod):
            return not mod.visible and mod.tenant_id and not mod.auto_apply
        return self._find_module(_match, "Could not find invisible module")

    def _find_module(self, match_fn, not_found_message, find_all=False,
                     fail_on_not_found=True):
        found = [] if find_all else None
        for test_module in self.test_modules:
            if match_fn(test_module):
                if find_all:
                    found.append(test_module)
                else:
                    found = test_module
                    break
        if not found:
            if fail_on_not_found:
                self.fail(not_found_message)
            else:
                SkipTest(not_found_message)
        return found

    def _find_auto_apply_module(self):
        def _match(mod):
            return mod.auto_apply and mod.tenant_id and mod.visible
        return self._find_module(_match, "Could not find auto-apply module")

    def _find_live_update_module(self):
        def _match(mod):
            return mod.live_update and mod.tenant_id and mod.visible
        return self._find_module(_match, "Could not find live-update module")

    def _find_all_tenant_module(self):
        def _match(mod):
            return mod.tenant_id is None and mod.visible
        return self._find_module(_match, "Could not find all tenant module")

    def _find_priority_apply_module(self):
        def _match(mod):
            return mod.priority_apply and mod.tenant_id and mod.visible
        return self._find_module(_match,
                                 "Could not find priority-apply module")

    def _find_diff_datastore_module(self):
        def _match(mod):
            return (mod.datastore and
                    mod.datastore != models.Modules.MATCH_ALL_NAME and
                    mod.datastore != self.instance_info.dbaas_datastore)
        return self._find_module(_match,
                                 "Could not find different datastore module",
                                 fail_on_not_found=False)

    def _find_all_auto_apply_modules(self, visible=None):
        def _match(mod):
            return mod.auto_apply and (
                visible is None or mod.visible == visible)
        return self._find_module(
            _match, "Could not find all auto apply modules", find_all=True)

    def _find_module_by_id(self, module_id):
        def _match(mod):
            return mod.id == module_id
        return self._find_module(_match, "Could not find module with id %s" %
                                 module_id)

    # Tests start here
    def run_module_delete_existing(self):
        modules = self.admin_client.modules.list()
        for module in modules:
            if module.name.startswith(self.MODULE_NAME):
                self.admin_client.modules.delete(module.id)

    def run_module_create_bad_type(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        client = self.auth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.modules.create,
            self.MODULE_NAME, 'invalid-type', self.MODULE_NEG_CONTENTS)

    def run_module_create_non_admin_auto(
            self, expected_exception=exceptions.Forbidden,
            expected_http_code=403):
        client = self.auth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.modules.create,
            self.MODULE_NAME, self.module_type, self.MODULE_NEG_CONTENTS,
            auto_apply=True)

    def run_module_create_non_admin_all_tenant(
            self, expected_exception=exceptions.Forbidden,
            expected_http_code=403):
        client = self.auth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.modules.create,
            self.MODULE_NAME, self.module_type, self.MODULE_NEG_CONTENTS,
            all_tenants=True)

    def run_module_create_non_admin_hidden(
            self, expected_exception=exceptions.Forbidden,
            expected_http_code=403):
        client = self.auth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.modules.create,
            self.MODULE_NAME, self.module_type, self.MODULE_NEG_CONTENTS,
            visible=False)

    def run_module_create_non_admin_priority(
            self, expected_exception=exceptions.Forbidden,
            expected_http_code=403):
        client = self.auth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.modules.create,
            self.MODULE_NAME, self.module_type, self.MODULE_NEG_CONTENTS,
            priority_apply=True)

    def run_module_create_non_admin_no_full_access(
            self, expected_exception=exceptions.Forbidden,
            expected_http_code=403):
        client = self.auth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.modules.create,
            self.MODULE_NAME, self.module_type, self.MODULE_NEG_CONTENTS,
            full_access=False)

    def run_module_create_full_access_with_admin_opt(
            self, expected_exception=exceptions.BadRequest,
            expected_http_code=400):
        client = self.admin_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.modules.create,
            self.MODULE_NAME, self.module_type, self.MODULE_NEG_CONTENTS,
            full_access=True, auto_apply=True)

    def run_module_create_bad_datastore(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        client = self.auth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.modules.create,
            self.MODULE_NAME, self.module_type, self.MODULE_NEG_CONTENTS,
            datastore='bad-datastore')

    def run_module_create_bad_datastore_version(
            self, expected_exception=exceptions.BadRequest,
            expected_http_code=400):
        client = self.auth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.modules.create,
            self.MODULE_NAME, self.module_type, self.MODULE_NEG_CONTENTS,
            datastore=self.instance_info.dbaas_datastore,
            datastore_version='bad-datastore-version')

    def run_module_create_missing_datastore(
            self, expected_exception=exceptions.BadRequest,
            expected_http_code=400):
        client = self.auth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.modules.create,
            self.MODULE_NAME, self.module_type, self.MODULE_NEG_CONTENTS,
            datastore_version=self.instance_info.dbaas_datastore_version)

    def run_module_create(self):
        # Necessary to test that the count increases.
        self.module_count_prior_to_create = len(
            self.auth_client.modules.list())
        self.module_ds_count_prior_to_create = len(
            self.auth_client.modules.list(
                datastore=self.instance_info.dbaas_datastore))
        self.module_ds_all_count_prior_to_create = len(
            self.auth_client.modules.list(
                datastore=models.Modules.MATCH_ALL_NAME))
        self.module_all_tenant_count_prior_to_create = len(
            self.unauth_client.modules.list())
        self.module_auto_apply_count_prior_to_create = len(
            [module for module in self.admin_client.modules.list()
             if module.auto_apply])
        self.module_admin_count_prior_to_create = len(
            self.admin_client.modules.list())
        self.module_other_count_prior_to_create = len(
            self.unauth_client.modules.list())
        self.assert_module_create(self.auth_client, 10)

    def assert_module_create(self, client, name_order,
                             name=None, module_type=None,
                             contents=None, description=None,
                             all_tenants=False,
                             datastore=None, datastore_version=None,
                             auto_apply=False,
                             live_update=False, visible=True,
                             priority_apply=None,
                             apply_order=None,
                             full_access=None):
        (temp_name, temp_description, temp_contents,
         temp_priority, temp_order) = self.build_module_args(name_order)
        name = name if name is not None else temp_name
        description = (
            description if description is not None else temp_description)
        contents = contents if contents is not None else temp_contents
        priority_apply = (
            priority_apply if priority_apply is not None else temp_priority)
        apply_order = apply_order if apply_order is not None else temp_order
        module_type = module_type or self.module_type
        result = client.modules.create(
            name, module_type, contents,
            description=description,
            all_tenants=all_tenants,
            datastore=datastore, datastore_version=datastore_version,
            auto_apply=auto_apply,
            live_update=live_update, visible=visible,
            priority_apply=priority_apply,
            apply_order=apply_order,
            full_access=full_access)
        username = client.real_client.client.username
        if (('alt' in username and 'admin' not in username) or
                ('admin' in username and visible)):
            self.module_create_count += 1
            if datastore:
                if datastore == self.instance_info.dbaas_datastore:
                    self.module_ds_create_count += 1
            else:
                self.module_ds_all_create_count += 1
        elif not visible:
            self.module_admin_create_count += 1
        else:
            self.module_other_create_count += 1
        if all_tenants and visible:
            self.module_all_tenant_create_count += 1
        if auto_apply and visible:
            self.module_auto_apply_create_count += 1
        self.test_modules.append(result)

        tenant_id = None
        tenant = models.Modules.MATCH_ALL_NAME
        if not all_tenants:
            tenant, tenant_id = self.get_client_tenant(client)
            # If we find a way to grab the tenant name in the module
            # stuff, the line below can be removed
            tenant = tenant_id
        datastore = datastore or models.Modules.MATCH_ALL_NAME
        datastore_version = datastore_version or models.Modules.MATCH_ALL_NAME
        self.validate_module(
            result, validate_all=False,
            expected_name=name,
            expected_module_type=module_type,
            expected_description=description,
            expected_tenant=tenant,
            expected_tenant_id=tenant_id,
            expected_datastore=datastore,
            expected_datastore_version=datastore_version,
            expected_auto_apply=auto_apply,
            expected_contents=contents,
            expected_is_admin=('admin' in username and not full_access))

    def validate_module(self, module, validate_all=False,
                        expected_name=None,
                        expected_module_type=None,
                        expected_description=None,
                        expected_tenant=None,
                        expected_tenant_id=None,
                        expected_datastore=None,
                        expected_datastore_id=None,
                        expected_all_datastores=None,
                        expected_datastore_version=None,
                        expected_datastore_version_id=None,
                        expected_all_datastore_versions=None,
                        expected_all_tenants=None,
                        expected_auto_apply=None,
                        expected_live_update=None,
                        expected_visible=None,
                        expected_contents=None,
                        expected_priority_apply=None,
                        expected_apply_order=None,
                        expected_is_admin=None,
                        expected_full_access=None):

        if expected_all_tenants:
            expected_tenant = expected_tenant or models.Modules.MATCH_ALL_NAME
        if expected_all_datastores:
            expected_datastore = models.Modules.MATCH_ALL_NAME
            expected_datastore_id = None
        if expected_all_datastore_versions:
            expected_datastore_version = models.Modules.MATCH_ALL_NAME
            expected_datastore_version_id = None
        if expected_name:
            self.assert_equal(expected_name, module.name,
                              'Unexpected module name')
        if expected_module_type:
            self.assert_equal(expected_module_type.lower(), module.type,
                              'Unexpected module type')
        if expected_description:
            self.assert_equal(expected_description, module.description,
                              'Unexpected module description')
        if expected_tenant_id:
            self.assert_equal(expected_tenant_id, module.tenant_id,
                              'Unexpected tenant id')
        if expected_tenant:
            self.assert_equal(expected_tenant, module.tenant,
                              'Unexpected tenant name')
        if expected_datastore:
            self.assert_equal(expected_datastore, module.datastore,
                              'Unexpected datastore')
        if expected_datastore_version:
            self.assert_equal(expected_datastore_version,
                              module.datastore_version,
                              'Unexpected datastore version')
        if expected_auto_apply is not None:
            self.assert_equal(expected_auto_apply, module.auto_apply,
                              'Unexpected auto_apply')
        if expected_priority_apply is not None:
            self.assert_equal(expected_priority_apply, module.priority_apply,
                              'Unexpected priority_apply')
        if expected_apply_order is not None:
            self.assert_equal(expected_apply_order, module.apply_order,
                              'Unexpected apply_order')
        if expected_is_admin is not None:
            self.assert_equal(expected_is_admin, module.is_admin,
                              'Unexpected is_admin')
        if expected_full_access is not None:
            self.assert_equal(expected_full_access, not module.is_admin,
                              'Unexpected full_access')
        if validate_all:
            if expected_datastore_id:
                self.assert_equal(expected_datastore_id, module.datastore_id,
                                  'Unexpected datastore id')
            if expected_datastore_version_id:
                self.assert_equal(expected_datastore_version_id,
                                  module.datastore_version_id,
                                  'Unexpected datastore version id')
            if expected_live_update is not None:
                self.assert_equal(expected_live_update, module.live_update,
                                  'Unexpected live_update')
            if expected_visible is not None:
                self.assert_equal(expected_visible, module.visible,
                                  'Unexpected visible')

    def run_module_create_for_update(self):
        self.assert_module_create(self.auth_client, 14)

    def run_module_create_dupe(
            self, expected_exception=exceptions.BadRequest,
            expected_http_code=400):
        client = self.auth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.modules.create,
            self.MODULE_NAME, self.module_type, self.MODULE_NEG_CONTENTS)

    def run_module_update_missing_datastore(
            self, expected_exception=exceptions.BadRequest,
            expected_http_code=400):
        client = self.auth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.modules.update,
            self.update_test_module.id,
            datastore_version=self.instance_info.dbaas_datastore_version)

    def run_module_create_bin(self):
        self.assert_module_create(
            self.admin_client, 0,
            contents=self.MODULE_BINARY_CONTENTS,
            auto_apply=True, visible=False)

    def run_module_create_bin2(self):
        self.assert_module_create(
            self.admin_client, 1,
            contents=self.MODULE_BINARY_CONTENTS2,
            auto_apply=True, visible=False)

    def run_module_show(self):
        test_module = self.main_test_module
        result = self.auth_client.modules.get(test_module.id)
        self.validate_module(
            result, validate_all=True,
            expected_name=test_module.name,
            expected_module_type=test_module.type,
            expected_description=test_module.description,
            expected_tenant=test_module.tenant,
            expected_datastore=test_module.datastore,
            expected_datastore_version=test_module.datastore_version,
            expected_auto_apply=test_module.auto_apply,
            expected_live_update=False,
            expected_visible=True,
            expected_priority_apply=test_module.priority_apply,
            expected_apply_order=test_module.apply_order,
            expected_is_admin=test_module.is_admin)

    def run_module_show_unauth_user(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        client = self.unauth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.modules.get, self.main_test_module.id)

    def run_module_list(self):
        self.assert_module_list(
            self.auth_client,
            self.module_count_prior_to_create + self.module_create_count)

    def assert_module_list(self, client, expected_count, datastore=None):
        if datastore:
            module_list = client.modules.list(datastore=datastore)
        else:
            module_list = client.modules.list()
        self.assert_equal(expected_count, len(module_list),
                          "Wrong number of modules for list")
        for module in module_list:
            # only validate the test modules
            if module.name.startswith(self.MODULE_NAME):
                test_module = self._find_module_by_id(module.id)
                self.validate_module(
                    module, validate_all=True,
                    expected_name=test_module.name,
                    expected_module_type=test_module.type,
                    expected_description=test_module.description,
                    expected_tenant=test_module.tenant,
                    expected_datastore=test_module.datastore,
                    expected_datastore_version=test_module.datastore_version,
                    expected_auto_apply=test_module.auto_apply,
                    expected_priority_apply=test_module.priority_apply,
                    expected_apply_order=test_module.apply_order,
                    expected_is_admin=test_module.is_admin)

    def run_module_list_unauth_user(self):
        self.assert_module_list(
            self.unauth_client,
            (self.module_all_tenant_count_prior_to_create +
             self.module_all_tenant_create_count +
             self.module_other_create_count))

    def run_module_create_admin_all(self):
        self.assert_module_create(
            self.admin_client, 2,
            all_tenants=True,
            visible=False,
            auto_apply=True)

    def run_module_create_admin_hidden(self):
        self.assert_module_create(
            self.admin_client, 3,
            visible=False)

    def run_module_create_admin_auto(self):
        self.assert_module_create(
            self.admin_client, 4,
            auto_apply=True)

    def run_module_create_admin_live_update(self):
        self.assert_module_create(
            self.admin_client, 5,
            live_update=True)
        self.live_update_orig_md5 = self.test_modules[-1].md5

    def run_module_create_admin_priority_apply(self):
        self.assert_module_create(
            self.admin_client, 6)

    def run_module_create_datastore(self):
        self.assert_module_create(
            self.admin_client, 7,
            datastore=self.instance_info.dbaas_datastore)

    def run_module_create_different_datastore(self):
        diff_datastore = self._get_different_datastore()
        if not diff_datastore:
            raise SkipTest("Could not find a different datastore")
        self.assert_module_create(
            self.auth_client, 11,
            datastore=diff_datastore)

    def _get_different_datastore(self):
        different_datastore = None
        datastores = self.admin_client.datastores.list()
        for datastore in datastores:
            self.report.log("Found datastore: %s" % datastore.name)
            if datastore.name != self.instance_info.dbaas_datastore:
                different_datastore = datastore.name
                break
        return different_datastore

    def run_module_create_ds_version(self):
        self.assert_module_create(
            self.admin_client, 8,
            datastore=self.instance_info.dbaas_datastore,
            datastore_version=self.instance_info.dbaas_datastore_version)

    def run_module_create_all_tenant(self):
        self.assert_module_create(
            self.admin_client, 9,
            all_tenants=True,
            datastore=self.instance_info.dbaas_datastore,
            datastore_version=self.instance_info.dbaas_datastore_version)

    def run_module_create_different_tenant(self):
        self.assert_module_create(
            self.unauth_client, 12)

    def run_module_create_full_access(self):
        self.assert_module_create(
            self.admin_client, 13,
            full_access=True)

    def run_module_full_access_toggle(self):
        self.assert_module_update(
            self.admin_client,
            self.main_test_module.id,
            full_access=False)
        self.assert_module_update(
            self.admin_client,
            self.main_test_module.id,
            full_access=True)

    def run_module_list_again(self):
        self.assert_module_list(
            self.auth_client,
            self.module_count_prior_to_create + self.module_create_count)

    def run_module_list_ds(self):
        self.assert_module_list(
            self.auth_client,
            self.module_ds_count_prior_to_create + self.module_ds_create_count,
            datastore=self.instance_info.dbaas_datastore)

    def run_module_list_ds_all(self):
        self.assert_module_list(
            self.auth_client,
            (self.module_ds_all_count_prior_to_create +
             self.module_ds_all_create_count),
            datastore=models.Modules.MATCH_ALL_NAME)

    def run_module_show_invisible(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        module = self._find_invisible_module()
        client = self.auth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.modules.get, module.id)

    def run_module_list_admin(self):
        self.assert_module_list(
            self.admin_client,
            (self.module_admin_count_prior_to_create +
             self.module_create_count +
             self.module_admin_create_count +
             self.module_other_create_count))

    def run_module_update(self):
        self.assert_module_update(
            self.auth_client,
            self.main_test_module.id,
            description=self.MODULE_DESC + " modified")

    def assert_module_update(self, client, module_id, **kwargs):
        result = client.modules.update(module_id, **kwargs)
        found = False
        index = -1
        for test_module in self.test_modules:
            index += 1
            if test_module.id == module_id:
                found = True
                break
        if not found:
            self.fail("Could not find updated module in module list")
        self.test_modules[index] = result

        expected_args = {}
        for key, value in kwargs.items():
            new_key = 'expected_' + key
            expected_args[new_key] = value
        self.validate_module(result, **expected_args)

    def run_module_update_same_contents(self):
        old_md5 = self.main_test_module.md5
        self.assert_module_update(
            self.auth_client,
            self.main_test_module.id,
            contents=self.get_module_contents(self.main_test_module.name))
        self.assert_equal(old_md5, self.main_test_module.md5,
                          "MD5 changed with same contents")

    def run_module_update_auto_toggle(self,
                                      expected_exception=exceptions.Forbidden,
                                      expected_http_code=403):
        module = self._find_auto_apply_module()
        toggle_off_args = {'auto_apply': False}
        toggle_on_args = {'auto_apply': True}
        self.assert_module_toggle(module, toggle_off_args, toggle_on_args,
                                  expected_exception=expected_exception,
                                  expected_http_code=expected_http_code)

    def assert_module_toggle(self, module, toggle_off_args, toggle_on_args,
                             expected_exception, expected_http_code):
        # First try to update the module based on the change
        # (this should toggle the state but still not allow non-admin access)
        client = self.admin_client
        self.assert_module_update(client, module.id, **toggle_off_args)
        # The non-admin client should fail to update
        non_admin_client = self.auth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            non_admin_client, non_admin_client.modules.update, module.id,
            description='Updated by non-admin')
        # Make sure we can still update with the admin client
        self.assert_module_update(
            client, module.id, description='Updated by admin')
        # Now set it back
        self.assert_module_update(
            client, module.id, description=module.description,
            **toggle_on_args)

    def run_module_update_all_tenant_toggle(
            self, expected_exception=exceptions.Forbidden,
            expected_http_code=403):
        module = self._find_all_tenant_module()
        toggle_off_args = {'all_tenants': False}
        toggle_on_args = {'all_tenants': True}
        self.assert_module_toggle(module, toggle_off_args, toggle_on_args,
                                  expected_exception=expected_exception,
                                  expected_http_code=expected_http_code)

    def run_module_update_invisible_toggle(
            self, expected_exception=exceptions.Forbidden,
            expected_http_code=403):
        module = self._find_invisible_module()
        toggle_off_args = {'visible': True}
        toggle_on_args = {'visible': False}
        self.assert_module_toggle(module, toggle_off_args, toggle_on_args,
                                  expected_exception=expected_exception,
                                  expected_http_code=expected_http_code)

    def run_module_update_priority_toggle(
            self, expected_exception=exceptions.Forbidden,
            expected_http_code=403):
        module = self._find_priority_apply_module()
        toggle_off_args = {'priority_apply': False}
        toggle_on_args = {'priority_apply': True}
        self.assert_module_toggle(module, toggle_off_args, toggle_on_args,
                                  expected_exception=expected_exception,
                                  expected_http_code=expected_http_code)

    def run_module_update_unauth(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        client = self.unauth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.modules.update,
            self.main_test_module.id, description='Upd')

    def run_module_update_non_admin_auto(
            self, expected_exception=exceptions.Forbidden,
            expected_http_code=403):
        client = self.auth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.modules.update,
            self.main_test_module.id, visible=False)

    def run_module_update_non_admin_auto_off(
            self, expected_exception=exceptions.Forbidden,
            expected_http_code=403):
        module = self._find_auto_apply_module()
        client = self.auth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.modules.update, module.id, auto_apply=False)

    def run_module_update_non_admin_auto_any(
            self, expected_exception=exceptions.Forbidden,
            expected_http_code=403):
        module = self._find_auto_apply_module()
        client = self.auth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.modules.update, module.id, description='Upd')

    def run_module_update_non_admin_all_tenant(
            self, expected_exception=exceptions.Forbidden,
            expected_http_code=403):
        client = self.auth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.modules.update,
            self.main_test_module.id, all_tenants=True)

    def run_module_update_non_admin_all_tenant_off(
            self, expected_exception=exceptions.Forbidden,
            expected_http_code=403):
        module = self._find_all_tenant_module()
        client = self.auth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.modules.update, module.id, all_tenants=False)

    def run_module_update_non_admin_all_tenant_any(
            self, expected_exception=exceptions.Forbidden,
            expected_http_code=403):
        module = self._find_all_tenant_module()
        client = self.auth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.modules.update, module.id, description='Upd')

    def run_module_update_non_admin_invisible(
            self, expected_exception=exceptions.Forbidden,
            expected_http_code=403):
        client = self.auth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.modules.update,
            self.main_test_module.id, visible=False)

    def run_module_update_non_admin_invisible_off(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        module = self._find_invisible_module()
        client = self.auth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.modules.update, module.id, visible=True)

    def run_module_update_non_admin_invisible_any(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        module = self._find_invisible_module()
        client = self.auth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.modules.update, module.id, description='Upd')

    # ModuleInstanceGroup methods
    def run_module_list_instance_empty(self):
        self.assert_module_list_instance(
            self.auth_client, self.instance_info.id,
            self.module_auto_apply_count_prior_to_create)

    def assert_module_list_instance(self, client, instance_id, expected_count,
                                    expected_http_code=200):
        module_list = client.instances.modules(instance_id)
        self.assert_client_code(client, expected_http_code)
        count = len(module_list)
        self.assert_equal(expected_count, count,
                          "Wrong number of modules from list instance")

        for module in module_list:
            self.validate_module(module)

    def run_module_instances_empty(self):
        self.assert_module_instances(
            self.auth_client, self.main_test_module.id, 0)

    def assert_module_instances(self, client, module_id, expected_count,
                                expected_http_code=200):
        instance_list = client.modules.instances(module_id)
        self.assert_client_code(client, expected_http_code)
        count = len(instance_list)
        self.assert_equal(expected_count, count,
                          "Wrong number of instances applied from module")

    def run_module_instance_count_empty(self):
        self.assert_module_instance_count(
            self.auth_client, self.main_test_module.id, 0)

    def assert_module_instance_count(self, client, module_id,
                                     expected_rows, expected_count=None,
                                     expected_http_code=200):
        instance_count_list = client.modules.instances(module_id,
                                                       count_only=True)
        self.assert_client_code(client, expected_http_code)
        rowcount = len(instance_count_list)
        self.assert_equal(expected_rows, rowcount,
                          "Wrong number of instance count records from module")
        # expected_count is a dict of md5->count pairs.
        if expected_rows and expected_count:
            for row in instance_count_list:
                self.assert_equal(
                    expected_count[row.module_md5], row.instance_count,
                    "Wrong count in record from module instances; md5: %s" %
                    row.module_md5)

    def run_module_query_empty(self):
        self.assert_module_query(
            self.auth_client, self.instance_info.id,
            self.module_auto_apply_count_prior_to_create)

    def run_module_query_after_remove(self):
        self.assert_module_query(
            self.auth_client, self.instance_info.id,
            self.module_auto_apply_count_prior_to_create + 2)

    def assert_module_query(self, client, instance_id, expected_count,
                            expected_http_code=200, expected_results=None):
        modquery_list = client.instances.module_query(instance_id)
        self.assert_client_code(client, expected_http_code)
        count = len(modquery_list)
        self.assert_equal(expected_count, count,
                          "Wrong number of modules from query")
        expected_results = expected_results or {}
        name_index = len(self.module_name_order)
        for modquery in modquery_list:
            if modquery.name in expected_results:
                self.report.log("Validating module '%s'" % modquery.name)
                expected = expected_results[modquery.name]
                self.validate_module_apply_info(
                    modquery,
                    expected_status=expected['status'],
                    expected_message=expected['message'])
                # make sure we're in the correct order
                found = False
                while name_index > 0:
                    name_index -= 1
                    name_order_rec = self.module_name_order[name_index]
                    order_name = self.MODULE_NAME + name_order_rec['suffix']
                    self.report.log("Next module order '%s'" % order_name)
                    if order_name == modquery.name:
                        self.report.log("Match found")
                        found = True
                        break
                if name_index == 0 and not found:
                    self.fail("Module '%s' was not found in the correct order"
                              % modquery.name)

    def run_module_apply(self):
        self.assert_module_apply(self.auth_client, self.instance_info.id,
                                 self.main_test_module)
        self.apply_count += 1

    def assert_module_apply(self, client, instance_id, module,
                            expected_is_admin=False,
                            expected_status=None, expected_message=None,
                            expected_contents=None,
                            expected_http_code=200):
        module_apply_list = client.instances.module_apply(
            instance_id, [module.id])
        self.assert_client_code(client, expected_http_code)
        expected_status = expected_status or 'OK'
        expected_message = (expected_message or
                            self.get_module_message(module.name))
        for module_apply in module_apply_list:
            self.validate_module_apply_info(
                module_apply,
                expected_name=module.name,
                expected_module_type=module.type,
                expected_datastore=module.datastore,
                expected_datastore_version=module.datastore_version,
                expected_auto_apply=module.auto_apply,
                expected_visible=module.visible,
                expected_contents=expected_contents,
                expected_status=expected_status,
                expected_message=expected_message,
                expected_is_admin=expected_is_admin)

    def validate_module_apply_info(self, module_apply,
                                   expected_name=None,
                                   expected_module_type=None,
                                   expected_datastore=None,
                                   expected_datastore_version=None,
                                   expected_auto_apply=None,
                                   expected_visible=None,
                                   expected_contents=None,
                                   expected_message=None,
                                   expected_status=None,
                                   expected_is_admin=None):

        prefix = "Module: %s -" % expected_name
        if expected_name:
            self.assert_equal(expected_name, module_apply.name,
                              '%s Unexpected module name' % prefix)
        if expected_module_type:
            self.assert_equal(expected_module_type, module_apply.type,
                              '%s Unexpected module type' % prefix)
        if expected_datastore:
            self.assert_equal(expected_datastore, module_apply.datastore,
                              '%s Unexpected datastore' % prefix)
        if expected_datastore_version:
            self.assert_equal(expected_datastore_version,
                              module_apply.datastore_version,
                              '%s Unexpected datastore version' % prefix)
        if expected_auto_apply is not None:
            self.assert_equal(expected_auto_apply, module_apply.auto_apply,
                              '%s Unexpected auto_apply' % prefix)
        if expected_visible is not None:
            self.assert_equal(expected_visible, module_apply.visible,
                              '%s Unexpected visible' % prefix)
        if expected_contents is not None:
            self.assert_equal(expected_contents, module_apply.contents,
                              '%s Unexpected contents' % prefix)
        if expected_message is not None:
            regex = re.compile(expected_message)
            self.assert_true(regex.match(module_apply.message),
                             "%s Unexpected message '%s', expected '%s'" %
                             (prefix, module_apply.message, expected_message))
        if expected_status is not None:
            self.assert_equal(expected_status, module_apply.status,
                              '%s Unexpected status' % prefix)
        if expected_is_admin is not None:
            self.assert_equal(expected_is_admin, module_apply.is_admin,
                              '%s Unexpected is_admin' % prefix)

    def run_module_apply_wrong_module(
            self, expected_exception=exceptions.BadRequest,
            expected_http_code=400):
        module = self._find_diff_datastore_module()
        self.report.log("Found 'wrong' module: %s" % module.name)
        client = self.auth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.instances.module_apply,
            self.instance_info.id, [module.id])

    def run_module_list_instance_after_apply(self):
        self.assert_module_list_instance(
            self.auth_client, self.instance_info.id, self.apply_count)

    def run_module_apply_another(self):
        self.assert_module_apply(self.auth_client, self.instance_info.id,
                                 self.update_test_module)
        self.apply_count += 1

    def run_module_list_instance_after_apply_another(self):
        self.assert_module_list_instance(
            self.auth_client, self.instance_info.id, self.apply_count)

    def run_module_update_after_remove(self):
        name, description, contents, priority, order = (
            self.build_module_args(15))
        self.assert_module_update(
            self.auth_client,
            self.update_test_module.id,
            name=name,
            datastore=self.instance_info.dbaas_datastore,
            datastore_version=self.instance_info.dbaas_datastore_version,
            contents=contents)

    def run_module_instances_after_apply(self):
        self.assert_module_instances(
            self.auth_client, self.main_test_module.id, 1)

    def run_module_instance_count_after_apply(self):
        self.assert_module_instance_count(
            self.auth_client, self.main_test_module.id, 1,
            {self.main_test_module.md5: 1})

    def run_module_query_after_apply(self):
        expected_count = self.module_auto_apply_count_prior_to_create + 2
        expected_results = self.create_default_query_expected_results(
            [self.main_test_module])
        self.assert_module_query(self.auth_client, self.instance_info.id,
                                 expected_count=expected_count,
                                 expected_results=expected_results)

    def create_default_query_expected_results(self, modules, is_admin=False):
        expected_results = {}
        for module in modules:
            status = 'OK'
            message = self.get_module_message(module.name)
            contents = self.get_module_contents(module.name)
            if not is_admin and (not module.visible or module.auto_apply or
                                 not module.tenant_id):
                contents = ('Must be admin to retrieve contents for module %s'
                            % module.name)
            elif self.MODULE_BINARY_SUFFIX in module.name:
                status = 'ERROR'
                message = ('^(Could not extract ping message|'
                           'Message not found in contents file).*')
                contents = self.MODULE_BINARY_CONTENTS
                if self.MODULE_BINARY_SUFFIX2 in module.name:
                    contents = self.MODULE_BINARY_CONTENTS2
            expected_results[module.name] = {
                'status': status,
                'message': message,
                'datastore': module.datastore,
                'datastore_version': module.datastore_version,
                'contents': contents,
            }
        return expected_results

    def run_module_instances_after_apply_another(self):
        self.assert_module_instances(
            self.auth_client, self.main_test_module.id, 1)

    def run_module_instance_count_after_apply_another(self):
        self.assert_module_instance_count(
            self.auth_client, self.main_test_module.id, 1,
            {self.main_test_module.md5: 1})

    def run_module_query_after_apply_another(self):
        expected_count = self.module_auto_apply_count_prior_to_create + 3
        expected_results = self.create_default_query_expected_results(
            [self.main_test_module, self.update_test_module])
        self.assert_module_query(self.auth_client, self.instance_info.id,
                                 expected_count=expected_count,
                                 expected_results=expected_results)

    def run_module_update_not_live(
            self, expected_exception=exceptions.Forbidden,
            expected_http_code=403):
        client = self.auth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.modules.update,
            self.main_test_module.id, description='Do not allow this change')

    def run_module_apply_live_update(self):
        module = self.live_update_test_module
        self.assert_module_apply(self.auth_client, self.instance_info.id,
                                 module, expected_is_admin=module.is_admin)
        self.apply_count += 1

    def run_module_list_instance_after_apply_live(self):
        self.assert_module_list_instance(
            self.auth_client, self.instance_info.id, self.apply_count)

    def run_module_update_live_update(self):
        module = self.live_update_test_module
        new_contents = self.get_module_contents(name=module.name + '_upd')
        self.assert_module_update(
            self.admin_client,
            module.id,
            contents=new_contents)

    def run_module_update_after_remove_again(self):
        self.assert_module_update(
            self.auth_client,
            self.update_test_module.id,
            name=self.MODULE_NAME + '_updated_back',
            all_datastores=True,
            all_datastore_versions=True)

    def run_create_inst_with_mods(self, expected_http_code=200):
        live_update = self.live_update_test_module
        self.mod_inst_id = self.assert_inst_mod_create(
            [self.main_test_module.id, live_update.id],
            '_module', expected_http_code)
        self.mod_inst_apply_count += 2

    def assert_inst_mod_create(self, module_ids, name_suffix,
                               expected_http_code):
        client = self.auth_client
        inst = client.instances.create(
            self.instance_info.name + name_suffix,
            self.instance_info.dbaas_flavor_href,
            self.instance_info.volume,
            datastore=self.instance_info.dbaas_datastore,
            datastore_version=self.instance_info.dbaas_datastore_version,
            nics=self.instance_info.nics,
            modules=module_ids,
        )
        self.assert_client_code(client, expected_http_code)
        self.register_debug_inst_ids(inst.id)
        return inst.id

    def run_create_inst_with_wrong_module(
            self, expected_exception=exceptions.BadRequest,
            expected_http_code=400):
        module = self._find_diff_datastore_module()
        self.report.log("Found 'wrong' module: %s" % module.name)

        client = self.auth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.instances.create,
            self.instance_info.name + '_wrong_ds',
            self.instance_info.dbaas_flavor_href,
            self.instance_info.volume,
            datastore=self.instance_info.dbaas_datastore,
            datastore_version=self.instance_info.dbaas_datastore_version,
            nics=self.instance_info.nics,
            modules=[module.id])

    def run_module_delete_applied(
            self, expected_exception=exceptions.Forbidden,
            expected_http_code=403):
        client = self.auth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.modules.delete, self.main_test_module.id)

    def run_module_remove(self):
        self.assert_module_remove(self.auth_client, self.instance_info.id,
                                  self.update_test_module.id)

    def assert_module_remove(self, client, instance_id, module_id,
                             expected_http_code=200):
        client.instances.module_remove(instance_id, module_id)
        self.assert_client_code(client, expected_http_code)

    def run_wait_for_inst_with_mods(self, expected_states=['BUILD', 'ACTIVE']):
        self.assert_instance_action(self.mod_inst_id, expected_states)

    def run_module_query_after_inst_create(self):
        auto_modules = self._find_all_auto_apply_modules(visible=True)
        expected_count = self.mod_inst_apply_count + len(auto_modules)
        expected_results = self.create_default_query_expected_results(
            [self.main_test_module] + auto_modules)
        self.assert_module_query(self.auth_client, self.mod_inst_id,
                                 expected_count=expected_count,
                                 expected_results=expected_results)

    def run_module_retrieve_after_inst_create(self):
        auto_modules = self._find_all_auto_apply_modules(visible=True)
        expected_count = self.mod_inst_apply_count + len(auto_modules)
        expected_results = self.create_default_query_expected_results(
            [self.main_test_module] + auto_modules)
        self.assert_module_retrieve(self.auth_client, self.mod_inst_id,
                                    expected_count=expected_count,
                                    expected_results=expected_results)

    def assert_module_retrieve(self, client, instance_id, expected_count,
                               expected_http_code=200, expected_results=None):
        try:
            temp_dir = tempfile.mkdtemp()
            prefix = 'contents'
            modretrieve_list = client.instances.module_retrieve(
                instance_id, directory=temp_dir, prefix=prefix)
            self.assert_client_code(client, expected_http_code)
            count = len(modretrieve_list)
            self.assert_equal(expected_count, count,
                              "Wrong number of modules from retrieve")
            expected_results = expected_results or {}
            for module_name, filename in modretrieve_list.items():
                if module_name in expected_results:
                    expected = expected_results[module_name]
                    contents_name = '%s_%s_%s_%s' % (
                        prefix, module_name,
                        expected['datastore'], expected['datastore_version'])
                    expected_filename = guestagent_utils.build_file_path(
                        temp_dir, contents_name, 'dat')
                    self.assert_equal(expected_filename, filename,
                                      'Unexpected retrieve filename')
                    if 'contents' in expected and expected['contents']:
                        with open(filename, 'rb') as fh:
                            contents = fh.read()
                        # convert contents into bytearray to work with py27
                        # and py34
                        contents = bytes([ord(item) for item in contents])
                        expected_contents = bytes(
                            [ord(item) for item in expected['contents']])
                        self.assert_equal(expected_contents, contents,
                                          "Unexpected contents for %s" %
                                          module_name)
        finally:
            operating_system.remove(temp_dir)

    def run_module_query_after_inst_create_admin(self):
        auto_modules = self._find_all_auto_apply_modules()
        expected_count = self.mod_inst_apply_count + len(auto_modules)
        expected_results = self.create_default_query_expected_results(
            [self.main_test_module] + auto_modules, is_admin=True)
        self.assert_module_query(self.admin_client, self.mod_inst_id,
                                 expected_count=expected_count,
                                 expected_results=expected_results)

    def run_module_retrieve_after_inst_create_admin(self):
        auto_modules = self._find_all_auto_apply_modules()
        expected_count = self.mod_inst_apply_count + len(auto_modules)
        expected_results = self.create_default_query_expected_results(
            [self.main_test_module] + auto_modules, is_admin=True)
        self.assert_module_retrieve(self.admin_client, self.mod_inst_id,
                                    expected_count=expected_count,
                                    expected_results=expected_results)

    def run_module_delete_auto_applied(
            self, expected_exception=exceptions.Forbidden,
            expected_http_code=403):
        module = self._find_auto_apply_module()
        client = self.auth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.modules.delete, module.id)

    def run_module_list_instance_after_mod_inst(self):
        self.assert_module_list_instance(
            self.auth_client, self.mod_inst_id,
            self.module_auto_apply_create_count + 2)

    def run_module_instances_after_mod_inst(self):
        self.assert_module_instances(
            self.auth_client, self.live_update_test_module.id, 2)

    def run_module_instance_count_after_mod_inst(self):
        self.assert_module_instance_count(
            self.auth_client, self.live_update_test_module.id, 2,
            {self.live_update_test_module.md5: 1,
             self.live_update_orig_md5: 1})

    def run_module_reapply_with_md5(self, expected_http_code=202):
        self.assert_module_reapply(
            self.auth_client, self.live_update_test_module,
            expected_http_code=expected_http_code,
            md5=self.live_update_test_module.md5)

    def assert_module_reapply(self, client, module, expected_http_code,
                              md5=None, force=False):
        self.reapply_max_upd_date = self.get_updated(client, module.id)
        client.modules.reapply(module.id, md5=md5, force=force)
        self.assert_client_code(client, expected_http_code)

    def run_module_reapply_with_md5_verify(self):
        # since this isn't supposed to do anything, we can't 'wait' for it to
        # finish, since we'll never know. So just sleep for a couple seconds
        # just to make sure.
        time.sleep(2)
        # Now we check that the max_updated_date field didn't change
        module_id = self.live_update_test_module.id
        instance_count_list = self.auth_client.modules.instances(
            module_id, count_only=True)
        mismatch = False
        for instance_count in instance_count_list:
            if self.reapply_max_upd_date != instance_count.max_updated_date:
                mismatch = True
        self.assert_true(
            mismatch,
            "Could not find record having max_updated_date different from %s" %
            self.reapply_max_upd_date)

    def run_module_list_instance_after_reapply_md5(self):
        self.assert_module_list_instance(
            self.auth_client, self.mod_inst_id,
            self.module_auto_apply_create_count + 2)

    def run_module_instances_after_reapply_md5(self):
        self.assert_module_instances(
            self.auth_client, self.live_update_test_module.id, 2)

    def run_module_instance_count_after_reapply_md5(self):
        self.assert_module_instance_count(
            self.auth_client, self.live_update_test_module.id, 2,
            {self.live_update_test_module.md5: 1,
             self.live_update_orig_md5: 1})

    def run_module_reapply_all(self, expected_http_code=202):
        module_id = self.live_update_test_module.id
        client = self.auth_client
        self.reapply_max_upd_date = self.get_updated(client, module_id)
        self.assert_module_reapply(
            client, self.live_update_test_module,
            expected_http_code=expected_http_code)

    def run_module_reapply_all_wait(self):
        self.wait_for_reapply(
            self.auth_client, self.live_update_test_module.id,
            md5=self.live_update_orig_md5)

    def wait_for_reapply(self, client, module_id, updated=None, md5=None):
        """Reapply is done when all the counts for 'md5' are gone.  If updated
        is passed in, the min_updated_date must all be greater than it.
        """
        if not updated and not md5:
            raise RuntimeError("Code error: Must pass in 'updated' or 'md5'.")
        self.report.log("Waiting for all md5:%s modules to have an updated "
                        "date greater than %s" % (md5, updated))

        def _all_updated():
            min_updated = self.get_updated(
                client, module_id, max=False, md5=md5)
            if md5:
                return min_updated is None
            return min_updated > updated

        timeout = 60
        try:
            poll_until(_all_updated, time_out=timeout, sleep_time=5)
            self.report.log("All instances now have the current module "
                            "for md5: %s." % md5)
        except exception.PollTimeOut:
            self.fail("Some instances were not updated with the "
                      "timeout: %ds" % timeout)

    def get_updated(self, client, module_id, max=True, md5=None):
        updated = None
        instance_count_list = client.modules.instances(
            module_id, count_only=True)
        for instance_count in instance_count_list:
            if not md5 or md5 == instance_count.module_md5:
                if not updated or (
                        (max and instance_count.max_updated_date > updated) or
                        (not max and
                         instance_count.min_updated_date < updated)):
                    updated = (instance_count.max_updated_date
                               if max else instance_count.min_updated_date)
        return updated

    def run_module_list_instance_after_reapply(self):
        self.assert_module_list_instance(
            self.auth_client, self.mod_inst_id,
            self.module_auto_apply_create_count + 2)

    def run_module_instances_after_reapply(self):
        self.assert_module_instances(
            self.auth_client, self.live_update_test_module.id, 2)

    def run_module_instance_count_after_reapply(self):
        self.assert_module_instance_count(
            self.auth_client, self.live_update_test_module.id, 1,
            {self.live_update_test_module.md5: 2})

    def run_module_reapply_with_force(self, expected_http_code=202):
        self.assert_module_reapply(
            self.auth_client, self.live_update_test_module,
            expected_http_code=expected_http_code,
            force=True)

    def run_module_reapply_with_force_wait(self):
        self.wait_for_reapply(
            self.auth_client, self.live_update_test_module.id,
            updated=self.reapply_max_upd_date)

    def run_delete_inst_with_mods(self, expected_http_code=202):
        self.assert_delete_instance(self.mod_inst_id, expected_http_code)

    def assert_delete_instance(self, instance_id, expected_http_code):
        client = self.auth_client
        client.instances.delete(instance_id)
        self.assert_client_code(client, expected_http_code)

    def run_remove_mods_from_main_inst(self, expected_http_code=200):
        client = self.auth_client
        modquery_list = client.instances.module_query(self.instance_info.id)
        self.assert_client_code(client, expected_http_code)
        for modquery in modquery_list:
            client.instances.module_remove(self.instance_info.id, modquery.id)
            self.assert_client_code(client, expected_http_code)

    def run_wait_for_delete_inst_with_mods(
            self, expected_last_state=['SHUTDOWN']):
        self.assert_all_gone(self.mod_inst_id, expected_last_state)

    # ModuleDeleteGroup methods
    def run_module_delete_non_existent(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        client = self.auth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.modules.delete, 'bad_id')

    def run_module_delete_unauth_user(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        client = self.unauth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.modules.delete, self.main_test_module.id)

    def run_module_delete_hidden_by_non_admin(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        module = self._find_invisible_module()
        client = self.auth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.modules.delete, module.id)

    def run_module_delete_all_tenant_by_non_admin(
            self, expected_exception=exceptions.Forbidden,
            expected_http_code=403):
        module = self._find_all_tenant_module()
        client = self.auth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.modules.delete, module.id)

    def run_module_delete_auto_by_non_admin(
            self, expected_exception=exceptions.Forbidden,
            expected_http_code=403):
        module = self._find_auto_apply_module()
        client = self.auth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.modules.delete, module.id)

    def run_module_delete(self):
        expected_count = len(self.auth_client.modules.list()) - 1
        test_module = self.test_modules.pop(0)
        self.assert_module_delete(self.auth_client, test_module.id,
                                  expected_count)

    def run_module_delete_admin(self):
        start_count = count = len(self.admin_client.modules.list())
        for test_module in self.test_modules:
            count -= 1
            self.report.log("Deleting module '%s' (tenant: %s)" % (
                test_module.name, test_module.tenant_id))
            self.assert_module_delete(self.admin_client, test_module.id, count)
        self.assert_not_equal(start_count, count, "Nothing was deleted")
        count = len(self.admin_client.modules.list())
        self.assert_equal(self.module_admin_count_prior_to_create, count,
                          "Wrong number of admin modules after deleting all")
        count = len(self.auth_client.modules.list())
        self.assert_equal(self.module_count_prior_to_create, count,
                          "Wrong number of modules after deleting all")

    def assert_module_delete(self, client, module_id, expected_count):
        client.modules.delete(module_id)
        count = len(client.modules.list())
        self.assert_equal(expected_count, count,
                          "Wrong number of modules after delete")
