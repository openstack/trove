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


GROUP = "scenario.replication_group"


class ReplicationRunnerFactory(test_runners.RunnerFactory):

    _runner_ns = 'replication_runners'
    _runner_cls = 'ReplicationRunner'


@test(depends_on_groups=[instance_create_group.GROUP], groups=[GROUP])
class ReplicationGroup(TestGroup):
    """Test Replication functionality."""

    def __init__(self):
        super(ReplicationGroup, self).__init__(
            ReplicationRunnerFactory.instance())

    @test
    def add_data_for_replication(self):
        """Add data to master for initial replica setup."""
        self.test_runner.run_add_data_for_replication()

    @test(depends_on=[add_data_for_replication])
    def verify_data_for_replication(self):
        """Verify data exists on master."""
        self.test_runner.run_verify_data_for_replication()

    @test(runs_after=[verify_data_for_replication])
    def create_single_replica(self):
        """Test creating a single replica."""
        self.test_runner.run_create_single_replica()

    @test(runs_after=[create_single_replica])
    def add_data_after_replica(self):
        """Add data to master after initial replica is setup"""
        self.test_runner.run_add_data_after_replica()

    @test(runs_after=[add_data_after_replica])
    def verify_replica_data_after_single(self):
        """Verify data exists on single replica"""
        self.test_runner.run_verify_replica_data_after_single()

    @test(runs_after=[verify_replica_data_after_single])
    def create_multiple_replicas(self):
        """Test creating multiple replicas."""
        self.test_runner.run_create_multiple_replicas()

    @test(depends_on=[create_single_replica, create_multiple_replicas])
    def add_data_to_replicate(self):
        """Add data to master to verify replication."""
        self.test_runner.run_add_data_to_replicate()

    @test(depends_on=[add_data_to_replicate])
    def verify_data_to_replicate(self):
        """Verify data exists on master."""
        self.test_runner.run_verify_data_to_replicate()

    @test(depends_on=[create_single_replica, create_multiple_replicas,
                      add_data_to_replicate],
          runs_after=[verify_data_to_replicate])
    def wait_for_data_to_replicate(self):
        """Wait to ensure that the data is replicated."""
        self.test_runner.run_wait_for_data_to_replicate()

    @test(depends_on=[create_single_replica, create_multiple_replicas,
                      add_data_to_replicate],
          runs_after=[wait_for_data_to_replicate])
    def verify_replica_data_orig(self):
        """Verify original data was transferred to replicas."""
        self.test_runner.run_verify_replica_data_orig()

    @test(depends_on=[create_single_replica, create_multiple_replicas,
                      add_data_to_replicate],
          runs_after=[verify_replica_data_orig])
    def verify_replica_data_new(self):
        """Verify new data was transferred to replicas."""
        self.test_runner.run_verify_replica_data_new()

    @test(depends_on=[create_single_replica, create_multiple_replicas],
          runs_after=[verify_replica_data_new])
    def promote_master(self):
        """Ensure promoting master fails."""
        self.test_runner.run_promote_master()

    @test(depends_on=[create_single_replica, create_multiple_replicas],
          runs_after=[promote_master])
    def eject_replica(self):
        """Ensure ejecting non master fails."""
        self.test_runner.run_eject_replica()

    @test(depends_on=[create_single_replica, create_multiple_replicas],
          runs_after=[eject_replica])
    def eject_valid_master(self):
        """Ensure ejecting valid master fails."""
        self.test_runner.run_eject_valid_master()

    @test(depends_on=[create_single_replica, create_multiple_replicas],
          runs_after=[eject_valid_master])
    def delete_valid_master(self):
        """Ensure deleting valid master fails."""
        self.test_runner.run_delete_valid_master()

    @test(depends_on=[create_single_replica, create_multiple_replicas],
          runs_after=[delete_valid_master])
    def promote_to_replica_source(self):
        """Test promoting a replica to replica source (master)."""
        self.test_runner.run_promote_to_replica_source()

    @test(depends_on=[create_single_replica, create_multiple_replicas,
                      promote_to_replica_source])
    def add_data_to_replicate2(self):
        """Add data to new master to verify replication."""
        self.test_runner.run_add_data_to_replicate2()

    @test(depends_on=[add_data_to_replicate2])
    def verify_data_to_replicate2(self):
        """Verify data exists on new master."""
        self.test_runner.run_verify_data_to_replicate2()

    @test(depends_on=[add_data_to_replicate2],
          runs_after=[verify_data_to_replicate2])
    def wait_for_data_to_replicate2(self):
        """Wait to ensure that the new data was replicated."""
        self.test_runner.run_wait_for_data_to_replicate()

    @test(depends_on=[create_single_replica, create_multiple_replicas,
                      add_data_to_replicate2],
          runs_after=[wait_for_data_to_replicate2])
    def verify_replica_data_new2(self):
        """Verify data was transferred to new replicas."""
        self.test_runner.run_verify_replica_data_new2()

    @test(depends_on=[promote_to_replica_source],
          runs_after=[verify_replica_data_new2])
    def promote_original_source(self):
        """Test promoting back the original replica source."""
        self.test_runner.run_promote_original_source()

    @test(depends_on=[promote_original_source])
    def remove_replicated_data(self):
        """Remove replication data."""
        self.test_runner.run_remove_replicated_data()

    @test(depends_on=[promote_original_source],
          runs_after=[remove_replicated_data])
    def detach_replica_from_source(self):
        """Test detaching a replica from the master."""
        self.test_runner.run_detach_replica_from_source()

    @test(depends_on=[promote_original_source],
          runs_after=[detach_replica_from_source])
    def delete_detached_replica(self):
        """Test deleting the detached replica."""
        self.test_runner.run_delete_detached_replica()

    @test(runs_after=[delete_detached_replica])
    def delete_all_replicas(self):
        """Test deleting all the remaining replicas."""
        self.test_runner.run_delete_all_replicas()

    @test(runs_after=[delete_all_replicas])
    def test_backup_deleted(self):
        """Test that the created backup is now gone."""
        self.test_runner.run_test_backup_deleted()

    @test(runs_after=[test_backup_deleted])
    def cleanup_master_instance(self):
        """Remove slave users from master instance."""
        self.test_runner.run_cleanup_master_instance()
