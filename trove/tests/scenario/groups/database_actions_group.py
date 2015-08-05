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
from trove.tests.scenario.groups.test_group import TestGroup
from trove.tests.scenario.groups import user_actions_group

GROUP = "dbaas.api.database_actions_tests"


@test(depends_on_groups=[GROUP_START_SIMPLE], groups=[GROUP],
      runs_after=[WaitForGuestInstallationToFinish],
      runs_after_groups=[user_actions_group.GROUP])
class DatabaseActionsGroup(TestGroup):

    def __init__(self):
        super(DatabaseActionsGroup, self).__init__(
            'database_actions_runners', 'DatabaseActionsRunner')

    @test
    def create_databases(self):
        self.test_runner.run_databases_create()

    @test(depends_on=[create_databases])
    def list_databases(self):
        self.test_runner.run_databases_list()

    @test(depends_on=[create_databases],
          runs_after=[list_databases])
    def negative_create_database(self):
        self.test_runner.run_negative_database_create()

    @test(depends_on=[create_databases],
          runs_after=[negative_create_database])
    def delete_database(self):
        self.test_runner.run_database_delete()

    @test
    def nonexisting_database_delete(self):
        self.test_runner.run_nonexisting_database_delete()

    @test
    def system_database_create(self):
        self.test_runner.run_system_database_create()

    @test
    def system_database_delete(self):
        self.test_runner.run_system_database_delete()
