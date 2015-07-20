# Copyright [2015] Hewlett-Packard Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Integration tests for Redis datastore.
APIs tested for Redis are:
1. create
2. restart
3. resize-volume
4. resize-instance
5. delete
6. cluster-create
7. cluster-delete
"""

from proboscis import asserts
from proboscis.decorators import before_class
from proboscis import SkipTest
from proboscis import test
from troveclient.compat import exceptions

from trove.common import cfg
from trove.common.utils import poll_until
from trove.tests.api.instances import EPHEMERAL_SUPPORT
from trove.tests.api.instances import GROUP_START_SIMPLE
from trove.tests.api.instances import instance_info
from trove.tests.api.instances import WaitForGuestInstallationToFinish
from trove.tests.config import CONFIG
from trove.tests.util.check import TypeCheck
from trove.tests.util import create_dbaas_client

CONF = cfg.CONF

REDIS_GROUP = "dbaas.api.redis"
TIMEOUT = 2300
SLEEP_TIME = 60


@test(depends_on_groups=[GROUP_START_SIMPLE], groups=[REDIS_GROUP],
      runs_after=[WaitForGuestInstallationToFinish])
class RedisTest(object):
    """Tests Redis Datastore Features."""

    @before_class
    def setUp(self):
        self.instance = instance_info
        self.rd_client = create_dbaas_client(self.instance.user)
        self.report = CONFIG.get_report()

    def _find_status(self, rd_client, instance_id, expected_status):
        """Tracks instance status, until it gets to expected_status."""
        instance = rd_client.instances.get(instance_id)
        self.report.log("Instance info %s." % instance._info)
        if instance.status == expected_status:
            self.report.log("Instance: %s is ready." % instance_id)
            return True
        else:
            return False

    @test
    def test_instance_restart(self):
        """Tests the restart API."""
        if not getattr(self, 'instance', None):
            raise SkipTest(
                "Skipping this test since instance is not available.")

        self.rd_client = create_dbaas_client(self.instance.user)
        self.rd_client.instances.restart(self.instance.id)

        asserts.assert_equal(202, self.rd_client.last_http_code)
        test_instance = self.rd_client.instances.get(self.instance.id)
        asserts.assert_equal("REBOOT", test_instance.status)

        poll_until(lambda: self._find_status(self.rd_client,
                                             self.instance.id, "ACTIVE"),
                   sleep_time=SLEEP_TIME, time_out=TIMEOUT)
        self.report.log("Restarted Instance: %s." % self.instance.id)

    @test(depends_on=[test_instance_restart], enabled=False)
    def test_instance_resize_volume(self):
        """Tests the resize volume API."""
        old_volume_size = int(instance_info.volume['size'])
        new_volume_size = old_volume_size + 1
        if not getattr(self, 'instance', None):
            raise SkipTest(
                "Skipping this test since instance is not available.")

        self.rd_client = create_dbaas_client(self.instance.user)
        self.rd_client.instances.resize_volume(self.instance.id,
                                               new_volume_size)

        asserts.assert_equal(202, self.rd_client.last_http_code)
        test_instance = self.rd_client.instances.get(self.instance.id)
        asserts.assert_equal("RESIZE", test_instance.status)

        poll_until(lambda: self._find_status(self.rd_client,
                                             self.instance.id, "ACTIVE"),
                   sleep_time=SLEEP_TIME, time_out=TIMEOUT)

        instance = self.rd_client.instances.get(self.instance.id)
        asserts.assert_equal(instance.volume['size'], new_volume_size)
        self.report.log("Resized Volume for Instance ID: %s to %s." % (
            self.instance.id, new_volume_size))

    @test(depends_on=[test_instance_resize_volume])
    def test_instance_resize_flavor(self):
        """Tests the resize instance/flavor API."""

        if EPHEMERAL_SUPPORT:
            flavor_name = CONFIG.values.get('instance_bigger_eph_flavor_name',
                                            'eph.rd-smaller')
        else:
            flavor_name = CONFIG.values.get('instance_bigger_flavor_name',
                                            'm1.small')
        flavors = self.instance.dbaas.find_flavors_by_name(flavor_name)
        new_flavor = flavors[0]

        asserts.assert_true(new_flavor is not None,
                            "Flavor '%s' not found!" % flavor_name)

        if not getattr(self, 'instance', None):
            raise SkipTest(
                "Skipping this test since instance is not available.")

        self.rd_client = create_dbaas_client(self.instance.user)
        self.rd_client.instances.resize_instance(self.instance.id,
                                                 new_flavor.id)

        asserts.assert_equal(202, self.rd_client.last_http_code)
        test_instance = self.rd_client.instances.get(self.instance.id)
        asserts.assert_equal("RESIZE", test_instance.status)

        poll_until(lambda: self._find_status(self.rd_client,
                                             self.instance.id, "ACTIVE"),
                   sleep_time=SLEEP_TIME, time_out=TIMEOUT)

        test_instance = self.rd_client.instances.get(self.instance.id)
        asserts.assert_equal(int(test_instance.flavor['id']), new_flavor.id)
        self.report.log("Resized Flavor for Instance ID: %s to %s." % (
            self.instance.id, new_flavor.id))

    @test(depends_on=[test_instance_resize_flavor])
    def test_instance_delete(self):
        """Tests the instance delete."""
        if not getattr(self, 'instance', None):
            raise SkipTest(
                "Skipping this test since instance is not available.")

        self.rd_client = create_dbaas_client(self.instance.user)
        self.rd_client.instances.delete(self.instance.id)

        asserts.assert_equal(202, self.rd_client.last_http_code)
        test_instance = self.rd_client.instances.get(self.instance.id)
        asserts.assert_equal("SHUTDOWN", test_instance.status)

        def _poll():
            try:
                instance = self.rd_client.instances.get(self.instance.id)
                self.report.log("Instance info %s" % instance._info)
                asserts.assert_equal("SHUTDOWN", instance.status)
                return False
            except exceptions.NotFound:
                self.report.log("Instance has gone.")
                asserts.assert_equal(404, self.rd_client.last_http_code)
                return True

        poll_until(_poll, sleep_time=SLEEP_TIME, time_out=TIMEOUT)
        self.report.log("Deleted Instance ID: %s " % self.instance.id)

    @test(depends_on=[test_instance_delete])
    def test_create_cluster_successfuly(self):
        valid_request_body = [{"flavorRef": self.instance.dbaas_flavor_href,
                              'volume': {'size': 1}}] * 2

        self.cluster = self.rd_client.clusters.create(
            "test_cluster", self.instance.dbaas_datastore,
            self.instance.dbaas_datastore_version,
            instances=valid_request_body)

        with TypeCheck('Cluster', self.cluster) as check:
            check.has_field("id", basestring)
            check.has_field("name", basestring)
            check.has_field("datastore", dict)
            check.has_field("instances", list)
            check.has_field("links", list)
            check.has_field("created", unicode)
            check.has_field("updated", unicode)
            for instance in self.cluster.instances:
                isinstance(instance, dict)
                asserts.assert_is_not_none(instance['id'])
                asserts.assert_is_not_none(instance['links'])
                asserts.assert_is_not_none(instance['name'])
        asserts.assert_equal(200, self.rd_client.last_http_code)

    def _cluster_is_active(self):
        cluster = self.rd_client.clusters.get(self.cluster.id)
        cluster_instances = [
            self.rd_client.instances.get(instance['id'])
            for instance in cluster.instances]
        self.report.log("Cluster info %s." % cluster._info)
        self.report.log("Cluster instances info %s." % cluster_instances)
        if cluster.task['name'] == "NONE":

            if ["ERROR"] * len(cluster_instances) == [
               str(instance.status) for instance in cluster_instances]:
                self.report.log("Cluster provisioning failed.")
                asserts.fail("Cluster provisioning failed.")

            if ["ACTIVE"] * len(cluster_instances) == [
               str(instance.status) for instance in cluster_instances]:
                self.report.log("Cluster is ready.")
                return True
        else:
            asserts.assert_not_equal(
                ["ERROR"] * len(cluster_instances),
                [instance.status
                 for instance in cluster_instances])
        self.report.log("Continue polling, cluster is not ready yet.")

    @test(depends_on=[test_create_cluster_successfuly])
    def test_wait_until_cluster_is_active(self):
        if not getattr(self, 'cluster', None):
            raise SkipTest(
                "Skipping this test since cluster is not available.")

        poll_until(self._cluster_is_active,
                   sleep_time=SLEEP_TIME, time_out=TIMEOUT)
        self.report.log("Created cluster, ID = %s." % self.cluster.id)

    @test(depends_on=[test_wait_until_cluster_is_active])
    def test_cluster_grow(self):

        if not getattr(self, 'cluster', None):
            raise SkipTest(
                "Skipping this test since cluster is not available.")

        beginning_instance_count = len(self.cluster.instances)

        valid_request_body = [
            {"name": "foo", "flavorRef": self.instance.dbaas_flavor_href,
             'volume': {'size': 1}},
            {"name": "bar", "flavorRef": self.instance.dbaas_flavor_href,
             'volume': {'size': 1}}]

        self.cluster = self.rd_client.clusters.grow(self.cluster.id,
                                                    valid_request_body)

        asserts.assert_equal(2, len(self.cluster.instances)
                             - beginning_instance_count)
        asserts.assert_equal(202, self.rd_client.last_http_code)

        poll_until(self._cluster_is_active,
                   sleep_time=SLEEP_TIME, time_out=TIMEOUT)

    @test(depends_on=[test_cluster_grow])
    def test_cluster_shrink(self):

        if not getattr(self, 'cluster', None):
            raise SkipTest(
                "Skipping this test since cluster is not available.")

        foo_instance = None
        for instance in self.cluster.instances:
            if instance['name'] == 'foo':
                foo_instance = instance
                break
        asserts.assert_is_not_none(foo_instance, "Could not find foo instance")

        beginning_instance_count = len(self.cluster.instances)

        valid_request_body = [{"id": foo_instance['id']}]

        self.cluster = self.rd_client.clusters.shrink(self.cluster.id,
                                                      valid_request_body)

        asserts.assert_equal(-1, len(self.cluster.instances)
                             - beginning_instance_count)
        asserts.assert_equal(202, self.rd_client.last_http_code)

        poll_until(self._cluster_is_active,
                   sleep_time=SLEEP_TIME, time_out=TIMEOUT)

    @test(depends_on=[test_create_cluster_successfuly],
          runs_after=[test_cluster_shrink])
    def test_cluster_delete(self):

        if not getattr(self, 'cluster', None):
            raise SkipTest(
                "Skipping this test since cluster is not available.")

        self.rd_client.clusters.delete(self.cluster.id)
        asserts.assert_equal(202, self.rd_client.last_http_code)

        def _poll():
            try:
                cluster = self.rd_client.clusters.get(
                    self.cluster.id)
                self.report.log("Cluster info %s" % cluster._info)
                asserts.assert_equal("DELETING", cluster.task['name'])
                return False
            except exceptions.NotFound:
                self.report.log("Cluster is not available.")
                asserts.assert_equal(404, self.rd_client.last_http_code)
                return True

        poll_until(_poll, sleep_time=SLEEP_TIME, time_out=TIMEOUT)
        self.report.log("Deleted cluster: %s." % self.cluster.id)
