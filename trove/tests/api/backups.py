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
from proboscis.asserts import assert_is_not_none
from proboscis.asserts import assert_true
from proboscis import test
from proboscis import SkipTest
from proboscis import before_class
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
from trove.tests import util
from trove.tests.api.instances import WaitForGuestInstallationToFinish
from trove.tests.api.instances import instance_info
from trove.tests.api.instances import assert_unprocessable
from trove.tests.api.instances import GROUP_START
from trove.tests.util.users import Requirements
from trove.tests.api.instances import assert_unprocessable
#from reddwarfclient import backups
from troveclient import exceptions
from datetime import datetime
# Define groups

GROUP = "dbaas.api.backups"
GROUP_POSITIVE = GROUP + ".positive"
GROUP_NEGATIVE = GROUP + ".negative"
# Define Globals
BACKUP_NAME = 'backup_test'
BACKUP_DESC = 'test description for backup'
BACKUP_DB_NAME = "backup_DB"
backup_name = None
backup_desc = None
deleted_backup_id = None

databases = []
users = []
backup_resp = None


@test(depends_on_classes=[WaitForGuestInstallationToFinish],
      depends_on_groups=[GROUP_START],
      groups=[GROUP])
class BackupsBase(object):
    """
    Base class for Positive and Negative classes for test cases
    """
    #def set_up(self):
    def __init__(self):
        self.backup_status = None
        self.backup_id = None
        self.restore_id = None
        self.dbaas = util.create_dbaas_client(instance_info.user)

    def _create_backup(self, backup_name, backup_desc, inst_id=None):
        if inst_id is None:
            inst_id = instance_info.id
        backup_resp = instance_info.dbaas.backups.create(backup_name,
                                                         inst_id,
                                                         backup_desc)
        return backup_resp

    def _create_restore(self, client, backup_id):
        restorePoint = {"backupRef": backup_id}
        restore_resp = client.instances.create(
            BACKUP_NAME + "_restore",
            instance_info.dbaas_flavor_href,
            instance_info.volume,
            restorePoint=restorePoint)
        return restore_resp

    def _create_new_restore(self, backup_id, name, flavor=None, volume=None):
        restorePoint = {"backupRef": backup_id}
        restore_resp = instance_info.dbaas.instances.create(
            name + "_restore",
            (1 if flavor is None else flavor),
            {'size': (1 if volume is None else volume)},
            restorePoint=restorePoint)
        return restore_resp

    def _list_backups_by_instance(self, inst_id=None):
        if inst_id is None:
            inst_id = instance_info.id
        return instance_info.dbaas.instances.backups(inst_id)

    def _get_backup_status(self, backup_id):
        return instance_info.dbaas.backups.get(backup_id).status

    def _delete_backup(self, backup_id):
        assert_not_equal(backup_id, None, "Backup ID is not found")
        instance_info.dbaas.backups.delete(backup_id)
        assert_equal(202, instance_info.dbaas.last_http_code)

    def _backup_is_gone(self, backup_id=None):
        result = None
        if backup_id is None:
            backup_id = self.backup_id
        try:
            result = instance_info.dbaas.backups.get(backup_id)
        except exceptions.NotFound:
            assert_equal(result.status, "404",
                         "status error: %r != 404)" % result.status)
        finally:
            return result is None

    def _instance_is_gone(self, inst_id):
        try:
            instance_info.dbaas.instances.get(inst_id)
            return False
        except exceptions.NotFound:
            return True

    def _result_is_active(self):
        instance = instance_info.dbaas.instances.get(self.restore_id)
        if instance.status == "ACTIVE":
            return True
        else:
            # If its not ACTIVE, anything but BUILD must be an error.
            assert_equal("BUILD", instance.status)
            if instance_info.volume is not None:
                assert_equal(instance.volume.get('used', None), None)
                return False

    def _verify_instance_is_active(self):
        result = instance_info.dbaas.instances.get(instance_info.id)
        return result.status == 'ACTIVE'

    def _verify_instance_status(self, instance_id, status):
        result = instance_info.dbaas.instances.get(instance_id)
        return result.status == status

    def _verify_backup_status(self, backup_id, status):
        result = instance_info.dbaas.backups.get(backup_id)
        return result.status == status

    def _verify_backup_exists(self, result, backup_id):
        assert_true(len(result) >= 1)
        backup = None
        for b in result:
            if b.id == backup_id:
                backup = b
        assert_is_not_none(backup, "Backup not found")
        return backup

    def _verify_databases(self, db_name):
        databases = instance_info.dbaas.databases.list(instance_info.id)
        dbs = [database.name for database in databases]
        for db in instance_info.databases:
            assert_true(db_name in dbs)

        # Test to make sure that user in other tenant is not able
        # to GET this backup
        reqs = Requirements(is_admin=False)
        other_user = CONFIG.users.find_user(
            reqs,
            black_list=[instance_info.user.auth_user])
        other_client = create_dbaas_client(other_user)
        assert_raises(exceptions.NotFound, other_client.backups.get,
                      self.backup_info.id)


@test(depends_on_classes=[WaitForGuestInstallationToFinish],
      groups=[GROUP, GROUP_POSITIVE])
class TestBackupPositive(BackupsBase):
    backup_id = None
    restore_id = None
    database_name = "backup_DB"
    restored_name = "restored_backup"
    restored_desc = "Backup from Restored Instance"

    @test
    def test_create_backup(self):
        databases = []
        databases.append({"name": BACKUP_DB_NAME, "charset": "latin2",
                          "collate": "latin2_general_ci"})
        instance_info.dbaas.databases.create(instance_info.id, databases)
        assert_equal(202, instance_info.dbaas.last_http_code)
        backup = self._create_backup(BACKUP_NAME, BACKUP_DESC,
                                     instance_info.id)
        self.backup_id = backup.id
        assert_equal(backup.name, BACKUP_NAME)
        assert_equal(backup.description, BACKUP_DESC)
        assert_equal(backup.instance_id, instance_info.id)
        assert_equal(backup.status, 'NEW')
        assert_is_not_none(backup.id, 'backup.id does not exist')
        assert_is_not_none(backup.created, 'backup.created does not exist')
        assert_is_not_none(backup.updated, 'backup.updated does not exist')
        instance = instance_info.dbaas.instances.get(instance_info.id)
        assert_true(instance.status in ('ACTIVE', 'BACKUP'))
        # Get Backup status by backup id during and after backup creation
        poll_until(lambda: self._verify_instance_status(instance.id,
                                                        'BACKUP'),
                   time_out=120, sleep_time=2)
        poll_until(lambda: self._verify_backup_status(backup.id, 'BUILDING'),
                   time_out=120, sleep_time=2)
        poll_until(lambda: self._verify_backup_status(backup.id, 'COMPLETED'),
                   time_out=120, sleep_time=2)
        poll_until(lambda: self._verify_instance_status(instance.id,
                                                        'ACTIVE'),
                   time_out=120, sleep_time=2)

    @test(depends_on=[test_create_backup])
    def test_list_backups(self):
        result = instance_info.dbaas.backups.list()
        for each in result:
            print("ID: %r  Name: %r Status: %r" % (each.id,
                                                   each.name,
                                                   each.status))
        backup = self._verify_backup_exists(result, self.backup_id)
        assert_is_not_none(backup, "Backup not found")
        assert_equal(backup.name, BACKUP_NAME)
        assert_equal(backup.description, BACKUP_DESC)
        assert_equal(backup.instance_id, instance_info.id)
        assert_equal(backup.status, 'COMPLETED')
        assert_is_not_none(backup.id, 'backup.id does not exist')
        assert_is_not_none(backup.created, 'backup.created does not exist')
        assert_is_not_none(backup.updated, 'backup.updated does not exist')

    @test(depends_on=[test_create_backup, test_list_backups])
    def test_list_backups_for_instance(self):
        result = self._list_backups_by_instance()
        backup = self._verify_backup_exists(result, self.backup_id)
        assert_equal(backup.name, BACKUP_NAME)
        assert_equal(backup.description, BACKUP_DESC)
        assert_equal(backup.instance_id, instance_info.id)
        assert_equal(backup.status, 'COMPLETED')
        assert_is_not_none(backup.id, 'backup.id does not exist')
        assert_is_not_none(backup.created, 'backup.created does not exist')
        assert_is_not_none(backup.updated, 'backup.updated does not exist')

    @test(depends_on=[test_create_backup])
    def test_get_backup(self):
        backup = instance_info.dbaas.backups.get(self.backup_id)
        assert_equal(backup.id, self.backup_id)
        assert_equal(backup.name, BACKUP_NAME)
        assert_equal(backup.description, BACKUP_DESC)
        assert_equal(backup.instance_id, instance_info.id)
        assert_equal(backup.status, 'COMPLETED')
        assert_is_not_none(backup.created, 'backup.created does not exist')
        assert_is_not_none(backup.updated, 'backup.updated does not exist')

    @test(depends_on=[test_create_backup, test_list_backups_for_instance])
    def test_restore_backup(self):
        if test_config.auth_strategy == "fake":
            # We should create restore logic in fake guest agent to not skip
            raise SkipTest("Skipping restore tests for fake mode.")
        restore_resp = self._create_restore(instance_info.dbaas,
                                            self.backup_id)
        assert_equal(200, instance_info.dbaas.last_http_code)
        assert_equal("BUILD", restore_resp.status)
        assert_is_not_none(restore_resp.id, 'restored inst_id does not exist')
        self.restore_id = restore_resp.id
        poll_until(self._result_is_active)
        restored_inst = instance_info.dbaas.instances.get(self.restore_id)
        assert_is_not_none(restored_inst, 'restored instance does not exist')
        assert_equal(restored_inst.name, BACKUP_NAME + "_restore")
        assert_equal(restored_inst.status, 'ACTIVE')
        assert_is_not_none(restored_inst.id, 'restored inst_id does not exist')
        self._verify_databases(BACKUP_DB_NAME)

    @test(depends_on=[test_restore_backup, test_list_backups_for_instance],
          always_run=True)
    def test_delete_backup(self):
        self._delete_backup(self.backup_id)
        poll_until(self._backup_is_gone)

    @test(depends_on=[test_restore_backup], always_run=True)
    def test_delete_restored_instance(self):
        if test_config.auth_strategy == "fake":
            raise SkipTest("Skipping delete restored instance for fake mode.")
            # Create a backup to list after instance is deleted
        backup = self._create_backup(self.restored_name,
                                     self.restored_desc,
                                     inst_id=self.restore_id)
        assert_equal(202, instance_info.dbaas.last_http_code)
        poll_until(lambda: self._verify_backup_status(backup.id, 'COMPLETED'),
                   time_out=120, sleep_time=2)
        self.deleted_backup_id = backup.id
        instance_info.dbaas.instances.delete(self.restore_id)
        assert_equal(202, instance_info.dbaas.last_http_code)
        poll_until(lambda: self._instance_is_gone(self.restore_id))
        assert_raises(exceptions.NotFound, instance_info.dbaas.instances.get,
                      self.restore_id)

    @test(depends_on=[test_delete_restored_instance])
    def test_list_backups_for_deleted_instance(self):
        if test_config.auth_strategy == "fake":
            raise SkipTest("Skipping deleted instance tests for fake mode.")
        result = self._list_backups_by_instance(inst_id=self.restore_id)
        backup = self._verify_backup_exists(result, self.deleted_backup_id)
        assert_equal(backup.name, self.restored_name)
        assert_equal(backup.description, self.restored_desc)
        assert_equal(backup.instance_id, self.restore_id)
        assert_equal(backup.status, 'COMPLETED')
        assert_is_not_none(backup.id, 'backup.id does not exist')
        assert_is_not_none(backup.created, 'backup.created does not exist')
        assert_is_not_none(backup.updated, 'backup.updated does not exist')


@test(depends_on_classes=[WaitForGuestInstallationToFinish],
      groups=[GROUP, GROUP_NEGATIVE])
class TestBackupNegative(BackupsBase):
    databases = []
    users = []
    starttime_list = []
    xtra_instance = None
    xtra_backup = None
    spare_client = None
    spare_user = None

    @before_class
    def setUp(self):
        #instance_info.dbaas.instances.get().
        self.spare_user = test_config.users.find_user(
            Requirements(is_admin=False, services=["trove"]),
            black_list=[instance_info.user.auth_user])
        self.spare_client = util.create_dbaas_client(self.spare_user)

    def test_create_backup(self):
        backup = self._create_backup(BACKUP_NAME, BACKUP_DESC,
                                     instance_info.id)
        poll_until(lambda: self._verify_backup_status(backup.id, 'COMPLETED'),
                   time_out=120, sleep_time=2)

    @test(runs_after=[test_create_backup])
    def test_create_backup_with_instance_not_active(self):
        name = "spare_instance"
        flavor = 2
        self.databases.append({"name": "db2"})
        self.users.append({"name": "lite", "password": "litepass",
                           "databases": [{"name": "db2"}]})
        volume = {'size': 2}
        self.xtra_instance = instance_info.dbaas.instances.create(
            name,
            flavor,
            volume,
            self.databases,
            self.users)
        assert_equal(200, instance_info.dbaas.last_http_code)
        # immediately create the backup while instance is still in "BUILD"
        try:
            self.xtra_backup = self._create_backup(
                BACKUP_NAME, BACKUP_DESC, inst_id=self.xtra_instance.id)
            assert_true(False, "Expected 422 from create backup")
        except exceptions.UnprocessableEntity:
            assert_equal(422, instance_info.dbaas.last_http_code)
        assert_equal(422, instance_info.dbaas.last_http_code)
        # make sure the instance status goes back to "ACTIVE"
        poll_until(lambda: self._verify_instance_status(self.xtra_instance.id,
                                                        "ACTIVE"),
                   time_out=120, sleep_time=2)
        # Now that it's active, create the backup
        self.xtra_backup = self._create_backup(BACKUP_NAME, BACKUP_DESC)
        assert_equal(202, instance_info.dbaas.last_http_code)
        poll_until(lambda: self._verify_backup_status(self.xtra_backup.id,
                                                      'COMPLETED'),
                   time_out=120, sleep_time=2)
        # DON'T Delete backup instance now, Need it for restore to smaller

    @test(runs_after=[test_create_backup_with_instance_not_active])
    def test_restore_backups_to_smaller_instance(self):
        raise SkipTest("Test case is not completed")
        if test_config.auth_strategy == "fake":
            raise SkipTest("Skipping restore tests for fake mode.")
            # Create a 2GB volume instance and add the 2G of data

        # Backup a 2GB Database
        backup = self._create_backup("2GB_backup", "restore backup to smaller")
        assert_equal(202, instance_info.dbaas.last_http_code)
        poll_until(lambda: self._verify_backup_status(backup.id, 'COMPLETED'),
                   time_out=120, sleep_time=2)
        # Try to restore it to a 1GB instance
        try:
            self._create_new_restore(backup.id,
                                     "1GB instance too small",
                                     flavor=1,
                                     volume=1)
            assert_true(False, "Expected 422 create new backup")
        except exceptions.UnprocessableEntity:
            assert_equal(422, instance_info.dbaas.last_http_code)
            # Now delete the backup
        self._delete_backup(backup.id)
        assert_equal(202, instance_info.dbaas.last_http_code)
        poll_until(lambda: self._backup_is_gone(backup_id=backup.id))

    @test
    def test_list_backups_account_not_owned(self):
        raise SkipTest("Please see Launchpad Bug #1188822")
        std_backup = instance_info.dbaas.backups.list()[0]
        try:
            self.spare_client.backups.get(std_backup)
        except exceptions.NotFound:
            assert_equal(404, self.spare_client.last_http_code)
            # The SPARE user should not be able to "get" the STD user backups
        assert_equal(404, self.spare_client.last_http_code)

    @test(runs_after=[test_restore_backups_to_smaller_instance])
    def test_restore_backup_account_not_owned(self):
        if test_config.auth_strategy == "fake":
            raise SkipTest("Skipping restore tests for fake mode.")
        backup = self._create_backup("rest_not_owned_backup",
                                     "restoring a backup of a different user")
        assert_equal(202, instance_info.dbaas.last_http_code)
        poll_until(lambda: self._verify_backup_status(backup.id, 'COMPLETED'),
                   time_out=120, sleep_time=2)
        try:
            self._create_restore(self.spare_client, backup.id)
            assert_true(False, "Expected 404 from create restore")
        except exceptions.ClientException:
            assert_equal(404, self.spare_client.last_http_code)
        instance_info.dbaas.backups.delete(backup.id)
        poll_until(lambda: self._backup_is_gone(backup_id=backup.id))

    @test
    def test_delete_backup_account_not_owned(self):
        raise SkipTest("Please see Launchpad Bug #1188822")
        std_backup = instance_info.dbaas.backups.list()[0]
        print("SPARE USER: %r STD BACKUP: %r" %
              (self.spare_user.auth_user,
               self.spare_client.backups.get(std_backup)))
        instance_info.dbaas.backups.delete(std_backup.id)
        print("Resp code: Delete backup no owned: %r " %
              instance_info.dbaas.last_http_code)

    @test
    def test_backup_create_instance_not_found(self):
        """test create backup with unknown instance"""
        assert_raises(exceptions.NotFound, instance_info.dbaas.backups.create,
                      BACKUP_NAME, 'nonexistent_instance', BACKUP_DESC)

    @test
    def test_backup_delete_not_found(self):
        """test delete unknown backup"""
        assert_raises(exceptions.NotFound, instance_info.dbaas.backups.delete,
                      'nonexistent_backup')

    @test(runs_after=[test_restore_backup_account_not_owned])
    def test_restore_backup_that_did_not_complete(self):
        if test_config.auth_strategy == "fake":
            raise SkipTest("Skipping restore tests for fake mode.")
            # Backup a 10GB Database
        backup = self._create_backup("10GB_backup", "restore before complete")
        assert_equal(202, instance_info.dbaas.last_http_code)
        # restore immediately, before the backup is completed
        try:
            self._create_new_restore(backup.id,
                                     "backup did not complete",
                                     flavor=2,
                                     volume=10)
            assert_true(False, "Expected 409 from create new restore")
        except exceptions.ClientException:
            assert_equal(409, instance_info.dbaas.last_http_code)
        poll_until(lambda: self._verify_backup_status(backup.id, 'COMPLETED'),
                   time_out=120, sleep_time=2)
        instance_info.dbaas.backups.delete(backup.id)
        poll_until(lambda: self._backup_is_gone(backup_id=backup.id))

    @test(runs_after=[test_restore_backup_that_did_not_complete])
    def test_delete_while_backing_up(self):
        backup = self._create_backup("delete_as_backup",
                                     "delete backup while backing up")
        assert_equal(202, instance_info.dbaas.last_http_code)
        # Dont wait for backup to complete, try to delete it
        try:
            self._delete_backup(backup.id)
            assert_true(False, "Expected 422 from delete backup")
        except:
            assert_equal(422, instance_info.dbaas.last_http_code)
        poll_until(lambda: self._verify_backup_status(backup.id, 'COMPLETED'),
                   time_out=120, sleep_time=1)
        # DCF WHy is this delete different than the one above that uses the helper function?
        instance_info.dbaas.backups.delete(backup.id)
        poll_until(lambda: self._backup_is_gone(backup_id=backup.id))

    def test_instance_action_right_after_backup_create(self):
        """test any instance action while backup is running"""
        backup = self._create_backup("modify_during_create",
                                     "modify instance while creating backup")
        assert_equal(202, instance_info.dbaas.last_http_code)
        # Dont wait for backup to complete, try to delete it
        assert_unprocessable(instance_info.dbaas.instances.resize_instance,
                             instance_info.id, 1)
        poll_until(lambda: self._verify_backup_status(backup.id, 'COMPLETED'),
                   time_out=120, sleep_time=2)

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

    @test
    def test_restore_deleted_backup(self):
        if test_config.auth_strategy == "fake":
            raise SkipTest("Skipping restore tests for fake mode.")
        backup = self._create_backup("rest_del_backup",
                                     "restoring a deleted backup")
        assert_equal(202, instance_info.dbaas.last_http_code)
        poll_until(lambda: self._verify_backup_status(backup.id, 'COMPLETED'),
                   time_out=120, sleep_time=2)
        self._delete_backup(backup.id)
        poll_until(self._backup_is_gone)
        try:
            self._create_restore(instance_info.dbaas, backup.id)
            assert_true(False, "Expected 404 from create restore")
        except exceptions.ClientException:
            assert_equal(404, instance_info.dbaas.last_http_code)

    @test
    def test_delete_deleted_backup(self):
        backup = self._create_backup("del_backup", "delete a deleted backup")
        assert_equal(202, instance_info.dbaas.last_http_code)
        poll_until(lambda: self._verify_backup_status(backup.id, 'COMPLETED'),
                   time_out=120, sleep_time=1)
        self._delete_backup(backup.id)
        poll_until(lambda: self._backup_is_gone(backup.id))
        try:
            self._delete_backup(backup.id)
            assert_true(False, "Expected 404 from delete backup")
        except exceptions.NotFound:
            assert_equal(404, instance_info.dbaas.last_http_code)

    @test(runs_after=[test_create_backup_with_instance_not_active,
                      test_restore_backups_to_smaller_instance,
                      test_restore_deleted_backup],
          always_run=True)
    def test_delete_negative_instance(self):
        try:
            self._delete_backup(self.xtra_backup.id)
            assert_equal(202, instance_info.dbaas.last_http_code)
            poll_until(lambda: self._backup_is_gone(self.xtra_backup.id))
        except exceptions.NotFound:
            assert_equal(404, instance_info.dbaas.last_http_code)
        try:
            instance_info.dbaas.instances.delete(self.xtra_instance.id)
            assert_equal(202, instance_info.dbaas.last_http_code)
            poll_until(lambda: self._instance_is_gone(self.xtra_instance.id))
        except exceptions.NotFound:
            assert_equal(404, instance_info.dbaas.last_http_code)
        finally:
            assert_raises(exceptions.NotFound,
                          instance_info.dbaas.instances.get,
                          self.xtra_instance.id)


@test(depends_on_classes=[WaitForGuestInstallationToFinish],
      runs_after=[TestBackupPositive, TestBackupNegative],
      groups=[GROUP, GROUP_NEGATIVE, GROUP_POSITIVE])
class TestBackupCleanup(BackupsBase):
    @test(always_run=True)
    def test_clean_up_backups(self):
        backup_list = instance_info.dbaas.backups.list()
        for backup in backup_list:
            print("Cleanup backup: %r and status: %r" % (backup.id, backup.status))
            if backup.status == 'COMPLETED':
                try:
                    self._delete_backup(backup.id)
                    assert_equal(202, instance_info.dbaas.last_http_code)
                    poll_until(lambda: self._backup_is_gone(backup.id))
                except exceptions.NotFound:
                    assert_equal(404, instance_info.dbaas.last_http_code)
