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


GROUP = "scenario.instance_delete_group"


class InstanceDeleteRunnerFactory(test_runners.RunnerFactory):

    _runner_ns = 'instance_delete_runners'
    _runner_cls = 'InstanceDeleteRunner'


@test(depends_on_groups=[groups.INST_CREATE_WAIT],
      groups=[GROUP, groups.INST_DELETE],
      runs_after_groups=[groups.INST_INIT_DELETE,
                         groups.INST_ACTIONS,
                         groups.INST_ACTIONS_RESIZE_WAIT,
                         groups.BACKUP_INST_DELETE,
                         groups.BACKUP_INC_INST_DELETE,
                         groups.CFGGRP_INST_DELETE,
                         groups.DB_ACTION_DELETE,
                         groups.DB_ACTION_INST_DELETE,
                         groups.MODULE_INST_DELETE,
                         groups.REPL_INST_DELETE_WAIT,
                         groups.ROOT_ACTION_INST_DELETE,
                         groups.USER_ACTION_DELETE,
                         groups.USER_ACTION_INST_DELETE])
class InstanceDeleteGroup(TestGroup):
    """Test Instance Delete functionality."""

    def __init__(self):
        super(InstanceDeleteGroup, self).__init__(
            InstanceDeleteRunnerFactory.instance())

    @test
    def instance_delete(self):
        """Delete an existing instance."""
        self.test_runner.run_instance_delete()


@test(depends_on_groups=[groups.INST_DELETE],
      groups=[GROUP, groups.INST_DELETE_WAIT],
      runs_after_groups=[groups.BACKUP_INST_DELETE_WAIT,
                         groups.BACKUP_INC_INST_DELETE_WAIT,
                         groups.CFGGRP_INST_DELETE_WAIT,
                         groups.DB_ACTION_INST_DELETE_WAIT,
                         groups.MODULE_INST_DELETE_WAIT,
                         groups.REPL_INST_DELETE_WAIT,
                         groups.ROOT_ACTION_INST_DELETE_WAIT,
                         groups.USER_ACTION_INST_DELETE_WAIT])
class InstanceDeleteWaitGroup(TestGroup):
    """Test that Instance Delete Completes."""

    def __init__(self):
        super(InstanceDeleteWaitGroup, self).__init__(
            InstanceDeleteRunnerFactory.instance())

    @test
    def instance_delete_wait(self):
        """Wait for existing instance to be gone."""
        self.test_runner.run_instance_delete_wait()
