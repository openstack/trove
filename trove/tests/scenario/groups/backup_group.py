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


GROUP = "scenario.backup_restore_group"


class BackupRunnerFactory(test_runners.RunnerFactory):

    _runner_ns = 'backup_runners'
    _runner_cls = 'BackupRunner'


@test(depends_on_groups=[groups.INST_CREATE_WAIT],
      groups=[GROUP, groups.BACKUP, groups.BACKUP_CREATE],
      runs_after_groups=[groups.MODULE_INST_DELETE,
                         groups.CFGGRP_INST_DELETE])
class BackupCreateGroup(TestGroup):
    """Test Backup Create functionality."""

    def __init__(self):
        super(BackupCreateGroup, self).__init__(
            BackupRunnerFactory.instance())

    @test
    def add_data_for_backup(self):
        """Add data to instance for restore verification."""
        self.test_runner.run_add_data_for_backup()

    @test(runs_after=[add_data_for_backup])
    def verify_data_for_backup(self):
        """Verify data in instance."""
        self.test_runner.run_verify_data_for_backup()

    @test(runs_after=[verify_data_for_backup])
    def save_backup_counts(self):
        """Store the existing backup counts."""
        self.test_runner.run_save_backup_counts()

    @test(runs_after=[save_backup_counts])
    def backup_create(self):
        """Check that create backup is started successfully."""
        self.test_runner.run_backup_create()


@test(depends_on_groups=[groups.BACKUP_CREATE],
      groups=[groups.BACKUP_CREATE_NEGATIVE])
class BackupCreateNegativeGroup(TestGroup):
    """Test Backup Create Negative functionality."""

    def __init__(self):
        super(BackupCreateNegativeGroup, self).__init__(
            BackupRunnerFactory.instance())

    @test
    def backup_delete_while_backup_running(self):
        """Ensure delete backup fails while it is running."""
        self.test_runner.run_backup_delete_while_backup_running()

    @test(runs_after=[backup_delete_while_backup_running])
    def restore_instance_from_not_completed_backup(self):
        """Ensure a restore fails while the backup is running."""
        self.test_runner.run_restore_instance_from_not_completed_backup()

    @test(runs_after=[restore_instance_from_not_completed_backup])
    def backup_create_another_backup_running(self):
        """Ensure create backup fails when another backup is running."""
        self.test_runner.run_backup_create_another_backup_running()

    @test(runs_after=[backup_create_another_backup_running])
    def instance_action_right_after_backup_create(self):
        """Ensure any instance action fails while backup is running."""
        self.test_runner.run_instance_action_right_after_backup_create()

    @test(runs_after=[instance_action_right_after_backup_create])
    def delete_unknown_backup(self):
        """Ensure deleting an unknown backup fails."""
        self.test_runner.run_delete_unknown_backup()

    @test(runs_after=[instance_action_right_after_backup_create])
    def backup_create_instance_invalid(self):
        """Ensure create backup fails with invalid instance id."""
        self.test_runner.run_backup_create_instance_invalid()

    @test(runs_after=[instance_action_right_after_backup_create])
    def backup_create_instance_not_found(self):
        """Ensure create backup fails with unknown instance id."""
        self.test_runner.run_backup_create_instance_not_found()


@test(depends_on_groups=[groups.BACKUP_CREATE],
      groups=[GROUP, groups.BACKUP, groups.BACKUP_CREATE_WAIT],
      runs_after_groups=[groups.BACKUP_CREATE_NEGATIVE])
class BackupCreateWaitGroup(TestGroup):
    """Wait for Backup Create to Complete."""

    def __init__(self):
        super(BackupCreateWaitGroup, self).__init__(
            BackupRunnerFactory.instance())

    @test
    def backup_create_completed(self):
        """Check that the backup completes successfully."""
        self.test_runner.run_backup_create_completed()

    @test(depends_on=[backup_create_completed])
    def instance_goes_active(self):
        """Check that the instance goes active after the backup."""
        self.test_runner.run_instance_goes_active()

    @test(depends_on=[backup_create_completed])
    def backup_list(self):
        """Test list backups."""
        self.test_runner.run_backup_list()

    @test(depends_on=[backup_create_completed])
    def backup_list_filter_datastore(self):
        """Test list backups and filter by datastore."""
        self.test_runner.run_backup_list_filter_datastore()

    @test(depends_on=[backup_create_completed])
    def backup_list_filter_different_datastore(self):
        """Test list backups and filter by different datastore."""
        self.test_runner.run_backup_list_filter_different_datastore()

    @test(depends_on=[backup_create_completed])
    def backup_list_filter_datastore_not_found(self):
        """Test list backups and filter by unknown datastore."""
        self.test_runner.run_backup_list_filter_datastore_not_found()

    @test(depends_on=[backup_create_completed])
    def backup_list_for_instance(self):
        """Test backup list for instance."""
        self.test_runner.run_backup_list_for_instance()

    @test(depends_on=[backup_create_completed])
    def backup_get(self):
        """Test backup show."""
        self.test_runner.run_backup_get()

    @test(depends_on=[backup_create_completed])
    def backup_get_unauthorized_user(self):
        """Ensure backup show fails for an unauthorized user."""
        self.test_runner.run_backup_get_unauthorized_user()


@test(depends_on_groups=[groups.BACKUP_CREATE],
      groups=[GROUP, groups.BACKUP_INC, groups.BACKUP_INC_CREATE])
class BackupIncCreateGroup(TestGroup):
    """Test Backup Incremental Create functionality."""

    def __init__(self):
        super(BackupIncCreateGroup, self).__init__(
            BackupRunnerFactory.instance())

    @test
    def add_data_for_inc_backup_1(self):
        """Add data to instance for inc backup 1."""
        self.test_runner.run_add_data_for_inc_backup_1()

    @test(depends_on=[add_data_for_inc_backup_1])
    def verify_data_for_inc_backup_1(self):
        """Verify data in instance for inc backup 1."""
        self.test_runner.run_verify_data_for_inc_backup_1()

    @test(depends_on=[verify_data_for_inc_backup_1])
    def inc_backup_1(self):
        """Run incremental backup 1."""
        self.test_runner.run_inc_backup_1()

    @test(depends_on=[inc_backup_1])
    def wait_for_inc_backup_1(self):
        """Check that inc backup 1 completes successfully."""
        self.test_runner.run_wait_for_inc_backup_1()

    @test(depends_on=[wait_for_inc_backup_1])
    def add_data_for_inc_backup_2(self):
        """Add data to instance for inc backup 2."""
        self.test_runner.run_add_data_for_inc_backup_2()

    @test(depends_on=[add_data_for_inc_backup_2])
    def verify_data_for_inc_backup_2(self):
        """Verify data in instance for inc backup 2."""
        self.test_runner.run_verify_data_for_inc_backup_2()

    @test(depends_on=[wait_for_inc_backup_1],
          runs_after=[verify_data_for_inc_backup_2])
    def instance_goes_active_inc_1(self):
        """Check that the instance goes active after the inc 1 backup."""
        self.test_runner.run_instance_goes_active()

    @test(depends_on=[verify_data_for_inc_backup_2],
          runs_after=[instance_goes_active_inc_1])
    def inc_backup_2(self):
        """Run incremental backup 2."""
        self.test_runner.run_inc_backup_2()

    @test(depends_on=[inc_backup_2])
    def wait_for_inc_backup_2(self):
        """Check that inc backup 2 completes successfully."""
        self.test_runner.run_wait_for_inc_backup_2()

    @test(depends_on=[wait_for_inc_backup_2])
    def instance_goes_active_inc_2(self):
        """Check that the instance goes active after the inc 2 backup."""
        self.test_runner.run_instance_goes_active()


@test(depends_on_groups=[groups.BACKUP_CREATE],
      groups=[GROUP, groups.BACKUP_INST, groups.BACKUP_INST_CREATE])
class BackupInstCreateGroup(TestGroup):
    """Test Backup Instance Create functionality."""

    def __init__(self):
        super(BackupInstCreateGroup, self).__init__(
            BackupRunnerFactory.instance())

    @test
    def restore_from_backup(self):
        """Check that restoring an instance from a backup starts."""
        self.test_runner.run_restore_from_backup()


@test(depends_on_groups=[groups.BACKUP_INC_CREATE],
      groups=[GROUP, groups.BACKUP_INC_INST,
              groups.BACKUP_INC_INST_CREATE],
      runs_after_groups=[groups.BACKUP_INST_CREATE])
class BackupIncInstCreateGroup(TestGroup):
    """Test Backup Incremental Instance Create functionality."""

    def __init__(self):
        super(BackupIncInstCreateGroup, self).__init__(
            BackupRunnerFactory.instance())

    @test
    def restore_from_inc_1_backup(self):
        """Check that restoring an instance from inc 1 backup starts."""
        self.test_runner.run_restore_from_inc_1_backup()


@test(depends_on_groups=[groups.BACKUP_INST_CREATE],
      groups=[GROUP, groups.BACKUP_INST, groups.BACKUP_INST_CREATE_WAIT],
      runs_after_groups=[groups.BACKUP_INC_INST_CREATE,
                         groups.DB_ACTION_INST_CREATE,
                         groups.INST_ACTIONS_RESIZE])
class BackupInstCreateWaitGroup(TestGroup):
    """Test Backup Instance Create completes."""

    def __init__(self):
        super(BackupInstCreateWaitGroup, self).__init__(
            BackupRunnerFactory.instance())

    @test
    def restore_from_backup_completed(self):
        """Wait until restoring an instance from a backup completes."""
        self.test_runner.run_restore_from_backup_completed()

    @test(depends_on=[restore_from_backup_completed])
    def verify_data_in_restored_instance(self):
        """Verify data in restored instance."""
        self.test_runner.run_verify_data_in_restored_instance()

    @test(depends_on=[restore_from_backup_completed])
    def verify_databases_in_restored_instance(self):
        """Verify databases in restored instance."""
        self.test_runner.run_verify_databases_in_restored_instance()


@test(depends_on_groups=[groups.BACKUP_INC_INST_CREATE],
      groups=[GROUP, groups.BACKUP_INC_INST,
              groups.BACKUP_INC_INST_CREATE_WAIT],
      runs_after_groups=[groups.BACKUP_INST_CREATE_WAIT])
class BackupIncInstCreateWaitGroup(TestGroup):
    """Test Backup Incremental Instance Create completes."""

    def __init__(self):
        super(BackupIncInstCreateWaitGroup, self).__init__(
            BackupRunnerFactory.instance())

    @test
    def restore_from_inc_1_backup_completed(self):
        """Wait until restoring an inst from inc 1 backup completes."""
        self.test_runner.run_restore_from_inc_1_backup_completed()

    @test(depends_on=[restore_from_inc_1_backup_completed])
    def verify_data_in_restored_inc_1_instance(self):
        """Verify data in restored inc 1 instance."""
        self.test_runner.run_verify_data_in_restored_inc_1_instance()

    @test(depends_on=[restore_from_inc_1_backup_completed])
    def verify_databases_in_restored_inc_1_instance(self):
        """Verify databases in restored inc 1 instance."""
        self.test_runner.run_verify_databases_in_restored_inc_1_instance()


@test(depends_on_groups=[groups.BACKUP_INST_CREATE_WAIT],
      groups=[GROUP, groups.BACKUP_INST, groups.BACKUP_INST_DELETE],
      runs_after_groups=[groups.BACKUP_INC_INST_CREATE_WAIT])
class BackupInstDeleteGroup(TestGroup):
    """Test Backup Instance Delete functionality."""

    def __init__(self):
        super(BackupInstDeleteGroup, self).__init__(
            BackupRunnerFactory.instance())

    @test
    def delete_restored_instance(self):
        """Test deleting the restored instance."""
        self.test_runner.run_delete_restored_instance()


@test(depends_on_groups=[groups.BACKUP_INC_INST_CREATE_WAIT],
      groups=[GROUP, groups.BACKUP_INC_INST,
              groups.BACKUP_INC_INST_DELETE],
      runs_after_groups=[groups.BACKUP_INST_DELETE])
class BackupIncInstDeleteGroup(TestGroup):
    """Test Backup Incremental Instance Delete functionality."""

    def __init__(self):
        super(BackupIncInstDeleteGroup, self).__init__(
            BackupRunnerFactory.instance())

    @test
    def delete_restored_inc_1_instance(self):
        """Test deleting the restored inc 1 instance."""
        self.test_runner.run_delete_restored_inc_1_instance()


@test(depends_on_groups=[groups.BACKUP_INST_DELETE],
      groups=[GROUP, groups.BACKUP_INST, groups.BACKUP_INST_DELETE_WAIT],
      runs_after_groups=[groups.INST_DELETE])
class BackupInstDeleteWaitGroup(TestGroup):
    """Test Backup Instance Delete completes."""

    def __init__(self):
        super(BackupInstDeleteWaitGroup, self).__init__(
            BackupRunnerFactory.instance())

    @test
    def wait_for_restored_instance_delete(self):
        """Wait until deleting the restored instance completes."""
        self.test_runner.run_wait_for_restored_instance_delete()


@test(depends_on_groups=[groups.BACKUP_INC_INST_DELETE],
      groups=[GROUP, groups.BACKUP_INC_INST,
              groups.BACKUP_INC_INST_DELETE_WAIT],
      runs_after_groups=[groups.INST_DELETE])
class BackupIncInstDeleteWaitGroup(TestGroup):
    """Test Backup Incremental Instance Delete completes."""

    def __init__(self):
        super(BackupIncInstDeleteWaitGroup, self).__init__(
            BackupRunnerFactory.instance())

    @test
    def wait_for_restored_inc_1_instance_delete(self):
        """Wait until deleting the restored inc 1 instance completes."""
        self.test_runner.run_wait_for_restored_inc_1_instance_delete()


@test(depends_on_groups=[groups.BACKUP_INC_CREATE],
      groups=[GROUP, groups.BACKUP_INC, groups.BACKUP_INC_DELETE],
      runs_after_groups=[groups.BACKUP_INC_INST_CREATE_WAIT])
class BackupIncDeleteGroup(TestGroup):
    """Test Backup Incremental Delete functionality."""

    def __init__(self):
        super(BackupIncDeleteGroup, self).__init__(
            BackupRunnerFactory.instance())

    @test
    def delete_inc_2_backup(self):
        """Test deleting the inc 2 backup."""
        # We only delete the inc 2 backup, as the inc 1 should be deleted
        # by the full backup delete that runs after.
        self.test_runner.run_delete_inc_2_backup()


@test(depends_on_groups=[groups.BACKUP_CREATE],
      groups=[GROUP, groups.BACKUP, groups.BACKUP_DELETE],
      runs_after_groups=[groups.BACKUP_INST_CREATE_WAIT,
                         groups.BACKUP_INC_DELETE,
                         groups.INST_ACTIONS_RESIZE_WAIT])
class BackupDeleteGroup(TestGroup):
    """Test Backup Delete functionality."""

    def __init__(self):
        super(BackupDeleteGroup, self).__init__(
            BackupRunnerFactory.instance())

    @test
    def delete_backup_unauthorized_user(self):
        """Ensure deleting backup by an unauthorized user fails."""
        self.test_runner.run_delete_backup_unauthorized_user()

    @test(runs_after=[delete_backup_unauthorized_user])
    def delete_backup(self):
        """Test deleting the backup."""
        self.test_runner.run_delete_backup()

    @test(depends_on=[delete_backup])
    def check_for_incremental_backup(self):
        """Test that backup children are deleted."""
        self.test_runner.run_check_for_incremental_backup()

    @test
    def remove_backup_data_from_instance(self):
        """Remove the backup data from the original instance."""
        self.test_runner.run_remove_backup_data_from_instance()
