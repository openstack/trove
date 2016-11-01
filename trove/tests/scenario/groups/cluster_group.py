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


GROUP = "scenario.cluster_group"


class ClusterRunnerFactory(test_runners.RunnerFactory):

    _runner_ns = 'cluster_runners'
    _runner_cls = 'ClusterRunner'


@test(groups=[GROUP, groups.CLUSTER_CREATE],
      runs_after_groups=[groups.MODULE_DELETE,
                         groups.CFGGRP_INST_DELETE,
                         groups.INST_ACTIONS_RESIZE_WAIT,
                         groups.DB_ACTION_INST_DELETE,
                         groups.USER_ACTION_DELETE,
                         groups.USER_ACTION_INST_DELETE,
                         groups.ROOT_ACTION_INST_DELETE,
                         groups.REPL_INST_DELETE_WAIT,
                         groups.INST_DELETE])
class ClusterCreateGroup(TestGroup):

    def __init__(self):
        super(ClusterCreateGroup, self).__init__(
            ClusterRunnerFactory.instance())

    @test
    def cluster_create(self):
        """Create a cluster."""
        self.test_runner.run_cluster_create()


@test(groups=[GROUP, groups.CLUSTER_CREATE_WAIT],
      depends_on_groups=[groups.CLUSTER_CREATE],
      runs_after_groups=[groups.MODULE_INST_DELETE_WAIT,
                         groups.CFGGRP_INST_DELETE_WAIT,
                         groups.DB_ACTION_INST_DELETE_WAIT,
                         groups.USER_ACTION_INST_DELETE_WAIT,
                         groups.ROOT_ACTION_INST_DELETE_WAIT,
                         groups.INST_DELETE_WAIT])
class ClusterCreateWaitGroup(TestGroup):

    def __init__(self):
        super(ClusterCreateWaitGroup, self).__init__(
            ClusterRunnerFactory.instance())

    @test
    def cluster_create_wait(self):
        """Wait for cluster create to complete."""
        self.test_runner.run_cluster_create_wait()

    @test(depends_on=[cluster_create_wait])
    def add_initial_cluster_data(self):
        """Add data to cluster."""
        self.test_runner.run_add_initial_cluster_data()

    @test(depends_on=[add_initial_cluster_data])
    def verify_initial_cluster_data(self):
        """Verify the initial data exists on cluster."""
        self.test_runner.run_verify_initial_cluster_data()

    @test(depends_on=[cluster_create_wait])
    def cluster_list(self):
        """List the clusters."""
        self.test_runner.run_cluster_list()

    @test(depends_on=[cluster_create_wait])
    def cluster_show(self):
        """Show a cluster."""
        self.test_runner.run_cluster_show()


@test(groups=[GROUP, groups.CLUSTER_ACTIONS,
              groups.CLUSTER_ACTIONS_RESTART],
      depends_on_groups=[groups.CLUSTER_CREATE_WAIT])
class ClusterRestartGroup(TestGroup):

    def __init__(self):
        super(ClusterRestartGroup, self).__init__(
            ClusterRunnerFactory.instance())

    @test
    def cluster_restart(self):
        """Restart the cluster."""
        self.test_runner.run_cluster_restart()


@test(groups=[GROUP, groups.CLUSTER_ACTIONS,
              groups.CLUSTER_ACTIONS_RESTART_WAIT],
      depends_on_groups=[groups.CLUSTER_ACTIONS_RESTART])
class ClusterRestartWaitGroup(TestGroup):

    def __init__(self):
        super(ClusterRestartWaitGroup, self).__init__(
            ClusterRunnerFactory.instance())

    @test
    def cluster_restart_wait(self):
        """Wait for cluster restart to complete."""
        self.test_runner.run_cluster_restart_wait()

    @test(depends_on=[cluster_restart_wait])
    def verify_initial_cluster_data(self):
        """Verify the initial data still exists after cluster restart."""
        self.test_runner.run_verify_initial_cluster_data()


@test(groups=[GROUP, groups.CLUSTER_ACTIONS,
              groups.CLUSTER_ACTIONS_ROOT_ENABLE],
      depends_on_groups=[groups.CLUSTER_CREATE_WAIT],
      runs_after_groups=[groups.CLUSTER_ACTIONS_RESTART_WAIT])
class ClusterRootEnableGroup(TestGroup):

    def __init__(self):
        super(ClusterRootEnableGroup, self).__init__(
            ClusterRunnerFactory.instance())

    @test
    def cluster_root_enable(self):
        """Root Enable."""
        self.test_runner.run_cluster_root_enable()

    @test(depends_on=[cluster_root_enable])
    def verify_cluster_root_enable(self):
        """Verify Root Enable."""
        self.test_runner.run_verify_cluster_root_enable()


@test(groups=[GROUP, groups.CLUSTER_ACTIONS,
              groups.CLUSTER_ACTIONS_GROW_SHRINK,
              groups.CLUSTER_ACTIONS_GROW],
      depends_on_groups=[groups.CLUSTER_CREATE_WAIT],
      runs_after_groups=[groups.CLUSTER_ACTIONS_ROOT_ENABLE])
class ClusterGrowGroup(TestGroup):

    def __init__(self):
        super(ClusterGrowGroup, self).__init__(
            ClusterRunnerFactory.instance())

    @test
    def cluster_grow(self):
        """Grow cluster."""
        self.test_runner.run_cluster_grow()


@test(groups=[GROUP, groups.CLUSTER_ACTIONS,
              groups.CLUSTER_ACTIONS_GROW_SHRINK,
              groups.CLUSTER_ACTIONS_GROW_WAIT],
      depends_on_groups=[groups.CLUSTER_ACTIONS_GROW])
class ClusterGrowWaitGroup(TestGroup):
    def __init__(self):
        super(ClusterGrowWaitGroup, self).__init__(
            ClusterRunnerFactory.instance())

    @test
    def cluster_grow_wait(self):
        """Wait for cluster grow to complete."""
        self.test_runner.run_cluster_grow_wait()

    @test(depends_on=[cluster_grow_wait])
    def verify_initial_cluster_data_after_grow(self):
        """Verify the initial data still exists after cluster grow."""
        self.test_runner.run_verify_initial_cluster_data()

    @test(depends_on=[cluster_grow_wait],
          runs_after=[verify_initial_cluster_data_after_grow])
    def add_grow_cluster_data(self):
        """Add more data to cluster after grow."""
        self.test_runner.run_add_grow_cluster_data()

    @test(depends_on=[add_grow_cluster_data])
    def verify_grow_cluster_data(self):
        """Verify the data added after cluster grow."""
        self.test_runner.run_verify_grow_cluster_data()

    @test(depends_on=[add_grow_cluster_data],
          runs_after=[verify_grow_cluster_data])
    def remove_grow_cluster_data(self):
        """Remove the data added after cluster grow."""
        self.test_runner.run_remove_grow_cluster_data()


@test(groups=[GROUP, groups.CLUSTER_ACTIONS,
              groups.CLUSTER_ACTIONS_ROOT_ACTIONS,
              groups.CLUSTER_ACTIONS_ROOT_GROW],
      depends_on_groups=[groups.CLUSTER_ACTIONS_GROW_WAIT])
class ClusterRootEnableGrowGroup(TestGroup):

    def __init__(self):
        super(ClusterRootEnableGrowGroup, self).__init__(
            ClusterRunnerFactory.instance())

    @test
    def verify_cluster_root_enable_after_grow(self):
        """Verify Root Enabled after grow."""
        self.test_runner.run_verify_cluster_root_enable()


@test(groups=[GROUP, groups.CLUSTER_UPGRADE],
      depends_on_groups=[groups.CLUSTER_CREATE_WAIT],
      runs_after_groups=[groups.CLUSTER_ACTIONS_GROW_WAIT,
                         groups.CLUSTER_ACTIONS_ROOT_GROW])
class ClusterUpgradeGroup(TestGroup):

    def __init__(self):
        super(ClusterUpgradeGroup, self).__init__(
            ClusterRunnerFactory.instance())

    @test
    def cluster_upgrade(self):
        """Upgrade cluster."""
        self.test_runner.run_cluster_upgrade()


@test(groups=[GROUP, groups.CLUSTER_UPGRADE_WAIT],
      depends_on_groups=[groups.CLUSTER_UPGRADE])
class ClusterUpgradeWaitGroup(TestGroup):
    def __init__(self):
        super(ClusterUpgradeWaitGroup, self).__init__(
            ClusterRunnerFactory.instance())

    @test
    def cluster_upgrade_wait(self):
        """Wait for cluster upgrade to complete."""
        self.test_runner.run_cluster_upgrade_wait()

    @test(depends_on=[cluster_upgrade_wait])
    def verify_initial_cluster_data_after_upgrade(self):
        """Verify the initial data still exists after cluster upgrade."""
        self.test_runner.run_verify_initial_cluster_data()

    @test(depends_on=[cluster_upgrade_wait],
          runs_after=[verify_initial_cluster_data_after_upgrade])
    def add_upgrade_cluster_data_after_upgrade(self):
        """Add more data to cluster after upgrade."""
        self.test_runner.run_add_upgrade_cluster_data()

    @test(depends_on=[add_upgrade_cluster_data_after_upgrade])
    def verify_upgrade_cluster_data_after_upgrade(self):
        """Verify the data added after cluster upgrade."""
        self.test_runner.run_verify_upgrade_cluster_data()

    @test(depends_on=[add_upgrade_cluster_data_after_upgrade],
          runs_after=[verify_upgrade_cluster_data_after_upgrade])
    def remove_upgrade_cluster_data_after_upgrade(self):
        """Remove the data added after cluster upgrade."""
        self.test_runner.run_remove_upgrade_cluster_data()


@test(groups=[GROUP, groups.CLUSTER_ACTIONS,
              groups.CLUSTER_ACTIONS_GROW_SHRINK,
              groups.CLUSTER_ACTIONS_SHRINK],
      depends_on_groups=[groups.CLUSTER_ACTIONS_GROW_WAIT],
      runs_after_groups=[groups.CLUSTER_UPGRADE_WAIT])
class ClusterShrinkGroup(TestGroup):

    def __init__(self):
        super(ClusterShrinkGroup, self).__init__(
            ClusterRunnerFactory.instance())

    @test
    def cluster_shrink(self):
        """Shrink cluster."""
        self.test_runner.run_cluster_shrink()


@test(groups=[GROUP, groups.CLUSTER_ACTIONS,
              groups.CLUSTER_ACTIONS_SHRINK_WAIT],
      depends_on_groups=[groups.CLUSTER_ACTIONS_SHRINK])
class ClusterShrinkWaitGroup(TestGroup):
    def __init__(self):
        super(ClusterShrinkWaitGroup, self).__init__(
            ClusterRunnerFactory.instance())

    @test
    def cluster_shrink_wait(self):
        """Wait for the cluster shrink to complete."""
        self.test_runner.run_cluster_shrink_wait()

    @test(depends_on=[cluster_shrink_wait])
    def verify_initial_cluster_data_after_shrink(self):
        """Verify the initial data still exists after cluster shrink."""
        self.test_runner.run_verify_initial_cluster_data()

    @test(runs_after=[verify_initial_cluster_data_after_shrink])
    def add_shrink_cluster_data(self):
        """Add more data to cluster after shrink."""
        self.test_runner.run_add_shrink_cluster_data()

    @test(depends_on=[add_shrink_cluster_data])
    def verify_shrink_cluster_data(self):
        """Verify the data added after cluster shrink."""
        self.test_runner.run_verify_shrink_cluster_data()

    @test(depends_on=[add_shrink_cluster_data],
          runs_after=[verify_shrink_cluster_data])
    def remove_shrink_cluster_data(self):
        """Remove the data added after cluster shrink."""
        self.test_runner.run_remove_shrink_cluster_data()


@test(groups=[GROUP, groups.CLUSTER_ACTIONS,
              groups.CLUSTER_ACTIONS_ROOT_ACTIONS,
              groups.CLUSTER_ACTIONS_ROOT_SHRINK],
      depends_on_groups=[groups.CLUSTER_ACTIONS_SHRINK_WAIT])
class ClusterRootEnableShrinkGroup(TestGroup):

    def __init__(self):
        super(ClusterRootEnableShrinkGroup, self).__init__(
            ClusterRunnerFactory.instance())

    @test
    def verify_cluster_root_enable_after_shrink(self):
        """Verify Root Enable after shrink."""
        self.test_runner.run_verify_cluster_root_enable()


@test(groups=[GROUP, groups.CLUSTER_ACTIONS,
              groups.CLUSTER_DELETE],
      depends_on_groups=[groups.CLUSTER_CREATE_WAIT],
      runs_after_groups=[groups.CLUSTER_ACTIONS_ROOT_ENABLE,
                         groups.CLUSTER_ACTIONS_ROOT_GROW,
                         groups.CLUSTER_ACTIONS_ROOT_SHRINK,
                         groups.CLUSTER_ACTIONS_GROW_WAIT,
                         groups.CLUSTER_ACTIONS_SHRINK_WAIT,
                         groups.CLUSTER_UPGRADE_WAIT,
                         groups.CLUSTER_ACTIONS_RESTART_WAIT])
class ClusterDeleteGroup(TestGroup):

    def __init__(self):
        super(ClusterDeleteGroup, self).__init__(
            ClusterRunnerFactory.instance())

    @test
    def remove_initial_cluster_data(self):
        """Remove the initial data from cluster."""
        self.test_runner.run_remove_initial_cluster_data()

    @test(runs_after=[remove_initial_cluster_data])
    def cluster_delete(self):
        """Delete an existing cluster."""
        self.test_runner.run_cluster_delete()


@test(groups=[GROUP, groups.CLUSTER_ACTIONS,
              groups.CLUSTER_DELETE_WAIT],
      depends_on_groups=[groups.CLUSTER_DELETE])
class ClusterDeleteWaitGroup(TestGroup):

    def __init__(self):
        super(ClusterDeleteWaitGroup, self).__init__(
            ClusterRunnerFactory.instance())

    @test
    def cluster_delete_wait(self):
        """Wait for the existing cluster to be gone."""
        self.test_runner.run_cluster_delete_wait()
