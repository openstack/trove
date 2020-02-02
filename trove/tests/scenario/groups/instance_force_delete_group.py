# Copyright 2016 Tesora Inc.
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


GROUP = "scenario.instance_force_delete_group"


class InstanceForceDeleteRunnerFactory(test_runners.RunnerFactory):

    _runner_ns = 'instance_force_delete_runners'
    _runner_cls = 'InstanceForceDeleteRunner'


@test(depends_on_groups=[groups.INST_ERROR_DELETE_WAIT],
      groups=[GROUP, groups.INST_FORCE_DELETE])
class InstanceForceDeleteGroup(TestGroup):
    """Test Instance Force Delete functionality."""

    def __init__(self):
        super(InstanceForceDeleteGroup, self).__init__(
            InstanceForceDeleteRunnerFactory.instance())

    @test
    def create_build_instance(self):
        """Create an instance in BUILD state."""
        self.test_runner.run_create_build_instance()

    @test(depends_on=['create_build_instance'])
    def delete_build_instance(self):
        """Make sure the instance in BUILD state deletes."""
        self.test_runner.run_delete_build_instance()


@test(depends_on_classes=[InstanceForceDeleteGroup],
      groups=[GROUP, groups.INST_FORCE_DELETE_WAIT])
class InstanceForceDeleteWaitGroup(TestGroup):
    """Make sure the Force Delete instance goes away."""

    def __init__(self):
        super(InstanceForceDeleteWaitGroup, self).__init__(
            InstanceForceDeleteRunnerFactory.instance())

    @test
    def wait_for_force_delete(self):
        """Wait for the Force Delete instance to be gone."""
        self.test_runner.run_wait_for_force_delete()
