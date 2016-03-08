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

from trove.tests.scenario.groups import instance_create_group
from trove.tests.scenario.groups.test_group import TestGroup


GROUP = "scenario.module_group"
GROUP_MODULE_CREATE = "scenario.module_create_group"
GROUP_INSTANCE_MODULE = "scenario.instance_module_group"
GROUP_MODULE_DELETE = "scenario.module_delete_group"


@test(groups=[GROUP, GROUP_MODULE_CREATE])
class ModuleGroup(TestGroup):
    """Test Module functionality."""

    def __init__(self):
        super(ModuleGroup, self).__init__(
            'module_runners', 'ModuleRunner')

    @test(groups=[GROUP, GROUP_MODULE_CREATE])
    def module_delete_existing(self):
        """Delete all previous test modules."""
        self.test_runner.run_module_delete_existing()

    @test(groups=[GROUP, GROUP_MODULE_CREATE])
    def module_create_bad_type(self):
        """Ensure create module with invalid type fails."""
        self.test_runner.run_module_create_bad_type()

    @test(groups=[GROUP, GROUP_MODULE_CREATE])
    def module_create_non_admin_auto(self):
        """Ensure create auto_apply module for non-admin fails."""
        self.test_runner.run_module_create_non_admin_auto()

    @test(groups=[GROUP, GROUP_MODULE_CREATE])
    def module_create_non_admin_all_tenant(self):
        """Ensure create all tenant module for non-admin fails."""
        self.test_runner.run_module_create_non_admin_all_tenant()

    @test(groups=[GROUP, GROUP_MODULE_CREATE])
    def module_create_non_admin_hidden(self):
        """Ensure create hidden module for non-admin fails."""
        self.test_runner.run_module_create_non_admin_hidden()

    @test(groups=[GROUP, GROUP_MODULE_CREATE])
    def module_create_bad_datastore(self):
        """Ensure create module with invalid datastore fails."""
        self.test_runner.run_module_create_bad_datastore()

    @test(groups=[GROUP, GROUP_MODULE_CREATE])
    def module_create_bad_datastore_version(self):
        """Ensure create module with invalid datastore_version fails."""
        self.test_runner.run_module_create_bad_datastore_version()

    @test(groups=[GROUP, GROUP_MODULE_CREATE])
    def module_create_missing_datastore(self):
        """Ensure create module with missing datastore fails."""
        self.test_runner.run_module_create_missing_datastore()

    @test(groups=[GROUP, GROUP_MODULE_CREATE],
          runs_after=[module_delete_existing])
    def module_create(self):
        """Check that create module works."""
        self.test_runner.run_module_create()

    @test(groups=[GROUP, GROUP_MODULE_CREATE],
          depends_on=[module_create])
    def module_create_dupe(self):
        """Ensure create with duplicate info fails."""
        self.test_runner.run_module_create_dupe()

    @test(groups=[GROUP, GROUP_MODULE_CREATE],
          runs_after=[module_create])
    def module_create_bin(self):
        """Check that create module with binary contents works."""
        self.test_runner.run_module_create_bin()

    @test(groups=[GROUP, GROUP_MODULE_CREATE],
          runs_after=[module_create_bin])
    def module_create_bin2(self):
        """Check that create module with other binary contents works."""
        self.test_runner.run_module_create_bin2()

    @test(groups=[GROUP, GROUP_MODULE_CREATE],
          depends_on=[module_create])
    def module_show(self):
        """Check that show module works."""
        self.test_runner.run_module_show()

    @test(groups=[GROUP, GROUP_MODULE_CREATE],
          depends_on=[module_create])
    def module_show_unauth_user(self):
        """Ensure that show module for unauth user fails."""
        self.test_runner.run_module_show_unauth_user()

    @test(groups=[GROUP, GROUP_MODULE_CREATE],
          depends_on=[module_create, module_create_bin, module_create_bin2])
    def module_list(self):
        """Check that list modules works."""
        self.test_runner.run_module_list()

    @test(groups=[GROUP, GROUP_MODULE_CREATE],
          depends_on=[module_create, module_create_bin, module_create_bin2])
    def module_list_unauth_user(self):
        """Ensure that list module for unauth user fails."""
        self.test_runner.run_module_list_unauth_user()

    @test(groups=[GROUP, GROUP_MODULE_CREATE],
          depends_on=[module_create, module_create_bin, module_create_bin2],
          runs_after=[module_list])
    def module_create_admin_all(self):
        """Check that create module works with all admin options."""
        self.test_runner.run_module_create_admin_all()

    @test(groups=[GROUP, GROUP_MODULE_CREATE],
          depends_on=[module_create, module_create_bin, module_create_bin2],
          runs_after=[module_create_admin_all])
    def module_create_admin_hidden(self):
        """Check that create module works with hidden option."""
        self.test_runner.run_module_create_admin_hidden()

    @test(groups=[GROUP, GROUP_MODULE_CREATE],
          depends_on=[module_create, module_create_bin, module_create_bin2],
          runs_after=[module_create_admin_hidden])
    def module_create_admin_auto(self):
        """Check that create module works with auto option."""
        self.test_runner.run_module_create_admin_auto()

    @test(groups=[GROUP, GROUP_MODULE_CREATE],
          depends_on=[module_create, module_create_bin, module_create_bin2],
          runs_after=[module_create_admin_auto])
    def module_create_admin_live_update(self):
        """Check that create module works with live-update option."""
        self.test_runner.run_module_create_admin_live_update()

    @test(groups=[GROUP, GROUP_MODULE_CREATE],
          depends_on=[module_create, module_create_bin, module_create_bin2],
          runs_after=[module_create_admin_live_update])
    def module_create_datastore(self):
        """Check that create module with datastore works."""
        self.test_runner.run_module_create_datastore()

    @test(groups=[GROUP, GROUP_MODULE_CREATE],
          depends_on=[module_create, module_create_bin, module_create_bin2],
          runs_after=[module_create_datastore])
    def module_create_ds_version(self):
        """Check that create module with ds version works."""
        self.test_runner.run_module_create_ds_version()

    @test(groups=[GROUP, GROUP_MODULE_CREATE],
          depends_on=[module_create, module_create_bin, module_create_bin2],
          runs_after=[module_create_ds_version])
    def module_create_all_tenant(self):
        """Check that create 'all' tenants with datastore module works."""
        self.test_runner.run_module_create_all_tenant()

    @test(groups=[GROUP, GROUP_MODULE_CREATE],
          depends_on=[module_create, module_create_bin, module_create_bin2],
          runs_after=[module_create_all_tenant, module_list_unauth_user])
    def module_create_different_tenant(self):
        """Check that create with same name on different tenant works."""
        self.test_runner.run_module_create_different_tenant()

    @test(groups=[GROUP, GROUP_MODULE_CREATE],
          depends_on=[module_create_all_tenant],
          runs_after=[module_create_different_tenant])
    def module_list_again(self):
        """Check that list modules skips invisible modules."""
        self.test_runner.run_module_list_again()

    @test(groups=[GROUP, GROUP_MODULE_CREATE],
          depends_on=[module_create_ds_version],
          runs_after=[module_list_again])
    def module_list_ds(self):
        """Check that list modules by datastore works."""
        self.test_runner.run_module_list_ds()

    @test(groups=[GROUP, GROUP_MODULE_CREATE],
          depends_on=[module_create_ds_version],
          runs_after=[module_list_ds])
    def module_list_ds_all(self):
        """Check that list modules by all datastores works."""
        self.test_runner.run_module_list_ds_all()

    @test(groups=[GROUP, GROUP_MODULE_CREATE],
          depends_on=[module_create_admin_hidden])
    def module_show_invisible(self):
        """Ensure that show invisible module for non-admin fails."""
        self.test_runner.run_module_show_invisible()

    @test(groups=[GROUP, GROUP_MODULE_CREATE],
          depends_on=[module_create_all_tenant],
          runs_after=[module_create_different_tenant])
    def module_list_admin(self):
        """Check that list modules for admin works."""
        self.test_runner.run_module_list_admin()

    @test(groups=[GROUP, GROUP_MODULE_CREATE],
          depends_on=[module_create],
          runs_after=[module_show])
    def module_update(self):
        """Check that update module works."""
        self.test_runner.run_module_update()

    @test(groups=[GROUP, GROUP_MODULE_CREATE],
          depends_on=[module_update])
    def module_update_same_contents(self):
        """Check that update module with same contents works."""
        self.test_runner.run_module_update_same_contents()

    @test(groups=[GROUP, GROUP_MODULE_CREATE],
          depends_on=[module_update],
          runs_after=[module_update_same_contents])
    def module_update_auto_toggle(self):
        """Check that update module works for auto apply toggle."""
        self.test_runner.run_module_update_auto_toggle()

    @test(groups=[GROUP, GROUP_MODULE_CREATE],
          depends_on=[module_update],
          runs_after=[module_update_auto_toggle])
    def module_update_all_tenant_toggle(self):
        """Check that update module works for all tenant toggle."""
        self.test_runner.run_module_update_all_tenant_toggle()

    @test(groups=[GROUP, GROUP_MODULE_CREATE],
          depends_on=[module_update],
          runs_after=[module_update_all_tenant_toggle])
    def module_update_invisible_toggle(self):
        """Check that update module works for invisible toggle."""
        self.test_runner.run_module_update_invisible_toggle()

    @test(groups=[GROUP, GROUP_MODULE_CREATE],
          depends_on=[module_update],
          runs_after=[module_update_invisible_toggle])
    def module_update_unauth(self):
        """Ensure update module for unauth user fails."""
        self.test_runner.run_module_update_unauth()

    @test(groups=[GROUP, GROUP_MODULE_CREATE],
          depends_on=[module_update],
          runs_after=[module_update_invisible_toggle])
    def module_update_non_admin_auto(self):
        """Ensure update module to auto_apply for non-admin fails."""
        self.test_runner.run_module_update_non_admin_auto()

    @test(groups=[GROUP, GROUP_MODULE_CREATE],
          depends_on=[module_update],
          runs_after=[module_update_invisible_toggle])
    def module_update_non_admin_auto_off(self):
        """Ensure update module to auto_apply off for non-admin fails."""
        self.test_runner.run_module_update_non_admin_auto_off()

    @test(groups=[GROUP, GROUP_MODULE_CREATE],
          depends_on=[module_update],
          runs_after=[module_update_invisible_toggle])
    def module_update_non_admin_auto_any(self):
        """Ensure any update module to auto_apply for non-admin fails."""
        self.test_runner.run_module_update_non_admin_auto_any()

    @test(groups=[GROUP, GROUP_MODULE_CREATE],
          depends_on=[module_update],
          runs_after=[module_update_invisible_toggle])
    def module_update_non_admin_all_tenant(self):
        """Ensure update module to all tenant for non-admin fails."""
        self.test_runner.run_module_update_non_admin_all_tenant()

    @test(groups=[GROUP, GROUP_MODULE_CREATE],
          depends_on=[module_update],
          runs_after=[module_update_invisible_toggle])
    def module_update_non_admin_all_tenant_off(self):
        """Ensure update module to all tenant off for non-admin fails."""
        self.test_runner.run_module_update_non_admin_all_tenant_off()

    @test(groups=[GROUP, GROUP_MODULE_CREATE],
          depends_on=[module_update],
          runs_after=[module_update_invisible_toggle])
    def module_update_non_admin_all_tenant_any(self):
        """Ensure any update module to all tenant for non-admin fails."""
        self.test_runner.run_module_update_non_admin_all_tenant_any()

    @test(groups=[GROUP, GROUP_MODULE_CREATE],
          depends_on=[module_update],
          runs_after=[module_update_invisible_toggle])
    def module_update_non_admin_invisible(self):
        """Ensure update module to invisible for non-admin fails."""
        self.test_runner.run_module_update_non_admin_invisible()

    @test(groups=[GROUP, GROUP_MODULE_CREATE],
          depends_on=[module_update],
          runs_after=[module_update_invisible_toggle])
    def module_update_non_admin_invisible_off(self):
        """Ensure update module to invisible off for non-admin fails."""
        self.test_runner.run_module_update_non_admin_invisible_off()

    @test(groups=[GROUP, GROUP_MODULE_CREATE],
          depends_on=[module_update],
          runs_after=[module_update_invisible_toggle])
    def module_update_non_admin_invisible_any(self):
        """Ensure any update module to invisible for non-admin fails."""
        self.test_runner.run_module_update_non_admin_invisible_any()


@test(depends_on_groups=[instance_create_group.GROUP,
                         GROUP_MODULE_CREATE],
      groups=[GROUP, GROUP_INSTANCE_MODULE])
class ModuleInstanceGroup(TestGroup):
    """Test Instance Module functionality."""

    def __init__(self):
        super(ModuleInstanceGroup, self).__init__(
            'module_runners', 'ModuleRunner')

    @test(groups=[GROUP, GROUP_INSTANCE_MODULE])
    def module_list_instance_empty(self):
        """Check that the instance has no modules associated."""
        self.test_runner.run_module_list_instance_empty()

    @test(groups=[GROUP, GROUP_INSTANCE_MODULE],
          runs_after=[module_list_instance_empty])
    def module_instances_empty(self):
        """Check that the module hasn't been applied to any instances."""
        self.test_runner.run_module_instances_empty()

    @test(groups=[GROUP, GROUP_INSTANCE_MODULE],
          runs_after=[module_instances_empty])
    def module_query_empty(self):
        """Check that the instance has no modules applied."""
        self.test_runner.run_module_query_empty()

    @test(groups=[GROUP, GROUP_INSTANCE_MODULE],
          runs_after=[module_query_empty])
    def module_apply(self):
        """Check that module-apply works."""
        self.test_runner.run_module_apply()

    @test(groups=[GROUP, GROUP_INSTANCE_MODULE],
          depends_on=[module_apply])
    def module_list_instance_after_apply(self):
        """Check that the instance has one module associated."""
        self.test_runner.run_module_list_instance_after_apply()

    @test(groups=[GROUP, GROUP_INSTANCE_MODULE],
          depends_on=[module_apply])
    def module_query_after_apply(self):
        """Check that module-query works."""
        self.test_runner.run_module_query_after_apply()

    @test(groups=[GROUP, GROUP_INSTANCE_MODULE],
          depends_on=[module_apply],
          runs_after=[module_query_after_apply])
    def create_inst_with_mods(self):
        """Check that creating an instance with modules works."""
        self.test_runner.run_create_inst_with_mods()

    @test(groups=[GROUP, GROUP_INSTANCE_MODULE],
          depends_on=[module_apply])
    def module_delete_applied(self):
        """Ensure that deleting an applied module fails."""
        self.test_runner.run_module_delete_applied()

    @test(groups=[GROUP, GROUP_INSTANCE_MODULE],
          depends_on=[module_apply],
          runs_after=[module_list_instance_after_apply,
                      module_query_after_apply])
    def module_remove(self):
        """Check that module-remove works."""
        self.test_runner.run_module_remove()

    @test(groups=[GROUP, GROUP_INSTANCE_MODULE],
          depends_on=[module_remove])
    def module_query_empty_after(self):
        """Check that the instance has no modules applied after remove."""
        self.test_runner.run_module_query_empty()

    @test(groups=[GROUP, GROUP_INSTANCE_MODULE],
          depends_on=[create_inst_with_mods],
          runs_after=[module_query_empty_after])
    def wait_for_inst_with_mods(self):
        """Wait for create instance with modules to finish."""
        self.test_runner.run_wait_for_inst_with_mods()

    @test(groups=[GROUP, GROUP_INSTANCE_MODULE],
          depends_on=[wait_for_inst_with_mods])
    def module_query_after_inst_create(self):
        """Check that module-query works on new instance."""
        self.test_runner.run_module_query_after_inst_create()

    @test(groups=[GROUP, GROUP_INSTANCE_MODULE],
          depends_on=[wait_for_inst_with_mods],
          runs_after=[module_query_after_inst_create])
    def module_retrieve_after_inst_create(self):
        """Check that module-retrieve works on new instance."""
        self.test_runner.run_module_retrieve_after_inst_create()

    @test(groups=[GROUP, GROUP_INSTANCE_MODULE],
          depends_on=[wait_for_inst_with_mods],
          runs_after=[module_retrieve_after_inst_create])
    def module_query_after_inst_create_admin(self):
        """Check that module-query works for admin."""
        self.test_runner.run_module_query_after_inst_create_admin()

    @test(groups=[GROUP, GROUP_INSTANCE_MODULE],
          depends_on=[wait_for_inst_with_mods],
          runs_after=[module_query_after_inst_create_admin])
    def module_retrieve_after_inst_create_admin(self):
        """Check that module-retrieve works for admin."""
        self.test_runner.run_module_retrieve_after_inst_create_admin()

    @test(groups=[GROUP, GROUP_INSTANCE_MODULE],
          depends_on=[wait_for_inst_with_mods],
          runs_after=[module_retrieve_after_inst_create_admin])
    def module_delete_auto_applied(self):
        """Ensure that module-delete on auto-applied module fails."""
        self.test_runner.run_module_delete_auto_applied()

    @test(groups=[GROUP, GROUP_INSTANCE_MODULE],
          depends_on=[wait_for_inst_with_mods],
          runs_after=[module_delete_auto_applied])
    def delete_inst_with_mods(self):
        """Check that instance with module can be deleted."""
        self.test_runner.run_delete_inst_with_mods()


@test(depends_on_groups=[GROUP_MODULE_CREATE],
      groups=[GROUP, GROUP_MODULE_DELETE])
class ModuleDeleteGroup(TestGroup):
    """Test Module Delete functionality."""

    def __init__(self):
        super(ModuleDeleteGroup, self).__init__(
            'module_runners', 'ModuleRunner')

    @test(groups=[GROUP, GROUP_MODULE_DELETE])
    def module_delete_non_existent(self):
        """Ensure delete non-existent module fails."""
        self.test_runner.run_module_delete_non_existent()

    @test(groups=[GROUP, GROUP_MODULE_DELETE])
    def module_delete_unauth_user(self):
        """Ensure delete module by unauth user fails."""
        self.test_runner.run_module_delete_unauth_user()

    @test(groups=[GROUP, GROUP_MODULE_DELETE],
          runs_after=[module_delete_unauth_user])
    def module_delete_hidden_by_non_admin(self):
        """Ensure delete hidden module by non-admin user fails."""
        self.test_runner.run_module_delete_hidden_by_non_admin()

    @test(groups=[GROUP, GROUP_MODULE_DELETE],
          runs_after=[module_delete_hidden_by_non_admin])
    def module_delete_all_tenant_by_non_admin(self):
        """Ensure delete all tenant module by non-admin user fails."""
        self.test_runner.run_module_delete_all_tenant_by_non_admin()

    @test(groups=[GROUP, GROUP_MODULE_DELETE],
          runs_after=[module_delete_all_tenant_by_non_admin])
    def module_delete_auto_by_non_admin(self):
        """Ensure delete auto-apply module by non-admin user fails."""
        self.test_runner.run_module_delete_auto_by_non_admin()

    @test(groups=[GROUP, GROUP_MODULE_DELETE],
          runs_after=[module_delete_auto_by_non_admin])
    def module_delete(self):
        """Check that delete module works."""
        self.test_runner.run_module_delete()

    @test(groups=[GROUP, GROUP_MODULE_DELETE],
          runs_after=[module_delete])
    def module_delete_admin(self):
        """Check that delete module works for admin."""
        self.test_runner.run_module_delete_admin()

    @test(groups=[GROUP, GROUP_MODULE_DELETE],
          runs_after=[module_delete_admin])
    def module_delete_remaining(self):
        """Delete all remaining test modules."""
        self.test_runner.run_module_delete_existing()
