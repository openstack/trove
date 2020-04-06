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
from trove.tests.scenario.helpers.test_helper import DataType
from trove.tests.scenario.runners.test_runners import TestRunner


class BackupRunner(TestRunner):

    def __init__(self):
        self.TIMEOUT_BACKUP_CREATE = 60 * 60
        self.TIMEOUT_BACKUP_DELETE = 120

        super(BackupRunner, self).__init__(timeout=self.TIMEOUT_BACKUP_CREATE)

        self.BACKUP_NAME = 'backup_test'
        self.BACKUP_DESC = 'test description'

        self.backup_host = None
        self.backup_info = None
        self.backup_count_prior_to_create = 0
        self.backup_count_for_ds_prior_to_create = 0
        self.backup_count_for_instance_prior_to_create = 0
        self.databases_before_backup = None

        self.backup_inc_1_info = None
        self.backup_inc_2_info = None
        self.data_types_added = []
        self.restore_instance_id = None
        self.restore_host = None
        self.restore_inc_1_instance_id = None
        self.restore_inc_1_host = None

    def run_backup_create_instance_invalid(
            self, expected_exception=exceptions.BadRequest,
            expected_http_code=400):
        invalid_inst_id = 'invalid-inst-id'
        client = self.auth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.backups.create,
            self.BACKUP_NAME, invalid_inst_id, self.BACKUP_DESC)

    def run_backup_create_instance_not_found(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        client = self.auth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.backups.create,
            self.BACKUP_NAME, generate_uuid(), self.BACKUP_DESC)

    def run_add_data_for_backup(self):
        self.backup_host = self.get_instance_host()
        self.assert_add_data_for_backup(self.backup_host, DataType.large)

    def assert_add_data_for_backup(self, host, data_type):
        """In order for this to work, the corresponding datastore
        'helper' class should implement the 'add_actual_data' method.
        """
        self.test_helper.add_data(data_type, host)
        self.data_types_added.append(data_type)

    def run_verify_data_for_backup(self):
        self.assert_verify_backup_data(self.backup_host, DataType.large)

    def assert_verify_backup_data(self, host, data_type):
        """In order for this to work, the corresponding datastore
        'helper' class should implement the 'verify_actual_data' method.
        """
        self.test_helper.verify_data(data_type, host)

    def run_save_backup_counts(self):
        # Necessary to test that the count increases.
        self.backup_count_prior_to_create = len(
            self.auth_client.backups.list())
        self.backup_count_for_ds_prior_to_create = len(
            self.auth_client.backups.list(
                datastore=self.instance_info.dbaas_datastore))
        self.backup_count_for_instance_prior_to_create = len(
            self.auth_client.instances.backups(self.instance_info.id))

    def run_backup_create(self):
        if self.test_helper.get_valid_database_definitions():
            self.databases_before_backup = self._get_databases(
                self.instance_info.id)
        self.backup_info = self.assert_backup_create(
            self.BACKUP_NAME, self.BACKUP_DESC, self.instance_info.id)

    def _get_databases(self, instance_id):
        return [database.name for database in
                self.auth_client.databases.list(instance_id)]

    def assert_backup_create(self, name, desc, instance_id, parent_id=None,
                             incremental=False):
        client = self.auth_client
        datastore_version = client.datastore_versions.get(
            self.instance_info.dbaas_datastore,
            self.instance_info.dbaas_datastore_version)
        if incremental:
            result = client.backups.create(
                name, instance_id, desc, incremental=incremental)
        else:
            result = client.backups.create(
                name, instance_id, desc, parent_id=parent_id)
        self.assert_equal(name, result.name,
                          'Unexpected backup name')
        self.assert_equal(desc, result.description,
                          'Unexpected backup description')
        self.assert_equal(instance_id, result.instance_id,
                          'Unexpected instance ID for backup')
        self.assert_equal('NEW', result.status,
                          'Unexpected status for backup')
        if parent_id:
            self.assert_equal(parent_id, result.parent_id,
                              'Unexpected status for backup')

        instance = client.instances.get(instance_id)
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
        return result

    def run_restore_instance_from_not_completed_backup(
            self, expected_exception=exceptions.Conflict,
            expected_http_code=409):
        client = self.auth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            None, self._restore_from_backup, client, self.backup_info.id)
        self.assert_client_code(client, expected_http_code)

    def run_instance_action_right_after_backup_create(
            self, expected_exception=exceptions.UnprocessableEntity,
            expected_http_code=422):
        client = self.auth_client
        self.assert_raises(expected_exception, expected_http_code,
                           client, client.instances.resize_instance,
                           self.instance_info.id, 1)

    def run_backup_create_another_backup_running(
            self, expected_exception=exceptions.UnprocessableEntity,
            expected_http_code=422):
        client = self.auth_client
        self.assert_raises(expected_exception, expected_http_code,
                           client, client.backups.create,
                           'backup_test2', self.instance_info.id,
                           'test description2')

    def run_backup_delete_while_backup_running(
            self, expected_exception=exceptions.UnprocessableEntity,
            expected_http_code=422):
        client = self.auth_client
        result = client.backups.list()
        backup = result[0]
        self.assert_raises(expected_exception, expected_http_code,
                           client, client.backups.delete, backup.id)

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

    def run_instance_goes_active(self, expected_states=['BACKUP', 'HEALTHY']):
        self._assert_instance_states(self.instance_info.id, expected_states)

    def run_backup_list(self):
        backup_list = self.auth_client.backups.list()
        self.assert_backup_list(
            backup_list, self.backup_count_prior_to_create + 1)

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
        self.assert_backup_list(
            backup_list, self.backup_count_for_ds_prior_to_create + 1)

    def run_backup_list_filter_datastore_not_found(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        client = self.auth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.backups.list,
            datastore='NOT_FOUND')

    def run_backup_list_for_instance(self):
        backup_list = self.auth_client.instances.backups(
            self.instance_info.id)
        self.assert_backup_list(
            backup_list, self.backup_count_for_instance_prior_to_create + 1)

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
        client = self.unauth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.backups.get, self.backup_info.id)

    def run_add_data_for_inc_backup_1(self):
        self.backup_host = self.get_instance_host()
        self.assert_add_data_for_backup(self.backup_host, DataType.tiny)

    def run_verify_data_for_inc_backup_1(self):
        self.assert_verify_backup_data(self.backup_host, DataType.tiny)

    def run_inc_backup_1(self):
        suffix = '_inc_1'
        self.backup_inc_1_info = self.assert_backup_create(
            self.BACKUP_NAME + suffix, self.BACKUP_DESC + suffix,
            self.instance_info.id, parent_id=self.backup_info.id)

    def run_wait_for_inc_backup_1(self):
        self._verify_backup(self.backup_inc_1_info.id)

    def run_add_data_for_inc_backup_2(self):
        self.backup_host = self.get_instance_host()
        self.assert_add_data_for_backup(self.backup_host, DataType.tiny2)

    def run_verify_data_for_inc_backup_2(self):
        self.assert_verify_backup_data(self.backup_host, DataType.tiny2)

    def run_inc_backup_2(self):
        suffix = '_inc_2'
        self.backup_inc_2_info = self.assert_backup_create(
            self.BACKUP_NAME + suffix, self.BACKUP_DESC + suffix,
            self.instance_info.id, parent_id=self.backup_inc_1_info.id,
            incremental=True)

    def run_wait_for_inc_backup_2(self):
        self._verify_backup(self.backup_inc_2_info.id)

    def run_restore_from_backup(self, expected_http_code=200, suffix=''):
        self.restore_instance_id = self.assert_restore_from_backup(
            self.backup_info.id, suffix=suffix,
            expected_http_code=expected_http_code)

    def assert_restore_from_backup(self, backup_ref, suffix='',
                                   expected_http_code=200):
        client = self.auth_client
        result = self._restore_from_backup(client, backup_ref, suffix=suffix)
        self.assert_client_code(client, expected_http_code)
        self.assert_equal('BUILD', result.status,
                          'Unexpected instance status')
        self.register_debug_inst_ids(result.id)
        return result.id

    def _restore_from_backup(self, client, backup_ref, suffix=''):
        restore_point = {'backupRef': backup_ref}
        result = client.instances.create(
            self.instance_info.name + '_restore' + suffix,
            self.instance_info.dbaas_flavor_href,
            self.instance_info.volume,
            nics=self.instance_info.nics,
            restorePoint=restore_point,
            datastore=self.instance_info.dbaas_datastore,
            datastore_version=self.instance_info.dbaas_datastore_version)
        return result

    def run_restore_from_inc_1_backup(self, expected_http_code=200):
        self.restore_inc_1_instance_id = self.assert_restore_from_backup(
            self.backup_inc_1_info.id, suffix='_inc_1',
            expected_http_code=expected_http_code)

    def run_restore_from_backup_completed(
            self, expected_states=['BUILD', 'HEALTHY']):
        self.assert_restore_from_backup_completed(
            self.restore_instance_id, expected_states)
        self.restore_host = self.get_instance_host(self.restore_instance_id)

    def assert_restore_from_backup_completed(
            self, instance_id, expected_states):
        self._assert_instance_states(instance_id, expected_states)

    def run_restore_from_inc_1_backup_completed(
            self, expected_states=['BUILD', 'HEALTHY']):
        self.assert_restore_from_backup_completed(
            self.restore_inc_1_instance_id, expected_states)
        self.restore_inc_1_host = self.get_instance_host(
            self.restore_inc_1_instance_id)

    def run_verify_data_in_restored_instance(self):
        self.assert_verify_backup_data(self.restore_host, DataType.large)

    def run_verify_databases_in_restored_instance(self):
        self.assert_verify_backup_databases(self.restore_instance_id,
                                            self.databases_before_backup)

    def run_verify_data_in_restored_inc_1_instance(self):
        self.assert_verify_backup_data(self.restore_inc_1_host, DataType.large)
        self.assert_verify_backup_data(self.restore_inc_1_host, DataType.tiny)

    def run_verify_databases_in_restored_inc_1_instance(self):
        self.assert_verify_backup_databases(self.restore_inc_1_instance_id,
                                            self.databases_before_backup)

    def assert_verify_backup_databases(self, instance_id, expected_databases):
        if expected_databases is not None:
            actual = self._get_databases(instance_id)
            self.assert_list_elements_equal(
                expected_databases, actual,
                "Unexpected databases on the restored instance.")
        else:
            raise SkipTest("Datastore does not support databases.")

    def run_delete_restored_instance(self, expected_http_code=202):
        self.assert_delete_restored_instance(
            self.restore_instance_id, expected_http_code)

    def assert_delete_restored_instance(
            self, instance_id, expected_http_code):
        client = self.auth_client
        client.instances.delete(instance_id)
        self.assert_client_code(client, expected_http_code)

    def run_delete_restored_inc_1_instance(self, expected_http_code=202):
        self.assert_delete_restored_instance(
            self.restore_inc_1_instance_id, expected_http_code)

    def run_wait_for_restored_instance_delete(self, expected_state='SHUTDOWN'):
        self.assert_restored_instance_deleted(
            self.restore_instance_id, expected_state)
        self.restore_instance_id = None
        self.restore_host = None

    def assert_restored_instance_deleted(self, instance_id, expected_state):
        self.assert_all_gone(instance_id, expected_state)

    def run_wait_for_restored_inc_1_instance_delete(
            self, expected_state='SHUTDOWN'):
        self.assert_restored_instance_deleted(
            self.restore_inc_1_instance_id, expected_state)
        self.restore_inc_1_instance_id = None
        self.restore_inc_1_host = None

    def run_delete_unknown_backup(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        client = self.auth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.backups.delete,
            'unknown_backup')

    def run_delete_backup_unauthorized_user(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        client = self.unauth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.backups.delete, self.backup_info.id)

    def run_delete_inc_2_backup(self, expected_http_code=202):
        self.assert_delete_backup(
            self.backup_inc_2_info.id, expected_http_code)
        self.backup_inc_2_info = None

    def assert_delete_backup(
            self, backup_id, expected_http_code):
        client = self.auth_client
        client.backups.delete(backup_id)
        self.assert_client_code(client, expected_http_code)
        self._wait_until_backup_is_gone(client, backup_id)

    def _wait_until_backup_is_gone(self, client, backup_id):
        def _backup_is_gone():
            try:
                client.backups.get(backup_id)
                return False
            except exceptions.NotFound:
                return True

        poll_until(_backup_is_gone,
                   time_out=self.TIMEOUT_BACKUP_DELETE)

    def run_delete_backup(self, expected_http_code=202):
        self.assert_delete_backup(self.backup_info.id, expected_http_code)

    def run_check_for_incremental_backup(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        if self.backup_inc_1_info is None:
            raise SkipTest("Incremental Backup not created")
        client = self.auth_client
        self.assert_raises(
            expected_exception, expected_http_code,
            client, client.backups.get,
            self.backup_inc_1_info.id)
        self.backup_inc_1_info = None

    def run_remove_backup_data_from_instance(self):
        for data_type in self.data_types_added:
            self.test_helper.remove_data(data_type, self.backup_host)
        self.data_types_added = []

    def run_check_has_incremental(self):
        self.assert_incremental_exists(self.backup_info.id)

    def assert_incremental_exists(self, parent_id):
        def _backup_with_parent_found():
            backup_list = self.auth_client.backups.list()
            for bkup in backup_list:
                if bkup.parent_id == parent_id:
                    return True

            return False

        poll_until(_backup_with_parent_found, time_out=30)


class RedisBackupRunner(BackupRunner):
    def run_check_has_incremental(self):
        pass
