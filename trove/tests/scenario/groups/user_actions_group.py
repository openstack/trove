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

from trove.tests.scenario.groups import instance_create_group
from trove.tests.scenario.groups.test_group import TestGroup


GROUP = "scenario.user_actions_group"


@test(depends_on_groups=[instance_create_group.GROUP], groups=[GROUP])
class UserActionsGroup(TestGroup):

    def __init__(self):
        super(UserActionsGroup, self).__init__(
            'user_actions_runners', 'UserActionsRunner')
        self.instance_create_runner = self.get_runner(
            'instance_create_runners', 'InstanceCreateRunner')
        self.database_actions_runner = self.get_runner(
            'database_actions_runners', 'DatabaseActionsRunner')

    @test
    def create_initialized_instance(self):
        """Create an instance with initial users."""
        self.instance_create_runner.run_initialized_instance_create(
            with_dbs=False, with_users=True, configuration_id=None,
            create_helper_user=False)

    @test(runs_after=[create_initialized_instance])
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
    def update_user_with_no_attributes(self):
        """Ensure updating a user with blank specification fails."""
        self.test_runner.run_user_update_with_no_attributes()

    @test(depends_on=[create_users],
          runs_after=[update_user_with_no_attributes])
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

    @test(depends_on=[create_users],
          runs_after=[update_user_attributes])
    def delete_user(self):
        """Delete the created users."""
        self.test_runner.run_user_delete()

    @test(runs_after=[delete_user])
    def show_nonexisting_user(self):
        """Delete non-existing users."""
        self.test_runner.run_nonexisting_user_show()

    @test(runs_after=[show_nonexisting_user])
    def update_nonexisting_user(self):
        """Ensure updating a non-existing user fails."""
        self.test_runner.run_nonexisting_user_update()

    @test(runs_after=[update_nonexisting_user])
    def delete_nonexisting_user(self):
        """Ensure deleting a non-existing user fails."""
        self.test_runner.run_nonexisting_user_delete()

    @test(runs_after=[delete_nonexisting_user])
    def create_system_user(self):
        """Ensure creating a system user fails."""
        self.test_runner.run_system_user_create()

    @test(runs_after=[create_system_user])
    def show_system_user(self):
        """Ensure showing a system user fails."""
        self.test_runner.run_system_user_show()

    @test(runs_after=[show_system_user])
    def update_system_user(self):
        """Ensure updating a system user fails."""
        self.test_runner.run_system_user_attribute_update()

    @test(runs_after=[update_system_user])
    def delete_system_user(self):
        """Ensure deleting a system user fails."""
        self.test_runner.run_system_user_delete()

    @test(depends_on=[create_user_databases], runs_after=[delete_system_user])
    def delete_user_databases(self):
        """Delete the user databases."""
        self.database_actions_runner.run_database_delete()

    @test(depends_on=[create_initialized_instance],
          runs_after=[delete_user_databases])
    def wait_for_instances(self):
        """Waiting for all instances to become active."""
        self.instance_create_runner.wait_for_created_instances()

    @test(depends_on=[wait_for_instances])
    def validate_initialized_instance(self):
        """Validate the initialized instance data and properties."""
        self.instance_create_runner.run_validate_initialized_instance()

    @test(runs_after=[validate_initialized_instance])
    def delete_initialized_instance(self):
        """Delete the initialized instance."""
        self.instance_create_runner.run_initialized_instance_delete()
