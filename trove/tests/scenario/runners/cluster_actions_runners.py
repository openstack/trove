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

import time as timer

from trove.tests.scenario.runners.test_runners import TestRunner
from trove.tests.util.check import TypeCheck
from troveclient.compat import exceptions


class ClusterActionsRunner(TestRunner):

    def __init__(self):
        super(ClusterActionsRunner, self).__init__()

        self.cluster_id = 0

    def run_cluster_create(
            self, num_nodes=2, expected_instance_states=['BUILD', 'ACTIVE'],
            expected_http_code=200):
        instances_def = [
            self.build_flavor(
                flavor_id=self.instance_info.dbaas_flavor_href,
                volume_size=self.instance_info.volume['size'])] * num_nodes

        self.cluster_id = self.assert_cluster_create(
            'test_cluster', instances_def,
            expected_instance_states,
            expected_http_code)

    def assert_cluster_create(self, cluster_name, instances_def,
                              expected_instance_states, expected_http_code):
        self.report.log("Testing cluster create: %s" % cluster_name)
        cluster = self.auth_client.clusters.create(
            cluster_name, self.instance_info.dbaas_datastore,
            self.instance_info.dbaas_datastore_version,
            instances=instances_def)
        cluster_id = cluster.id

        self._assert_cluster_action(cluster_id, 'BUILDING', expected_http_code)

        cluster_instances = self._get_cluster_instances(cluster_id)
        self.assert_all_instance_states(
            cluster_instances, expected_instance_states)

        self._assert_cluster_state(cluster_id, 'NONE')

        return cluster_id

    def run_cluster_delete(
            self, expected_last_instance_state='SHUTDOWN',
            expected_http_code=202):
        self.assert_cluster_delete(
            self.cluster_id, expected_last_instance_state, expected_http_code)

    def assert_cluster_delete(self, cluster_id, expected_last_instance_state,
                              expected_http_code):
        self.report.log("Testing cluster delete: %s" % cluster_id)
        cluster_instances = self._get_cluster_instances(cluster_id)

        self.auth_client.clusters.delete(cluster_id)
        self._assert_cluster_action(cluster_id, 'DELETING', expected_http_code)

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
            self._assert_cluster_state(cluster_id, expected_state)

    def _assert_cluster_state(self, cluster_id, expected_state):
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
            self.auth_client.clusters.get(cluster_id)
            self.fail(
                "Cluster '%s' still existed after %s seconds."
                % (cluster_id, self._time_since(t0)))
        except exceptions.NotFound:
            self.assert_client_code(404)


class MongodbClusterActionsRunner(ClusterActionsRunner):

    def run_cluster_create(self, num_nodes=3,
                           expected_instance_states=['BUILD', 'ACTIVE'],
                           expected_http_code=200):
        super(MongodbClusterActionsRunner, self).run_cluster_create(
            num_nodes=num_nodes,
            expected_instance_states=expected_instance_states,
            expected_http_code=expected_http_code)
