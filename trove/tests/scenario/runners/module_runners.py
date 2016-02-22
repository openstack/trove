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

from proboscis import SkipTest

from troveclient.compat import exceptions

from trove.common import utils
from trove.module import models
from trove.tests.scenario.runners.test_runners import TestRunner


# Variables here are set up to be used across multiple groups,
# since each group will instantiate a new runner
test_modules = []
module_count_prior_to_create = 0
module_admin_count_prior_to_create = 0
module_other_count_prior_to_create = 0
module_create_count = 0
module_admin_create_count = 0
module_other_create_count = 0


class ModuleRunner(TestRunner):

    def __init__(self):
        self.TIMEOUT_MODULE_APPLY = 60 * 10

        super(ModuleRunner, self).__init__(
            sleep_time=10, timeout=self.TIMEOUT_MODULE_APPLY)

        self.MODULE_NAME = 'test_module_1'
        self.MODULE_DESC = 'test description'
        self.MODULE_CONTENTS = utils.encode_string(
            'mode=echo\nkey=mysecretkey\n')

        self.temp_module = None
        self._module_type = None

    @property
    def module_type(self):
        if not self._module_type:
            self._module_type = self.test_helper.get_valid_module_type()
        return self._module_type

    @property
    def main_test_module(self):
        if not test_modules or not test_modules[0]:
            SkipTest("No main module created")
        return test_modules[0]

    def run_module_delete_existing(self):
        modules = self.admin_client.modules.list()
        for module in modules:
            if module.name.startswith(self.MODULE_NAME):
                self.admin_client.modules.delete(module.id)

    def run_module_create_bad_type(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        self.assert_raises(
            expected_exception, expected_http_code,
            self.auth_client.modules.create,
            self.MODULE_NAME, 'invalid-type', self.MODULE_CONTENTS)

    def run_module_create_non_admin_auto(
            self, expected_exception=exceptions.Forbidden,
            expected_http_code=403):
        self.assert_raises(
            expected_exception, expected_http_code,
            self.auth_client.modules.create,
            self.MODULE_NAME, self.module_type, self.MODULE_CONTENTS,
            auto_apply=True)

    def run_module_create_non_admin_all_tenant(
            self, expected_exception=exceptions.Forbidden,
            expected_http_code=403):
        self.assert_raises(
            expected_exception, expected_http_code,
            self.auth_client.modules.create,
            self.MODULE_NAME, self.module_type, self.MODULE_CONTENTS,
            all_tenants=True)

    def run_module_create_non_admin_hidden(
            self, expected_exception=exceptions.Forbidden,
            expected_http_code=403):
        self.assert_raises(
            expected_exception, expected_http_code,
            self.auth_client.modules.create,
            self.MODULE_NAME, self.module_type, self.MODULE_CONTENTS,
            visible=False)

    def run_module_create_bad_datastore(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        self.assert_raises(
            expected_exception, expected_http_code,
            self.auth_client.modules.create,
            self.MODULE_NAME, self.module_type, self.MODULE_CONTENTS,
            datastore='bad-datastore')

    def run_module_create_bad_datastore_version(
            self, expected_exception=exceptions.BadRequest,
            expected_http_code=400):
        self.assert_raises(
            expected_exception, expected_http_code,
            self.auth_client.modules.create,
            self.MODULE_NAME, self.module_type, self.MODULE_CONTENTS,
            datastore=self.instance_info.dbaas_datastore,
            datastore_version='bad-datastore-version')

    def run_module_create_missing_datastore(
            self, expected_exception=exceptions.BadRequest,
            expected_http_code=400):
        self.assert_raises(
            expected_exception, expected_http_code,
            self.auth_client.modules.create,
            self.MODULE_NAME, self.module_type, self.MODULE_CONTENTS,
            datastore_version=self.instance_info.dbaas_datastore_version)

    def run_module_create(self):
        # Necessary to test that the count increases.
        global module_count_prior_to_create
        global module_admin_count_prior_to_create
        global module_other_count_prior_to_create
        module_count_prior_to_create = len(
            self.auth_client.modules.list())
        module_admin_count_prior_to_create = len(
            self.admin_client.modules.list())
        module_other_count_prior_to_create = len(
            self.unauth_client.modules.list())
        self.assert_module_create(
            self.auth_client,
            name=self.MODULE_NAME,
            module_type=self.module_type,
            contents=self.MODULE_CONTENTS,
            description=self.MODULE_DESC)

    def assert_module_create(self, client, name=None, module_type=None,
                             contents=None, description=None,
                             all_tenants=False,
                             datastore=None, datastore_version=None,
                             auto_apply=False,
                             live_update=False, visible=True):
        result = client.modules.create(
            name, module_type, contents,
            description=description,
            all_tenants=all_tenants,
            datastore=datastore, datastore_version=datastore_version,
            auto_apply=auto_apply,
            live_update=live_update, visible=visible)
        global module_create_count
        global module_admin_create_count
        global module_other_create_count
        if (client == self.auth_client or
                (client == self.admin_client and visible)):
            module_create_count += 1
        elif not visible:
            module_admin_create_count += 1
        else:
            module_other_create_count += 1
        global test_modules
        test_modules.append(result)

        tenant_id = None
        tenant = models.Modules.MATCH_ALL_NAME
        if not all_tenants:
            tenant, tenant_id = self.get_client_tenant(client)
            # TODO(peterstac) we don't support tenant name yet ...
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
            expected_ds_version=datastore_version,
            expected_auto_apply=auto_apply)

    def validate_module(self, module, validate_all=False,
                        expected_name=None,
                        expected_module_type=None,
                        expected_description=None,
                        expected_tenant=None,
                        expected_tenant_id=None,
                        expected_datastore=None,
                        expected_datastore_id=None,
                        expected_ds_version=None,
                        expected_ds_version_id=None,
                        expected_all_tenants=None,
                        expected_auto_apply=None,
                        expected_live_update=None,
                        expected_visible=None,
                        expected_contents=None):

        if expected_all_tenants:
            expected_tenant = expected_tenant or models.Modules.MATCH_ALL_NAME
        if expected_name:
            self.assert_equal(expected_name, module.name,
                              'Unexpected module name')
        if expected_module_type:
            self.assert_equal(expected_module_type, module.type,
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
        if expected_ds_version:
            self.assert_equal(expected_ds_version,
                              module.datastore_version,
                              'Unexpected datastore version')
        if expected_auto_apply is not None:
            self.assert_equal(expected_auto_apply, module.auto_apply,
                              'Unexpected auto_apply')
        if validate_all:
            if expected_datastore_id:
                self.assert_equal(expected_datastore_id, module.datastore_id,
                                  'Unexpected datastore id')
            if expected_ds_version_id:
                self.assert_equal(expected_ds_version_id,
                                  module.datastore_version_id,
                                  'Unexpected datastore version id')
            if expected_live_update is not None:
                self.assert_equal(expected_live_update, module.live_update,
                                  'Unexpected live_update')
            if expected_visible is not None:
                self.assert_equal(expected_visible, module.visible,
                                  'Unexpected visible')

    def run_module_create_dupe(
            self, expected_exception=exceptions.BadRequest,
            expected_http_code=400):
        self.assert_raises(
            expected_exception, expected_http_code,
            self.auth_client.modules.create,
            self.MODULE_NAME, self.module_type, self.MODULE_CONTENTS)

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
            expected_ds_version=test_module.datastore_version,
            expected_auto_apply=test_module.auto_apply,
            expected_live_update=False,
            expected_visible=True)

    def run_module_show_unauth_user(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        self.assert_raises(
            expected_exception, None,
            self.unauth_client.modules.get, self.main_test_module.id)
        # we're using a different client, so we'll check the return code
        # on it explicitly, instead of depending on 'assert_raises'
        self.assert_client_code(expected_http_code=expected_http_code,
                                client=self.unauth_client)

    def run_module_list(self):
        self.assert_module_list(
            self.auth_client,
            module_count_prior_to_create + module_create_count)

    def assert_module_list(self, client, expected_count,
                           skip_validation=False):
        module_list = client.modules.list()
        self.assert_equal(expected_count, len(module_list),
                          "Wrong number of modules for list")
        if not skip_validation:
            for module in module_list:
                if module.name != self.MODULE_NAME:
                    continue
                test_module = self.main_test_module
                self.validate_module(
                    module, validate_all=False,
                    expected_name=test_module.name,
                    expected_module_type=test_module.type,
                    expected_description=test_module.description,
                    expected_tenant=test_module.tenant,
                    expected_datastore=test_module.datastore,
                    expected_ds_version=test_module.datastore_version,
                    expected_auto_apply=test_module.auto_apply)

    def run_module_list_unauth_user(self):
        self.assert_module_list(self.unauth_client, 0)

    def run_module_create_admin_all(self):
        self.assert_module_create(
            self.admin_client,
            name=self.MODULE_NAME + '_admin_apply',
            module_type=self.module_type,
            contents=self.MODULE_CONTENTS,
            description=(self.MODULE_DESC + ' admin apply'),
            all_tenants=True,
            visible=False,
            auto_apply=True)

    def run_module_create_admin_hidden(self):
        self.assert_module_create(
            self.admin_client,
            name=self.MODULE_NAME + '_hidden',
            module_type=self.module_type,
            contents=self.MODULE_CONTENTS,
            description=self.MODULE_DESC + ' hidden',
            visible=False)

    def run_module_create_admin_auto(self):
        self.assert_module_create(
            self.admin_client,
            name=self.MODULE_NAME + '_auto',
            module_type=self.module_type,
            contents=self.MODULE_CONTENTS,
            description=self.MODULE_DESC + ' hidden',
            auto_apply=True)

    def run_module_create_admin_live_update(self):
        self.assert_module_create(
            self.admin_client,
            name=self.MODULE_NAME + '_live',
            module_type=self.module_type,
            contents=self.MODULE_CONTENTS,
            description=(self.MODULE_DESC + ' live update'),
            live_update=True)

    def run_module_create_all_tenant(self):
        self.assert_module_create(
            self.admin_client,
            name=self.MODULE_NAME + '_all_tenant',
            module_type=self.module_type,
            contents=self.MODULE_CONTENTS,
            description=self.MODULE_DESC + ' all tenant',
            all_tenants=True,
            datastore=self.instance_info.dbaas_datastore,
            datastore_version=self.instance_info.dbaas_datastore_version)

    def run_module_create_different_tenant(self):
        self.assert_module_create(
            self.unauth_client,
            name=self.MODULE_NAME,
            module_type=self.module_type,
            contents=self.MODULE_CONTENTS,
            description=self.MODULE_DESC)

    def run_module_list_again(self):
        self.assert_module_list(
            self.auth_client,
            # TODO(peterstac) remove the '-1' once the list is fixed to
            # include 'all' tenant modules
            module_count_prior_to_create + module_create_count - 1,
            skip_validation=True)

    def run_module_show_invisible(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        module = self._find_invisible_module()
        self.assert_raises(
            expected_exception, expected_http_code,
            self.auth_client.modules.get, module.id)

    def _find_invisible_module(self):
        def _match(mod):
            return not mod.visible and mod.tenant_id and not mod.auto_apply
        return self._find_module(_match, "Could not find invisible module")

    def _find_module(self, match_fn, not_found_message):
        module = None
        for test_module in test_modules:
            if match_fn(test_module):
                module = test_module
                break
        if not module:
            self.fail(not_found_message)
        return module

    def run_module_list_admin(self):
        self.assert_module_list(
            self.admin_client,
            (module_admin_count_prior_to_create +
             module_create_count +
             module_admin_create_count +
             module_other_create_count),
            skip_validation=True)

    def run_module_update(self):
        self.assert_module_update(
            self.auth_client,
            self.main_test_module.id,
            description=self.MODULE_DESC + " modified")

    def run_module_update_same_contents(self):
        old_md5 = self.main_test_module.md5
        self.assert_module_update(
            self.auth_client,
            self.main_test_module.id,
            contents=self.MODULE_CONTENTS)
        self.assert_equal(old_md5, self.main_test_module.md5,
                          "MD5 changed with same contents")

    def run_module_update_auto_toggle(self):
        module = self._find_auto_apply_module()
        toggle_off_args = {'auto_apply': False}
        toggle_on_args = {'auto_apply': True}
        self.assert_module_toggle(module, toggle_off_args, toggle_on_args)

    def assert_module_toggle(self, module, toggle_off_args, toggle_on_args):
        # First try to update the module based on the change
        # (this should toggle the state and allow non-admin access)
        self.assert_module_update(
            self.admin_client, module.id, **toggle_off_args)
        # Now we can update using the non-admin client
        self.assert_module_update(
            self.auth_client, module.id, description='Updated by auth')
        # Now set it back
        self.assert_module_update(
            self.admin_client, module.id, description=module.description,
            **toggle_on_args)

    def run_module_update_all_tenant_toggle(self):
        module = self._find_all_tenant_module()
        toggle_off_args = {'all_tenants': False}
        toggle_on_args = {'all_tenants': True}
        self.assert_module_toggle(module, toggle_off_args, toggle_on_args)

    def run_module_update_invisible_toggle(self):
        module = self._find_invisible_module()
        toggle_off_args = {'visible': True}
        toggle_on_args = {'visible': False}
        self.assert_module_toggle(module, toggle_off_args, toggle_on_args)

    def assert_module_update(self, client, module_id, **kwargs):
        result = client.modules.update(module_id, **kwargs)
        global test_modules
        found = False
        index = -1
        for test_module in test_modules:
            index += 1
            if test_module.id == module_id:
                found = True
                break
        if not found:
            self.fail("Could not find updated module in module list")
        test_modules[index] = result

        expected_args = {}
        for key, value in kwargs.items():
            new_key = 'expected_' + key
            expected_args[new_key] = value
        self.validate_module(result, **expected_args)

    def run_module_update_unauth(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        self.assert_raises(
            expected_exception, expected_http_code,
            self.unauth_client.modules.update,
            self.main_test_module.id, description='Upd')

    def run_module_update_non_admin_auto(
            self, expected_exception=exceptions.Forbidden,
            expected_http_code=403):
        self.assert_raises(
            expected_exception, expected_http_code,
            self.auth_client.modules.update,
            self.main_test_module.id, visible=False)

    def run_module_update_non_admin_auto_off(
            self, expected_exception=exceptions.Forbidden,
            expected_http_code=403):
        module = self._find_auto_apply_module()
        self.assert_raises(
            expected_exception, expected_http_code,
            self.auth_client.modules.update, module.id, auto_apply=False)

    def _find_auto_apply_module(self):
        def _match(mod):
            return mod.auto_apply and mod.tenant_id and mod.visible
        return self._find_module(_match, "Could not find auto-apply module")

    def run_module_update_non_admin_auto_any(
            self, expected_exception=exceptions.Forbidden,
            expected_http_code=403):
        module = self._find_auto_apply_module()
        self.assert_raises(
            expected_exception, expected_http_code,
            self.auth_client.modules.update, module.id, description='Upd')

    def run_module_update_non_admin_all_tenant(
            self, expected_exception=exceptions.Forbidden,
            expected_http_code=403):
        self.assert_raises(
            expected_exception, expected_http_code,
            self.auth_client.modules.update,
            self.main_test_module.id, all_tenants=True)

    def run_module_update_non_admin_all_tenant_off(
            self, expected_exception=exceptions.Forbidden,
            expected_http_code=403):
        module = self._find_all_tenant_module()
        self.assert_raises(
            expected_exception, expected_http_code,
            self.auth_client.modules.update, module.id, all_tenants=False)

    def _find_all_tenant_module(self):
        def _match(mod):
            return mod.tenant_id is None and mod.visible
        return self._find_module(_match, "Could not find all tenant module")

    def run_module_update_non_admin_all_tenant_any(
            self, expected_exception=exceptions.Forbidden,
            expected_http_code=403):
        module = self._find_all_tenant_module()
        self.assert_raises(
            expected_exception, expected_http_code,
            self.auth_client.modules.update, module.id, description='Upd')

    def run_module_update_non_admin_invisible(
            self, expected_exception=exceptions.Forbidden,
            expected_http_code=403):
        self.assert_raises(
            expected_exception, expected_http_code,
            self.auth_client.modules.update,
            self.main_test_module.id, visible=False)

    def run_module_update_non_admin_invisible_off(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        module = self._find_invisible_module()
        self.assert_raises(
            expected_exception, expected_http_code,
            self.auth_client.modules.update, module.id, visible=True)

    def run_module_update_non_admin_invisible_any(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        module = self._find_invisible_module()
        self.assert_raises(
            expected_exception, expected_http_code,
            self.auth_client.modules.update, module.id, description='Upd')

    # ModuleDeleteGroup methods
    def run_module_delete_non_existent(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        self.assert_raises(
            expected_exception, expected_http_code,
            self.auth_client.modules.delete, 'bad_id')

    def run_module_delete_unauth_user(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        self.assert_raises(
            expected_exception, expected_http_code,
            self.unauth_client.modules.delete, self.main_test_module.id)

    def run_module_delete_hidden_by_non_admin(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        module = self._find_invisible_module()
        self.assert_raises(
            expected_exception, expected_http_code,
            self.auth_client.modules.delete, module.id)

    def run_module_delete_all_tenant_by_non_admin(
            self, expected_exception=exceptions.Forbidden,
            expected_http_code=403):
        module = self._find_all_tenant_module()
        self.assert_raises(
            expected_exception, expected_http_code,
            self.auth_client.modules.delete, module.id)

    def run_module_delete_auto_by_non_admin(
            self, expected_exception=exceptions.Forbidden,
            expected_http_code=403):
        module = self._find_auto_apply_module()
        self.assert_raises(
            expected_exception, expected_http_code,
            self.auth_client.modules.delete, module.id)

    def run_module_delete(self):
        expected_count = len(self.auth_client.modules.list()) - 1
        test_module = test_modules.pop(0)
        self.assert_module_delete(self.auth_client, test_module.id,
                                  expected_count)

    def run_module_delete_admin(self):
        start_count = count = len(self.admin_client.modules.list())
        for test_module in test_modules:
            count -= 1
            self.report.log("Deleting module '%s' (tenant: %s)" % (
                test_module.name, test_module.tenant_id))
            self.assert_module_delete(self.admin_client, test_module.id, count)
        self.assert_not_equal(start_count, count, "Nothing was deleted")
        count = len(self.admin_client.modules.list())
        self.assert_equal(module_admin_count_prior_to_create, count,
                          "Wrong number of admin modules after deleting all")
        count = len(self.auth_client.modules.list())
        self.assert_equal(module_count_prior_to_create, count,
                          "Wrong number of modules after deleting all")

    def assert_module_delete(self, client, module_id, expected_count):
        client.modules.delete(module_id)
        count = len(client.modules.list())
        self.assert_equal(expected_count, count,
                          "Wrong number of modules after delete")
