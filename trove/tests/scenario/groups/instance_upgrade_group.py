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
from proboscis import SkipTest
from proboscis import test

from trove.tests.scenario import groups
from trove.tests.scenario.groups.test_group import TestGroup
from trove.tests.scenario.runners import test_runners


GROUP = "scenario.instance_upgrade_group"


class InstanceUpgradeRunnerFactory(test_runners.RunnerFactory):

    _runner_ns = 'instance_upgrade_runners'
    _runner_cls = 'InstanceUpgradeRunner'


class UserActionsRunnerFactory(test_runners.RunnerFactory):

    _runner_ns = 'user_actions_runners'
    _runner_cls = 'UserActionsRunner'


class DatabaseActionsRunnerFactory(test_runners.RunnerFactory):

    _runner_ns = 'database_actions_runners'
    _runner_cls = 'DatabaseActionsRunner'


@test(depends_on_groups=[groups.INST_CREATE_WAIT],
      groups=[GROUP, groups.INST_UPGRADE],
      runs_after_groups=[groups.INST_ACTIONS])
class InstanceUpgradeGroup(TestGroup):

    def __init__(self):
        super(InstanceUpgradeGroup, self).__init__(
            InstanceUpgradeRunnerFactory.instance())
        self.database_actions_runner = DatabaseActionsRunnerFactory.instance()
        self.user_actions_runner = UserActionsRunnerFactory.instance()

    @test
    def create_user_databases(self):
        """Create user databases on an existing instance."""
        # These databases may be referenced by the users (below) so we need to
        # create them first.
        self.database_actions_runner.run_databases_create()

    @test(runs_after=[create_user_databases])
    def create_users(self):
        """Create users on an existing instance."""
        self.user_actions_runner.run_users_create()

    @test(runs_after=[create_users])
    def add_test_data(self):
        """Add test data."""
        self.test_runner.run_add_test_data()

    @test(depends_on=[add_test_data])
    def verify_test_data(self):
        """Verify test data."""
        self.test_runner.run_verify_test_data()

    @test(depends_on=[verify_test_data])
    def list_users_before_upgrade(self):
        """List the created users before upgrade."""
        self.user_actions_runner.run_users_list()

    @test(depends_on=[list_users_before_upgrade])
    def instance_upgrade(self):
        """Upgrade an existing instance."""
        raise SkipTest("Skip the instance upgrade integration test "
                       "temporarily because of not stable in CI")
        # self.test_runner.run_instance_upgrade()

    @test(depends_on=[list_users_before_upgrade])
    def show_user(self):
        """Show created users."""
        self.user_actions_runner.run_user_show()

    @test(depends_on=[create_users],
          runs_after=[show_user])
    def list_users(self):
        """List the created users."""
        self.user_actions_runner.run_users_list()

    @test(depends_on=[verify_test_data, instance_upgrade])
    def verify_test_data_after_upgrade(self):
        """Verify test data after upgrade."""
        self.test_runner.run_verify_test_data()

    @test(depends_on=[add_test_data],
          runs_after=[verify_test_data_after_upgrade])
    def remove_test_data(self):
        """Remove test data."""
        self.test_runner.run_remove_test_data()

    @test(depends_on=[create_users],
          runs_after=[list_users])
    def delete_user(self):
        """Delete the created users."""
        self.user_actions_runner.run_user_delete()

    @test(depends_on=[create_user_databases], runs_after=[delete_user])
    def delete_user_databases(self):
        """Delete the user databases."""
        self.database_actions_runner.run_database_delete()
