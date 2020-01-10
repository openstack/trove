# Copyright 2015 Tesora Inc.
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

from proboscis import test

from trove.tests.scenario import groups
from trove.tests.scenario.groups.test_group import TestGroup
from trove.tests.scenario.runners import test_runners


GROUP = "scenario.user_actions_group"


class UserActionsRunnerFactory(test_runners.RunnerFactory):

    _runner_ns = 'user_actions_runners'
    _runner_cls = 'UserActionsRunner'


class InstanceCreateRunnerFactory(test_runners.RunnerFactory):

    _runner_ns = 'instance_create_runners'
    _runner_cls = 'InstanceCreateRunner'


class DatabaseActionsRunnerFactory(test_runners.RunnerFactory):

    _runner_ns = 'database_actions_runners'
    _runner_cls = 'DatabaseActionsRunner'


@test(depends_on_groups=[groups.ROOT_ACTION_INST_DELETE_WAIT],
      groups=[GROUP, groups.USER_ACTION_CREATE])
class UserActionsCreateGroup(TestGroup):
    """Test User Actions Create functionality."""

    def __init__(self):
        super(UserActionsCreateGroup, self).__init__(
            UserActionsRunnerFactory.instance())
        self.database_actions_runner = DatabaseActionsRunnerFactory.instance()

    @test
    def create_user_databases(self):
        """Create user databases on an existing instance."""
        # These databases may be referenced by the users (below) so we need to
        # create them first.
        self.database_actions_runner.run_databases_create()

    @test(runs_after=[create_user_databases])
    def create_users(self):
        """Create users on an existing instance."""
        self.test_runner.run_users_create()

    @test(depends_on=[create_users])
    def show_user(self):
        """Show created users."""
        self.test_runner.run_user_show()

    @test(depends_on=[create_users],
          runs_after=[show_user])
    def list_users(self):
        """List the created users."""
        self.test_runner.run_users_list()

    @test(depends_on=[create_users],
          runs_after=[list_users])
    def show_user_access(self):
        """Show user access list."""
        self.test_runner.run_user_access_show()

    @test(depends_on=[create_users],
          runs_after=[show_user_access])
    def revoke_user_access(self):
        """Revoke user database access."""
        self.test_runner.run_user_access_revoke()

    @test(depends_on=[create_users],
          runs_after=[revoke_user_access])
    def grant_user_access(self):
        """Grant user database access."""
        self.test_runner.run_user_access_grant()

    @test(depends_on=[create_users],
          runs_after=[grant_user_access])
    def create_user_with_no_attributes(self):
        """Ensure creating a user with blank specification fails."""
        self.test_runner.run_user_create_with_no_attributes()

    @test(depends_on=[create_users],
          runs_after=[create_user_with_no_attributes])
    def create_user_with_blank_name(self):
        """Ensure creating a user with blank name fails."""
        self.test_runner.run_user_create_with_blank_name()

    @test(depends_on=[create_users],
          runs_after=[create_user_with_blank_name])
    def create_user_with_blank_password(self):
        """Ensure creating a user with blank password fails."""
        self.test_runner.run_user_create_with_blank_password()

    @test(depends_on=[create_users],
          runs_after=[create_user_with_blank_password])
    def create_existing_user(self):
        """Ensure creating an existing user fails."""
        self.test_runner.run_existing_user_create()

    @test(depends_on=[create_users],
          runs_after=[create_existing_user])
    def update_user_with_blank_name(self):
        """Ensure updating a user with blank name fails."""
        self.test_runner.run_user_update_with_blank_name()

    @test(depends_on=[create_users],
          runs_after=[update_user_with_blank_name])
    def update_user_with_existing_name(self):
        """Ensure updating a user with an existing name fails."""
        self.test_runner.run_user_update_with_existing_name()

    @test(depends_on=[create_users],
          runs_after=[update_user_with_existing_name])
    def update_user_attributes(self):
        """Update an existing user."""
        self.test_runner.run_user_attribute_update()

    @test(depends_on=[update_user_attributes])
    def recreate_user_with_no_access(self):
        """Re-create a renamed user with no access rights."""
        self.test_runner.run_user_recreate_with_no_access()

    @test
    def show_nonexisting_user(self):
        """Ensure show on non-existing user fails."""
        self.test_runner.run_nonexisting_user_show()

    @test
    def update_nonexisting_user(self):
        """Ensure updating a non-existing user fails."""
        self.test_runner.run_nonexisting_user_update()

    @test
    def delete_nonexisting_user(self):
        """Ensure deleting a non-existing user fails."""
        self.test_runner.run_nonexisting_user_delete()

    @test
    def create_system_user(self):
        """Ensure creating a system user fails."""
        self.test_runner.run_system_user_create()

    @test
    def show_system_user(self):
        """Ensure showing a system user fails."""
        self.test_runner.run_system_user_show()

    @test
    def update_system_user(self):
        """Ensure updating a system user fails."""
        self.test_runner.run_system_user_attribute_update()


@test(depends_on_classes=[UserActionsCreateGroup],
      groups=[GROUP, groups.USER_ACTION_DELETE])
class UserActionsDeleteGroup(TestGroup):
    """Test User Actions Delete functionality."""

    def __init__(self):
        super(UserActionsDeleteGroup, self).__init__(
            UserActionsRunnerFactory.instance())
        self.database_actions_runner = DatabaseActionsRunnerFactory.instance()

    @test
    def delete_user(self):
        """Delete the created users."""
        self.test_runner.run_user_delete()

    @test
    def delete_system_user(self):
        """Ensure deleting a system user fails."""
        self.test_runner.run_system_user_delete()

    @test
    def delete_user_databases(self):
        """Delete the user databases."""
        self.database_actions_runner.run_database_delete()


@test(groups=[GROUP, groups.USER_ACTION_INST, groups.USER_ACTION_INST_CREATE],
      depends_on_classes=[UserActionsDeleteGroup])
class UserActionsInstCreateGroup(TestGroup):
    """Test User Actions Instance Create functionality."""

    def __init__(self):
        super(UserActionsInstCreateGroup, self).__init__(
            UserActionsRunnerFactory.instance())
        self.instance_create_runner = InstanceCreateRunnerFactory.instance()

    @test
    def create_initialized_instance(self):
        """Create an instance with initial users."""
        self.instance_create_runner.run_initialized_instance_create(
            with_dbs=False, with_users=True, configuration_id=None,
            create_helper_user=False, name_suffix='_user')


@test(depends_on_classes=[UserActionsInstCreateGroup],
      groups=[GROUP, groups.USER_ACTION_INST,
              groups.USER_ACTION_INST_CREATE_WAIT])
class UserActionsInstCreateWaitGroup(TestGroup):
    """Wait for User Actions Instance Create to complete."""

    def __init__(self):
        super(UserActionsInstCreateWaitGroup, self).__init__(
            UserActionsRunnerFactory.instance())
        self.instance_create_runner = InstanceCreateRunnerFactory.instance()

    @test
    def wait_for_instances(self):
        """Waiting for user instance to become active."""
        self.instance_create_runner.run_wait_for_init_instance()

    @test(depends_on=[wait_for_instances])
    def validate_initialized_instance(self):
        """Validate the user instance data and properties."""
        self.instance_create_runner.run_validate_initialized_instance()


@test(depends_on_classes=[UserActionsInstCreateWaitGroup],
      groups=[GROUP, groups.USER_ACTION_INST, groups.USER_ACTION_INST_DELETE])
class UserActionsInstDeleteGroup(TestGroup):
    """Test User Actions Instance Delete functionality."""

    def __init__(self):
        super(UserActionsInstDeleteGroup, self).__init__(
            DatabaseActionsRunnerFactory.instance())
        self.instance_create_runner = InstanceCreateRunnerFactory.instance()

    @test
    def delete_initialized_instance(self):
        """Delete the user instance."""
        self.instance_create_runner.run_initialized_instance_delete()


@test(depends_on_classes=[UserActionsInstDeleteGroup],
      groups=[GROUP, groups.USER_ACTION_INST,
              groups.USER_ACTION_INST_DELETE_WAIT])
class UserActionsInstDeleteWaitGroup(TestGroup):
    """Wait for User Actions Instance Delete to complete."""

    def __init__(self):
        super(UserActionsInstDeleteWaitGroup, self).__init__(
            DatabaseActionsRunnerFactory.instance())
        self.instance_create_runner = InstanceCreateRunnerFactory.instance()

    @test
    def wait_for_delete_initialized_instance(self):
        """Wait for the user instance to delete."""
        self.instance_create_runner.run_wait_for_init_delete()
