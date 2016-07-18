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

from trove.tests import PRE_INSTANCES
from trove.tests.scenario import groups
from trove.tests.scenario.groups.test_group import TestGroup
from trove.tests.scenario.runners import test_runners


GROUP = "scenario.instance_error_create_group"


class InstanceErrorCreateRunnerFactory(test_runners.RunnerFactory):

    _runner_ns = 'instance_error_create_runners'
    _runner_cls = 'InstanceErrorCreateRunner'


@test(depends_on_groups=["services.initialize"],
      runs_after_groups=[PRE_INSTANCES, groups.INST_CREATE],
      groups=[GROUP, groups.INST_ERROR_CREATE])
class InstanceErrorCreateGroup(TestGroup):
    """Test Instance Error Create functionality."""

    def __init__(self):
        super(InstanceErrorCreateGroup, self).__init__(
            InstanceErrorCreateRunnerFactory.instance())

    @test
    def create_error_instance(self):
        """Create an instance in error state."""
        self.test_runner.run_create_error_instance()

    @test(runs_after=[create_error_instance])
    def create_error2_instance(self):
        """Create another instance in error state."""
        self.test_runner.run_create_error2_instance()


@test(depends_on_groups=[groups.INST_ERROR_CREATE],
      runs_after_groups=[groups.MODULE_CREATE, groups.CFGGRP_CREATE],
      groups=[GROUP, groups.INST_ERROR_CREATE_WAIT])
class InstanceErrorCreateWaitGroup(TestGroup):
    """Test that Instance Error Create Completes."""

    def __init__(self):
        super(InstanceErrorCreateWaitGroup, self).__init__(
            InstanceErrorCreateRunnerFactory.instance())

    @test
    def wait_for_error_instances(self):
        """Wait for the error instances to fail."""
        self.test_runner.run_wait_for_error_instances()

    @test(depends_on=[wait_for_error_instances])
    def validate_error_instance(self):
        """Validate the error instance fault message."""
        self.test_runner.run_validate_error_instance()

    @test(depends_on=[wait_for_error_instances],
          runs_after=[validate_error_instance])
    def validate_error2_instance(self):
        """Validate the error2 instance fault message as admin."""
        self.test_runner.run_validate_error2_instance()


@test(depends_on_groups=[groups.INST_ERROR_CREATE_WAIT],
      groups=[GROUP, groups.INST_ERROR_DELETE])
class InstanceErrorDeleteGroup(TestGroup):
    """Test Instance Error Delete functionality."""

    def __init__(self):
        super(InstanceErrorDeleteGroup, self).__init__(
            InstanceErrorCreateRunnerFactory.instance())

    @test
    def delete_error_instances(self):
        """Delete the error instances."""
        self.test_runner.run_delete_error_instances()


@test(depends_on_groups=[groups.INST_ERROR_DELETE],
      runs_after_groups=[groups.MODULE_INST_CREATE],
      groups=[GROUP, groups.INST_ERROR_DELETE_WAIT])
class InstanceErrorDeleteWaitGroup(TestGroup):
    """Test that Instance Error Delete Completes."""

    def __init__(self):
        super(InstanceErrorDeleteWaitGroup, self).__init__(
            InstanceErrorCreateRunnerFactory.instance())

    @test
    def wait_for_error_delete(self):
        """Wait for the error instances to be gone."""
        self.test_runner.run_wait_for_error_delete()
