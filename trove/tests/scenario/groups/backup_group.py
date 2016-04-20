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


GROUP = "scenario.backup_restore_group"
GROUP_BACKUP = "scenario.backup_group"
GROUP_BACKUP_LIST = "scenario.backup_list_group"
GROUP_RESTORE = "scenario.restore_group"


class BackupRunnerFactory(test_runners.RunnerFactory):

    _runner_ns = 'backup_runners'
    _runner_cls = 'BackupRunner'


@test(depends_on_groups=[instance_create_group.GROUP], groups=[GROUP])
class BackupGroup(TestGroup):
    """Test Backup and Restore functionality."""

    def __init__(self):
        super(BackupGroup, self).__init__(
            BackupRunnerFactory.instance())

    @test(groups=[GROUP_BACKUP])
    def backup_create_instance_invalid(self):
        """Ensure create backup fails with invalid instance id."""
        self.test_runner.run_backup_create_instance_invalid()

    @test(groups=[GROUP_BACKUP])
    def backup_create_instance_not_found(self):
        """Ensure create backup fails with unknown instance id."""
        self.test_runner.run_backup_create_instance_not_found()

    @test(groups=[GROUP_BACKUP])
    def add_data_for_backup(self):
        """Add data to instance for restore verification."""
        self.test_runner.run_add_data_for_backup()

    @test(groups=[GROUP_BACKUP],
          runs_after=[add_data_for_backup])
    def verify_data_for_backup(self):
        """Verify data in instance."""
        self.test_runner.run_verify_data_for_backup()

    @test(groups=[GROUP_BACKUP],
          runs_after=[verify_data_for_backup])
    def backup_create(self):
        """Check that create backup is started successfully."""
        self.test_runner.run_backup_create()

    @test(groups=[GROUP_BACKUP],
          depends_on=[backup_create])
    def backup_delete_while_backup_running(self):
        """Ensure delete backup fails while it is running."""
        self.test_runner.run_backup_delete_while_backup_running()

    @test(groups=[GROUP_BACKUP],
          depends_on=[backup_create],
          runs_after=[backup_delete_while_backup_running])
    def restore_instance_from_not_completed_backup(self):
        """Ensure a restore fails while the backup is running."""
        self.test_runner.run_restore_instance_from_not_completed_backup()

    @test(groups=[GROUP_BACKUP],
          depends_on=[backup_create],
          runs_after=[restore_instance_from_not_completed_backup])
    def backup_create_another_backup_running(self):
        """Ensure create backup fails when another backup is running."""
        self.test_runner.run_backup_create_another_backup_running()

    @test(groups=[GROUP_BACKUP],
          depends_on=[backup_create],
          runs_after=[backup_create_another_backup_running])
    def instance_action_right_after_backup_create(self):
        """Ensure any instance action fails while backup is running."""
        self.test_runner.run_instance_action_right_after_backup_create()

    @test(groups=[GROUP_BACKUP],
          depends_on=[backup_create],
          runs_after=[instance_action_right_after_backup_create])
    def backup_create_completed(self):
        """Check that the backup completes successfully."""
        self.test_runner.run_backup_create_completed()

    @test(groups=[GROUP_BACKUP, GROUP_BACKUP_LIST],
          depends_on=[backup_create_completed])
    def backup_list(self):
        """Test list backups."""
        self.test_runner.run_backup_list()

    @test(groups=[GROUP_BACKUP, GROUP_BACKUP_LIST],
          depends_on=[backup_create_completed])
    def backup_list_filter_datastore(self):
        """Test list backups and filter by datastore."""
        self.test_runner.run_backup_list_filter_datastore()

    @test(groups=[GROUP_BACKUP, GROUP_BACKUP_LIST],
          depends_on=[backup_create_completed])
    def backup_list_filter_different_datastore(self):
        """Test list backups and filter by different datastore."""
        self.test_runner.run_backup_list_filter_different_datastore()

    @test(groups=[GROUP_BACKUP, GROUP_BACKUP_LIST],
          depends_on=[backup_create_completed])
    def backup_list_filter_datastore_not_found(self):
        """Test list backups and filter by unknown datastore."""
        self.test_runner.run_backup_list_filter_datastore_not_found()

    @test(groups=[GROUP_BACKUP, GROUP_BACKUP_LIST],
          depends_on=[backup_create_completed])
    def backup_list_for_instance(self):
        """Test backup list for instance."""
        self.test_runner.run_backup_list_for_instance()

    @test(groups=[GROUP_BACKUP, GROUP_BACKUP_LIST],
          depends_on=[backup_create_completed])
    def backup_get(self):
        """Test backup show."""
        self.test_runner.run_backup_get()

    @test(groups=[GROUP_BACKUP, GROUP_BACKUP_LIST],
          depends_on=[backup_create_completed])
    def backup_get_unauthorized_user(self):
        """Ensure backup show fails for an unauthorized user."""
        self.test_runner.run_backup_get_unauthorized_user()

    @test(groups=[GROUP_RESTORE],
          depends_on=[backup_create_completed],
          runs_after_groups=[GROUP_BACKUP_LIST])
    def restore_from_backup(self):
        """Check that restoring an instance from a backup starts."""
        self.test_runner.run_restore_from_backup()

    @test(groups=[GROUP_RESTORE],
          depends_on=[restore_from_backup])
    def restore_from_backup_completed(self):
        """Wait until restoring an instance from a backup completes."""
        self.test_runner.run_restore_from_backup_completed()

    @test(groups=[GROUP_RESTORE],
          depends_on=[restore_from_backup_completed])
    def verify_data_in_restored_instance(self):
        """Verify data in restored instance."""
        self.test_runner.run_verify_data_in_restored_instance()

    @test(groups=[GROUP_RESTORE],
          depends_on=[restore_from_backup_completed],
          runs_after=[verify_data_in_restored_instance])
    def delete_restored_instance(self):
        """Test deleting the restored instance."""
        self.test_runner.run_delete_restored_instance()

    @test(groups=[GROUP_BACKUP],
          depends_on=[backup_create_completed],
          runs_after=[delete_restored_instance])
    def delete_unknown_backup(self):
        """Ensure deleting an unknown backup fails."""
        self.test_runner.run_delete_unknown_backup()

    @test(groups=[GROUP_BACKUP],
          depends_on=[backup_create_completed],
          runs_after=[delete_unknown_backup])
    def delete_backup_unauthorized_user(self):
        """Ensure deleting backup by an unauthorized user fails."""
        self.test_runner.run_delete_backup_unauthorized_user()

    @test(groups=[GROUP_BACKUP],
          depends_on=[backup_create_completed],
          runs_after=[delete_backup_unauthorized_user])
    def delete_backup(self):
        """Test deleting the backup."""
        self.test_runner.run_delete_backup()

    @test(depends_on=[delete_backup])
    def check_for_incremental_backup(self):
        """Test that backup children are deleted."""
        self.test_runner.run_check_for_incremental_backup()
