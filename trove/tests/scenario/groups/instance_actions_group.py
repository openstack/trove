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
from trove.tests.scenario.runners import test_runners


GROUP = "scenario.instance_actions_group"


class InstanceActionsRunnerFactory(test_runners.RunnerFactory):

    _runner_ns = 'instance_actions_runners'
    _runner_cls = 'InstanceActionsRunner'


@test(depends_on_groups=[instance_create_group.GROUP], groups=[GROUP])
class InstanceActionsGroup(TestGroup):

    def __init__(self):
        super(InstanceActionsGroup, self).__init__(
            InstanceActionsRunnerFactory.instance())

    @test
    def instance_restart(self):
        """Restart an existing instance."""
        self.test_runner.run_instance_restart()

    @test(depends_on=[instance_restart])
    def instance_resize_volume(self):
        """Resize attached volume."""
        self.test_runner.run_instance_resize_volume()

    @test(depends_on=[instance_resize_volume])
    def instance_resize_flavor(self):
        """Resize instance flavor."""
        self.test_runner.run_instance_resize_flavor()
