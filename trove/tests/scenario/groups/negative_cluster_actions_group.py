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


GROUP = "scenario.negative_cluster_actions_group"


class NegativeClusterActionsRunnerFactory(test_runners.RunnerFactory):

    _runner_ns = 'negative_cluster_actions_runners'
    _runner_cls = 'NegativeClusterActionsRunner'


@test(groups=[GROUP])
class NegativeClusterActionsGroup(TestGroup):

    def __init__(self):
        super(NegativeClusterActionsGroup, self).__init__(
            NegativeClusterActionsRunnerFactory.instance())

    @test
    def create_constrained_size_cluster(self):
        """Ensure creating a cluster with wrong number of nodes fails."""
        self.test_runner.run_create_constrained_size_cluster()

    @test
    def create_heterogeneous_cluster(self):
        """Ensure creating a cluster with unequal nodes fails."""
        self.test_runner.run_create_heterogeneous_cluster()
