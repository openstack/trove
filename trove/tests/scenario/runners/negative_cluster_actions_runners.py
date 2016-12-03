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

from trove.tests.scenario.runners.test_runners import TestRunner
from troveclient.compat import exceptions


class NegativeClusterActionsRunner(TestRunner):

    def __init__(self):
        super(NegativeClusterActionsRunner, self).__init__()

    def run_create_constrained_size_cluster(self, min_nodes=2, max_nodes=None,
                                            expected_http_code=400):
        self.assert_create_constrained_size_cluster('negative_cluster',
                                                    min_nodes, max_nodes,
                                                    expected_http_code)

    def assert_create_constrained_size_cluster(self, cluster_name,
                                               min_nodes, max_nodes,
                                               expected_http_code):
        # Create a cluster with less than 'min_nodes'.
        if min_nodes:
            instances_def = [self.build_flavor()] * (min_nodes - 1)
            self._assert_cluster_create_raises(cluster_name, instances_def,
                                               expected_http_code)

        # Create a cluster with mare than 'max_nodes'.
        if max_nodes:
            instances_def = [self.build_flavor()] * (max_nodes + 1)
            self._assert_cluster_create_raises(cluster_name, instances_def,
                                               expected_http_code)

    def run_create_heterogeneous_cluster(self, expected_http_code=400):
        # Create a cluster with different node flavors.
        instances_def = [self.build_flavor(flavor_id=2, volume_size=1),
                         self.build_flavor(flavor_id=3, volume_size=1)]
        self._assert_cluster_create_raises('heterocluster',
                                           instances_def, expected_http_code)

        # Create a cluster with different volume sizes.
        instances_def = [self.build_flavor(flavor_id=2, volume_size=1),
                         self.build_flavor(flavor_id=2, volume_size=2)]
        self._assert_cluster_create_raises('heterocluster',
                                           instances_def, expected_http_code)

    def _assert_cluster_create_raises(self, cluster_name, instances_def,
                                      expected_http_code):
        client = self.auth_client
        self.assert_raises(exceptions.BadRequest, expected_http_code,
                           client, client.clusters.create,
                           cluster_name,
                           self.instance_info.dbaas_datastore,
                           self.instance_info.dbaas_datastore_version,
                           instances=instances_def)


class MongodbNegativeClusterActionsRunner(NegativeClusterActionsRunner):

    def run_create_constrained_size_cluster(self):
        super(NegativeClusterActionsRunner,
              self).run_create_constrained_size_cluster(min_nodes=3,
                                                        max_nodes=3)


class CassandraNegativeClusterActionsRunner(NegativeClusterActionsRunner):

    def run_create_constrained_size_cluster(self):
        raise SkipTest("No constraints apply to the number of cluster nodes.")

    def run_create_heterogeneous_cluster(self):
        raise SkipTest("No constraints apply to the size of cluster nodes.")


class RedisNegativeClusterActionsRunner(NegativeClusterActionsRunner):

    def run_create_constrained_size_cluster(self):
        raise SkipTest("No constraints apply to the number of cluster nodes.")

    def run_create_heterogeneous_cluster(self):
        raise SkipTest("No constraints apply to the size of cluster nodes.")


class PxcNegativeClusterActionsRunner(NegativeClusterActionsRunner):

    def run_create_constrained_size_cluster(self):
        raise SkipTest("No constraints apply to the number of cluster nodes.")
