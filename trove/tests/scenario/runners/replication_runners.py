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
from trove.tests.scenario.helpers.test_helper import DataType
from trove.tests.scenario import runners
from trove.tests.scenario.runners.test_runners import CheckInstance
from trove.tests.scenario.runners.test_runners import SkipKnownBug
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
        self.non_affinity_master_id = None
        self.non_affinity_srv_grp_id = None
        self.non_affinity_repl_id = None
        self.locality = 'affinity'

    def run_add_data_for_replication(self, data_type=DataType.small):
        self.assert_add_replication_data(data_type, self.master_host)

    def assert_add_replication_data(self, data_type, host):
        """In order for this to work, the corresponding datastore
        'helper' class should implement the 'add_actual_data' method.
        """
        self.test_helper.add_data(data_type, host)
        self.used_data_sets.add(data_type)

    def run_add_data_after_replica(self, data_type=DataType.micro):
        self.assert_add_replication_data(data_type, self.master_host)

    def run_verify_data_for_replication(self, data_type=DataType.small):
        self.assert_verify_replication_data(data_type, self.master_host)

    def assert_verify_replication_data(self, data_type, host):
        """In order for this to work, the corresponding datastore
        'helper' class should implement the 'verify_actual_data' method.
        """
        self.test_helper.verify_data(data_type, host)

    def run_create_non_affinity_master(self, expected_http_code=200):
        self.non_affinity_master_id = self.auth_client.instances.create(
            self.instance_info.name + '_non-affinity',
            self.instance_info.dbaas_flavor_href,
            self.instance_info.volume,
            datastore=self.instance_info.dbaas_datastore,
            datastore_version=self.instance_info.dbaas_datastore_version,
            nics=self.instance_info.nics,
            locality='anti-affinity').id
        self.assert_client_code(expected_http_code, client=self.auth_client)

    def run_create_single_replica(self, expected_http_code=200):
        self.master_backup_count = len(
            self.auth_client.instances.backups(self.master_id))
        self.replica_1_id = self.assert_replica_create(
            self.master_id, 'replica1', 1, expected_http_code)

    def assert_replica_create(
            self, master_id, replica_name, replica_count, expected_http_code):
        replica = self.auth_client.instances.create(
            self.instance_info.name + '_' + replica_name,
            self.instance_info.dbaas_flavor_href,
            self.instance_info.volume, replica_of=master_id,
            datastore=self.instance_info.dbaas_datastore,
            datastore_version=self.instance_info.dbaas_datastore_version,
            nics=self.instance_info.nics,
            replica_count=replica_count)
        self.assert_client_code(expected_http_code, client=self.auth_client)
        return replica.id

    def run_wait_for_single_replica(self, expected_states=['BUILD', 'ACTIVE']):
        self.assert_instance_action(self.replica_1_id, expected_states)
        self._assert_is_master(self.master_id, [self.replica_1_id])
        self._assert_is_replica(self.replica_1_id, self.master_id)
        self._assert_locality(self.master_id)
        self.replica_1_host = self.get_instance_host(self.replica_1_id)

    def _assert_is_master(self, instance_id, replica_ids):
        instance = self.get_instance(instance_id, client=self.admin_client)
        self.assert_client_code(200, client=self.admin_client)
        CheckInstance(instance._info).slaves()
        self.assert_true(
            set(replica_ids).issubset(self._get_replica_set(instance_id)))
        self._validate_master(instance_id)

    def _get_replica_set(self, master_id):
        instance = self.get_instance(master_id)
        return set([replica['id'] for replica in instance._info['replicas']])

    def _assert_is_replica(self, instance_id, master_id):
        instance = self.get_instance(instance_id, client=self.admin_client)
        self.assert_client_code(200, client=self.admin_client)
        CheckInstance(instance._info).replica_of()
        self.assert_equal(master_id, instance._info['replica_of']['id'],
                          'Unexpected replication master ID')
        self._validate_replica(instance_id)

    def _assert_locality(self, instance_id):
        replica_ids = self._get_replica_set(instance_id)
        instance = self.get_instance(instance_id)
        self.assert_equal(self.locality, instance.locality,
                          "Unexpected locality for instance '%s'" %
                          instance_id)
        for replica_id in replica_ids:
            replica = self.get_instance(replica_id)
            self.assert_equal(self.locality, replica.locality,
                              "Unexpected locality for instance '%s'" %
                              replica_id)

    def run_wait_for_non_affinity_master(self,
                                         expected_states=['BUILD', 'ACTIVE']):
        self._assert_instance_states(self.non_affinity_master_id,
                                     expected_states)
        self.non_affinity_srv_grp_id = self.assert_server_group_exists(
            self.non_affinity_master_id)

    def run_create_non_affinity_replica(self, expected_http_code=200):
        self.non_affinity_repl_id = self.auth_client.instances.create(
            self.instance_info.name + '_non-affinity-repl',
            self.instance_info.dbaas_flavor_href,
            self.instance_info.volume,
            datastore=self.instance_info.dbaas_datastore,
            datastore_version=self.instance_info.dbaas_datastore_version,
            nics=self.instance_info.nics,
            replica_of=self.non_affinity_master_id,
            replica_count=1).id
        self.assert_client_code(expected_http_code, client=self.auth_client)

    def run_create_multiple_replicas(self, expected_http_code=200):
        self.replica_2_id = self.assert_replica_create(
            self.master_id, 'replica2', 2, expected_http_code)

    def run_wait_for_multiple_replicas(
            self, expected_states=['BUILD', 'ACTIVE']):
        replica_ids = self._get_replica_set(self.master_id)
        self.report.log("Waiting for replicas: %s" % replica_ids)
        self.assert_instance_action(replica_ids, expected_states)
        self._assert_is_master(self.master_id, replica_ids)
        for replica_id in replica_ids:
            self._assert_is_replica(replica_id, self.master_id)
        self._assert_locality(self.master_id)

    def run_wait_for_non_affinity_replica_fail(
            self, expected_states=['BUILD', 'ERROR']):
        self._assert_instance_states(self.non_affinity_repl_id,
                                     expected_states,
                                     fast_fail_status=['ACTIVE'])

    def run_delete_non_affinity_repl(self, expected_http_code=202):
        self.assert_delete_instances(
            self.non_affinity_repl_id, expected_http_code=expected_http_code)

    def assert_delete_instances(self, instance_ids, expected_http_code):
        instance_ids = (instance_ids if utils.is_collection(instance_ids)
                        else [instance_ids])
        for instance_id in instance_ids:
            self.auth_client.instances.delete(instance_id)
            self.assert_client_code(expected_http_code,
                                    client=self.auth_client)

    def run_wait_for_delete_non_affinity_repl(
            self, expected_last_status=['SHUTDOWN']):
        self.assert_all_gone([self.non_affinity_repl_id],
                             expected_last_status=expected_last_status)

    def run_delete_non_affinity_master(self, expected_http_code=202):
        self.assert_delete_instances(
            self.non_affinity_master_id, expected_http_code=expected_http_code)

    def run_wait_for_delete_non_affinity_master(
            self, expected_last_status=['SHUTDOWN']):
        self.assert_all_gone([self.non_affinity_master_id],
                             expected_last_status=expected_last_status)
        self.assert_server_group_gone(self.non_affinity_srv_grp_id)

    def run_add_data_to_replicate(self):
        self.assert_add_replication_data(DataType.tiny, self.master_host)

    def run_verify_data_to_replicate(self):
        self.assert_verify_replication_data(DataType.tiny, self.master_host)

    def run_verify_replica_data_orig(self):
        self.assert_verify_replica_data(self.instance_info.id, DataType.small)

    def assert_verify_replica_data(self, master_id, data_type):
        replica_ids = self._get_replica_set(master_id)
        for replica_id in replica_ids:
            host = self.get_instance_host(replica_id)
            self.report.log("Checking data on host %s" % host)
            self.assert_verify_replication_data(data_type, host)

    def run_verify_replica_data_after_single(self):
        self.assert_verify_replica_data(self.instance_info.id, DataType.micro)

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
        # self.assert_raises(
        #     expected_exception, expected_http_code,
        #     self.auth_client.instances.eject_replica_source,
        #     self.instance_info.id)
        # Uncomment once BUG_EJECT_VALID_MASTER is fixed
        raise SkipKnownBug(runners.BUG_EJECT_VALID_MASTER)

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

    def run_verify_replica_data_new_master(self):
        self.assert_verify_replication_data(
            DataType.small, self.replica_1_host)
        self.assert_verify_replication_data(
            DataType.tiny, self.replica_1_host)

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

    def run_add_final_data_to_replicate(self):
        self.assert_add_replication_data(DataType.tiny3, self.master_host)

    def run_verify_data_to_replicate_final(self):
        self.assert_verify_replication_data(DataType.tiny3, self.master_host)

    def run_verify_final_data_replicated(self):
        self.assert_verify_replica_data(self.master_id, DataType.tiny3)

    def run_remove_replicated_data(self):
        self.assert_remove_replicated_data(self.master_host)

    def assert_remove_replicated_data(self, host):
        """In order for this to work, the corresponding datastore
        'helper' class should implement the 'remove_actual_data' method.
        """
        for data_set in self.used_data_sets:
            self.report.log("Removing replicated data set: %s" % data_set)
            self.test_helper.remove_data(data_set, host)

    def run_detach_replica_from_source(self,
                                       expected_states=['DETACH', 'ACTIVE'],
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
        self._assert_is_not_replica(replica_id)

    def assert_detach_replica(
            self, replica_id, expected_states, expected_http_code):
        self.auth_client.instances.edit(replica_id,
                                        detach_replica_source=True)
        self.assert_instance_action(
            replica_id, expected_states, expected_http_code)

    def _assert_is_not_replica(self, instance_id):
        instance = self.get_instance(instance_id, client=self.admin_client)
        self.assert_client_code(200, client=self.admin_client)

        if 'replica_of' not in instance._info:
            try:
                self._validate_replica(instance_id)
                self.fail("The instance is still configured as a replica "
                          "after detached: %s" % instance_id)
            except AssertionError:
                pass
        else:
            self.fail("Unexpected replica_of ID.")

    def run_delete_detached_replica(self, expected_http_code=202):
        self.assert_delete_instances(
            self.replica_1_id, expected_http_code=expected_http_code)

    def run_delete_all_replicas(self, expected_http_code=202):
        self.assert_delete_all_replicas(
            self.instance_info.id, expected_http_code)

    def assert_delete_all_replicas(
            self, master_id, expected_http_code):
        self.report.log("Deleting a replication set: %s" % master_id)
        replica_ids = self._get_replica_set(master_id)
        self.assert_delete_instances(replica_ids, expected_http_code)

    def run_wait_for_delete_replicas(
            self, expected_last_status=['SHUTDOWN']):
        replica_ids = self._get_replica_set(self.master_id)
        replica_ids.add(self.replica_1_id)
        self.assert_all_gone(replica_ids,
                             expected_last_status=expected_last_status)

    def run_test_backup_deleted(self):
        backup = self.auth_client.instances.backups(self.master_id)
        self.assert_equal(self.master_backup_count, len(backup))

    def run_cleanup_master_instance(self):
        pass

    def _validate_master(self, instance_id):
        """This method is intended to be overridden by each
        datastore as needed. It is to be used for any database
        specific master instance validation.
        """
        pass

    def _validate_replica(self, instance_id):
        """This method is intended to be overridden by each
        datastore as needed. It is to be used for any database
        specific replica instance validation.
        """
        pass


class MysqlReplicationRunner(ReplicationRunner):

    def run_cleanup_master_instance(self):
        for user in self.auth_client.users.list(self.master_id):
            if user.name.startswith("slave_"):
                self.auth_client.users.delete(self.master_id, user.name,
                                              user.host)

    def _validate_master(self, instance_id):
        """For Mysql validate that the master has its
        binlog_format set to MIXED.
        """
        host = self.get_instance_host(instance_id)
        self._validate_binlog_fmt(instance_id, host)

    def _validate_replica(self, instance_id):
        """For Mysql validate that any replica has its
        binlog_format set to MIXED and it is in read_only
        mode.
        """
        host = self.get_instance_host(instance_id)
        self._validate_binlog_fmt(instance_id, host)
        self._validate_read_only(instance_id, host)

    def _validate_binlog_fmt(self, instance_id, host):
        binlog_fmt = self.test_helper.get_configuration_value('binlog_format',
                                                              host)
        self.assert_equal(self._get_expected_binlog_format(), binlog_fmt,
                          'Wrong binlog format detected for %s' % instance_id)

    def _get_expected_binlog_format(self):
        return 'MIXED'

    def _validate_read_only(self, instance_id, host):
        read_only = self.test_helper.get_configuration_value('read_only',
                                                             host)
        self.assert_equal('ON', read_only, 'Wrong read only mode detected '
                          'for %s' % instance_id)


class PerconaReplicationRunner(MysqlReplicationRunner):
    pass


class MariadbReplicationRunner(MysqlReplicationRunner):

    def _get_expected_binlog_format(self):
        return 'STATEMENT'
