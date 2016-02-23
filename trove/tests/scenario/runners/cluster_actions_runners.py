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

import os

from proboscis import SkipTest
import time as timer

from trove.common import cfg
from trove.common import exception
from trove.common.utils import poll_until
from trove.tests.scenario.helpers.test_helper import DataType
from trove.tests.scenario.runners.test_runners import TestRunner
from trove.tests.util.check import TypeCheck
from troveclient.compat import exceptions


CONF = cfg.CONF


class ClusterActionsRunner(TestRunner):

    USE_CLUSTER_ID_FLAG = 'TESTS_USE_CLUSTER_ID'
    DO_NOT_DELETE_CLUSTER_FLAG = 'TESTS_DO_NOT_DELETE_CLUSTER'

    EXTRA_INSTANCE_NAME = "named_instance"

    def __init__(self):
        super(ClusterActionsRunner, self).__init__()

        self.cluster_id = 0
        self.current_root_creds = None

    @property
    def is_using_existing_cluster(self):
        return self.has_env_flag(self.USE_CLUSTER_ID_FLAG)

    @property
    def has_do_not_delete_cluster(self):
        return self.has_env_flag(self.DO_NOT_DELETE_CLUSTER_FLAG)

    def run_cluster_create(self, num_nodes=None, expected_task_name='BUILDING',
                           expected_instance_states=['BUILD', 'ACTIVE'],
                           expected_http_code=200):
        if not num_nodes:
            num_nodes = self.min_cluster_node_count

        instances_def = [
            self.build_flavor(
                flavor_id=self.instance_info.dbaas_flavor_href,
                volume_size=self.instance_info.volume['size'])] * num_nodes

        self.cluster_id = self.assert_cluster_create(
            'test_cluster', instances_def, expected_task_name,
            expected_instance_states, expected_http_code)

    @property
    def min_cluster_node_count(self):
        return 2

    def assert_cluster_create(
            self, cluster_name, instances_def, expected_task_name,
            expected_instance_states, expected_http_code):
        self.report.log("Testing cluster create: %s" % cluster_name)

        cluster = self.get_existing_cluster()
        if cluster:
            self.report.log("Using an existing cluster: %s" % cluster.id)
            cluster_instances = self._get_cluster_instances(cluster.id)
            self.assert_all_instance_states(
                cluster_instances, expected_instance_states[-1:])
        else:
            cluster = self.auth_client.clusters.create(
                cluster_name, self.instance_info.dbaas_datastore,
                self.instance_info.dbaas_datastore_version,
                instances=instances_def)
            self._assert_cluster_action(cluster.id, expected_task_name,
                                        expected_http_code)
            cluster_instances = self._get_cluster_instances(cluster.id)
            self.assert_all_instance_states(
                cluster_instances, expected_instance_states)
            # Create the helper user/database on the first node.
            # The cluster should handle the replication itself.
            self.create_test_helper_on_instance(cluster_instances[0])

        cluster_id = cluster.id

        # Although all instances have already acquired the expected state,
        # we still need to poll for the final cluster task, because
        # it may take up to the periodic task interval until the task name
        # gets updated in the Trove database.
        self._assert_cluster_states(cluster_id, ['NONE'])
        self._assert_cluster_response(cluster_id, 'NONE')

        return cluster_id

    def get_existing_cluster(self):
        if self.is_using_existing_cluster:
            cluster_id = os.environ.get(self.USE_CLUSTER_ID_FLAG)
            return self.auth_client.clusters.get(cluster_id)

        return None

    def run_cluster_root_enable(self, expected_task_name=None,
                                expected_http_code=200):
        root_credentials = self.test_helper.get_helper_credentials_root()
        self.current_root_creds = self.auth_client.root.create_cluster_root(
            self.cluster_id, root_credentials['password'])
        self.assert_equal(root_credentials['name'],
                          self.current_root_creds[0])
        self.assert_equal(root_credentials['password'],
                          self.current_root_creds[1])
        self._assert_cluster_action(self.cluster_id, expected_task_name,
                                    expected_http_code)

    def run_verify_cluster_root_enable(self):
        if not self.current_root_creds:
            raise SkipTest("Root not enabled.")
        cluster = self.auth_client.clusters.get(self.cluster_id)
        for instance in cluster.instances:
            root_enabled_test = self.auth_client.root.is_instance_root_enabled(
                instance['id'])
            self.assert_true(root_enabled_test.rootEnabled)

        ping_response = self.test_helper.ping(
            cluster.ip[0],
            username=self.current_root_creds[0],
            password=self.current_root_creds[1]
        )
        self.assert_true(ping_response)

    def run_add_initial_cluster_data(self, data_type=DataType.tiny):
        self.assert_add_cluster_data(data_type, self.cluster_id)

    def run_add_extra_cluster_data(self, data_type=DataType.tiny2):
        self.assert_add_cluster_data(data_type, self.cluster_id)

    def assert_add_cluster_data(self, data_type, cluster_id):
        cluster = self.auth_client.clusters.get(cluster_id)
        self.test_helper.add_data(data_type, cluster.ip[0])

    def run_verify_initial_cluster_data(self, data_type=DataType.tiny):
        self.assert_verify_cluster_data(data_type, self.cluster_id)

    def run_verify_extra_cluster_data(self, data_type=DataType.tiny2):
        self.assert_verify_cluster_data(data_type, self.cluster_id)

    def assert_verify_cluster_data(self, data_type, cluster_id):
        cluster = self.auth_client.clusters.get(cluster_id)
        self.test_helper.verify_data(data_type, cluster.ip[0])

    def run_remove_initial_cluster_data(self, data_type=DataType.tiny):
        self.assert_remove_cluster_data(data_type, self.cluster_id)

    def run_remove_extra_cluster_data(self, data_type=DataType.tiny2):
        self.assert_remove_cluster_data(data_type, self.cluster_id)

    def assert_remove_cluster_data(self, data_type, cluster_id):
        cluster = self.auth_client.clusters.get(cluster_id)
        self.test_helper.remove_data(data_type, cluster.ip[0])

    def run_cluster_grow(self, expected_task_name='GROWING_CLUSTER',
                         expected_http_code=202):
        # Add two instances. One with an explicit name.
        added_instance_defs = [
            self._build_instance_def(self.instance_info.dbaas_flavor_href,
                                     self.instance_info.volume['size']),
            self._build_instance_def(self.instance_info.dbaas_flavor_href,
                                     self.instance_info.volume['size'],
                                     self.EXTRA_INSTANCE_NAME)]
        self.assert_cluster_grow(
            self.cluster_id, added_instance_defs, expected_task_name,
            expected_http_code)

    def _build_instance_def(self, flavor_id, volume_size, name=None):
        instance_def = self.build_flavor(
            flavor_id=flavor_id, volume_size=volume_size)
        if name:
            instance_def.update({'name': name})
        return instance_def

    def assert_cluster_grow(self, cluster_id, added_instance_defs,
                            expected_task_name, expected_http_code):
        cluster = self.auth_client.clusters.get(cluster_id)
        initial_instance_count = len(cluster.instances)

        cluster = self.auth_client.clusters.grow(cluster_id,
                                                 added_instance_defs)
        self._assert_cluster_action(cluster_id, expected_task_name,
                                    expected_http_code)

        self.assert_equal(len(added_instance_defs),
                          len(cluster.instances) - initial_instance_count,
                          "Unexpected number of added nodes.")

        cluster_instances = self._get_cluster_instances(cluster_id)
        self.assert_all_instance_states(cluster_instances, ['ACTIVE'])

        self._assert_cluster_states(cluster_id, ['NONE'])
        self._assert_cluster_response(cluster_id, 'NONE')

    def run_cluster_shrink(
            self, expected_task_name=None, expected_http_code=202):
        self.assert_cluster_shrink(self.cluster_id, [self.EXTRA_INSTANCE_NAME],
                                   expected_task_name, expected_http_code)

    def assert_cluster_shrink(self, cluster_id, removed_instance_names,
                              expected_task_name, expected_http_code):
        cluster = self.auth_client.clusters.get(cluster_id)
        initial_instance_count = len(cluster.instances)

        removed_instances = self._find_cluster_instances_by_name(
            cluster, removed_instance_names)

        cluster = self.auth_client.clusters.shrink(
            cluster_id, [{'id': instance['id']}
                         for instance in removed_instances])

        self._assert_cluster_action(cluster_id, expected_task_name,
                                    expected_http_code)

        self._assert_cluster_states(cluster_id, ['NONE'])
        cluster = self.auth_client.clusters.get(cluster_id)
        self.assert_equal(
            len(removed_instance_names),
            initial_instance_count - len(cluster.instances),
            "Unexpected number of removed nodes.")

        cluster_instances = self._get_cluster_instances(cluster_id)
        self.assert_all_instance_states(cluster_instances, ['ACTIVE'])

        self._assert_cluster_response(cluster_id, 'NONE')

    def _find_cluster_instances_by_name(self, cluster, instance_names):
        return [instance for instance in cluster.instances
                if instance['name'] in instance_names]

    def run_cluster_delete(
            self, expected_task_name='DELETING',
            expected_last_instance_state='SHUTDOWN', expected_http_code=202):
        if self.has_do_not_delete_cluster:
            self.report.log("TESTS_DO_NOT_DELETE_CLUSTER=True was "
                            "specified, skipping delete...")
            raise SkipTest("TESTS_DO_NOT_DELETE_CLUSTER was specified.")

        self.assert_cluster_delete(
            self.cluster_id, expected_task_name, expected_last_instance_state,
            expected_http_code)

    def assert_cluster_delete(
            self, cluster_id, expected_task_name, expected_last_instance_state,
            expected_http_code):
        self.report.log("Testing cluster delete: %s" % cluster_id)
        cluster_instances = self._get_cluster_instances(cluster_id)

        self.auth_client.clusters.delete(cluster_id)
        self._assert_cluster_action(cluster_id, expected_task_name,
                                    expected_http_code)

        self.assert_all_gone(cluster_instances, expected_last_instance_state)
        self._assert_cluster_gone(cluster_id)

    def _get_cluster_instances(self, cluster_id):
        cluster = self.auth_client.clusters.get(cluster_id)
        return [self.auth_client.instances.get(instance['id'])
                for instance in cluster.instances]

    def _assert_cluster_action(
            self, cluster_id, expected_state, expected_http_code):
        if expected_http_code is not None:
            self.assert_client_code(expected_http_code)
        if expected_state:
            self._assert_cluster_response(cluster_id, expected_state)

    def _assert_cluster_states(self, cluster_id, expected_states,
                               fast_fail_status=None):
        for status in expected_states:
            start_time = timer.time()
            try:
                poll_until(lambda: self._has_task(
                    cluster_id, status, fast_fail_status=fast_fail_status),
                    sleep_time=self.def_sleep_time,
                    time_out=self.def_timeout)
                self.report.log("Cluster has gone '%s' in %s." %
                                (status, self._time_since(start_time)))
            except exception.PollTimeOut:
                self.report.log(
                    "Status of cluster '%s' did not change to '%s' after %s."
                    % (cluster_id, status, self._time_since(start_time)))
                return False

        return True

    def _has_task(self, cluster_id, task, fast_fail_status=None):
        cluster = self.auth_client.clusters.get(cluster_id)
        task_name = cluster.task['name']
        self.report.log("Waiting for cluster '%s' to become '%s': %s"
                        % (cluster_id, task, task_name))
        if fast_fail_status and task_name == fast_fail_status:
            raise RuntimeError("Cluster '%s' acquired a fast-fail task: %s"
                               % (cluster_id, task))
        return task_name == task

    def _assert_cluster_response(self, cluster_id, expected_state):
        cluster = self.auth_client.clusters.get(cluster_id)
        with TypeCheck('Cluster', cluster) as check:
            check.has_field("id", basestring)
            check.has_field("name", basestring)
            check.has_field("datastore", dict)
            check.has_field("instances", list)
            check.has_field("links", list)
            check.has_field("created", unicode)
            check.has_field("updated", unicode)
            for instance in cluster.instances:
                isinstance(instance, dict)
                self.assert_is_not_none(instance['id'])
                self.assert_is_not_none(instance['links'])
                self.assert_is_not_none(instance['name'])
        self.assert_equal(expected_state, cluster.task['name'],
                          'Unexpected cluster task name')

    def _assert_cluster_gone(self, cluster_id):
        t0 = timer.time()
        try:
            # This will poll until the cluster goes away.
            self._assert_cluster_states(cluster_id, ['NONE'])
            self.fail(
                "Cluster '%s' still existed after %s seconds."
                % (cluster_id, self._time_since(t0)))
        except exceptions.NotFound:
            self.assert_client_code(404)


class CassandraClusterActionsRunner(ClusterActionsRunner):

    def run_cluster_root_enable(self):
        raise SkipTest("Operation is currently not supported.")


class MariadbClusterActionsRunner(ClusterActionsRunner):

    @property
    def min_cluster_node_count(self):
        return self.get_datastore_config_property('min_cluster_member_count')

    def run_cluster_root_enable(self):
        raise SkipTest("Operation is currently not supported.")


class PxcClusterActionsRunner(ClusterActionsRunner):

    @property
    def min_cluster_node_count(self):
        return self.get_datastore_config_property('min_cluster_member_count')


class VerticaClusterActionsRunner(ClusterActionsRunner):

    @property
    def min_cluster_node_count(self):
        return self.get_datastore_config_property('cluster_member_count')


class RedisClusterActionsRunner(ClusterActionsRunner):

    def run_cluster_root_enable(self):
        raise SkipTest("Operation is currently not supported.")


class MongodbClusterActionsRunner(ClusterActionsRunner):

    def run_cluster_root_enable(self):
        raise SkipTest("Operation is currently not supported.")
