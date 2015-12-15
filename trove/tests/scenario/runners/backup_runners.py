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

from proboscis import SkipTest

from troveclient.compat import exceptions

from trove.common.utils import generate_uuid
from trove.common.utils import poll_until
from trove.tests.config import CONFIG
from trove.tests.scenario.helpers.test_helper import DataType
from trove.tests.scenario.runners.test_runners import TestRunner
from trove.tests.util import create_dbaas_client
from trove.tests.util.users import Requirements


class BackupRunner(TestRunner):

    def __init__(self):
        self.TIMEOUT_BACKUP_CREATE = 60 * 30
        self.TIMEOUT_BACKUP_DELETE = 120

        super(BackupRunner, self).__init__(sleep_time=20,
                                           timeout=self.TIMEOUT_BACKUP_CREATE)

        self.BACKUP_NAME = 'backup_test'
        self.BACKUP_DESC = 'test description'

        self.backup_host = None
        self.backup_info = None
        self.backup_count_prior_to_create = 0
        self.backup_count_for_instance_prior_to_create = 0

        self.incremental_backup_info = None
        self.restore_instance_id = 0
        self.restore_host = None
        self.other_client = None

    def run_backup_create_instance_invalid(
            self, expected_exception=exceptions.BadRequest,
            expected_http_code=400):
        invalid_inst_id = 'invalid-inst-id'
        self.assert_raises(
            expected_exception, expected_http_code,
            self.auth_client.backups.create,
            self.BACKUP_NAME, invalid_inst_id, self.BACKUP_DESC)

    def run_backup_create_instance_not_found(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        self.assert_raises(
            expected_exception, expected_http_code,
            self.auth_client.backups.create,
            self.BACKUP_NAME, generate_uuid(), self.BACKUP_DESC)

    def run_add_data_for_backup(self):
        self.backup_host = self.get_instance_host()
        self.assert_add_data_for_backup(self.backup_host)

    def assert_add_data_for_backup(self, host):
        """In order for this to work, the corresponding datastore
        'helper' class should implement the 'add_large_data' method.
        """
        self.test_helper.add_data(DataType.large, host)

    def run_verify_data_for_backup(self):
        self.assert_verify_backup_data(self.backup_host)

    def assert_verify_backup_data(self, host):
        """In order for this to work, the corresponding datastore
        'helper' class should implement the 'verify_large_data' method.
        """
        self.test_helper.verify_data(DataType.large, host)

    def run_backup_create(self):
        self.assert_backup_create()

    def assert_backup_create(self):
        # Necessary to test that the count increases.
        self.backup_count_prior_to_create = len(
            self.auth_client.backups.list())
        self.backup_count_for_instance_prior_to_create = len(
            self.auth_client.instances.backups(self.instance_info.id))

        result = self.auth_client.backups.create(
            self.BACKUP_NAME, self.instance_info.id, self.BACKUP_DESC)
        self.backup_info = result
        self.assert_equal(self.BACKUP_NAME, result.name,
                          'Unexpected backup name')
        self.assert_equal(self.BACKUP_DESC, result.description,
                          'Unexpected backup description')
        self.assert_equal(self.instance_info.id, result.instance_id,
                          'Unexpected instance ID for backup')
        self.assert_equal('NEW', result.status,
                          'Unexpected status for backup')
        instance = self.auth_client.instances.get(
            self.instance_info.id)

        datastore_version = self.auth_client.datastore_versions.get(
            self.instance_info.dbaas_datastore,
            self.instance_info.dbaas_datastore_version)

        self.assert_equal('BACKUP', instance.status,
                          'Unexpected instance status')
        self.assert_equal(self.instance_info.dbaas_datastore,
                          result.datastore['type'],
                          'Unexpected datastore')
        self.assert_equal(self.instance_info.dbaas_datastore_version,
                          result.datastore['version'],
                          'Unexpected datastore version')
        self.assert_equal(datastore_version.id, result.datastore['version_id'],
                          'Unexpected datastore version id')

    def run_restore_instance_from_not_completed_backup(
            self, expected_exception=exceptions.Conflict,
            expected_http_code=409):
        self.assert_raises(
            expected_exception, expected_http_code,
            self._restore_from_backup, self.backup_info.id)

    def run_instance_action_right_after_backup_create(
            self, expected_exception=exceptions.UnprocessableEntity,
            expected_http_code=422):
        self.assert_raises(expected_exception, expected_http_code,
                           self.auth_client.instances.resize_instance,
                           self.instance_info.id, 1)

    def run_backup_create_another_backup_running(
            self, expected_exception=exceptions.UnprocessableEntity,
            expected_http_code=422):
        self.assert_raises(expected_exception, expected_http_code,
                           self.auth_client.backups.create,
                           'backup_test2', self.instance_info.id,
                           'test description2')

    def run_backup_delete_while_backup_running(
            self, expected_exception=exceptions.UnprocessableEntity,
            expected_http_code=422):
        result = self.auth_client.backups.list()
        backup = result[0]
        self.assert_raises(expected_exception, expected_http_code,
                           self.auth_client.backups.delete, backup.id)

    def run_backup_create_completed(self):
        self._verify_backup(self.backup_info.id)

    def _verify_backup(self, backup_id):
        def _result_is_active():
            backup = self.auth_client.backups.get(backup_id)
            if backup.status == 'COMPLETED':
                return True
            else:
                self.assert_not_equal('FAILED', backup.status,
                                      'Backup status should not be')
                return False

        poll_until(_result_is_active, time_out=self.TIMEOUT_BACKUP_CREATE)

    def run_backup_list(self):
        backup_list = self.auth_client.backups.list()
        self.assert_backup_list(backup_list,
                                self.backup_count_prior_to_create + 1)

    def assert_backup_list(self, backup_list, expected_count):
        self.assert_equal(expected_count, len(backup_list),
                          'Unexpected number of backups found')
        if expected_count:
            backup = backup_list[0]
            self.assert_equal(self.BACKUP_NAME, backup.name,
                              'Unexpected backup name')
            self.assert_equal(self.BACKUP_DESC, backup.description,
                              'Unexpected backup description')
            self.assert_not_equal(0.0, backup.size, 'Unexpected backup size')
            self.assert_equal(self.instance_info.id, backup.instance_id,
                              'Unexpected instance id')
            self.assert_equal('COMPLETED', backup.status,
                              'Unexpected backup status')

    def run_backup_list_filter_datastore(self):
        backup_list = self.auth_client.backups.list(
            datastore=self.instance_info.dbaas_datastore)
        self.assert_backup_list(backup_list,
                                self.backup_count_prior_to_create + 1)

    def run_backup_list_filter_different_datastore(self):
        backup_list = self.auth_client.backups.list(
            datastore='Test_Datastore_1')
        self.assert_backup_list(backup_list, 0)

    def run_backup_list_filter_datastore_not_found(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        self.assert_raises(
            expected_exception, expected_http_code,
            self.auth_client.backups.list,
            datastore='NOT_FOUND')

    def run_backup_list_for_instance(self):
        backup_list = self.auth_client.instances.backups(
            self.instance_info.id)
        self.assert_backup_list(backup_list,
                                self.backup_count_prior_to_create + 1)

    def run_backup_get(self):
        backup = self.auth_client.backups.get(self.backup_info.id)
        self.assert_backup_list([backup], 1)
        self.assert_equal(self.instance_info.dbaas_datastore,
                          backup.datastore['type'],
                          'Unexpected datastore type')
        self.assert_equal(self.instance_info.dbaas_datastore_version,
                          backup.datastore['version'],
                          'Unexpected datastore version')

        datastore_version = self.auth_client.datastore_versions.get(
            self.instance_info.dbaas_datastore,
            self.instance_info.dbaas_datastore_version)
        self.assert_equal(datastore_version.id, backup.datastore['version_id'])

    def run_backup_get_unauthorized_user(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        self._create_other_client()
        self.assert_raises(
            expected_exception, None,
            self.other_client.backups.get, self.backup_info.id)
        # we're using a different client, so we'll check the return code
        # on it explicitly, instead of depending on 'assert_raises'
        self.assert_client_code(expected_http_code=expected_http_code,
                                client=self.other_client)

    def _create_other_client(self):
        if not self.other_client:
            requirements = Requirements(is_admin=False)
            other_user = CONFIG.users.find_user(
                requirements, black_list=[self.instance_info.user.auth_user])
            self.other_client = create_dbaas_client(other_user)

    def run_restore_from_backup(self):
        self.assert_restore_from_backup(self.backup_info.id)

    def assert_restore_from_backup(self, backup_ref):
        result = self._restore_from_backup(backup_ref)
        # TODO(peterstac) - This should probably return code 202
        self.assert_client_code(200)
        self.assert_equal('BUILD', result.status,
                          'Unexpected instance status')
        self.restore_instance_id = result.id

    def _restore_from_backup(self, backup_ref):
        restore_point = {'backupRef': backup_ref}
        result = self.auth_client.instances.create(
            self.instance_info.name + '_restore',
            self.instance_info.dbaas_flavor_href,
            self.instance_info.volume,
            nics=self.instance_info.nics,
            restorePoint=restore_point)
        return result

    def run_restore_from_backup_completed(
            self, expected_states=['BUILD', 'ACTIVE'],
            # TODO(peterstac) - This should probably return code 202
            expected_http_code=200):
        self.assert_restore_from_backup_completed(
            self.restore_instance_id, expected_states, expected_http_code)
        self.restore_host = self.get_instance_host(self.restore_instance_id)

    def assert_restore_from_backup_completed(
            self, instance_id, expected_states, expected_http_code):
        self.assert_instance_action(instance_id, expected_states,
                                    expected_http_code)

    def run_verify_data_in_restored_instance(self):
        self.assert_verify_backup_data(self.restore_host)

    def run_delete_restored_instance(
            self, expected_states=['SHUTDOWN'],
            expected_http_code=202):
        self.assert_delete_restored_instance(
            self.restore_instance_id, expected_states, expected_http_code)

    def assert_delete_restored_instance(
            self, instance_id, expected_states, expected_http_code):
        self.auth_client.instances.delete(instance_id)
        self.assert_instance_action(instance_id, expected_states,
                                    expected_http_code)
        self.assert_all_gone(instance_id, expected_states[-1])

    def run_delete_unknown_backup(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        self.assert_raises(
            expected_exception, expected_http_code,
            self.auth_client.backups.delete,
            'unknown_backup')

    def run_delete_backup_unauthorized_user(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        self._create_other_client()
        self.assert_raises(
            expected_exception, None,
            self.other_client.backups.delete, self.backup_info.id)
        # we're using a different client, so we'll check the return code
        # on it explicitly, instead of depending on 'assert_raises'
        self.assert_client_code(expected_http_code=expected_http_code,
                                client=self.other_client)

    def run_delete_backup(self, expected_http_code=202):
        self.assert_delete_backup(self.backup_info.id, expected_http_code)

    def assert_delete_backup(
            self, backup_id, expected_http_code):
        self.auth_client.backups.delete(backup_id)
        self.assert_client_code(expected_http_code)
        self._wait_until_backup_is_gone(backup_id)

    def _wait_until_backup_is_gone(self, backup_id):
        def _backup_is_gone():
            try:
                self.auth_client.backups.get(backup_id)
                return False
            except exceptions.NotFound:
                return True

        poll_until(_backup_is_gone,
                   time_out=self.TIMEOUT_BACKUP_DELETE)

    def run_check_for_incremental_backup(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        if self.incremental_backup_info is None:
            raise SkipTest("Incremental Backup not created")
        self.assert_raises(
            expected_exception, expected_http_code,
            self.auth_client.backups.get,
            self.incremental_backup_info.id)
