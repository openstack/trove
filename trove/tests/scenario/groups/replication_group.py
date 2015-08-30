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

GROUP = "scenario.replication_group"


@test(depends_on_groups=[GROUP_START_SIMPLE], groups=[GROUP],
      runs_after=[WaitForGuestInstallationToFinish])
class ReplicationGroup(TestGroup):

    def __init__(self):
        super(ReplicationGroup, self).__init__(
            'replication_runners', 'ReplicationRunner')

    @test
    def add_data_for_replication(self):
        self.test_runner.run_add_data_for_replication()

    @test(runs_after=[add_data_for_replication])
    def create_replicas(self):
        self.test_runner.run_create_replicas()

    @test(depends_on=[create_replicas])
    def add_data_to_replicate(self):
        self.test_runner.run_add_data_to_replicate()

    @test(depends_on=[add_data_to_replicate])
    def verify_replicated_data(self):
        self.test_runner.run_verify_replicated_data()

    @test(depends_on=[add_data_to_replicate])
    def remove_replicated_data(self):
        self.test_runner.run_remove_replicated_data()

    @test(depends_on=[create_replicas],
          runs_after=[remove_replicated_data])
    def promote_master(self):
        self.test_runner.run_promote_master()

    @test(depends_on=[promote_master])
    def eject_replica(self):
        self.test_runner.run_eject_replica()

    @test(depends_on=[eject_replica])
    def eject_valid_master(self):
        self.test_runner.run_eject_valid_master()

    @test(depends_on=[eject_valid_master])
    def delete_valid_master(self):
        self.test_runner.run_delete_valid_master()

    @test(depends_on=[delete_valid_master])
    def swap_replica_master(self):
        self.test_runner.run_swap_replica_master()

    # TODO(peterstac): Add more tests

    @test(depends_on=[swap_replica_master])
    def delete_replica_set(self):
        self.run_delete_replica_set()
