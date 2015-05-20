#    Copyright 2013 OpenStack LLC
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

from proboscis.asserts import assert_not_equal
from proboscis.asserts import assert_raises
from proboscis.asserts import assert_true
from proboscis import before_class
from proboscis.check import Check
from proboscis import test
from troveclient.compat import exceptions

from trove.tests.api.instances import create_new_instance
from trove.tests.api.instances import CreateInstance
from trove.tests.config import CONFIG
from trove.tests import DBAAS_API
from trove.tests import INSTANCES
from trove.tests import PRE_INSTANCES
from trove.tests.util import create_dbaas_client
from trove.tests.util.users import Requirements

GROUP = "dbaas.api.mgmt.hosts"


def percent_boundary(used_ram, total_ram):
    """Return a upper and lower bound for percent ram used."""
    calc = int((1.0 * used_ram / total_ram) * 100)
    # return calculated percent +/- 2 to account for rounding errors
    lower_boundary = calc - 2
    upper_boundary = calc + 2
    return lower_boundary, upper_boundary


@test(groups=[DBAAS_API, GROUP, PRE_INSTANCES],
      depends_on_groups=["services.initialize"],
      enabled=create_new_instance())
class HostsBeforeInstanceCreation(object):

    @before_class
    def setUp(self):
        self.user = CONFIG.users.find_user(Requirements(is_admin=True))
        self.client = create_dbaas_client(self.user)
        self.host = None

    @test
    def test_empty_index_host_list(self):
        host_index_result = self.client.hosts.index()
        assert_not_equal(host_index_result, None,
                         "list hosts call should not be empty: %s" %
                         str(host_index_result))
        assert_true(len(host_index_result) > 0,
                    "list hosts length should be greater than zero: %r" %
                    host_index_result)

        self.host = host_index_result[0]
        assert_true(self.host is not None, "Expected to find a host.")

    @test(depends_on=[test_empty_index_host_list])
    def test_empty_index_host_list_single(self):
        self.host.name = self.host.name.replace(".", "\.")
        result = self.client.hosts.get(self.host)
        assert_not_equal(result, None,
                         "Get host should not be empty for: %s" % self.host)
        with Check() as check:
            used_ram = int(result.usedRAM)
            total_ram = int(result.totalRAM)
            percent_used = int(result.percentUsed)
            lower, upper = percent_boundary(used_ram, total_ram)
            check.true(percent_used > lower,
                       "percentUsed %r is below the lower boundary %r"
                       % (percent_used, lower))
            check.true(percent_used < upper,
                       "percentUsed %r is above the upper boundary %r"
                       % (percent_used, upper))
            check.true(used_ram < total_ram,
                       "usedRAM %r should be less than totalRAM %r"
                       % (used_ram, total_ram))
            check.true(percent_used < 100,
                       "percentUsed should be less than 100 but was %r"
                       % percent_used)
            check.true(total_ram > 0,
                       "totalRAM should be greater than 0 but was %r"
                       % total_ram)
            check.true(used_ram < total_ram,
                       "usedRAM %r should be less than totalRAM %r"
                       % (used_ram, total_ram))


@test(groups=[INSTANCES, GROUP],
      depends_on=[CreateInstance],
      enabled=create_new_instance())
class HostsMgmtCommands(object):

    @before_class
    def setUp(self):
        self.user = CONFIG.users.find_user(Requirements(is_admin=True))
        self.client = create_dbaas_client(self.user)
        self.host = None

    @test
    def test_index_host_list(self):
        result = self.client.hosts.index()
        assert_not_equal(len(result), 0,
                         "list hosts should not be empty: %s" % str(result))
        hosts = []
        # Find a host with a instanceCount > 0
        for host in result:
            msg = 'Host: %s, Count: %s' % (host.name, host.instanceCount)
            hosts.append(msg)
            if int(host.instanceCount) > 0:
                self.host = host
                break

        msg = "Unable to find a host with instances: %r" % hosts
        assert_not_equal(self.host, None, msg)

    @test(depends_on=[test_index_host_list])
    def test_index_host_list_single(self):
        self.host.name = self.host.name.replace(".", "\.")
        result = self.client.hosts.get(self.host)
        assert_not_equal(result, None,
                         "list hosts should not be empty: %s" % str(result))
        assert_true(len(result.instances) > 0,
                    "instance list on the host should not be empty: %r"
                    % result.instances)
        with Check() as check:
            used_ram = int(result.usedRAM)
            total_ram = int(result.totalRAM)
            percent_used = int(result.percentUsed)
            lower, upper = percent_boundary(used_ram, total_ram)
            check.true(percent_used > lower,
                       "percentUsed %r is below the lower boundary %r"
                       % (percent_used, lower))
            check.true(percent_used < upper,
                       "percentUsed %r is above the upper boundary %r"
                       % (percent_used, upper))
            check.true(used_ram < total_ram,
                       "usedRAM %r should be less than totalRAM %r"
                       % (used_ram, total_ram))
            check.true(percent_used < 100,
                       "percentUsed should be less than 100 but was %r"
                       % percent_used)
            check.true(total_ram > 0,
                       "totalRAM should be greater than 0 but was %r"
                       % total_ram)
            check.true(used_ram < total_ram,
                       "usedRAM %r should be less than totalRAM %r"
                       % (used_ram, total_ram))

            # Check all active instances and validate all the fields exist
            active_instance = None
            for instance in result.instances:
                print("instance: %s" % instance)
                if instance['status'] != 'ACTIVE':
                    continue
                active_instance = instance
                check.is_not_none(instance['id'])
                check.is_not_none(instance['name'])
                check.is_not_none(instance['status'])
                check.is_not_none(instance['server_id'])
                check.is_not_none(instance['tenant_id'])
            check.true(active_instance is not None, "No active instances")

    def _get_ids(self):
        """Get all the ids of instances that are ACTIVE."""
        ids = []
        results = self.client.hosts.index()
        for host in results:
            result = self.client.hosts.get(host)
            for instance in result.instances:
                if instance['status'] == 'ACTIVE':
                    ids.append(instance['id'])
        return ids

    @test
    def test_update_hosts(self):
        ids = self._get_ids()
        assert_not_equal(ids, [], "No active instances found")
        before_versions = {}
        for _id in ids:
            diagnostics = self.client.diagnostics.get(_id)
            before_versions[_id] = diagnostics.version

        hosts = self.client.hosts.index()
        for host in hosts:
            self.client.hosts.update_all(host.name)

        after_versions = {}
        for _id in ids:
            diagnostics = self.client.diagnostics.get(_id)
            after_versions[_id] = diagnostics.version

        assert_not_equal(before_versions, {},
                         "No versions found before update")
        assert_not_equal(after_versions, {},
                         "No versions found after update")
        if CONFIG.fake_mode:
            for _id in after_versions:
                assert_not_equal(before_versions[_id], after_versions[_id])

    @test
    def test_host_not_found(self):
        hostname = "host@$%3dne"
        assert_raises(exceptions.NotFound, self.client.hosts.get, hostname)
