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

import json
import os

from proboscis import SkipTest
import six
import time as timer

from trove.common import exception
from trove.common.utils import poll_until
from trove.tests.scenario.helpers.test_helper import DataType
from trove.tests.scenario import runners
from trove.tests.scenario.runners.test_runners import SkipKnownBug
from trove.tests.scenario.runners.test_runners import TestRunner
from trove.tests.util.check import TypeCheck
from troveclient.compat import exceptions


class ClusterRunner(TestRunner):

    USE_CLUSTER_ID_FLAG = 'TESTS_USE_CLUSTER_ID'
    DO_NOT_DELETE_CLUSTER_FLAG = 'TESTS_DO_NOT_DELETE_CLUSTER'

    EXTRA_INSTANCE_NAME = "named_instance"

    def __init__(self):
        super(ClusterRunner, self).__init__()

        self.cluster_name = 'test_cluster'
        self.cluster_id = 0
        self.cluster_inst_ids = None
        self.cluster_count_before_create = None
        self.srv_grp_id = None
        self.current_root_creds = None
        self.locality = 'affinity'
        self.initial_instance_count = None
        self.cluster_instances = None
        self.cluster_removed_instances = None
        self.active_config_group_id = None
        self.config_requires_restart = False
        self.initial_group_id = None
        self.dynamic_group_id = None
        self.non_dynamic_group_id = None

    @property
    def is_using_existing_cluster(self):
        return self.has_env_flag(self.USE_CLUSTER_ID_FLAG)

    @property
    def has_do_not_delete_cluster(self):
        return self.has_env_flag(self.DO_NOT_DELETE_CLUSTER_FLAG)

    @property
    def min_cluster_node_count(self):
        return 2

    def run_initial_configuration_create(self, expected_http_code=200):
        group_id, requires_restart = self.create_initial_configuration(
            expected_http_code)
        if group_id:
            self.initial_group_id = group_id
            self.config_requires_restart = requires_restart
        else:
            raise SkipTest("No groups defined.")

    def run_cluster_create(self, num_nodes=None, expected_task_name='BUILDING',
                           expected_http_code=200):
        self.cluster_count_before_create = len(
            self.auth_client.clusters.list())
        if not num_nodes:
            num_nodes = self.min_cluster_node_count

        instance_flavor = self.get_instance_flavor()

        instance_defs = [
            self.build_flavor(
                flavor_id=self.get_flavor_href(instance_flavor),
                volume_size=self.instance_info.volume['size'])
            for count in range(0, num_nodes)]
        types = self.test_helper.get_cluster_types()
        for index, instance_def in enumerate(instance_defs):
            instance_def['nics'] = self.instance_info.nics
            if types and index < len(types):
                instance_def['type'] = types[index]

        self.cluster_id = self.assert_cluster_create(
            self.cluster_name, instance_defs, self.locality,
            self.initial_group_id, expected_task_name, expected_http_code)

    def assert_cluster_create(
            self, cluster_name, instances_def, locality, configuration,
            expected_task_name, expected_http_code):

        self.report.log("Testing cluster create: %s" % cluster_name)

        client = self.auth_client
        cluster = self.get_existing_cluster()
        if cluster:
            self.report.log("Using an existing cluster: %s" % cluster.id)
        else:
            cluster = client.clusters.create(
                cluster_name, self.instance_info.dbaas_datastore,
                self.instance_info.dbaas_datastore_version,
                instances=instances_def, locality=locality,
                configuration=configuration)
            self.assert_client_code(client, expected_http_code)
            self.active_config_group_id = configuration
            self._assert_cluster_values(cluster, expected_task_name)
            for instance in cluster.instances:
                self.register_debug_inst_ids(instance['id'])
        return cluster.id

    def run_cluster_create_wait(self,
                                expected_instance_states=['BUILD', 'HEALTHY']):

        self.assert_cluster_create_wait(
            self.cluster_id, expected_instance_states=expected_instance_states)

    def assert_cluster_create_wait(
            self, cluster_id, expected_instance_states):
        client = self.auth_client
        cluster_instances = self._get_cluster_instances(client, cluster_id)
        self.assert_all_instance_states(
            cluster_instances, expected_instance_states)
        # Create the helper user/database on the first node.
        # The cluster should handle the replication itself.
        if not self.get_existing_cluster():
            self.create_test_helper_on_instance(cluster_instances[0])

        # Although all instances have already acquired the expected state,
        # we still need to poll for the final cluster task, because
        # it may take up to the periodic task interval until the task name
        # gets updated in the Trove database.
        self._assert_cluster_states(client, cluster_id, ['NONE'])

        # make sure the server_group was created
        self.cluster_inst_ids = [inst.id for inst in cluster_instances]
        for id in self.cluster_inst_ids:
            srv_grp_id = self.assert_server_group_exists(id)
            if self.srv_grp_id and self.srv_grp_id != srv_grp_id:
                self.fail("Found multiple server groups for cluster")
            self.srv_grp_id = srv_grp_id

    def get_existing_cluster(self):
        if self.is_using_existing_cluster:
            cluster_id = os.environ.get(self.USE_CLUSTER_ID_FLAG)
            return self.auth_client.clusters.get(cluster_id)

    def run_cluster_list(self, expected_http_code=200):

        self.assert_cluster_list(
            self.cluster_count_before_create + 1,
            expected_http_code)

    def assert_cluster_list(self, expected_count, expected_http_code):
        client = self.auth_client
        count = len(client.clusters.list())
        self.assert_client_code(client, expected_http_code)
        self.assert_equal(expected_count, count, "Unexpected cluster count")

    def run_cluster_show(self, expected_http_code=200,
                         expected_task_name='NONE'):
        self.assert_cluster_show(
            self.cluster_id, expected_task_name, expected_http_code)

    def run_cluster_restart(self, expected_http_code=202,
                            expected_task_name='RESTARTING_CLUSTER'):
        self.assert_cluster_restart(
            self.cluster_id, expected_task_name, expected_http_code)

    def assert_cluster_restart(
            self, cluster_id, expected_task_name, expected_http_code):
        client = self.auth_client
        client.clusters.restart(cluster_id)
        self.assert_client_code(client, expected_http_code)
        self._assert_cluster_response(
            client, cluster_id, expected_task_name)

    def run_cluster_restart_wait(self):
        self.assert_cluster_restart_wait(self.cluster_id)

    def assert_cluster_restart_wait(self, cluster_id):
        client = self.auth_client
        cluster_instances = self._get_cluster_instances(
            client, cluster_id)
        self.assert_all_instance_states(
            cluster_instances, ['REBOOT', 'HEALTHY'])

        self._assert_cluster_states(
            client, cluster_id, ['NONE'])
        self._assert_cluster_response(
            client, cluster_id, 'NONE')

    def assert_cluster_show(self, cluster_id, expected_task_name,
                            expected_http_code):
        self._assert_cluster_response(self.auth_client,
                                      cluster_id, expected_task_name)

    def run_cluster_root_enable(self, expected_task_name=None,
                                expected_http_code=200):
        root_credentials = self.test_helper.get_helper_credentials_root()
        if not root_credentials or not root_credentials.get('name'):
            raise SkipTest("No root credentials provided.")
        client = self.auth_client
        self.current_root_creds = client.root.create_cluster_root(
            self.cluster_id, root_credentials['password'])
        self.assert_client_code(client, expected_http_code)
        self._assert_cluster_response(
            client, self.cluster_id, expected_task_name)
        self.assert_equal(root_credentials['name'],
                          self.current_root_creds[0])
        self.assert_equal(root_credentials['password'],
                          self.current_root_creds[1])

    def run_verify_cluster_root_enable(self):
        if not self.current_root_creds:
            raise SkipTest("Root not enabled.")
        cluster = self.auth_client.clusters.get(self.cluster_id)
        for instance in cluster.instances:
            root_enabled_test = self.auth_client.root.is_instance_root_enabled(
                instance['id'])
            self.assert_true(root_enabled_test.rootEnabled)

        for ipv4 in self.extract_ipv4s(cluster.ip):
            self.report.log("Pinging cluster as superuser via node: %s" % ipv4)
            ping_response = self.test_helper.ping(
                ipv4,
                username=self.current_root_creds[0],
                password=self.current_root_creds[1])
            self.assert_true(ping_response)

    def run_add_initial_cluster_data(self, data_type=DataType.tiny):
        self.assert_add_cluster_data(data_type, self.cluster_id)

    def assert_add_cluster_data(self, data_type, cluster_id):
        cluster = self.auth_client.clusters.get(cluster_id)
        self.test_helper.add_data(data_type, self.extract_ipv4s(cluster.ip)[0])

    def run_verify_initial_cluster_data(self, data_type=DataType.tiny):
        self.assert_verify_cluster_data(data_type, self.cluster_id)

    def assert_verify_cluster_data(self, data_type, cluster_id):
        cluster = self.auth_client.clusters.get(cluster_id)
        for ipv4 in self.extract_ipv4s(cluster.ip):
            self.report.log("Verifying cluster data via node: %s" % ipv4)
            self.test_helper.verify_data(data_type, ipv4)

    def run_remove_initial_cluster_data(self, data_type=DataType.tiny):
        self.assert_remove_cluster_data(data_type, self.cluster_id)

    def assert_remove_cluster_data(self, data_type, cluster_id):
        cluster = self.auth_client.clusters.get(cluster_id)
        self.test_helper.remove_data(
            data_type, self.extract_ipv4s(cluster.ip)[0])

    def run_cluster_grow(self, expected_task_name='GROWING_CLUSTER',
                         expected_http_code=202):
        # Add two instances. One with an explicit name.
        flavor_href = self.get_flavor_href(self.get_instance_flavor())
        added_instance_defs = [
            self._build_instance_def(flavor_href,
                                     self.instance_info.volume['size']),
            self._build_instance_def(flavor_href,
                                     self.instance_info.volume['size'],
                                     self.EXTRA_INSTANCE_NAME)]
        types = self.test_helper.get_cluster_types()
        if types and types[0]:
            added_instance_defs[0]['type'] = types[0]

        self.assert_cluster_grow(
            self.cluster_id, added_instance_defs, expected_task_name,
            expected_http_code)

    def _build_instance_def(self, flavor_id, volume_size, name=None):
        instance_def = self.build_flavor(
            flavor_id=flavor_id, volume_size=volume_size)
        if name:
            instance_def.update({'name': name})
        instance_def.update({'nics': self.instance_info.nics})
        return instance_def

    def assert_cluster_grow(self, cluster_id, added_instance_defs,
                            expected_task_name, expected_http_code):
        client = self.auth_client
        cluster = client.clusters.get(cluster_id)
        initial_instance_count = len(cluster.instances)

        cluster = client.clusters.grow(cluster_id, added_instance_defs)
        self.assert_client_code(client, expected_http_code)
        self._assert_cluster_response(client, cluster_id, expected_task_name)

        self.assert_equal(len(added_instance_defs),
                          len(cluster.instances) - initial_instance_count,
                          "Unexpected number of added nodes.")

    def run_cluster_grow_wait(self):
        self.assert_cluster_grow_wait(self.cluster_id)

    def assert_cluster_grow_wait(self, cluster_id):
        client = self.auth_client
        cluster_instances = self._get_cluster_instances(client, cluster_id)
        self.assert_all_instance_states(cluster_instances, ['HEALTHY'])

        self._assert_cluster_states(client, cluster_id, ['NONE'])
        self._assert_cluster_response(client, cluster_id, 'NONE')

    def run_add_grow_cluster_data(self, data_type=DataType.tiny2):
        self.assert_add_cluster_data(data_type, self.cluster_id)

    def run_verify_grow_cluster_data(self, data_type=DataType.tiny2):
        self.assert_verify_cluster_data(data_type, self.cluster_id)

    def run_remove_grow_cluster_data(self, data_type=DataType.tiny2):
        self.assert_remove_cluster_data(data_type, self.cluster_id)

    def run_cluster_upgrade(self, expected_task_name='UPGRADING_CLUSTER',
                            expected_http_code=202):
        self.assert_cluster_upgrade(self.cluster_id,
                                    expected_task_name, expected_http_code)

    def assert_cluster_upgrade(self, cluster_id,
                               expected_task_name, expected_http_code):
        client = self.auth_client
        cluster = client.clusters.get(cluster_id)
        self.initial_instance_count = len(cluster.instances)

        client.clusters.upgrade(
            cluster_id, self.instance_info.dbaas_datastore_version)
        self.assert_client_code(client, expected_http_code)
        self._assert_cluster_response(client, cluster_id, expected_task_name)

    def run_cluster_upgrade_wait(self):
        self.assert_cluster_upgrade_wait(
            self.cluster_id,
            expected_last_instance_states=['HEALTHY']
        )

    def assert_cluster_upgrade_wait(self, cluster_id,
                                    expected_last_instance_states):
        client = self.auth_client
        self._assert_cluster_states(client, cluster_id, ['NONE'])
        cluster_instances = self._get_cluster_instances(client, cluster_id)
        self.assert_equal(
            self.initial_instance_count,
            len(cluster_instances),
            "Unexpected number of instances after upgrade.")
        self.assert_all_instance_states(cluster_instances,
                                        expected_last_instance_states)
        self._assert_cluster_response(client, cluster_id, 'NONE')

    def run_add_upgrade_cluster_data(self, data_type=DataType.tiny3):
        self.assert_add_cluster_data(data_type, self.cluster_id)

    def run_verify_upgrade_cluster_data(self, data_type=DataType.tiny3):
        self.assert_verify_cluster_data(data_type, self.cluster_id)

    def run_remove_upgrade_cluster_data(self, data_type=DataType.tiny3):
        self.assert_remove_cluster_data(data_type, self.cluster_id)

    def run_cluster_shrink(self, expected_task_name='SHRINKING_CLUSTER',
                           expected_http_code=202):
        self.assert_cluster_shrink(self.auth_client,
                                   self.cluster_id, [self.EXTRA_INSTANCE_NAME],
                                   expected_task_name, expected_http_code)

    def assert_cluster_shrink(self, client, cluster_id, removed_instance_names,
                              expected_task_name, expected_http_code):
        cluster = client.clusters.get(cluster_id)
        self.initial_instance_count = len(cluster.instances)

        self.cluster_removed_instances = (
            self._find_cluster_instances_by_name(
                cluster, removed_instance_names))

        client.clusters.shrink(
            cluster_id, [{'id': instance.id}
                         for instance in self.cluster_removed_instances])

        self.assert_client_code(client, expected_http_code)
        self._assert_cluster_response(client, cluster_id, expected_task_name)

    def _find_cluster_instances_by_name(self, cluster, instance_names):
        return [self.auth_client.instances.get(instance['id'])
                for instance in cluster.instances
                if instance['name'] in instance_names]

    def run_cluster_shrink_wait(self):
        self.assert_cluster_shrink_wait(
            self.cluster_id, expected_last_instance_state='SHUTDOWN')

    def assert_cluster_shrink_wait(self, cluster_id,
                                   expected_last_instance_state):
        client = self.auth_client
        self._assert_cluster_states(client, cluster_id, ['NONE'])
        cluster = client.clusters.get(cluster_id)
        self.assert_equal(
            len(self.cluster_removed_instances),
            self.initial_instance_count - len(cluster.instances),
            "Unexpected number of removed nodes.")

        cluster_instances = self._get_cluster_instances(client, cluster_id)
        self.assert_all_instance_states(cluster_instances, ['HEALTHY'])
        self.assert_all_gone(self.cluster_removed_instances,
                             expected_last_instance_state)
        self._assert_cluster_response(client, cluster_id, 'NONE')

    def run_add_shrink_cluster_data(self, data_type=DataType.tiny4):
        self.assert_add_cluster_data(data_type, self.cluster_id)

    def run_verify_shrink_cluster_data(self, data_type=DataType.tiny4):
        self.assert_verify_cluster_data(data_type, self.cluster_id)

    def run_remove_shrink_cluster_data(self, data_type=DataType.tiny4):
        self.assert_remove_cluster_data(data_type, self.cluster_id)

    def run_cluster_delete(
            self, expected_task_name='DELETING', expected_http_code=202):
        if self.has_do_not_delete_cluster:
            self.report.log("TESTS_DO_NOT_DELETE_CLUSTER=True was "
                            "specified, skipping delete...")
            raise SkipTest("TESTS_DO_NOT_DELETE_CLUSTER was specified.")

        self.assert_cluster_delete(
            self.cluster_id, expected_http_code)

    def assert_cluster_delete(self, cluster_id, expected_http_code):
        self.report.log("Testing cluster delete: %s" % cluster_id)
        client = self.auth_client
        self.cluster_instances = self._get_cluster_instances(client,
                                                             cluster_id)

        client.clusters.delete(cluster_id)
        self.assert_client_code(client, expected_http_code)

    def _get_cluster_instances(self, client, cluster_id):
        cluster = client.clusters.get(cluster_id)
        return [client.instances.get(instance['id'])
                for instance in cluster.instances]

    def run_cluster_delete_wait(
            self, expected_task_name='DELETING',
            expected_last_instance_state='SHUTDOWN'):
        if self.has_do_not_delete_cluster:
            self.report.log("TESTS_DO_NOT_DELETE_CLUSTER=True was "
                            "specified, skipping delete wait...")
            raise SkipTest("TESTS_DO_NOT_DELETE_CLUSTER was specified.")

        self.assert_cluster_delete_wait(
            self.cluster_id, expected_task_name, expected_last_instance_state)

    def assert_cluster_delete_wait(
            self, cluster_id, expected_task_name,
            expected_last_instance_state):
        client = self.auth_client
        # Since the server_group is removed right at the beginning of the
        # cluster delete process we can't check for locality anymore.
        self._assert_cluster_response(client, cluster_id, expected_task_name,
                                      check_locality=False)

        self.assert_all_gone(self.cluster_instances,
                             expected_last_instance_state)
        self._assert_cluster_gone(client, cluster_id)
        # make sure the server group is gone too
        self.assert_server_group_gone(self.srv_grp_id)

    def _assert_cluster_states(self, client, cluster_id, expected_states,
                               fast_fail_status=None):
        for status in expected_states:
            start_time = timer.time()
            try:
                poll_until(
                    lambda: self._has_task(
                        client, cluster_id, status,
                        fast_fail_status=fast_fail_status),
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

    def _has_task(self, client, cluster_id, task, fast_fail_status=None):
        cluster = client.clusters.get(cluster_id)
        task_name = cluster.task['name']
        self.report.log("Waiting for cluster '%s' to become '%s': %s"
                        % (cluster_id, task, task_name))
        if fast_fail_status and task_name == fast_fail_status:
            raise RuntimeError("Cluster '%s' acquired a fast-fail task: %s"
                               % (cluster_id, task))
        return task_name == task

    def _assert_cluster_response(self, client, cluster_id, expected_task_name,
                                 check_locality=True):
        cluster = client.clusters.get(cluster_id)
        self._assert_cluster_values(cluster, expected_task_name,
                                    check_locality=check_locality)

    def _assert_cluster_values(self, cluster, expected_task_name,
                               check_locality=True):
        with TypeCheck('Cluster', cluster) as check:
            check.has_field("id", six.string_types)
            check.has_field("name", six.string_types)
            check.has_field("datastore", dict)
            check.has_field("instances", list)
            check.has_field("links", list)
            check.has_field("created", six.text_type)
            check.has_field("updated", six.text_type)
            if check_locality:
                check.has_field("locality", six.text_type)
            if self.active_config_group_id:
                check.has_field("configuration", six.text_type)
            for instance in cluster.instances:
                isinstance(instance, dict)
                self.assert_is_not_none(instance['id'])
                self.assert_is_not_none(instance['links'])
                self.assert_is_not_none(instance['name'])
        self.assert_equal(expected_task_name, cluster.task['name'],
                          'Unexpected cluster task name')
        if check_locality:
            self.assert_equal(self.locality, cluster.locality,
                              "Unexpected cluster locality")

    def _assert_cluster_gone(self, client, cluster_id):
        t0 = timer.time()
        try:
            # This will poll until the cluster goes away.
            self._assert_cluster_states(client, cluster_id, ['NONE'])
            self.fail(
                "Cluster '%s' still existed after %s seconds."
                % (cluster_id, self._time_since(t0)))
        except exceptions.NotFound:
            self.assert_client_code(client, 404)

    def restart_after_configuration_change(self):
        if self.config_requires_restart:
            self.run_cluster_restart()
            self.run_cluster_restart_wait()
            self.config_requires_restart = False
        else:
            raise SkipTest("Not required.")

    def run_create_dynamic_configuration(self, expected_http_code=200):
        values = self.test_helper.get_dynamic_group()
        if values:
            self.dynamic_group_id = self.assert_create_group(
                'dynamic_cluster_test_group',
                'a fully dynamic group should not require restart',
                values, expected_http_code)
        elif values is None:
            raise SkipTest("No dynamic group defined in %s." %
                           self.test_helper.get_class_name())
        else:
            raise SkipTest("Datastore has no dynamic configuration values.")

    def assert_create_group(self, name, description, values,
                            expected_http_code):
        json_def = json.dumps(values)
        client = self.auth_client
        result = client.configurations.create(
            name,
            json_def,
            description,
            datastore=self.instance_info.dbaas_datastore,
            datastore_version=self.instance_info.dbaas_datastore_version)
        self.assert_client_code(client, expected_http_code)

        return result.id

    def run_create_non_dynamic_configuration(self, expected_http_code=200):
        values = self.test_helper.get_non_dynamic_group()
        if values:
            self.non_dynamic_group_id = self.assert_create_group(
                'non_dynamic_cluster_test_group',
                'a group containing non-dynamic properties should always '
                'require restart',
                values, expected_http_code)
        elif values is None:
            raise SkipTest("No non-dynamic group defined in %s." %
                           self.test_helper.get_class_name())
        else:
            raise SkipTest("Datastore has no non-dynamic configuration "
                           "values.")

    def run_attach_dynamic_configuration(
            self, expected_states=['NONE'],
            expected_http_code=202):
        if self.dynamic_group_id:
            self.assert_attach_configuration(
                self.cluster_id, self.dynamic_group_id, expected_states,
                expected_http_code)

    def assert_attach_configuration(
            self, cluster_id, group_id, expected_states, expected_http_code,
            restart_inst=False):
        client = self.auth_client
        client.clusters.configuration_attach(cluster_id, group_id)
        self.assert_client_code(client, expected_http_code)
        self.active_config_group_id = group_id
        self._assert_cluster_states(client, cluster_id, expected_states)
        self.assert_configuration_group(client, cluster_id, group_id)

        if restart_inst:
            self.config_requires_restart = True
            cluster_instances = self._get_cluster_instances(cluster_id)
            for node in cluster_instances:
                self.assert_equal(
                    'RESTART_REQUIRED', node.status,
                    "Node '%s' should be in 'RESTART_REQUIRED' state."
                    % node.id)

    def assert_configuration_group(
            self, client, cluster_id, expected_group_id):
        cluster = client.clusters.get(cluster_id)
        self.assert_equal(
            expected_group_id, cluster.configuration,
            "Attached group does not have the expected ID.")

        cluster_instances = self._get_cluster_instances(client, cluster_id)
        for node in cluster_instances:
            self.assert_equal(
                expected_group_id, cluster.configuration,
                "Attached group does not have the expected ID on "
                "cluster node: %s" % node.id)

    def run_attach_non_dynamic_configuration(
            self, expected_states=['NONE'],
            expected_http_code=202):
        if self.non_dynamic_group_id:
            self.assert_attach_configuration(
                self.cluster_id, self.non_dynamic_group_id,
                expected_states, expected_http_code, restart_inst=True)

    def run_verify_initial_configuration(self):
        if self.initial_group_id:
            self.verify_configuration(self.cluster_id, self.initial_group_id)

    def verify_configuration(self, cluster_id, expected_group_id):
        self.assert_configuration_group(cluster_id, expected_group_id)
        self.assert_configuration_values(cluster_id, expected_group_id)

    def assert_configuration_values(self, cluster_id, group_id):
        if group_id == self.initial_group_id:
            if not self.config_requires_restart:
                expected_configs = self.test_helper.get_dynamic_group()
            else:
                expected_configs = self.test_helper.get_non_dynamic_group()
        if group_id == self.dynamic_group_id:
            expected_configs = self.test_helper.get_dynamic_group()
        elif group_id == self.non_dynamic_group_id:
            expected_configs = self.test_helper.get_non_dynamic_group()

        self._assert_configuration_values(cluster_id, expected_configs)

    def _assert_configuration_values(self, cluster_id, expected_configs):
        cluster_instances = self._get_cluster_instances(cluster_id)
        for node in cluster_instances:
            host = self.get_instance_host(node)
            self.report.log(
                "Verifying cluster configuration via node: %s" % host)
            for name, value in expected_configs.items():
                actual = self.test_helper.get_configuration_value(name, host)
                self.assert_equal(str(value), str(actual),
                                  "Unexpected value of property '%s'" % name)

    def run_verify_dynamic_configuration(self):
        if self.dynamic_group_id:
            self.verify_configuration(self.cluster_id, self.dynamic_group_id)

    def run_verify_non_dynamic_configuration(self):
        if self.non_dynamic_group_id:
            self.verify_configuration(
                self.cluster_id, self.non_dynamic_group_id)

    def run_detach_initial_configuration(self, expected_states=['NONE'],
                                         expected_http_code=202):
        if self.initial_group_id:
            self.assert_detach_configuration(
                self.cluster_id, expected_states, expected_http_code,
                restart_inst=self.config_requires_restart)

    def run_detach_dynamic_configuration(self, expected_states=['NONE'],
                                         expected_http_code=202):
        if self.dynamic_group_id:
            self.assert_detach_configuration(
                self.cluster_id, expected_states, expected_http_code)

    def assert_detach_configuration(
            self, cluster_id, expected_states, expected_http_code,
            restart_inst=False):
        client = self.auth_client
        client.clusters.configuration_detach(cluster_id)
        self.assert_client_code(client, expected_http_code)
        self.active_config_group_id = None
        self._assert_cluster_states(client, cluster_id, expected_states)
        cluster = client.clusters.get(cluster_id)
        self.assert_false(
            hasattr(cluster, 'configuration'),
            "Configuration group was not detached from the cluster.")

        cluster_instances = self._get_cluster_instances(client, cluster_id)
        for node in cluster_instances:
            self.assert_false(
                hasattr(node, 'configuration'),
                "Configuration group was not detached from cluster node: %s"
                % node.id)

        if restart_inst:
            self.config_requires_restart = True
            cluster_instances = self._get_cluster_instances(client, cluster_id)
            for node in cluster_instances:
                self.assert_equal(
                    'RESTART_REQUIRED', node.status,
                    "Node '%s' should be in 'RESTART_REQUIRED' state."
                    % node.id)

    def run_detach_non_dynamic_configuration(
            self, expected_states=['NONE'],
            expected_http_code=202):
        if self.non_dynamic_group_id:
            self.assert_detach_configuration(
                self.cluster_id, expected_states, expected_http_code,
                restart_inst=True)

    def run_delete_initial_configuration(self, expected_http_code=202):
        if self.initial_group_id:
            self.assert_group_delete(self.initial_group_id, expected_http_code)

    def assert_group_delete(self, group_id, expected_http_code):
        client = self.auth_client
        client.configurations.delete(group_id)
        self.assert_client_code(client, expected_http_code)

    def run_delete_dynamic_configuration(self, expected_http_code=202):
        if self.dynamic_group_id:
            self.assert_group_delete(self.dynamic_group_id, expected_http_code)

    def run_delete_non_dynamic_configuration(self, expected_http_code=202):
        if self.non_dynamic_group_id:
            self.assert_group_delete(self.non_dynamic_group_id,
                                     expected_http_code)


class CassandraClusterRunner(ClusterRunner):

    def run_cluster_root_enable(self):
        raise SkipTest("Operation is currently not supported.")


class MariadbClusterRunner(ClusterRunner):

    @property
    def min_cluster_node_count(self):
        return self.get_datastore_config_property('min_cluster_member_count')


class MongodbClusterRunner(ClusterRunner):

    @property
    def min_cluster_node_count(self):
        return 3

    def run_cluster_delete(self, expected_task_name='NONE',
                           expected_http_code=202):
        raise SkipKnownBug(runners.BUG_STOP_DB_IN_CLUSTER)


class PxcClusterRunner(ClusterRunner):

    @property
    def min_cluster_node_count(self):
        return self.get_datastore_config_property('min_cluster_member_count')


class RedisClusterRunner(ClusterRunner):

    # Since Redis runs all the shrink code in the API server, the call
    # will not return until the task name has been set back to 'NONE' so
    # we can't check it.
    def run_cluster_shrink(self, expected_task_name='NONE',
                           expected_http_code=202):
        return super(RedisClusterRunner, self).run_cluster_shrink(
            expected_task_name=expected_task_name,
            expected_http_code=expected_http_code)


class VerticaClusterRunner(ClusterRunner):

    @property
    def min_cluster_node_count(self):
        return self.get_datastore_config_property('cluster_member_count')
