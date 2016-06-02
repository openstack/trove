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


GROUP = "scenario.instance_actions_group"


class InstanceActionsRunnerFactory(test_runners.RunnerFactory):

    _runner_ns = 'instance_actions_runners'
    _runner_cls = 'InstanceActionsRunner'


@test(depends_on_groups=[groups.INST_CREATE_WAIT],
      groups=[GROUP, groups.INST_ACTIONS],
      runs_after_groups=[groups.MODULE_INST_CREATE,
                         groups.CFGGRP_INST_CREATE])
class InstanceActionsGroup(TestGroup):
    """Test Instance Actions functionality."""

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


@test(depends_on_groups=[groups.INST_CREATE_WAIT],
      groups=[GROUP, groups.INST_ACTIONS_RESIZE],
      runs_after_groups=[groups.INST_ACTIONS,
                         groups.MODULE_INST_CREATE_WAIT,
                         groups.CFGGRP_INST_CREATE_WAIT,
                         groups.BACKUP_CREATE,
                         groups.BACKUP_INC_CREATE])
class InstanceActionsResizeGroup(TestGroup):
    """Test Instance Actions Resize functionality."""

    def __init__(self):
        super(InstanceActionsResizeGroup, self).__init__(
            InstanceActionsRunnerFactory.instance())

    @test
    def instance_resize_flavor(self):
        """Resize instance flavor."""
        self.test_runner.run_instance_resize_flavor()


@test(depends_on_groups=[groups.INST_ACTIONS_RESIZE],
      groups=[GROUP, groups.INST_ACTIONS_RESIZE_WAIT],
      runs_after_groups=[groups.BACKUP_INST_CREATE,
                         groups.BACKUP_INC_INST_CREATE,
                         groups.DB_ACTION_INST_CREATE])
class InstanceActionsResizeWaitGroup(TestGroup):
    """Test that Instance Actions Resize Completes."""

    def __init__(self):
        super(InstanceActionsResizeWaitGroup, self).__init__(
            InstanceActionsRunnerFactory.instance())

    @test
    def wait_for_instance_resize_flavor(self):
        """Wait for resize instance flavor to complete."""
        self.test_runner.run_wait_for_instance_resize_flavor()
