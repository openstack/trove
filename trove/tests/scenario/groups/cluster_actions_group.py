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

from trove.tests.scenario.groups.test_group import TestGroup
from trove.tests.scenario.runners import test_runners


GROUP = "scenario.cluster_actions_group"


class ClusterActionsRunnerFactory(test_runners.RunnerFactory):

    _runner_ns = 'cluster_actions_runners'
    _runner_cls = 'ClusterActionsRunner'


@test(groups=[GROUP])
class ClusterActionsGroup(TestGroup):

    def __init__(self):
        super(ClusterActionsGroup, self).__init__(
            ClusterActionsRunnerFactory.instance())

    @test
    def cluster_create(self):
        """Create a cluster."""
        self.test_runner.run_cluster_create()

    @test(depends_on=[cluster_create])
    def add_initial_cluster_data(self):
        """Add data to cluster."""
        self.test_runner.run_add_initial_cluster_data()

    @test(depends_on=[add_initial_cluster_data])
    def verify_initial_cluster_data(self):
        """Verify the initial data exists on cluster."""
        self.test_runner.run_verify_initial_cluster_data()

    @test(depends_on=[cluster_create])
    def cluster_root_enable(self):
        """Root Enable."""
        self.test_runner.run_cluster_root_enable()

    @test(depends_on=[cluster_root_enable])
    def verify_cluster_root_enable(self):
        """Verify Root Enable."""
        self.test_runner.run_verify_cluster_root_enable()

    @test(depends_on=[cluster_create],
          runs_after=[verify_initial_cluster_data, verify_cluster_root_enable])
    def cluster_grow(self):
        """Grow cluster."""
        self.test_runner.run_cluster_grow()

    @test(depends_on=[cluster_grow])
    def verify_cluster_root_enable_after_grow(self):
        """Verify Root Enabled after grow."""
        self.test_runner.run_verify_cluster_root_enable()

    @test(depends_on=[cluster_grow, add_initial_cluster_data])
    def verify_initial_cluster_data_after_grow(self):
        """Verify the initial data still exists after cluster grow."""
        self.test_runner.run_verify_initial_cluster_data()

    @test(depends_on=[cluster_grow],
          runs_after=[verify_initial_cluster_data_after_grow])
    def add_extra_cluster_data_after_grow(self):
        """Add more data to cluster."""
        self.test_runner.run_add_extra_cluster_data()

    @test(depends_on=[add_extra_cluster_data_after_grow])
    def verify_extra_cluster_data_after_grow(self):
        """Verify the data added after cluster grow."""
        self.test_runner.run_verify_extra_cluster_data()

    @test(depends_on=[add_extra_cluster_data_after_grow],
          runs_after=[verify_extra_cluster_data_after_grow])
    def remove_extra_cluster_data_after_grow(self):
        """Remove the data added after cluster grow."""
        self.test_runner.run_remove_extra_cluster_data()

    @test(depends_on=[cluster_create],
          runs_after=[remove_extra_cluster_data_after_grow,
                      verify_cluster_root_enable_after_grow])
    def cluster_shrink(self):
        """Shrink cluster."""
        self.test_runner.run_cluster_shrink()

    @test(depends_on=[cluster_shrink])
    def verify_cluster_root_enable_after_shrink(self):
        """Verify Root Enable after shrink."""
        self.test_runner.run_verify_cluster_root_enable()

    @test(depends_on=[cluster_shrink, add_initial_cluster_data])
    def verify_initial_cluster_data_after_shrink(self):
        """Verify the initial data still exists after cluster shrink."""
        self.test_runner.run_verify_initial_cluster_data()

    @test(depends_on=[cluster_shrink],
          runs_after=[verify_initial_cluster_data_after_shrink])
    def add_extra_cluster_data_after_shrink(self):
        """Add more data to cluster."""
        self.test_runner.run_add_extra_cluster_data()

    @test(depends_on=[add_extra_cluster_data_after_shrink])
    def verify_extra_cluster_data_after_shrink(self):
        """Verify the data added after cluster shrink."""
        self.test_runner.run_verify_extra_cluster_data()

    @test(depends_on=[add_extra_cluster_data_after_shrink],
          runs_after=[verify_extra_cluster_data_after_shrink])
    def remove_extra_cluster_data_after_shrink(self):
        """Remove the data added after cluster shrink."""
        self.test_runner.run_remove_extra_cluster_data()

    @test(depends_on=[add_initial_cluster_data],
          runs_after=[remove_extra_cluster_data_after_shrink])
    def remove_initial_cluster_data(self):
        """Remove the initial data from cluster."""
        self.test_runner.run_remove_initial_cluster_data()

    @test(depends_on=[cluster_create],
          runs_after=[remove_initial_cluster_data,
                      verify_cluster_root_enable_after_shrink])
    def cluster_delete(self):
        """Delete an existing cluster."""
        self.test_runner.run_cluster_delete()
