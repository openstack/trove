# Copyright 2011 OpenStack LLC.
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
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_not_equal
from proboscis.asserts import assert_raises
from proboscis import test
from proboscis import SkipTest
from proboscis.decorators import time_out
from trove.tests.util import poll_until
from trove.tests.util import test_config
from trove.tests.util import create_dbaas_client
from trove.tests.util.users import Requirements
from trove.tests.config import CONFIG
from troveclient import exceptions
from trove.tests.api.instances import WaitForGuestInstallationToFinish
from trove.tests.api.instances import instance_info
from trove.tests.api.instances import assert_unprocessable

GROUP = "dbaas.api.backups"
BACKUP_NAME = 'backup_test'
BACKUP_DESC = 'test description'


backup_info = None
restore_instance_id = None


@test(depends_on_classes=[WaitForGuestInstallationToFinish],
      groups=[GROUP])
class CreateBackups(object):

    @test
    def test_backup_create_instance_not_found(self):
        """test create backup with unknown instance"""
        assert_raises(exceptions.NotFound, instance_info.dbaas.backups.create,
                      BACKUP_NAME, 'nonexistent_instance', BACKUP_DESC)

    @test
    def test_backup_create_instance(self):
        """test create backup for a given instance"""
        result = instance_info.dbaas.backups.create(BACKUP_NAME,
                                                    instance_info.id,
                                                    BACKUP_DESC)
        assert_equal(BACKUP_NAME, result.name)
        assert_equal(BACKUP_DESC, result.description)
        assert_equal(instance_info.id, result.instance_id)
        assert_equal('NEW', result.status)
        instance = instance_info.dbaas.instances.list()[0]
        assert_equal('BACKUP', instance.status)
        global backup_info
        backup_info = result


@test(runs_after=[CreateBackups],
      groups=[GROUP])
class AfterBackupCreation(object):

    @test
    def test_instance_action_right_after_backup_create(self):
        """test any instance action while backup is running"""
        assert_unprocessable(instance_info.dbaas.instances.resize_instance,
                             instance_info.id, 1)

    @test
    def test_backup_create_another_backup_running(self):
        """test create backup when another backup is running"""
        assert_unprocessable(instance_info.dbaas.backups.create,
                             'backup_test2', instance_info.id,
                             'test description2')

    @test
    def test_backup_delete_still_running(self):
        """test delete backup when it is running"""
        result = instance_info.dbaas.backups.list()
        backup = result[0]
        assert_unprocessable(instance_info.dbaas.backups.delete, backup.id)


@test(runs_after=[AfterBackupCreation],
      groups=[GROUP])
class WaitForBackupCreateToFinish(object):
    """
        Wait until the backup create is finished.
    """

    @test
    @time_out(60 * 30)
    def test_backup_created(self):
        # This version just checks the REST API status.
        def result_is_active():
            backup = instance_info.dbaas.backups.get(backup_info.id)
            if backup.status == "COMPLETED":
                return True
            else:
                assert_not_equal("FAILED", backup.status)
                return False

        poll_until(result_is_active)


@test(depends_on=[WaitForBackupCreateToFinish],
      groups=[GROUP])
class ListBackups(object):

    @test
    def test_backup_list(self):
        """test list backups"""
        result = instance_info.dbaas.backups.list()
        assert_equal(1, len(result))
        backup = result[0]
        assert_equal(BACKUP_NAME, backup.name)
        assert_equal(BACKUP_DESC, backup.description)
        assert_equal(instance_info.id, backup.instance_id)
        assert_equal('COMPLETED', backup.status)

    @test
    def test_backup_list_for_instance(self):
        """test backup list for instance"""
        result = instance_info.dbaas.instances.backups(instance_info.id)
        assert_equal(1, len(result))
        backup = result[0]
        assert_equal(BACKUP_NAME, backup.name)
        assert_equal(BACKUP_DESC, backup.description)
        assert_equal(instance_info.id, backup.instance_id)
        assert_equal('COMPLETED', backup.status)

    @test
    def test_backup_get(self):
        """test get backup"""
        backup = instance_info.dbaas.backups.get(backup_info.id)
        assert_equal(backup_info.id, backup.id)
        assert_equal(backup_info.name, backup.name)
        assert_equal(backup_info.description, backup.description)
        assert_equal(instance_info.id, backup.instance_id)
        assert_equal('COMPLETED', backup.status)

        # Test to make sure that user in other tenant is not able
        # to GET this backup
        reqs = Requirements(is_admin=False)
        other_user = CONFIG.users.find_user(
            reqs,
            black_list=[instance_info.user.auth_user])
        other_client = create_dbaas_client(other_user)
        assert_raises(exceptions.NotFound, other_client.backups.get,
                      backup_info.id)


@test(runs_after=[ListBackups],
      groups=[GROUP])
class RestoreUsingBackup(object):

    @test
    def test_restore(self):
        """test restore"""
        if test_config.auth_strategy == "fake":
            raise SkipTest("Skipping restore tests for fake mode.")
        restorePoint = {"backupRef": backup_info.id}
        result = instance_info.dbaas.instances.create(
            instance_info.name + "_restore",
            instance_info.dbaas_flavor_href,
            instance_info.volume,
            restorePoint=restorePoint)
        assert_equal(200, instance_info.dbaas.last_http_code)
        assert_equal("BUILD", result.status)
        global restore_instance_id
        restore_instance_id = result.id


@test(depends_on_classes=[RestoreUsingBackup],
      runs_after=[RestoreUsingBackup],
      groups=[GROUP])
class WaitForRestoreToFinish(object):
    """
        Wait until the instance is finished restoring.
    """

    @test
    @time_out(60 * 32)
    def test_instance_restored(self):
        if test_config.auth_strategy == "fake":
            raise SkipTest("Skipping restore tests for fake mode.")

        # This version just checks the REST API status.
        def result_is_active():
            instance = instance_info.dbaas.instances.get(restore_instance_id)
            if instance.status == "ACTIVE":
                return True
            else:
                # If its not ACTIVE, anything but BUILD must be
                # an error.
                assert_equal("BUILD", instance.status)
                if instance_info.volume is not None:
                    assert_equal(instance.volume.get('used', None), None)
                return False

        poll_until(result_is_active)


@test(runs_after=[WaitForRestoreToFinish],
      groups=[GROUP])
class DeleteBackups(object):

    @test
    def test_delete_restored_instance(self):
        """test delete restored instance"""
        if test_config.auth_strategy == "fake":
            raise SkipTest("Skipping delete restored instance for fake mode.")
        instance_info.dbaas.instances.delete(restore_instance_id)
        assert_equal(202, instance_info.dbaas.last_http_code)

        def instance_is_gone():
            try:
                instance_info.dbaas.instances.get(restore_instance_id)
                return False
            except exceptions.NotFound:
                return True

        poll_until(instance_is_gone)
        assert_raises(exceptions.NotFound, instance_info.dbaas.instances.get,
                      restore_instance_id)

    @test
    def test_backup_delete_not_found(self):
        """test delete unknown backup"""
        assert_raises(exceptions.NotFound, instance_info.dbaas.backups.delete,
                      'nonexistent_backup')

    @test
    @time_out(60 * 2)
    def test_backup_delete(self):
        """test delete"""

        # Test to make sure that user in other tenant is not able
        # to DELETE this backup
        reqs = Requirements(is_admin=False)
        other_user = CONFIG.users.find_user(
            reqs,
            black_list=[instance_info.user.auth_user])
        other_client = create_dbaas_client(other_user)
        assert_raises(exceptions.NotFound, other_client.backups.delete,
                      backup_info.id)

        instance_info.dbaas.backups.delete(backup_info.id)
        assert_equal(202, instance_info.dbaas.last_http_code)

        def backup_is_gone():
            result = instance_info.dbaas.instances.backups(instance_info.id)
            if len(result) == 0:
                return True
            else:
                return False
        poll_until(backup_is_gone)
        assert_raises(exceptions.NotFound, instance_info.dbaas.backups.get,
                      backup_info.id)
