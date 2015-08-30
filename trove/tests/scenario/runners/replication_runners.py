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

from time import sleep

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
        self.replica_2_host = None

    def run_add_data_for_replication(self):
        self.assert_add_data_for_replication(self.master_host)

    def assert_add_data_for_replication(self, host):
        """In order for this to work, the corresponding datastore
        'helper' class should implement the 'add_small_data' method.
        """
        self.test_helper.add_data(DataType.small, host)

    def run_create_replicas(self, expected_states=['BUILD', 'ACTIVE'],
                            expected_http_code=200):
        self.assert_valid_replication_data(self.master_host)
        master_id = self.instance_info.id
        self.replica_1_id = self.assert_replica_create(
            master_id, 'replica1', expected_states,
            expected_http_code)
        self.replica_2_id = self.assert_replica_create(
            master_id, 'replica2', expected_states,
            expected_http_code)

        self._assert_is_master(master_id,
                               [self.replica_1_id, self.replica_2_id])
        self.replica_1_host = self.get_instance_host(self.replica_1_id)
        self.replica_2_host = self.get_instance_host(self.replica_2_id)
        self.assert_valid_replication_data(self.replica_1_host)
        self.assert_valid_replication_data(self.replica_2_host)

    def assert_valid_replication_data(self, host):
        """In order for this to work, the corresponding datastore
        'helper' class should implement the 'verify_small_data' method.
        """
        self.test_helper.verify_data(DataType.small, host)

    def assert_replica_create(self, master_id, replica_name, expected_states,
                              expected_http_code):
        replica = self.auth_client.instances.create(
            self.instance_info.name + replica_name,
            self.instance_info.dbaas_flavor_href,
            self.instance_info.volume,
            slave_of=master_id)
        replica_id = replica.id

        self.assert_instance_action(replica_id, expected_states,
                                    expected_http_code)

        self._assert_is_master(master_id, [replica_id])
        self._assert_is_replica(replica_id, master_id)

        return replica_id

    def run_add_data_to_replicate(self):
        self.assert_add_data_to_replicate(self.master_host)

    def assert_add_data_to_replicate(self, host):
        """In order for this to work, the corresponding datastore
        'helper' class should implement the 'add_tiny_data' method.
        """
        self.test_helper.add_data(DataType.tiny, host)

    def run_verify_replicated_data(self):
        sleep(30)
        self.assert_verify_replicated_data(self.master_host)
        self.assert_verify_replicated_data(self.replica_1_host)
        self.assert_verify_replicated_data(self.replica_2_host)

    def assert_verify_replicated_data(self, host):
        """In order for this to work, the corresponding datastore
        'helper' class should implement the 'add_tiny_data' method.
        """
        self.test_helper.verify_data(DataType.tiny, host)

    def run_remove_replicated_data(self):
        self.assert_remove_replicated_data(self.master_host)

    def assert_remove_replicated_data(self, host):
        """In order for this to work, the corresponding datastore
        'helper' class should implement the 'remove_tiny_data' method.
        """
        self.test_helper.remove_data(DataType.tiny, host)

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

    def run_swap_replica_master(
            self, expected_states=['PROMOTE', 'ACTIVE'],
            expected_http_code=202):
        self.assert_swap_replica_master(
            self.instance_info.id, self.replica_1_id, expected_states,
            expected_http_code)

    def assert_swap_replica_master(
            self, master_id, replica_id, expected_states, expected_http_code):
        other_replica_ids = self._get_replica_set(master_id)
        other_replica_ids.remove(replica_id)

        # Promote replica
        self.assert_replica_promote(self.replica_1_id, expected_states,
                                    expected_http_code)
        current_replicas = list(master_id)
        current_replicas.extend(other_replica_ids)
        self._assert_is_master(replica_id, current_replicas)
        self._assert_is_replica(master_id, replica_id)
        # Promote the original master
        self.assert_replica_promote(self.instance_info.id, expected_states,
                                    expected_http_code)
        current_replicas = list(replica_id)
        current_replicas.extend(other_replica_ids)
        self._assert_is_master(master_id, current_replicas)
        self._assert_is_replica(replica_id, master_id)

    def assert_replica_promote(self, replica_id, expected_states,
                               expected_http_code):
        replica = self.get_instance(replica_id)
        self.auth_client.instances.promote_to_replica_source(replica)
        self.assert_instance_action(replica_id, expected_states,
                                    expected_http_code)

    def _assert_is_replica(self, instance_id, master_id):
        instance = self.get_instance(instance_id)
        self.assert_client_code(200)
        CheckInstance(instance._info).slave_of()
        self.assert_equal(master_id, instance._info['replica_of']['id'],
                          'Unexpected replication master ID')

    def _assert_is_master(self, instance_id, replica_ids):
        instance = self.get_instance(instance_id)
        self.assert_client_code(200)
        CheckInstance(instance._info).slaves()
        self.assert_is_sublist(replica_ids, self._get_replica_set(instance_id))

    def _get_replica_set(self, master_id):
        instance = self.get_instance(master_id)
        replica_ids = [replica['id'] for replica in instance._info['replicas']]
        self.assert_unique(replica_ids, "Master '%s' has bad replica list"
                           % master_id)
        return replica_ids

    def run_delete_replica_set(self, expected_last_instance_state=['SHUTDOWN'],
                               expected_http_code=202):
        self.assert_delete_replica_set(
            self.instance_info.id, expected_last_instance_state,
            expected_http_code)

    def assert_delete_replica_set(self, master_id,
                                  expected_last_instance_state,
                                  expected_http_code):
        self.report.log("Deleting a replication set: %s" % master_id)
        master = self.get_instance(master_id)
        replicas = self._get_replica_set(master_id)

        instance_ids = zip([master], replicas)
        for instance_id in instance_ids:
            self.auth_client.instances.delete(instance_id)
            self.assert_client_code(expected_http_code)

        self.assert_all_gone(instance_ids, expected_last_instance_state)
