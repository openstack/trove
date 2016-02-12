# Copyright 2015 Tesora Inc.
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


GROUP = "scenario.guest_log_group"


@test(depends_on_groups=[instance_create_group.GROUP], groups=[GROUP])
class GuestLogGroup(TestGroup):
    """Test Guest Log functionality."""

    def __init__(self):
        super(GuestLogGroup, self).__init__(
            'guest_log_runners', 'GuestLogRunner')

    @test
    def test_log_list(self):
        """Test that log-list works."""
        self.test_runner.run_test_log_list()

    @test
    def test_admin_log_list(self):
        """Test that log-list works for admin user."""
        self.test_runner.run_test_admin_log_list()

    @test
    def test_log_show(self):
        """Test that log-show works on USER log."""
        self.test_runner.run_test_log_show()

    @test
    def test_log_enable_sys(self):
        """Ensure log-enable on SYS log fails."""
        self.test_runner.run_test_log_enable_sys()

    @test
    def test_log_disable_sys(self):
        """Ensure log-disable on SYS log fails."""
        self.test_runner.run_test_log_disable_sys()

    @test
    def test_log_show_unauth_user(self):
        """Ensure log-show by unauth client on USER log fails."""
        self.test_runner.run_test_log_show_unauth_user()

    @test
    def test_log_list_unauth_user(self):
        """Ensure log-list by unauth client on USER log fails."""
        self.test_runner.run_test_log_list_unauth_user()

    @test
    def test_log_generator_unauth_user(self):
        """Ensure log-generator by unauth client on USER log fails."""
        self.test_runner.run_test_log_generator_unauth_user()

    @test
    def test_log_generator_publish_unauth_user(self):
        """Ensure log-generator by unauth client with publish fails."""
        self.test_runner.run_test_log_generator_publish_unauth_user()

    @test
    def test_log_show_unexposed_user(self):
        """Ensure log-show on unexposed log fails for auth client."""
        self.test_runner.run_test_log_show_unexposed_user()

    @test
    def test_log_enable_unexposed_user(self):
        """Ensure log-enable on unexposed log fails for auth client."""
        self.test_runner.run_test_log_enable_unexposed_user()

    @test
    def test_log_disable_unexposed_user(self):
        """Ensure log-disable on unexposed log fails for auth client."""
        self.test_runner.run_test_log_disable_unexposed_user()

    @test
    def test_log_publish_unexposed_user(self):
        """Ensure log-publish on unexposed log fails for auth client."""
        self.test_runner.run_test_log_publish_unexposed_user()

    @test
    def test_log_discard_unexposed_user(self):
        """Ensure log-discard on unexposed log fails for auth client."""
        self.test_runner.run_test_log_discard_unexposed_user()

    @test(runs_after=[test_log_show])
    def test_log_enable_user(self):
        """Test log-enable on USER log."""
        self.test_runner.run_test_log_enable_user()

    @test(runs_after=[test_log_enable_user])
    def test_log_enable_flip_user(self):
        """Test that flipping restart-required log-enable works."""
        self.test_runner.run_test_log_enable_flip_user()

    @test(runs_after=[test_log_enable_flip_user])
    def test_restart_datastore(self):
        """Test restart datastore if required."""
        self.test_runner.run_test_restart_datastore()

    @test(runs_after=[test_restart_datastore])
    def test_wait_for_restart(self):
        """Wait for restart to complete."""
        self.test_runner.run_test_wait_for_restart()

    @test(runs_after=[test_wait_for_restart])
    def test_log_publish_user(self):
        """Test log-publish on USER log."""
        self.test_runner.run_test_log_publish_user()

    @test(runs_after=[test_log_publish_user])
    def test_add_data(self):
        """Add data for second log-publish on USER log."""
        self.test_runner.run_test_add_data()

    @test(runs_after=[test_add_data])
    def test_verify_data(self):
        """Verify data for second log-publish on USER log."""
        self.test_runner.run_test_verify_data()

    @test(runs_after=[test_verify_data])
    def test_log_publish_again_user(self):
        """Test log-publish again on USER log."""
        self.test_runner.run_test_log_publish_again_user()

    @test(runs_after=[test_log_publish_again_user])
    def test_log_generator_user(self):
        """Test log-generator on USER log."""
        self.test_runner.run_test_log_generator_user()

    @test(runs_after=[test_log_generator_user])
    def test_log_generator_publish_user(self):
        """Test log-generator with publish on USER log."""
        self.test_runner.run_test_log_generator_publish_user()

    @test(runs_after=[test_log_generator_publish_user])
    def test_log_generator_swift_client_user(self):
        """Test log-generator on USER log with passed-in Swift client."""
        self.test_runner.run_test_log_generator_swift_client_user()

    @test(runs_after=[test_log_generator_swift_client_user])
    def test_add_data_again(self):
        """Add more data for log-generator row-by-row test on USER log."""
        self.test_runner.run_test_add_data_again()

    @test(runs_after=[test_add_data_again])
    def test_verify_data_again(self):
        """Verify data for log-generator row-by-row test on USER log."""
        self.test_runner.run_test_verify_data_again()

    @test(runs_after=[test_verify_data_again])
    def test_log_generator_user_by_row(self):
        """Test log-generator on USER log row-by-row."""
        self.test_runner.run_test_log_generator_user_by_row()

    @test(depends_on=[test_log_publish_user],
          runs_after=[test_log_generator_user_by_row])
    def test_log_save_user(self):
        """Test log-save on USER log."""
        self.test_runner.run_test_log_save_user()

    @test(depends_on=[test_log_publish_user],
          runs_after=[test_log_save_user])
    def test_log_save_publish_user(self):
        """Test log-save on USER log with publish."""
        self.test_runner.run_test_log_save_publish_user()

    @test(runs_after=[test_log_save_publish_user])
    def test_log_discard_user(self):
        """Test log-discard on USER log."""
        self.test_runner.run_test_log_discard_user()

    @test(runs_after=[test_log_discard_user])
    def test_log_disable_user(self):
        """Test log-disable on USER log."""
        self.test_runner.run_test_log_disable_user()

    @test(runs_after=[test_log_disable_user])
    def test_restart_datastore_again(self):
        """Test restart datastore again if required."""
        self.test_runner.run_test_restart_datastore()

    @test(runs_after=[test_restart_datastore_again])
    def test_wait_for_restart_again(self):
        """Wait for restart to complete again."""
        self.test_runner.run_test_wait_for_restart()

    @test
    def test_log_show_sys(self):
        """Test that log-show works for SYS log."""
        self.test_runner.run_test_log_show_sys()

    @test(runs_after=[test_log_show_sys])
    def test_log_publish_sys(self):
        """Test log-publish on SYS log."""
        self.test_runner.run_test_log_publish_sys()

    @test(runs_after=[test_log_publish_sys])
    def test_log_publish_again_sys(self):
        """Test log-publish again on SYS log."""
        self.test_runner.run_test_log_publish_again_sys()

    @test(depends_on=[test_log_publish_again_sys])
    def test_log_generator_sys(self):
        """Test log-generator on SYS log."""
        self.test_runner.run_test_log_generator_sys()

    @test(runs_after=[test_log_generator_sys])
    def test_log_generator_publish_sys(self):
        """Test log-generator with publish on SYS log."""
        self.test_runner.run_test_log_generator_publish_sys()

    @test(depends_on=[test_log_publish_sys],
          runs_after=[test_log_generator_publish_sys])
    def test_log_generator_swift_client_sys(self):
        """Test log-generator on SYS log with passed-in Swift client."""
        self.test_runner.run_test_log_generator_swift_client_sys()

    @test(depends_on=[test_log_publish_sys],
          runs_after=[test_log_generator_swift_client_sys])
    def test_log_save_sys(self):
        """Test log-save on SYS log."""
        self.test_runner.run_test_log_save_sys()

    @test(runs_after=[test_log_save_sys])
    def test_log_save_publish_sys(self):
        """Test log-save on SYS log with publish."""
        self.test_runner.run_test_log_save_publish_sys()

    @test(runs_after=[test_log_save_publish_sys])
    def test_log_discard_sys(self):
        """Test log-discard on SYS log."""
        self.test_runner.run_test_log_discard_sys()
