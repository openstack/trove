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
Integration tests for PXC datastore.
APIs tested for PXC are:
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

from trove.common.utils import poll_until
from trove.tests.api.instances import GROUP_START_SIMPLE
from trove.tests.api.instances import instance_info
from trove.tests.api.instances import WaitForGuestInstallationToFinish
from trove.tests.config import CONFIG
from trove.tests.util.check import TypeCheck
from trove.tests.util import create_dbaas_client

PXC_GROUP = "dbaas.api.pxc"
TIMEOUT = 2300
SLEEP_TIME = 60


@test(depends_on_groups=[GROUP_START_SIMPLE], groups=[PXC_GROUP],
      runs_after=[WaitForGuestInstallationToFinish])
class PXCTest(object):
    """Tests PXC Datastore Features."""

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

    @test(depends_on=[test_instance_restart])
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

        flavor_name = CONFIG.values.get('instance_bigger_flavor_name',
                                        'm1.medium')
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
    def test_create_cluster_with_fewer_instances(self):
        invalid_request_body_with_few_instances = [
            {"flavorRef": 2, "volume": {"size": 1}}]

        self.rd_client = create_dbaas_client(self.instance.user)

        asserts.assert_raises(
            exceptions.BadRequest,
            self.rd_client.clusters.create,
            "test_cluster",
            self.instance.dbaas_datastore,
            self.instance.dbaas_datastore_version,
            instances=invalid_request_body_with_few_instances)

        asserts.assert_equal(400, self.rd_client.last_http_code)

    @test(depends_on=[test_create_cluster_with_fewer_instances])
    def test_create_cluster_with_different_flavors(self):
        invalid_request_body_with_different_flavors = [
            {"flavorRef": 3, "volume": {"size": 1}},
            {"flavorRef": 4, "volume": {"size": 1}}]

        asserts.assert_raises(
            exceptions.BadRequest,
            self.rd_client.clusters.create,
            "test_cluster",
            self.instance.dbaas_datastore,
            self.instance.dbaas_datastore_version,
            instances=invalid_request_body_with_different_flavors)

        asserts.assert_equal(400, self.rd_client.last_http_code)

    @test(depends_on=[test_create_cluster_with_different_flavors])
    def test_create_cluster_with_different_volumes(self):
        invalid_request_body_with_different_volumes = [
            {"flavorRef": 2, "volume": {"size": 2}},
            {"flavorRef": 2, "volume": {"size": 3}}]

        asserts.assert_raises(
            exceptions.BadRequest,
            self.rd_client.clusters.create,
            "test_cluster",
            self.instance.dbaas_datastore,
            self.instance.dbaas_datastore_version,
            instances=invalid_request_body_with_different_volumes)

        asserts.assert_equal(400, self.rd_client.last_http_code)

    @test(depends_on=[test_create_cluster_with_different_volumes])
    def test_create_cluster_successfuly(self):
        valid_request_body = [
            {"flavorRef": self.instance.dbaas_flavor_href,
             "volume": self.instance.volume},
            {"flavorRef": self.instance.dbaas_flavor_href,
             "volume": self.instance.volume}]

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

    @test(depends_on=[test_create_cluster_successfuly])
    def test_wait_until_cluster_is_active(self):
        if not getattr(self, 'cluster', None):
            raise SkipTest(
                "Skipping this test since cluster is not available.")

        def result_is_active():
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

        poll_until(result_is_active, sleep_time=SLEEP_TIME, time_out=TIMEOUT)
        self.report.log("Created cluster, ID = %s." % self.cluster.id)

    @test(depends_on=[test_wait_until_cluster_is_active])
    def test_cluster_communication(self):
        databases = []
        databases.append({"name": 'somenewdb'})
        cluster = self.rd_client.clusters.get(self.cluster.id)
        cluster_instances = [
            self.rd_client.instances.get(instance['id'])
            for instance in cluster.instances]
        databases_before = self.rd_client.databases.list(
            cluster_instances[0].id)
        self.rd_client.databases.create(cluster_instances[0].id,
                                        databases)
        for instance in cluster_instances:
            databases_after = self.rd_client.databases.list(
                cluster_instances[0].id)
            asserts.assert_true(len(databases_before) < len(databases_after))

    @test(depends_on=[test_wait_until_cluster_is_active],
          runs_after=[test_cluster_communication])
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
