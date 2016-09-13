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

from proboscis import test

from trove.tests.scenario import groups
from trove.tests.scenario.groups.test_group import TestGroup
from trove.tests.scenario.runners import test_runners


GROUP = "scenario.module_group"


class ModuleRunnerFactory(test_runners.RunnerFactory):

    _runner_ns = 'module_runners'
    _runner_cls = 'ModuleRunner'


@test(groups=[GROUP, groups.MODULE_CREATE])
class ModuleCreateGroup(TestGroup):
    """Test Module Create functionality."""

    def __init__(self):
        super(ModuleCreateGroup, self).__init__(
            ModuleRunnerFactory.instance())

    @test
    def module_delete_existing(self):
        """Delete all previous test modules."""
        self.test_runner.run_module_delete_existing()

    @test
    def module_create_bad_type(self):
        """Ensure create module with invalid type fails."""
        self.test_runner.run_module_create_bad_type()

    @test
    def module_create_non_admin_auto(self):
        """Ensure create auto_apply module for non-admin fails."""
        self.test_runner.run_module_create_non_admin_auto()

    @test
    def module_create_non_admin_all_tenant(self):
        """Ensure create all tenant module for non-admin fails."""
        self.test_runner.run_module_create_non_admin_all_tenant()

    @test
    def module_create_non_admin_hidden(self):
        """Ensure create hidden module for non-admin fails."""
        self.test_runner.run_module_create_non_admin_hidden()

    @test
    def module_create_bad_datastore(self):
        """Ensure create module with invalid datastore fails."""
        self.test_runner.run_module_create_bad_datastore()

    @test
    def module_create_bad_datastore_version(self):
        """Ensure create module with invalid datastore_version fails."""
        self.test_runner.run_module_create_bad_datastore_version()

    @test
    def module_create_missing_datastore(self):
        """Ensure create module with missing datastore fails."""
        self.test_runner.run_module_create_missing_datastore()

    @test(runs_after=[module_delete_existing])
    def module_create(self):
        """Check that create module works."""
        self.test_runner.run_module_create()

    @test(runs_after=[module_create])
    def module_create_for_update(self):
        """Check that create module for update works."""
        self.test_runner.run_module_create_for_update()

    @test(depends_on=[module_create])
    def module_create_dupe(self):
        """Ensure create with duplicate info fails."""
        self.test_runner.run_module_create_dupe()

    @test(depends_on=[module_create_for_update])
    def module_update_missing_datastore(self):
        """Ensure update module with missing datastore fails."""
        self.test_runner.run_module_update_missing_datastore()

    @test(runs_after=[module_create_for_update])
    def module_create_bin(self):
        """Check that create module with binary contents works."""
        self.test_runner.run_module_create_bin()

    @test(runs_after=[module_create_bin])
    def module_create_bin2(self):
        """Check that create module with other binary contents works."""
        self.test_runner.run_module_create_bin2()

    @test(depends_on=[module_create])
    def module_show(self):
        """Check that show module works."""
        self.test_runner.run_module_show()

    @test(depends_on=[module_create])
    def module_show_unauth_user(self):
        """Ensure that show module for unauth user fails."""
        self.test_runner.run_module_show_unauth_user()

    @test(depends_on=[module_create, module_create_bin, module_create_bin2])
    def module_list(self):
        """Check that list modules works."""
        self.test_runner.run_module_list()

    @test(depends_on=[module_create, module_create_bin, module_create_bin2])
    def module_list_unauth_user(self):
        """Ensure that list module for unauth user fails."""
        self.test_runner.run_module_list_unauth_user()

    @test(depends_on=[module_create, module_create_bin, module_create_bin2],
          runs_after=[module_list])
    def module_create_admin_all(self):
        """Check that create module works with all admin options."""
        self.test_runner.run_module_create_admin_all()

    @test(depends_on=[module_create, module_create_bin, module_create_bin2],
          runs_after=[module_create_admin_all])
    def module_create_admin_hidden(self):
        """Check that create module works with hidden option."""
        self.test_runner.run_module_create_admin_hidden()

    @test(depends_on=[module_create, module_create_bin, module_create_bin2],
          runs_after=[module_create_admin_hidden])
    def module_create_admin_auto(self):
        """Check that create module works with auto option."""
        self.test_runner.run_module_create_admin_auto()

    @test(depends_on=[module_create, module_create_bin, module_create_bin2],
          runs_after=[module_create_admin_auto])
    def module_create_admin_live_update(self):
        """Check that create module works with live-update option."""
        self.test_runner.run_module_create_admin_live_update()

    @test(depends_on=[module_create, module_create_bin, module_create_bin2],
          runs_after=[module_create_admin_live_update])
    def module_create_datastore(self):
        """Check that create module with datastore works."""
        self.test_runner.run_module_create_datastore()

    @test(depends_on=[module_create, module_create_bin, module_create_bin2],
          runs_after=[module_create_datastore])
    def module_create_ds_version(self):
        """Check that create module with ds version works."""
        self.test_runner.run_module_create_ds_version()

    @test(depends_on=[module_create, module_create_bin, module_create_bin2],
          runs_after=[module_create_ds_version])
    def module_create_all_tenant(self):
        """Check that create 'all' tenants with datastore module works."""
        self.test_runner.run_module_create_all_tenant()

    @test(depends_on=[module_create, module_create_bin, module_create_bin2],
          runs_after=[module_create_all_tenant, module_list_unauth_user])
    def module_create_different_tenant(self):
        """Check that create with same name on different tenant works."""
        self.test_runner.run_module_create_different_tenant()

    @test(depends_on=[module_create_all_tenant],
          runs_after=[module_create_different_tenant])
    def module_list_again(self):
        """Check that list modules skips invisible modules."""
        self.test_runner.run_module_list_again()

    @test(depends_on=[module_create_ds_version],
          runs_after=[module_list_again])
    def module_list_ds(self):
        """Check that list modules by datastore works."""
        self.test_runner.run_module_list_ds()

    @test(depends_on=[module_create_ds_version],
          runs_after=[module_list_ds])
    def module_list_ds_all(self):
        """Check that list modules by all datastores works."""
        self.test_runner.run_module_list_ds_all()

    @test(depends_on=[module_create_admin_hidden])
    def module_show_invisible(self):
        """Ensure that show invisible module for non-admin fails."""
        self.test_runner.run_module_show_invisible()

    @test(depends_on=[module_create_all_tenant],
          runs_after=[module_create_different_tenant])
    def module_list_admin(self):
        """Check that list modules for admin works."""
        self.test_runner.run_module_list_admin()

    @test(depends_on=[module_create],
          runs_after=[module_show])
    def module_update(self):
        """Check that update module works."""
        self.test_runner.run_module_update()

    @test(depends_on=[module_update])
    def module_update_same_contents(self):
        """Check that update module with same contents works."""
        self.test_runner.run_module_update_same_contents()

    @test(depends_on=[module_update],
          runs_after=[module_update_same_contents])
    def module_update_auto_toggle(self):
        """Check that update module works for auto apply toggle."""
        self.test_runner.run_module_update_auto_toggle()

    @test(depends_on=[module_update],
          runs_after=[module_update_auto_toggle])
    def module_update_all_tenant_toggle(self):
        """Check that update module works for all tenant toggle."""
        self.test_runner.run_module_update_all_tenant_toggle()

    @test(depends_on=[module_update],
          runs_after=[module_update_all_tenant_toggle])
    def module_update_invisible_toggle(self):
        """Check that update module works for invisible toggle."""
        self.test_runner.run_module_update_invisible_toggle()

    @test(depends_on=[module_update],
          runs_after=[module_update_invisible_toggle])
    def module_update_unauth(self):
        """Ensure update module for unauth user fails."""
        self.test_runner.run_module_update_unauth()

    @test(depends_on=[module_update],
          runs_after=[module_update_invisible_toggle])
    def module_update_non_admin_auto(self):
        """Ensure update module to auto_apply for non-admin fails."""
        self.test_runner.run_module_update_non_admin_auto()

    @test(depends_on=[module_update],
          runs_after=[module_update_invisible_toggle])
    def module_update_non_admin_auto_off(self):
        """Ensure update module to auto_apply off for non-admin fails."""
        self.test_runner.run_module_update_non_admin_auto_off()

    @test(depends_on=[module_update],
          runs_after=[module_update_invisible_toggle])
    def module_update_non_admin_auto_any(self):
        """Ensure any update module to auto_apply for non-admin fails."""
        self.test_runner.run_module_update_non_admin_auto_any()

    @test(depends_on=[module_update],
          runs_after=[module_update_invisible_toggle])
    def module_update_non_admin_all_tenant(self):
        """Ensure update module to all tenant for non-admin fails."""
        self.test_runner.run_module_update_non_admin_all_tenant()

    @test(depends_on=[module_update],
          runs_after=[module_update_invisible_toggle])
    def module_update_non_admin_all_tenant_off(self):
        """Ensure update module to all tenant off for non-admin fails."""
        self.test_runner.run_module_update_non_admin_all_tenant_off()

    @test(depends_on=[module_update],
          runs_after=[module_update_invisible_toggle])
    def module_update_non_admin_all_tenant_any(self):
        """Ensure any update module to all tenant for non-admin fails."""
        self.test_runner.run_module_update_non_admin_all_tenant_any()

    @test(depends_on=[module_update],
          runs_after=[module_update_invisible_toggle])
    def module_update_non_admin_invisible(self):
        """Ensure update module to invisible for non-admin fails."""
        self.test_runner.run_module_update_non_admin_invisible()

    @test(depends_on=[module_update],
          runs_after=[module_update_invisible_toggle])
    def module_update_non_admin_invisible_off(self):
        """Ensure update module to invisible off for non-admin fails."""
        self.test_runner.run_module_update_non_admin_invisible_off()

    @test(depends_on=[module_update],
          runs_after=[module_update_invisible_toggle])
    def module_update_non_admin_invisible_any(self):
        """Ensure any update module to invisible for non-admin fails."""
        self.test_runner.run_module_update_non_admin_invisible_any()


@test(depends_on_groups=[groups.INST_CREATE_WAIT, groups.MODULE_CREATE],
      runs_after_groups=[groups.INST_ERROR_DELETE, groups.INST_FORCE_DELETE],
      groups=[GROUP, groups.MODULE_INST, groups.MODULE_INST_CREATE])
class ModuleInstCreateGroup(TestGroup):
    """Test Module Instance Create functionality."""

    def __init__(self):
        super(ModuleInstCreateGroup, self).__init__(
            ModuleRunnerFactory.instance())

    @test
    def module_list_instance_empty(self):
        """Check that the instance has no modules associated."""
        self.test_runner.run_module_list_instance_empty()

    @test(runs_after=[module_list_instance_empty])
    def module_instances_empty(self):
        """Check that the module hasn't been applied to any instances."""
        self.test_runner.run_module_instances_empty()

    @test(runs_after=[module_instances_empty])
    def module_query_empty(self):
        """Check that the instance has no modules applied."""
        self.test_runner.run_module_query_empty()

    @test(runs_after=[module_query_empty])
    def module_apply(self):
        """Check that module-apply works."""
        self.test_runner.run_module_apply()

    @test(depends_on=[module_apply])
    def module_list_instance_after_apply(self):
        """Check that the instance has one module associated."""
        self.test_runner.run_module_list_instance_after_apply()

    @test(depends_on=[module_apply])
    def module_query_after_apply(self):
        """Check that module-query works."""
        self.test_runner.run_module_query_after_apply()

    @test(runs_after=[module_query_after_apply])
    def module_apply_another(self):
        """Check that module-apply works for another module."""
        self.test_runner.run_module_apply_another()

    @test(depends_on=[module_apply_another])
    def module_list_instance_after_apply_another(self):
        """Check that the instance has one module associated."""
        self.test_runner.run_module_list_instance_after_apply_another()

    @test(depends_on=[module_apply_another])
    def module_query_after_apply_another(self):
        """Check that module-query works after another apply."""
        self.test_runner.run_module_query_after_apply_another()

    @test(depends_on=[module_apply],
          runs_after=[module_query_after_apply_another])
    def create_inst_with_mods(self):
        """Check that creating an instance with modules works."""
        self.test_runner.run_create_inst_with_mods()

    @test(depends_on=[module_apply])
    def module_delete_applied(self):
        """Ensure that deleting an applied module fails."""
        self.test_runner.run_module_delete_applied()

    @test(depends_on=[module_apply],
          runs_after=[module_list_instance_after_apply,
                      module_query_after_apply])
    def module_remove(self):
        """Check that module-remove works."""
        self.test_runner.run_module_remove()

    @test(depends_on=[module_remove])
    def module_query_after_remove(self):
        """Check that the instance has one module applied after remove."""
        self.test_runner.run_module_query_after_remove()

    @test(depends_on=[module_remove],
          runs_after=[module_query_after_remove])
    def module_update_after_remove(self):
        """Check that update module after remove works."""
        self.test_runner.run_module_update_after_remove()

    @test(depends_on=[module_remove],
          runs_after=[module_update_after_remove])
    def module_apply_another_again(self):
        """Check that module-apply another works a second time."""
        self.test_runner.run_module_apply_another()

    @test(depends_on=[module_apply],
          runs_after=[module_apply_another_again])
    def module_query_after_apply_another2(self):
        """Check that module-query works after second apply."""
        self.test_runner.run_module_query_after_apply_another()

    @test(depends_on=[module_apply_another_again],
          runs_after=[module_query_after_apply_another2])
    def module_remove_again(self):
        """Check that module-remove works again."""
        self.test_runner.run_module_remove()

    @test(depends_on=[module_remove_again])
    def module_query_empty_after_again(self):
        """Check that the inst has one mod applied after 2nd remove."""
        self.test_runner.run_module_query_after_remove()

    @test(depends_on=[module_remove_again],
          runs_after=[module_query_empty_after_again])
    def module_update_after_remove_again(self):
        """Check that update module after remove again works."""
        self.test_runner.run_module_update_after_remove_again()


@test(depends_on_groups=[groups.MODULE_INST_CREATE],
      groups=[GROUP, groups.MODULE_INST, groups.MODULE_INST_CREATE_WAIT],
      runs_after_groups=[groups.INST_ACTIONS, groups.INST_UPGRADE])
class ModuleInstCreateWaitGroup(TestGroup):
    """Test that Module Instance Create Completes."""

    def __init__(self):
        super(ModuleInstCreateWaitGroup, self).__init__(
            ModuleRunnerFactory.instance())

    @test
    def wait_for_inst_with_mods(self):
        """Wait for create instance with modules to finish."""
        self.test_runner.run_wait_for_inst_with_mods()

    @test(depends_on=[wait_for_inst_with_mods])
    def module_query_after_inst_create(self):
        """Check that module-query works on new instance."""
        self.test_runner.run_module_query_after_inst_create()

    @test(depends_on=[wait_for_inst_with_mods],
          runs_after=[module_query_after_inst_create])
    def module_retrieve_after_inst_create(self):
        """Check that module-retrieve works on new instance."""
        self.test_runner.run_module_retrieve_after_inst_create()

    @test(depends_on=[wait_for_inst_with_mods],
          runs_after=[module_retrieve_after_inst_create])
    def module_query_after_inst_create_admin(self):
        """Check that module-query works for admin."""
        self.test_runner.run_module_query_after_inst_create_admin()

    @test(depends_on=[wait_for_inst_with_mods],
          runs_after=[module_query_after_inst_create_admin])
    def module_retrieve_after_inst_create_admin(self):
        """Check that module-retrieve works for admin."""
        self.test_runner.run_module_retrieve_after_inst_create_admin()

    @test(depends_on=[wait_for_inst_with_mods],
          runs_after=[module_retrieve_after_inst_create_admin])
    def module_delete_auto_applied(self):
        """Ensure that module-delete on auto-applied module fails."""
        self.test_runner.run_module_delete_auto_applied()


@test(depends_on_groups=[groups.MODULE_INST_CREATE_WAIT],
      groups=[GROUP, groups.MODULE_INST, groups.MODULE_INST_DELETE])
class ModuleInstDeleteGroup(TestGroup):
    """Test Module Instance Delete functionality."""

    def __init__(self):
        super(ModuleInstDeleteGroup, self).__init__(
            ModuleRunnerFactory.instance())

    @test
    def delete_inst_with_mods(self):
        """Check that instance with module can be deleted."""
        self.test_runner.run_delete_inst_with_mods()


@test(depends_on_groups=[groups.MODULE_INST_DELETE],
      groups=[GROUP, groups.MODULE_INST, groups.MODULE_INST_DELETE_WAIT],
      runs_after_groups=[groups.INST_DELETE])
class ModuleInstDeleteWaitGroup(TestGroup):
    """Test that Module Instance Delete Completes."""

    def __init__(self):
        super(ModuleInstDeleteWaitGroup, self).__init__(
            ModuleRunnerFactory.instance())

    @test
    def wait_for_delete_inst_with_mods(self):
        """Wait until the instance with module is gone."""
        self.test_runner.run_wait_for_delete_inst_with_mods()


@test(depends_on_groups=[groups.MODULE_CREATE],
      runs_after_groups=[groups.MODULE_INST_DELETE_WAIT],
      groups=[GROUP, groups.MODULE_DELETE])
class ModuleDeleteGroup(TestGroup):
    """Test Module Delete functionality."""

    def __init__(self):
        super(ModuleDeleteGroup, self).__init__(
            ModuleRunnerFactory.instance())

    def module_delete_non_existent(self):
        """Ensure delete non-existent module fails."""
        self.test_runner.run_module_delete_non_existent()

    def module_delete_unauth_user(self):
        """Ensure delete module by unauth user fails."""
        self.test_runner.run_module_delete_unauth_user()

    @test(runs_after=[module_delete_unauth_user,
                      module_delete_non_existent])
    def module_delete_hidden_by_non_admin(self):
        """Ensure delete hidden module by non-admin user fails."""
        self.test_runner.run_module_delete_hidden_by_non_admin()

    @test(runs_after=[module_delete_hidden_by_non_admin])
    def module_delete_all_tenant_by_non_admin(self):
        """Ensure delete all tenant module by non-admin user fails."""
        self.test_runner.run_module_delete_all_tenant_by_non_admin()

    @test(runs_after=[module_delete_all_tenant_by_non_admin])
    def module_delete_auto_by_non_admin(self):
        """Ensure delete auto-apply module by non-admin user fails."""
        self.test_runner.run_module_delete_auto_by_non_admin()

    @test(runs_after=[module_delete_auto_by_non_admin])
    def module_delete(self):
        """Check that delete module works."""
        self.test_runner.run_module_delete()

    @test(runs_after=[module_delete])
    def module_delete_admin(self):
        """Check that delete module works for admin."""
        self.test_runner.run_module_delete_admin()

    @test(runs_after=[module_delete_admin])
    def module_delete_remaining(self):
        """Delete all remaining test modules."""
        self.test_runner.run_module_delete_existing()
