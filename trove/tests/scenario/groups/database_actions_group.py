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


GROUP = "scenario.database_actions_group"


@test(depends_on_groups=[instance_create_group.GROUP], groups=[GROUP])
class DatabaseActionsGroup(TestGroup):

    def __init__(self):
        super(DatabaseActionsGroup, self).__init__(
            'database_actions_runners', 'DatabaseActionsRunner')
        self.instance_create_runner = self.get_runner(
            'instance_create_runners', 'InstanceCreateRunner')

    @test
    def create_initialized_instance(self):
        """Create an instance with initial databases."""
        self.instance_create_runner.run_initialized_instance_create(
            with_dbs=True, with_users=False, configuration_id=None)

    @test(runs_after=[create_initialized_instance])
    def create_databases(self):
        """Create databases on an existing instance."""
        self.test_runner.run_databases_create()

    @test(depends_on=[create_databases])
    def list_databases(self):
        """List the created databases."""
        self.test_runner.run_databases_list()

    @test(depends_on=[create_databases],
          runs_after=[list_databases])
    def create_database_with_no_attributes(self):
        """Ensure creating a database with blank specification fails."""
        self.test_runner.run_database_create_with_no_attributes()

    @test(depends_on=[create_databases],
          runs_after=[create_database_with_no_attributes])
    def create_database_with_blank_name(self):
        """Ensure creating a database with blank name fails."""
        self.test_runner.run_database_create_with_blank_name()

    @test(depends_on=[create_databases],
          runs_after=[create_database_with_blank_name])
    def create_existing_database(self):
        """Ensure creating an existing database fails."""
        self.test_runner.run_existing_database_create()

    @test(depends_on=[create_databases],
          runs_after=[create_existing_database])
    def delete_database(self):
        """Delete the created databases."""
        self.test_runner.run_database_delete()

    @test(runs_after=[delete_database])
    def delete_nonexisting_database(self):
        """Delete non-existing databases."""
        self.test_runner.run_nonexisting_database_delete()

    @test(runs_after=[delete_nonexisting_database])
    def create_system_database(self):
        """Ensure creating a system database fails."""
        self.test_runner.run_system_database_create()

    @test(runs_after=[create_system_database])
    def delete_system_database(self):
        """Ensure deleting a system database fails."""
        self.test_runner.run_system_database_delete()

    @test(depends_on=[create_initialized_instance],
          runs_after=[delete_system_database])
    def wait_for_instances(self):
        """Waiting for all instances to become active."""
        self.instance_create_runner.wait_for_created_instances()

    @test(depends_on=[wait_for_instances])
    def add_initialized_instance_data(self):
        """Add data to the initialized instance."""
        self.instance_create_runner.run_add_initialized_instance_data()

    @test(runs_after=[add_initialized_instance_data])
    def validate_initialized_instance(self):
        """Validate the initialized instance data and properties."""
        self.instance_create_runner.run_validate_initialized_instance()

    @test(runs_after=[validate_initialized_instance])
    def delete_initialized_instance(self):
        """Delete the initialized instance."""
        self.instance_create_runner.run_initialized_instance_delete()
