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


GROUP = "scenario.replication_group"


class ReplicationRunnerFactory(test_runners.RunnerFactory):

    _runner_ns = 'replication_runners'
    _runner_cls = 'ReplicationRunner'


class BackupRunnerFactory(test_runners.RunnerFactory):

    _runner_ns = 'backup_runners'
    _runner_cls = 'BackupRunner'


@test(depends_on_groups=[groups.INST_CREATE_WAIT],
      groups=[GROUP, groups.REPL_INST_CREATE],
      runs_after_groups=[groups.MODULE_INST_DELETE,
                         groups.CFGGRP_INST_DELETE,
                         groups.INST_ACTIONS_RESIZE_WAIT,
                         groups.DB_ACTION_INST_DELETE,
                         groups.USER_ACTION_DELETE,
                         groups.USER_ACTION_INST_DELETE,
                         groups.ROOT_ACTION_INST_DELETE])
class ReplicationInstCreateGroup(TestGroup):
    """Test Replication Instance Create functionality."""

    def __init__(self):
        super(ReplicationInstCreateGroup, self).__init__(
            ReplicationRunnerFactory.instance())

    @test
    def add_data_for_replication(self):
        """Add data to master for initial replica setup."""
        self.test_runner.run_add_data_for_replication()

    @test(depends_on=[add_data_for_replication])
    def verify_data_for_replication(self):
        """Verify initial data exists on master."""
        self.test_runner.run_verify_data_for_replication()

    @test(runs_after=[verify_data_for_replication])
    def create_non_affinity_master(self):
        """Test creating a non-affinity master."""
        self.test_runner.run_create_non_affinity_master()

    @test(runs_after=[create_non_affinity_master])
    def create_single_replica(self):
        """Test creating a single replica."""
        self.test_runner.run_create_single_replica()


@test(depends_on_groups=[groups.REPL_INST_CREATE],
      groups=[GROUP, groups.REPL_INST_CREATE_WAIT],
      runs_after_groups=[groups.INST_INIT_DELETE_WAIT])
class ReplicationInstCreateWaitGroup(TestGroup):
    """Wait for Replication Instance Create to complete."""

    def __init__(self):
        super(ReplicationInstCreateWaitGroup, self).__init__(
            ReplicationRunnerFactory.instance())

    @test
    def wait_for_non_affinity_master(self):
        """Wait for non-affinity master to complete."""
        self.test_runner.run_wait_for_non_affinity_master()

    @test(depends_on=[wait_for_non_affinity_master])
    def create_non_affinity_replica(self):
        """Test creating a non-affinity replica."""
        self.test_runner.run_create_non_affinity_replica()

    @test(depends_on=[create_non_affinity_replica])
    def wait_for_non_affinity_replica_fail(self):
        """Wait for non-affinity replica to fail."""
        self.test_runner.run_wait_for_non_affinity_replica_fail()

    @test(runs_after=[wait_for_non_affinity_replica_fail])
    def delete_non_affinity_repl(self):
        """Test deleting non-affinity replica."""
        self.test_runner.run_delete_non_affinity_repl()

    @test(runs_after=[delete_non_affinity_repl])
    def wait_for_single_replica(self):
        """Wait for single replica to complete."""
        self.test_runner.run_wait_for_single_replica()

    @test(depends_on=[wait_for_single_replica])
    def add_data_after_replica(self):
        """Add data to master after initial replica is setup"""
        self.test_runner.run_add_data_after_replica()

    @test(depends_on=[add_data_after_replica])
    def verify_replica_data_after_single(self):
        """Verify data exists on single replica"""
        self.test_runner.run_verify_replica_data_after_single()


@test(depends_on_groups=[groups.REPL_INST_CREATE_WAIT],
      groups=[GROUP, groups.REPL_INST_MULTI_CREATE])
class ReplicationInstMultiCreateGroup(TestGroup):
    """Test Replication Instance Multi-Create functionality."""

    def __init__(self):
        super(ReplicationInstMultiCreateGroup, self).__init__(
            ReplicationRunnerFactory.instance())
        self.backup_runner = BackupRunnerFactory.instance()

    @test
    def backup_master_instance(self):
        """Backup the master instance."""
        self.backup_runner.run_backup_create()
        self.backup_runner.run_backup_create_completed()
        self.test_runner.master_backup_count += 1

    @test(depends_on=[backup_master_instance])
    def create_multiple_replicas(self):
        """Test creating multiple replicas."""
        self.test_runner.run_create_multiple_replicas()

    @test(depends_on=[create_multiple_replicas])
    def check_has_incremental_backup(self):
        """Test that creating multiple replicas uses incr backup."""
        self.backup_runner.run_check_has_incremental()


@test(depends_on_groups=[groups.REPL_INST_CREATE_WAIT],
      groups=[GROUP, groups.REPL_INST_DELETE_NON_AFFINITY_WAIT],
      runs_after_groups=[groups.REPL_INST_MULTI_CREATE,
                         groups.USER_ACTION_DELETE])
class ReplicationInstDeleteNonAffReplWaitGroup(TestGroup):
    """Wait for Replication Instance Non-Affinity repl to be gone."""

    def __init__(self):
        super(ReplicationInstDeleteNonAffReplWaitGroup, self).__init__(
            ReplicationRunnerFactory.instance())

    @test
    def wait_for_delete_non_affinity_repl(self):
        """Wait for the non-affinity replica to delete."""
        self.test_runner.run_wait_for_delete_non_affinity_repl()

    @test(depends_on=[wait_for_delete_non_affinity_repl])
    def delete_non_affinity_master(self):
        """Test deleting non-affinity master."""
        self.test_runner.run_delete_non_affinity_master()


@test(depends_on_groups=[groups.REPL_INST_DELETE_NON_AFFINITY_WAIT,
                         groups.REPL_INST_MULTI_CREATE],
      groups=[GROUP, groups.REPL_INST_MULTI_CREATE_WAIT])
class ReplicationInstMultiCreateWaitGroup(TestGroup):
    """Wait for Replication Instance Multi-Create to complete."""

    def __init__(self):
        super(ReplicationInstMultiCreateWaitGroup, self).__init__(
            ReplicationRunnerFactory.instance())

    @test
    def wait_for_delete_non_affinity_master(self):
        """Wait for the non-affinity master to delete."""
        self.test_runner.run_wait_for_delete_non_affinity_master()

    @test(runs_after=[wait_for_delete_non_affinity_master])
    def wait_for_multiple_replicas(self):
        """Wait for multiple replicas to complete."""
        self.test_runner.run_wait_for_multiple_replicas()

    @test(depends_on=[wait_for_multiple_replicas])
    def verify_replica_data_orig(self):
        """Verify original data was transferred to replicas."""
        self.test_runner.run_verify_replica_data_orig()

    @test(depends_on=[wait_for_multiple_replicas],
          runs_after=[verify_replica_data_orig])
    def add_data_to_replicate(self):
        """Add new data to master to verify replication."""
        self.test_runner.run_add_data_to_replicate()

    @test(depends_on=[add_data_to_replicate])
    def verify_data_to_replicate(self):
        """Verify new data exists on master."""
        self.test_runner.run_verify_data_to_replicate()

    @test(depends_on=[add_data_to_replicate],
          runs_after=[verify_data_to_replicate])
    def verify_replica_data_orig2(self):
        """Verify original data was transferred to replicas."""
        self.test_runner.run_verify_replica_data_orig()

    @test(depends_on=[add_data_to_replicate],
          runs_after=[verify_replica_data_orig2])
    def verify_replica_data_new(self):
        """Verify new data was transferred to replicas."""
        self.test_runner.run_verify_replica_data_new()

    @test(depends_on=[wait_for_multiple_replicas],
          runs_after=[verify_replica_data_new])
    def promote_master(self):
        """Ensure promoting master fails."""
        self.test_runner.run_promote_master()

    @test(depends_on=[wait_for_multiple_replicas],
          runs_after=[promote_master])
    def eject_replica(self):
        """Ensure ejecting non master fails."""
        self.test_runner.run_eject_replica()

    @test(depends_on=[wait_for_multiple_replicas],
          runs_after=[eject_replica])
    def eject_valid_master(self):
        """Ensure ejecting valid master fails."""
        self.test_runner.run_eject_valid_master()

    @test(depends_on=[wait_for_multiple_replicas],
          runs_after=[eject_valid_master])
    def delete_valid_master(self):
        """Ensure deleting valid master fails."""
        self.test_runner.run_delete_valid_master()


@test(depends_on_groups=[groups.REPL_INST_MULTI_CREATE_WAIT],
      groups=[GROUP, groups.REPL_INST_MULTI_PROMOTE])
class ReplicationInstMultiPromoteGroup(TestGroup):
    """Test Replication Instance Multi-Promote functionality."""

    def __init__(self):
        super(ReplicationInstMultiPromoteGroup, self).__init__(
            ReplicationRunnerFactory.instance())

    @test
    def promote_to_replica_source(self):
        """Test promoting a replica to replica source (master)."""
        self.test_runner.run_promote_to_replica_source()

    @test(depends_on=[promote_to_replica_source])
    def verify_replica_data_new_master(self):
        """Verify data is still on new master."""
        self.test_runner.run_verify_replica_data_new_master()

    @test(depends_on=[promote_to_replica_source],
          runs_after=[verify_replica_data_new_master])
    def add_data_to_replicate2(self):
        """Add data to new master to verify replication."""
        self.test_runner.run_add_data_to_replicate2()

    @test(depends_on=[add_data_to_replicate2])
    def verify_data_to_replicate2(self):
        """Verify data exists on new master."""
        self.test_runner.run_verify_data_to_replicate2()

    @test(depends_on=[add_data_to_replicate2],
          runs_after=[verify_data_to_replicate2])
    def verify_replica_data_new2(self):
        """Verify data was transferred to new replicas."""
        self.test_runner.run_verify_replica_data_new2()

    @test(depends_on=[promote_to_replica_source],
          runs_after=[verify_replica_data_new2])
    def promote_original_source(self):
        """Test promoting back the original replica source."""
        self.test_runner.run_promote_original_source()

    @test(depends_on=[promote_original_source])
    def add_final_data_to_replicate(self):
        """Add final data to original master to verify switch."""
        self.test_runner.run_add_final_data_to_replicate()

    @test(depends_on=[add_final_data_to_replicate])
    def verify_data_to_replicate_final(self):
        """Verify final data exists on master."""
        self.test_runner.run_verify_data_to_replicate_final()

    @test(depends_on=[verify_data_to_replicate_final])
    def verify_final_data_replicated(self):
        """Verify final data was transferred to all replicas."""
        self.test_runner.run_verify_final_data_replicated()


@test(depends_on_groups=[groups.REPL_INST_MULTI_CREATE_WAIT],
      runs_after_groups=[groups.REPL_INST_MULTI_PROMOTE],
      groups=[GROUP, groups.REPL_INST_DELETE])
class ReplicationInstDeleteGroup(TestGroup):
    """Test Replication Instance Delete functionality."""

    def __init__(self):
        super(ReplicationInstDeleteGroup, self).__init__(
            ReplicationRunnerFactory.instance())

    @test
    def remove_replicated_data(self):
        """Remove replication data."""
        self.test_runner.run_remove_replicated_data()

    @test(runs_after=[remove_replicated_data])
    def detach_replica_from_source(self):
        """Test detaching a replica from the master."""
        self.test_runner.run_detach_replica_from_source()

    @test(runs_after=[detach_replica_from_source])
    def delete_detached_replica(self):
        """Test deleting the detached replica."""
        self.test_runner.run_delete_detached_replica()

    @test(runs_after=[delete_detached_replica])
    def delete_all_replicas(self):
        """Test deleting all the remaining replicas."""
        self.test_runner.run_delete_all_replicas()


@test(depends_on_groups=[groups.REPL_INST_DELETE],
      groups=[GROUP, groups.REPL_INST_DELETE_WAIT])
class ReplicationInstDeleteWaitGroup(TestGroup):
    """Wait for Replication Instance Delete to complete."""

    def __init__(self):
        super(ReplicationInstDeleteWaitGroup, self).__init__(
            ReplicationRunnerFactory.instance())
        self.backup_runner = BackupRunnerFactory.instance()

    @test
    def wait_for_delete_replicas(self):
        """Wait for all the replicas to delete."""
        self.test_runner.run_wait_for_delete_replicas()

    @test(runs_after=[wait_for_delete_replicas])
    def test_backup_deleted(self):
        """Remove the full backup and test that the created backup
           is now gone.
        """
        self.test_runner.run_test_backup_deleted()
        self.backup_runner.run_delete_backup()

    @test(runs_after=[test_backup_deleted])
    def cleanup_master_instance(self):
        """Remove slave users from master instance."""
        self.test_runner.run_cleanup_master_instance()
