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

from trove.common import utils
from trove.tests.api.instances import CheckInstance
from trove.tests.scenario.helpers.test_helper import DataType
from trove.tests.scenario.runners.test_runners import TestRunner
from troveclient.compat import exceptions


class ReplicationRunner(TestRunner):

    def __init__(self):
        super(ReplicationRunner, self).__init__()

        self.master_id = self.instance_info.id
        self.replica_1_id = 0
        self.replica_2_id = 0
        self.master_host = self.get_instance_host(self.master_id)
        self.replica_1_host = None
        self.master_backup_count = None
        self.used_data_sets = set()

    def run_add_data_for_replication(self, data_type=DataType.small):
        self.assert_add_replication_data(data_type, self.master_host)

    def assert_add_replication_data(self, data_type, host):
        """In order for this to work, the corresponding datastore
        'helper' class should implement the 'add_<data_type>_data' method.
        """
        self.test_helper.add_data(data_type, host)
        self.used_data_sets.add(data_type)

    def run_verify_data_for_replication(self, data_type=DataType.small):
        self.assert_verify_replication_data(data_type, self.master_host)

    def assert_verify_replication_data(self, data_type, host):
        """In order for this to work, the corresponding datastore
        'helper' class should implement the 'verify_<data_type>_data' method.
        """
        self.test_helper.verify_data(data_type, host)

    def run_create_single_replica(self, expected_states=['BUILD', 'ACTIVE'],
                                  expected_http_code=200):
        master_id = self.instance_info.id
        self.master_backup_count = len(
            self.auth_client.instances.backups(master_id))
        self.replica_1_id = self.assert_replica_create(
            master_id, 'replica1', 1, expected_states, expected_http_code)
        self.replica_1_host = self.get_instance_host(self.replica_1_id)

    def assert_replica_create(
            self, master_id, replica_name, replica_count,
            expected_states, expected_http_code):
        replica = self.auth_client.instances.create(
            self.instance_info.name + replica_name,
            self.instance_info.dbaas_flavor_href,
            self.instance_info.volume, replica_of=master_id,
            nics=self.instance_info.nics,
            replica_count=replica_count)
        replica_id = replica.id

        self.assert_instance_action(replica_id, expected_states,
                                    expected_http_code)
        self._assert_is_master(master_id, [replica_id])
        self._assert_is_replica(replica_id, master_id)
        return replica_id

    def _assert_is_master(self, instance_id, replica_ids):
        instance = self.get_instance(instance_id)
        self.assert_client_code(200)
        CheckInstance(instance._info).slaves()
        self.assert_true(
            set(replica_ids).issubset(self._get_replica_set(instance_id)))

    def _get_replica_set(self, master_id):
        instance = self.get_instance(master_id)
        return set([replica['id'] for replica in instance._info['replicas']])

    def _assert_is_replica(self, instance_id, master_id):
        instance = self.get_instance(instance_id)
        self.assert_client_code(200)
        CheckInstance(instance._info).replica_of()
        self.assert_equal(master_id, instance._info['replica_of']['id'],
                          'Unexpected replication master ID')

    def run_create_multiple_replicas(self, expected_states=['BUILD', 'ACTIVE'],
                                     expected_http_code=200):
        master_id = self.instance_info.id
        self.replica_2_id = self.assert_replica_create(
            master_id, 'replica2', 2, expected_states, expected_http_code)

    def run_add_data_to_replicate(self):
        self.assert_add_replication_data(DataType.tiny, self.master_host)

    def run_verify_data_to_replicate(self):
        self.assert_verify_replication_data(DataType.tiny, self.master_host)

    def run_wait_for_data_to_replicate(self):
        self.test_helper.wait_for_replicas()

    def run_verify_replica_data_orig(self):
        self.assert_verify_replica_data(self.instance_info.id, DataType.small)

    def assert_verify_replica_data(self, master_id, data_type):
        replica_ids = self._get_replica_set(master_id)
        for replica_id in replica_ids:
            replica_instance = self.get_instance(replica_id)
            host = str(replica_instance._info['ip'][0])
            self.report.log("Checking data on host %s" % host)
            self.assert_verify_replication_data(data_type, host)

    def run_verify_replica_data_new(self):
        self.assert_verify_replica_data(self.instance_info.id, DataType.tiny)

    def run_promote_master(self, expected_exception=exceptions.BadRequest,
                           expected_http_code=400):
        self.assert_raises(
            expected_exception, expected_http_code,
            self.auth_client.instances.promote_to_replica_source,
            self.instance_info.id)

    def run_eject_replica(self, expected_exception=exceptions.BadRequest,
                          expected_http_code=400):
        self.assert_raises(
            expected_exception, expected_http_code,
            self.auth_client.instances.eject_replica_source,
            self.replica_1_id)

    def run_eject_valid_master(self, expected_exception=exceptions.BadRequest,
                               expected_http_code=400):
        self.assert_raises(
            expected_exception, expected_http_code,
            self.auth_client.instances.eject_replica_source,
            self.instance_info.id)

    def run_delete_valid_master(self, expected_exception=exceptions.Forbidden,
                                expected_http_code=403):
        self.assert_raises(
            expected_exception, expected_http_code,
            self.auth_client.instances.delete,
            self.instance_info.id)

    def run_promote_to_replica_source(self,
                                      expected_states=['PROMOTE', 'ACTIVE'],
                                      expected_http_code=202):
        self.assert_promote_to_replica_source(
            self.replica_1_id, self.instance_info.id, expected_states,
            expected_http_code)

    def assert_promote_to_replica_source(
            self, new_master_id, old_master_id,
            expected_states, expected_http_code):
        original_replica_ids = self._get_replica_set(old_master_id)
        other_replica_ids = list(original_replica_ids)
        other_replica_ids.remove(new_master_id)

        # Promote replica
        self.assert_replica_promote(new_master_id, expected_states,
                                    expected_http_code)
        current_replica_ids = list(other_replica_ids)
        current_replica_ids.append(old_master_id)
        self._assert_is_master(new_master_id, current_replica_ids)
        self._assert_is_replica(old_master_id, new_master_id)

    def assert_replica_promote(
            self, new_master_id, expected_states, expected_http_code):
        self.auth_client.instances.promote_to_replica_source(new_master_id)
        self.assert_instance_action(new_master_id, expected_states,
                                    expected_http_code)

    def run_add_data_to_replicate2(self):
        self.assert_add_replication_data(DataType.tiny2, self.replica_1_host)

    def run_verify_data_to_replicate2(self):
        self.assert_verify_replication_data(DataType.tiny2,
                                            self.replica_1_host)

    def run_verify_replica_data_new2(self):
        self.assert_verify_replica_data(self.replica_1_id, DataType.tiny2)

    def run_promote_original_source(self,
                                    expected_states=['PROMOTE', 'ACTIVE'],
                                    expected_http_code=202):
        self.assert_promote_to_replica_source(
            self.instance_info.id, self.replica_1_id, expected_states,
            expected_http_code)

    def run_remove_replicated_data(self):
        self.assert_remove_replicated_data(self.master_host)

    def assert_remove_replicated_data(self, host):
        """In order for this to work, the corresponding datastore
        'helper' class should implement the 'remove_<type>_data' method.
        """
        for data_set in self.used_data_sets:
            self.report.log("Removing replicated data set: %s" % data_set)
            self.test_helper.remove_data(data_set, host)

    def run_detach_replica_from_source(self,
                                       expected_states=['ACTIVE'],
                                       expected_http_code=202):
        self.assert_detach_replica_from_source(
            self.instance_info.id, self.replica_1_id,
            expected_states, expected_http_code)

    def assert_detach_replica_from_source(
            self, master_id, replica_id, expected_states,
            expected_http_code):
        other_replica_ids = self._get_replica_set(master_id)
        other_replica_ids.remove(replica_id)

        self.assert_detach_replica(
            replica_id, expected_states, expected_http_code)

        self._assert_is_master(master_id, other_replica_ids)
        self._assert_is_not_replica(replica_id, master_id)

    def assert_detach_replica(
            self, replica_id, expected_states, expected_http_code):
        self.auth_client.instances.edit(replica_id,
                                        detach_replica_source=True)
        self.assert_instance_action(
            replica_id, expected_states, expected_http_code)

    def _assert_is_not_replica(self, instance_id, master_id):
        try:
            self._assert_is_replica(instance_id, master_id)
            self.fail("Non-replica '%s' is still replica of '%s'" %
                      (instance_id, master_id))
        except AssertionError:
            pass

    def run_delete_detached_replica(self,
                                    expected_last_state=['SHUTDOWN'],
                                    expected_http_code=202):
        self.assert_delete_instances(
            self.replica_1_id, expected_last_state=expected_last_state,
            expected_http_code=expected_http_code)

    def assert_delete_instances(
            self, instance_ids, expected_last_state, expected_http_code):
        instance_ids = (instance_ids if utils.is_collection(instance_ids)
                        else [instance_ids])
        for instance_id in instance_ids:
            self.auth_client.instances.delete(instance_id)
            self.assert_client_code(expected_http_code)

        self.assert_all_gone(instance_ids, expected_last_state)

    def run_delete_all_replicas(self, expected_last_state=['SHUTDOWN'],
                                expected_http_code=202):
        self.assert_delete_all_replicas(
            self.instance_info.id, expected_last_state,
            expected_http_code)

    def assert_delete_all_replicas(
            self, master_id, expected_last_state, expected_http_code):
        self.report.log("Deleting a replication set: %s" % master_id)
        replica_ids = self._get_replica_set(master_id)
        self.assert_delete_instances(replica_ids, expected_last_state,
                                     expected_http_code)

    def run_test_backup_deleted(self):
        backup = self.auth_client.instances.backups(self.master_id)
        self.assert_equal(self.master_backup_count, len(backup))
