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

from trove.tests.api.instances import GROUP_START_SIMPLE
from trove.tests.api.instances import WaitForGuestInstallationToFinish
from trove.tests.scenario.groups import instance_actions_group
from trove.tests.scenario.groups.test_group import TestGroup

GROUP = "dbaas.api.user_actions_tests"


@test(depends_on_groups=[GROUP_START_SIMPLE], groups=[GROUP],
      runs_after=[WaitForGuestInstallationToFinish],
      runs_after_groups=[instance_actions_group.GROUP])
class UserActionsGroup(TestGroup):

    def __init__(self):
        super(UserActionsGroup, self).__init__(
            'user_actions_runners', 'UserActionsRunner')

    @test
    def create_users(self):
        self.test_runner.run_users_create()

    @test(depends_on=[create_users])
    def show_user(self):
        self.test_runner.run_user_show()

    @test(depends_on=[create_users],
          runs_after=[show_user])
    def list_users(self):
        self.test_runner.run_users_list()

    @test(depends_on=[create_users],
          runs_after=[list_users])
    def negative_create_user(self):
        self.test_runner.run_negative_user_create()

    @test(depends_on=[create_users],
          runs_after=[list_users])
    def negative_user_attribute_update(self):
        self.test_runner.run_negative_user_attribute_update()

    @test(depends_on=[create_users],
          runs_after=[negative_user_attribute_update])
    def user_attribute_update(self):
        self.test_runner.run_user_attribute_update()

    @test(depends_on=[create_users],
          runs_after=[user_attribute_update])
    def delete_user(self):
        self.test_runner.run_user_delete()

    @test
    def nonexisting_user_show(self):
        self.test_runner.run_nonexisting_user_show()

    @test
    def nonexisting_user_attribute_update(self):
        self.test_runner.run_nonexisting_user_update()

    @test
    def nonexisting_user_delete(self):
        self.test_runner.run_nonexisting_user_delete()

    @test
    def system_user_create(self):
        self.test_runner.run_system_user_create()

    @test
    def system_user_show(self):
        self.test_runner.run_system_user_show()

    @test
    def system_user_attribute_update(self):
        self.test_runner.run_system_user_attribute_update()

    @test
    def system_user_delete(self):
        self.test_runner.run_system_user_delete()
