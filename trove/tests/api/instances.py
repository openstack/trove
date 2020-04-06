# Copyright 2011 OpenStack Foundation
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

import netaddr
import os
import time
import unittest
import uuid

from proboscis import asserts
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_not_equal
from proboscis.asserts import assert_raises
from proboscis.asserts import assert_true
from proboscis.asserts import fail
from proboscis import before_class
from proboscis.decorators import time_out
from proboscis import SkipTest
from proboscis import test
from troveclient.compat import exceptions

from trove.common import cfg
from trove.common.utils import poll_until
from trove.datastore import models as datastore_models
from trove import tests
from trove.tests.config import CONFIG
from trove.tests import util
from trove.tests.util.check import AttrCheck
from trove.tests.util import create_dbaas_client
from trove.tests.util import test_config
from trove.tests.util.usage import create_usage_verifier
from trove.tests.util.users import Requirements

CONF = cfg.CONF

FAKE = test_config.values['fake_mode']

TIMEOUT_INSTANCE_CREATE = 60 * 32
TIMEOUT_INSTANCE_RESTORE = 60 * 60
TIMEOUT_INSTANCE_DELETE = 120


class InstanceTestInfo(object):
    """Stores new instance information used by dependent tests."""

    def __init__(self):
        self.dbaas = None  # The rich client instance used by these tests.
        self.dbaas_admin = None  # The rich client with admin access.
        self.dbaas_flavor = None  # The flavor object of the instance.
        self.dbaas_flavor_href = None  # The flavor of the instance.
        self.dbaas_datastore = None  # The datastore id
        self.dbaas_datastore_version = None  # The datastore version id
        self.id = None  # The ID of the instance in the database.
        self.local_id = None

        # The IP address of the database instance for the user.
        self.address = None
        # The management network IP address.
        self.mgmt_address = None

        self.nics = None  # The dict of type/id for nics used on the instance.
        shared_network = CONFIG.get('shared_network', None)
        if shared_network:
            self.nics = [{'net-id': shared_network}]
        self.initial_result = None  # The initial result from the create call.
        self.result = None  # The instance info returned by the API
        self.nova_client = None  # The instance of novaclient.
        self.volume_client = None  # The instance of the volume client.
        self.name = None  # Test name, generated each test run.
        self.pid = None  # The process ID of the instance.
        self.user = None  # The user instance who owns the instance.
        self.admin_user = None  # The admin user for the management interfaces.
        self.volume = None  # The volume the instance will have.
        self.volume_id = None  # Id for the attached vo186lume
        self.storage = None  # The storage device info for the volumes.
        self.databases = None  # The databases created on the instance.
        self.host_info = None  # Host Info before creating instances
        self.user_context = None  # A regular user context
        self.users = None  # The users created on the instance.
        self.consumer = create_usage_verifier()
        self.flavors = None  # The cache of Nova flavors.

    def find_default_flavor(self):
        if EPHEMERAL_SUPPORT:
            flavor_name = CONFIG.values.get('instance_eph_flavor_name',
                                            'eph.rd-tiny')
        else:
            flavor_name = CONFIG.values.get('instance_flavor_name', 'm1.tiny')

        flavor = None
        flavor_href = None

        for item in self.flavors:
            if item.name == flavor_name:
                flavor = item
                flavor_href = item.id
                break

        asserts.assert_is_not_none(flavor)
        asserts.assert_is_not_none(flavor_href)

        return flavor, flavor_href

    def get_address(self, mgmt=False):
        if mgmt:
            if self.mgmt_address:
                return self.mgmt_address

            mgmt_netname = test_config.get("trove_mgmt_network", "trove-mgmt")
            result = self.dbaas_admin.mgmt.instances.show(self.id)
            mgmt_interfaces = result.server['addresses'].get(mgmt_netname, [])
            mgmt_addresses = [str(inf["addr"]) for inf in mgmt_interfaces
                              if inf["version"] == 4]
            if len(mgmt_addresses) == 0:
                fail("No IPV4 ip found for management network.")
            self.mgmt_address = mgmt_addresses[0]
            return self.mgmt_address
        else:
            if self.address:
                return self.address

            result = self.dbaas.instances.get(self.id)
            addresses = [str(ip) for ip in result.ip if netaddr.valid_ipv4(ip)]
            if len(addresses) == 0:
                fail("No IPV4 ip found for database network.")
            self.address = addresses[0]
            return self.address

    def get_local_id(self):
        mgmt_instance = self.dbaas_admin.management.show(self.id)
        return mgmt_instance.server["local_id"]

    def get_volume_filesystem_size(self):
        mgmt_instance = self.dbaas_admin.management.show(self.id)
        return mgmt_instance.volume["total"]


# The two variables are used below by tests which depend on an instance
# existing.
instance_info = InstanceTestInfo()
dbaas = None  # Rich client used throughout this test.
dbaas_admin = None  # Same as above, with admin privs.
ROOT_ON_CREATE = CONFIG.get('root_on_create', False)
VOLUME_SUPPORT = CONFIG.get('trove_volume_support', False)
EPHEMERAL_SUPPORT = not VOLUME_SUPPORT and CONFIG.get('device_path',
                                                      '/dev/vdb') is not None
ROOT_PARTITION = not VOLUME_SUPPORT and CONFIG.get('device_path',
                                                   None) is None


# This is like a cheat code which allows the tests to skip creating a new
# instance and use an old one.
def existing_instance():
    return os.environ.get("TESTS_USE_INSTANCE_ID", None)


def create_new_instance():
    return existing_instance() is None


def assert_unprocessable(func, *args):
    try:
        func(*args)
        # If the exception didn't get raised, but the instance is still in
        # the BUILDING state, that's a bug.
        result = dbaas.instances.get(instance_info.id)
        if result.status == "BUILD":
            fail("When an instance is being built, this function should "
                 "always raise UnprocessableEntity.")
    except exceptions.UnprocessableEntity:
        assert_equal(422, dbaas.last_http_code)
        pass  # Good


class CheckInstance(AttrCheck):
    """Class to check various attributes of Instance details."""

    def __init__(self, instance):
        super(CheckInstance, self).__init__()
        self.instance = instance

    def flavor(self):
        if 'flavor' not in self.instance:
            self.fail("'flavor' not found in instance.")
        else:
            allowed_attrs = ['id']
            self.contains_allowed_attrs(
                self.instance['flavor'], allowed_attrs,
                msg="Flavor")

    def datastore(self):
        if 'datastore' not in self.instance:
            self.fail("'datastore' not found in instance.")
        else:
            allowed_attrs = ['type', 'version']
            self.contains_allowed_attrs(
                self.instance['datastore'], allowed_attrs,
                msg="datastore")

    def volume_key_exists(self):
        if 'volume' not in self.instance:
            self.fail("'volume' not found in instance.")
            return False
        return True

    def volume(self):
        if not VOLUME_SUPPORT:
            return
        if self.volume_key_exists():
            allowed_attrs = ['size']
            if not create_new_instance():
                allowed_attrs.append('used')
            self.contains_allowed_attrs(
                self.instance['volume'], allowed_attrs,
                msg="Volumes")

    def used_volume(self):
        if not VOLUME_SUPPORT:
            return
        if self.volume_key_exists():
            allowed_attrs = ['size', 'used']
            print(self.instance)
            self.contains_allowed_attrs(
                self.instance['volume'], allowed_attrs,
                msg="Volumes")

    def volume_mgmt(self):
        if not VOLUME_SUPPORT:
            return
        if self.volume_key_exists():
            allowed_attrs = ['description', 'id', 'name', 'size']
            self.contains_allowed_attrs(
                self.instance['volume'], allowed_attrs,
                msg="Volumes")

    def addresses(self):
        allowed_attrs = ['addr', 'version']
        print(self.instance)
        networks = ['usernet']
        for network in networks:
            for address in self.instance['addresses'][network]:
                self.contains_allowed_attrs(
                    address, allowed_attrs,
                    msg="Address")

    def guest_status(self):
        allowed_attrs = ['created_at', 'deleted', 'deleted_at', 'instance_id',
                         'state', 'state_description', 'updated_at']
        self.contains_allowed_attrs(
            self.instance['guest_status'], allowed_attrs,
            msg="Guest status")

    def mgmt_volume(self):
        if not VOLUME_SUPPORT:
            return
        allowed_attrs = ['description', 'id', 'name', 'size']
        self.contains_allowed_attrs(
            self.instance['volume'], allowed_attrs,
            msg="Volume")

    def replica_of(self):
        if 'replica_of' not in self.instance:
            self.fail("'replica_of' not found in instance.")
        else:
            allowed_attrs = ['id', 'links']
            self.contains_allowed_attrs(
                self.instance['replica_of'], allowed_attrs,
                msg="Replica-of links not found")
            self.links(self.instance['replica_of']['links'])

    def slaves(self):
        if 'replicas' not in self.instance:
            self.fail("'replicas' not found in instance.")
        else:
            allowed_attrs = ['id', 'links']
            for slave in self.instance['replicas']:
                self.contains_allowed_attrs(
                    slave, allowed_attrs,
                    msg="Replica links not found")
                self.links(slave['links'])


@test(groups=[tests.DBAAS_API_INSTANCES],
      depends_on_groups=[tests.DBAAS_API_MGMT_DATASTORES])
class TestInstanceSetup(object):
    """Prepare the instance creation parameters."""

    @before_class
    def setUp(self):
        """Sets up the client."""

        reqs = Requirements(is_admin=True)
        instance_info.admin_user = CONFIG.users.find_user(reqs)
        instance_info.dbaas_admin = create_dbaas_client(
            instance_info.admin_user)
        global dbaas_admin
        dbaas_admin = instance_info.dbaas_admin

        # Make sure we create the client as the correct user if we're using
        # a pre-built instance.
        if existing_instance():
            mgmt_inst = dbaas_admin.mgmt.instances.show(existing_instance())
            t_id = mgmt_inst.tenant_id
            instance_info.user = CONFIG.users.find_user_by_tenant_id(t_id)
        else:
            reqs = Requirements(is_admin=False)
            instance_info.user = CONFIG.users.find_user(reqs)

        instance_info.dbaas = create_dbaas_client(instance_info.user)

        instance_info.nova_client = util.create_nova_client(instance_info.user)
        instance_info.flavors = instance_info.nova_client.flavors.list()

        global dbaas
        dbaas = instance_info.dbaas

    @test
    def test_find_flavor(self):
        flavor, flavor_href = instance_info.find_default_flavor()
        instance_info.dbaas_flavor = flavor
        instance_info.dbaas_flavor_href = flavor_href

    @test
    def create_instance_name(self):
        id = existing_instance()
        if id is None:
            instance_info.name = "TEST_" + str(uuid.uuid4())
        else:
            instance_info.name = dbaas.instances.get(id).name


@test(groups=[tests.DBAAS_API_INSTANCES],
      depends_on_classes=[TestInstanceSetup])
class TestCreateInstanceQuota(unittest.TestCase):
    def tearDown(self):
        quota_dict = {'instances': CONFIG.trove_max_instances_per_tenant,
                      'volumes': CONFIG.trove_max_volumes_per_tenant}
        dbaas_admin.quota.update(instance_info.user.tenant_id,
                                 quota_dict)

    def test_instance_size_too_big(self):
        if ('trove_max_accepted_volume_size' in CONFIG.values and
                VOLUME_SUPPORT):
            too_big = CONFIG.trove_max_accepted_volume_size

            assert_raises(exceptions.OverLimit,
                          dbaas.instances.create,
                          "volume_size_too_large",
                          instance_info.dbaas_flavor_href,
                          {'size': too_big + 1},
                          nics=instance_info.nics)

    def test_update_quota_invalid_resource_should_fail(self):
        quota_dict = {'invalid_resource': 100}
        assert_raises(exceptions.NotFound, dbaas_admin.quota.update,
                      instance_info.user.tenant_id, quota_dict)

    def test_update_quota_volume_should_fail_volume_not_supported(self):
        if VOLUME_SUPPORT:
            raise SkipTest("Volume support needs to be disabled")
        quota_dict = {'volumes': 100}
        assert_raises(exceptions.NotFound, dbaas_admin.quota.update,
                      instance_info.user.tenant_id, quota_dict)

    def test_create_too_many_instances(self):
        instance_quota = 0
        quota_dict = {'instances': instance_quota}
        new_quotas = dbaas_admin.quota.update(instance_info.user.tenant_id,
                                              quota_dict)

        set_quota = dbaas_admin.quota.show(instance_info.user.tenant_id)
        verify_quota = {q.resource: q.limit for q in set_quota}

        assert_equal(new_quotas['instances'], quota_dict['instances'])
        assert_equal(0, verify_quota['instances'])

        volume = None
        if VOLUME_SUPPORT:
            assert_equal(CONFIG.trove_max_volumes_per_tenant,
                         verify_quota['volumes'])
            volume = {'size': CONFIG.get('trove_volume_size', 1)}

        assert_raises(exceptions.OverLimit,
                      dbaas.instances.create,
                      "too_many_instances",
                      instance_info.dbaas_flavor_href,
                      volume,
                      nics=instance_info.nics)

        assert_equal(413, dbaas.last_http_code)

    def test_create_instances_total_volume_exceeded(self):
        if not VOLUME_SUPPORT:
            raise SkipTest("Volume support not enabled")
        volume_quota = 3
        quota_dict = {'volumes': volume_quota}
        new_quotas = dbaas_admin.quota.update(instance_info.user.tenant_id,
                                              quota_dict)
        assert_equal(volume_quota, new_quotas['volumes'])

        assert_raises(exceptions.OverLimit,
                      dbaas.instances.create,
                      "too_large_volume",
                      instance_info.dbaas_flavor_href,
                      {'size': volume_quota + 1},
                      nics=instance_info.nics)

        assert_equal(413, dbaas.last_http_code)


@test(groups=[tests.DBAAS_API_INSTANCES],
      depends_on_classes=[TestCreateInstanceQuota])
class CreateInstanceFail(object):
    """Negative instance creation tests."""
    def instance_in_error(self, instance_id):
        def check_if_error():
            instance = dbaas.instances.get(instance_id)
            if instance.status == "ERROR":
                return True
            else:
                # The status should still be BUILD
                assert_equal("BUILD", instance.status)
                return False
        return check_if_error

    def delete_async(self, instance_id):
        dbaas.instances.delete(instance_id)
        while True:
            try:
                dbaas.instances.get(instance_id)
            except exceptions.NotFound:
                return True
            time.sleep(1)

    @test
    def test_create_with_bad_availability_zone(self):
        instance_name = "instance-failure-with-bad-az"
        if VOLUME_SUPPORT:
            volume = {'size': CONFIG.get('trove_volume_size', 1)}
        else:
            volume = None
        databases = []
        result = dbaas.instances.create(instance_name,
                                        instance_info.dbaas_flavor_href,
                                        volume, databases,
                                        availability_zone="BAD_ZONE",
                                        nics=instance_info.nics)

        poll_until(self.instance_in_error(result.id), sleep_time=5,
                   time_out=30)
        instance = dbaas.instances.get(result.id)
        assert_equal("ERROR", instance.status)

        self.delete_async(result.id)

    @test
    def test_create_with_invalid_net_id(self):
        instance_name = "instance-failure-with-invalid-net"
        if VOLUME_SUPPORT:
            volume = {'size': CONFIG.get('trove_volume_size', 1)}
        else:
            volume = None
        databases = []
        bad_nic = [{"net-id": "1234"}]

        assert_raises(
            exceptions.BadRequest,
            dbaas.instances.create,
            instance_name, instance_info.dbaas_flavor_href,
            volume, databases, nics=bad_nic
        )
        assert_equal(400, dbaas.last_http_code)

    @test
    def test_create_with_multiple_net_id(self):
        instance_name = "instance_failure_with_multiple_net_id"
        volume = {'size': CONFIG.get('trove_volume_size', 1)}
        databases = []
        multi_nics = [
            {"net-id": str(uuid.uuid4())},
            {"net-id": str(uuid.uuid4())}
        ]

        assert_raises(
            exceptions.BadRequest,
            dbaas.instances.create,
            instance_name, instance_info.dbaas_flavor_href,
            volume, databases, nics=multi_nics
        )
        assert_equal(400, dbaas.last_http_code)

    @test
    def test_create_with_port_id(self):
        instance_name = "instance-failure-with-port-id"
        if VOLUME_SUPPORT:
            volume = {'size': CONFIG.get('trove_volume_size', 1)}
        else:
            volume = None
        databases = []
        bad_nic = [{"port-id": "1234"}]

        assert_raises(
            exceptions.BadRequest,
            dbaas.instances.create,
            instance_name, instance_info.dbaas_flavor_href,
            volume, databases, nics=bad_nic
        )
        assert_equal(400, dbaas.last_http_code)

    @test
    def test_create_failure_with_empty_flavor(self):
        instance_name = "instance-failure-with-empty-flavor"
        databases = []
        if VOLUME_SUPPORT:
            volume = {'size': CONFIG.get('trove_volume_size', 1)}
        else:
            volume = None
        assert_raises(exceptions.BadRequest, dbaas.instances.create,
                      instance_name, '',
                      volume, databases,
                      nics=instance_info.nics)
        assert_equal(400, dbaas.last_http_code)

    @test(enabled=VOLUME_SUPPORT)
    def test_create_failure_with_empty_volume(self):
        instance_name = "instance-failure-with-no-volume-size"
        databases = []
        volume = {}
        assert_raises(exceptions.BadRequest, dbaas.instances.create,
                      instance_name, instance_info.dbaas_flavor_href,
                      volume, databases,
                      nics=instance_info.nics)
        assert_equal(400, dbaas.last_http_code)

    @test(enabled=VOLUME_SUPPORT)
    def test_create_failure_with_no_volume_size(self):
        instance_name = "instance-failure-with-no-volume-size"
        databases = []
        volume = {'size': None}
        assert_raises(exceptions.BadRequest, dbaas.instances.create,
                      instance_name, instance_info.dbaas_flavor_href,
                      volume, databases,
                      nics=instance_info.nics)
        assert_equal(400, dbaas.last_http_code)

    @test(enabled=not VOLUME_SUPPORT)
    def test_create_failure_with_volume_size_and_volume_disabled(self):
        instance_name = "instance-failure-volume-size_and_volume_disabled"
        databases = []
        volume = {'size': 2}
        assert_raises(exceptions.HTTPNotImplemented, dbaas.instances.create,
                      instance_name, instance_info.dbaas_flavor_href,
                      volume, databases,
                      nics=instance_info.nics)
        assert_equal(501, dbaas.last_http_code)

    @test(enabled=EPHEMERAL_SUPPORT)
    def test_create_failure_with_no_ephemeral_flavor(self):
        instance_name = "instance-failure-with-no-ephemeral-flavor"
        databases = []
        flavor_name = CONFIG.values.get('instance_flavor_name', 'm1.tiny')

        flavor_id = None
        for item in instance_info.flavors:
            if item.name == flavor_name:
                flavor_id = item.id

        asserts.assert_is_not_none(flavor_id)

        assert_raises(exceptions.BadRequest, dbaas.instances.create,
                      instance_name, flavor_id, None, databases,
                      nics=instance_info.nics)
        assert_equal(400, dbaas.last_http_code)

    @test
    def test_create_failure_with_no_name(self):
        if VOLUME_SUPPORT:
            volume = {'size': CONFIG.get('trove_volume_size', 1)}
        else:
            volume = None
        instance_name = ""
        databases = []
        assert_raises(exceptions.BadRequest, dbaas.instances.create,
                      instance_name, instance_info.dbaas_flavor_href,
                      volume, databases,
                      nics=instance_info.nics)
        assert_equal(400, dbaas.last_http_code)

    @test
    def test_create_failure_with_spaces_for_name(self):
        if VOLUME_SUPPORT:
            volume = {'size': CONFIG.get('trove_volume_size', 1)}
        else:
            volume = None
        instance_name = "      "
        databases = []
        assert_raises(exceptions.BadRequest, dbaas.instances.create,
                      instance_name, instance_info.dbaas_flavor_href,
                      volume, databases,
                      nics=instance_info.nics)
        assert_equal(400, dbaas.last_http_code)

    @test
    def test_mgmt_get_instance_on_create(self):
        if CONFIG.test_mgmt:
            result = dbaas_admin.management.show(instance_info.id)
            allowed_attrs = ['account_id', 'addresses', 'created',
                             'databases', 'flavor', 'guest_status', 'host',
                             'hostname', 'id', 'name', 'datastore',
                             'server_state_description', 'status', 'updated',
                             'users', 'volume', 'root_enabled_at',
                             'root_enabled_by', 'fault',
                             'service_status_updated']
            with CheckInstance(result._info) as check:
                check.contains_allowed_attrs(
                    result._info, allowed_attrs,
                    msg="Mgmt get instance")
                check.flavor()
                check.datastore()
                check.guest_status()

    @test
    def test_create_failure_with_datastore_default_not_defined(self):
        if not FAKE:
            raise SkipTest("This test only for fake mode.")
        if VOLUME_SUPPORT:
            volume = {'size': CONFIG.get('trove_volume_size', 1)}
        else:
            volume = None
        instance_name = "datastore_default_notfound"
        databases = []
        users = []
        origin_default_datastore = (datastore_models.CONF.
                                    default_datastore)
        datastore_models.CONF.default_datastore = ""
        try:
            assert_raises(exceptions.NotFound,
                          dbaas.instances.create, instance_name,
                          instance_info.dbaas_flavor_href,
                          volume, databases, users,
                          nics=instance_info.nics)
        except exceptions.BadRequest as e:
            assert_equal(e.message,
                         "Please specify datastore. No default datastore "
                         "is defined.")
        datastore_models.CONF.default_datastore = \
            origin_default_datastore

    @test
    def test_create_failure_with_datastore_default_version_notfound(self):
        if VOLUME_SUPPORT:
            volume = {'size': CONFIG.get('trove_volume_size', 1)}
        else:
            volume = None
        instance_name = "datastore_default_version_notfound"
        databases = []
        users = []
        datastore = CONFIG.dbaas_datastore_name_no_versions

        try:
            assert_raises(exceptions.NotFound,
                          dbaas.instances.create, instance_name,
                          instance_info.dbaas_flavor_href,
                          volume, databases, users,
                          datastore=datastore,
                          nics=instance_info.nics)
        except exceptions.BadRequest as e:
            assert_equal(e.message,
                         "Default version for datastore '%s' not found." %
                         datastore)

    @test
    def test_create_failure_with_datastore_notfound(self):
        if VOLUME_SUPPORT:
            volume = {'size': CONFIG.get('trove_volume_size', 1)}
        else:
            volume = None
        instance_name = "datastore_notfound"
        databases = []
        users = []
        datastore = "nonexistent"
        try:
            assert_raises(exceptions.NotFound,
                          dbaas.instances.create, instance_name,
                          instance_info.dbaas_flavor_href,
                          volume, databases, users,
                          datastore=datastore,
                          nics=instance_info.nics)
        except exceptions.BadRequest as e:
            assert_equal(e.message,
                         "Datastore '%s' cannot be found." %
                         datastore)

    @test
    def test_create_failure_with_datastore_version_notfound(self):
        if VOLUME_SUPPORT:
            volume = {'size': CONFIG.get('trove_volume_size', 1)}
        else:
            volume = None
        instance_name = "datastore_version_notfound"
        databases = []
        users = []
        datastore = CONFIG.dbaas_datastore
        datastore_version = "nonexistent"
        try:
            assert_raises(exceptions.NotFound,
                          dbaas.instances.create, instance_name,
                          instance_info.dbaas_flavor_href,
                          volume, databases, users,
                          datastore=datastore,
                          datastore_version=datastore_version,
                          nics=instance_info.nics)
        except exceptions.BadRequest as e:
            assert_equal(e.message,
                         "Datastore version '%s' cannot be found." %
                         datastore_version)


@test(
    groups=[tests.DBAAS_API_INSTANCES],
    depends_on_classes=[CreateInstanceFail],
)
class CreateInstance(object):

    """Test to create a Database Instance

    If the call returns without raising an exception this test passes.

    """

    @test
    def test_create(self):
        databases = []
        databases.append({"name": "firstdb", "character_set": "latin2",
                          "collate": "latin2_general_ci"})
        databases.append({"name": "db2"})
        instance_info.databases = databases
        users = []
        users.append({"name": "lite", "password": "litepass",
                      "databases": [{"name": "firstdb"}]})
        instance_info.users = users
        instance_info.dbaas_datastore = CONFIG.dbaas_datastore
        instance_info.dbaas_datastore_version = CONFIG.dbaas_datastore_version
        if VOLUME_SUPPORT:
            instance_info.volume = {'size': CONFIG.get('trove_volume_size', 2)}
        else:
            instance_info.volume = None

        if create_new_instance():
            instance_info.initial_result = dbaas.instances.create(
                instance_info.name,
                instance_info.dbaas_flavor_href,
                instance_info.volume,
                databases,
                users,
                nics=instance_info.nics,
                availability_zone="nova",
                datastore=instance_info.dbaas_datastore,
                datastore_version=instance_info.dbaas_datastore_version)
            assert_equal(200, dbaas.last_http_code)
        else:
            id = existing_instance()
            instance_info.initial_result = dbaas.instances.get(id)

        result = instance_info.initial_result
        instance_info.id = result.id
        instance_info.dbaas_datastore_version = result.datastore['version']

        report = CONFIG.get_report()
        report.log("Instance UUID = %s" % instance_info.id)
        if create_new_instance():
            assert_equal("BUILD", instance_info.initial_result.status)

        else:
            report.log("Test was invoked with TESTS_USE_INSTANCE_ID=%s, so no "
                       "instance was actually created." % id)

        # Check these attrs only are returned in create response
        allowed_attrs = ['created', 'flavor', 'addresses', 'id', 'links',
                         'name', 'status', 'updated', 'datastore', 'fault',
                         'region', 'service_status_updated']
        if ROOT_ON_CREATE:
            allowed_attrs.append('password')
        if VOLUME_SUPPORT:
            allowed_attrs.append('volume')
        if CONFIG.trove_dns_support:
            allowed_attrs.append('hostname')

        with CheckInstance(result._info) as check:
            if create_new_instance():
                check.contains_allowed_attrs(
                    result._info, allowed_attrs,
                    msg="Create response")
            # Don't CheckInstance if the instance already exists.
            check.flavor()
            check.datastore()
            check.links(result._info['links'])
            if VOLUME_SUPPORT:
                check.volume()


@test(
    groups=[tests.DBAAS_API_INSTANCES],
    depends_on_classes=[CreateInstance],
    enabled=create_new_instance()
)
class AfterInstanceCreation(unittest.TestCase):

    # instance calls
    def test_instance_delete_right_after_create(self):
        assert_unprocessable(dbaas.instances.delete, instance_info.id)

    # root calls
    def test_root_create_root_user_after_create(self):
        assert_unprocessable(dbaas.root.create, instance_info.id)

    def test_root_is_root_enabled_after_create(self):
        assert_unprocessable(dbaas.root.is_root_enabled, instance_info.id)

    # database calls
    def test_database_index_after_create(self):
        assert_unprocessable(dbaas.databases.list, instance_info.id)

    def test_database_delete_after_create(self):
        assert_unprocessable(dbaas.databases.delete, instance_info.id,
                             "testdb")

    def test_database_create_after_create(self):
        assert_unprocessable(dbaas.databases.create, instance_info.id,
                             instance_info.databases)

    # user calls
    def test_users_index_after_create(self):
        assert_unprocessable(dbaas.users.list, instance_info.id)

    def test_users_delete_after_create(self):
        assert_unprocessable(dbaas.users.delete, instance_info.id,
                             "testuser")

    def test_users_create_after_create(self):
        users = list()
        users.append({"name": "testuser", "password": "password",
                      "databases": [{"name": "testdb"}]})
        assert_unprocessable(dbaas.users.create, instance_info.id, users)

    def test_resize_instance_after_create(self):
        assert_unprocessable(dbaas.instances.resize_instance,
                             instance_info.id, 8)

    def test_resize_volume_after_create(self):
        assert_unprocessable(dbaas.instances.resize_volume,
                             instance_info.id, 2)


@test(
    depends_on_classes=[AfterInstanceCreation],
    groups=[tests.DBAAS_API_INSTANCES],
    enabled=create_new_instance()
)
class WaitForGuestInstallationToFinish(object):
    @test
    @time_out(TIMEOUT_INSTANCE_CREATE)
    def test_instance_created(self):
        """Wait for normal instance to be created."""
        def result_is_active():
            instance = dbaas.instances.get(instance_info.id)
            if instance.status in CONFIG.running_status:
                return True
            else:
                # If its not ACTIVE, anything but BUILD must be
                # an error.
                assert_equal("BUILD", instance.status)
                if instance_info.volume is not None:
                    assert_equal(instance.volume.get('used', None), None)
                return False

        poll_until(result_is_active, sleep_time=5)
        dbaas.instances.get(instance_info.id)

        report = CONFIG.get_report()
        report.log("Created an instance, ID = %s." % instance_info.id)
        report.log("TIP:")
        report.log("Rerun the tests with TESTS_USE_INSTANCE_ID=%s "
                   "to skip ahead to this point." % instance_info.id)
        report.log("Add TESTS_DO_NOT_DELETE_INSTANCE=True to avoid deleting "
                   "the instance at the end of the tests.")


@test(depends_on_classes=[WaitForGuestInstallationToFinish],
      groups=[tests.DBAAS_API_INSTANCES])
class TestDBandUserAfterInstanceCreated(object):
    @test
    def test_databases(self):
        """Get databases after instance creation."""
        databases = dbaas.databases.list(instance_info.id)
        dbs = [database.name for database in databases]
        for db in instance_info.databases:
            assert_true(db["name"] in dbs)

    @test
    def test_users(self):
        """Get users after instance creation."""
        users = dbaas.users.list(instance_info.id)
        usernames = [user.name for user in users]
        for user in instance_info.users:
            assert_true(user["name"] in usernames)


@test(depends_on_classes=[WaitForGuestInstallationToFinish],
      groups=[tests.DBAAS_API_INSTANCES])
class TestGetInstances(object):
    @before_class
    def setUp(self):
        reqs = Requirements(is_admin=False)
        self.other_user = CONFIG.users.find_user(
            reqs,
            black_list=[instance_info.user.auth_user])
        self.other_client = create_dbaas_client(self.other_user)

    @test
    def test_index_list(self):
        allowed_attrs = ['id', 'links', 'name', 'status', 'flavor',
                         'datastore', 'ip', 'hostname', 'replica_of',
                         'region', 'addresses']
        if VOLUME_SUPPORT:
            allowed_attrs.append('volume')
        instances = dbaas.instances.list()
        assert_equal(200, dbaas.last_http_code)
        for instance in instances:
            instance_dict = instance._info
            with CheckInstance(instance_dict) as check:
                print("testing instance_dict=%s" % instance_dict)
                check.contains_allowed_attrs(
                    instance_dict, allowed_attrs,
                    msg="Instance Index")
                check.links(instance_dict['links'])
                check.flavor()
                check.datastore()
                check.volume()

    @test
    def test_detailed_list(self):
        allowed_attrs = ['created', 'databases', 'flavor', 'hostname', 'id',
                         'links', 'name', 'status', 'updated', 'ip',
                         'datastore', 'fault', 'region',
                         'service_status_updated', 'addresses']
        if VOLUME_SUPPORT:
            allowed_attrs.append('volume')
        instances = dbaas.instances.list(detailed=True)
        assert_equal(200, dbaas.last_http_code)
        for instance in instances:
            instance_dict = instance._info
            with CheckInstance(instance_dict) as check:
                check.contains_allowed_attrs(instance_dict, allowed_attrs,
                                             msg="Instance Detailed Index")
                check.flavor()
                check.datastore()
                check.volume()
                check.used_volume()

    @test
    def test_get_instance(self):
        allowed_attrs = ['created', 'databases', 'flavor', 'hostname', 'id',
                         'links', 'name', 'status', 'updated', 'ip',
                         'datastore', 'fault', 'region',
                         'service_status_updated', 'addresses']
        if VOLUME_SUPPORT:
            allowed_attrs.append('volume')
        else:
            allowed_attrs.append('local_storage')
        instance = dbaas.instances.get(instance_info.id)
        assert_equal(200, dbaas.last_http_code)
        instance_dict = instance._info
        print("instance_dict=%s" % instance_dict)
        with CheckInstance(instance_dict) as check:
            check.contains_allowed_attrs(
                instance_dict, allowed_attrs,
                msg="Get Instance")
            check.flavor()
            check.datastore()
            check.links(instance_dict['links'])
            check.used_volume()

    @test
    def test_get_instance_status(self):
        result = dbaas.instances.get(instance_info.id)
        assert_equal(200, dbaas.last_http_code)
        asserts.assert_true(result.status in CONFIG.running_status)

    @test
    def test_get_legacy_status(self):
        result = dbaas.instances.get(instance_info.id)
        assert_equal(200, dbaas.last_http_code)
        assert_true(result is not None)

    @test
    def test_get_legacy_status_notfound(self):
        assert_raises(exceptions.NotFound, dbaas.instances.get, -2)

    @test(enabled=VOLUME_SUPPORT)
    def test_volume_found(self):
        instance = dbaas.instances.get(instance_info.id)
        if create_new_instance():
            assert_equal(instance_info.volume['size'], instance.volume['size'])

    @test(enabled=EPHEMERAL_SUPPORT)
    def test_ephemeral_mount(self):
        instance = dbaas.instances.get(instance_info.id)
        assert_true(isinstance(instance.local_storage['used'], float))

    @test(enabled=ROOT_PARTITION)
    def test_root_partition(self):
        instance = dbaas.instances.get(instance_info.id)
        assert_true(isinstance(instance.local_storage['used'], float))

    @test
    def test_instance_not_shown_to_other_user(self):
        daffy_ids = [instance.id for instance in
                     self.other_client.instances.list()]
        assert_equal(200, self.other_client.last_http_code)
        admin_ids = [instance.id for instance in dbaas.instances.list()]
        assert_equal(200, dbaas.last_http_code)

        assert_not_equal(sorted(admin_ids), sorted(daffy_ids))
        assert_raises(exceptions.NotFound,
                      self.other_client.instances.get, instance_info.id)

        for id in admin_ids:
            assert_equal(daffy_ids.count(id), 0)

    @test
    def test_instance_not_deleted_by_other_user(self):
        assert_raises(exceptions.NotFound,
                      self.other_client.instances.get, instance_info.id)
        assert_raises(exceptions.NotFound,
                      self.other_client.instances.delete, instance_info.id)

    @test(enabled=CONFIG.test_mgmt)
    def test_mgmt_get_instance_after_started(self):
        result = dbaas_admin.management.show(instance_info.id)
        allowed_attrs = ['account_id', 'addresses', 'created', 'databases',
                         'flavor', 'guest_status', 'host', 'hostname', 'id',
                         'name', 'root_enabled_at', 'root_enabled_by',
                         'server_state_description', 'status', 'datastore',
                         'updated', 'users', 'volume', 'fault', 'region']
        with CheckInstance(result._info) as check:
            check.contains_allowed_attrs(
                result._info, allowed_attrs,
                msg="Mgmt get instance")
            check.flavor()
            check.datastore()
            check.guest_status()
            check.addresses()
            check.volume_mgmt()


@test(depends_on_classes=[TestGetInstances],
      groups=[tests.DBAAS_API_INSTANCES],
      enabled=CONFIG.test_mgmt)
class TestInstanceMgmtInfo(object):
    @before_class
    def set_up(self):
        self.mgmt_details = dbaas_admin.management.show(instance_info.id)

    @test
    def test_mgmt_ips_associated(self):
        """Every instances has exactly one address"""
        mgmt_index = dbaas_admin.management.index()
        for instance in mgmt_index:
            assert_equal(1, len(instance.ips))

    @test
    def test_mgmt_data(self):
        """Test management API returns all the values expected."""
        info = instance_info
        ir = info.initial_result
        cid = ir.id
        expected = {
            'id': cid,
            'name': ir.name,
            'account_id': info.user.auth_user,
            'databases': [
                {
                    'name': 'db2',
                    'character_set': 'utf8',
                    'collate': 'utf8_general_ci',
                },
                {
                    'name': 'firstdb',
                    'character_set': 'latin2',
                    'collate': 'latin2_general_ci',
                }
            ],
        }

        expected_entry = info.expected_dns_entry()
        if expected_entry:
            expected['hostname'] = expected_entry.name

        assert_true(self.mgmt_details is not None)
        for (k, v) in expected.items():
            msg = "Attr %r is missing." % k
            assert_true(hasattr(self.mgmt_details, k), msg)
            msg = ("Attr %r expected to be %r but was %r." %
                   (k, v, getattr(self.mgmt_details, k)))
            assert_equal(getattr(self.mgmt_details, k), v, msg)
        print(self.mgmt_details.users)
        for user in self.mgmt_details.users:
            assert_true('name' in user, "'name' not in users element.")


@test(depends_on_classes=[TestInstanceMgmtInfo],
      groups=[tests.DBAAS_API_INSTANCES])
class TestUpdateInstance(object):
    """Test updating instance."""
    @test
    def test_update_name(self):
        new_name = 'new-name'
        result = dbaas.instances.edit(instance_info.id, name=new_name)
        assert_equal(202, dbaas.last_http_code)
        result = dbaas.instances.get(instance_info.id)
        assert_equal(200, dbaas.last_http_code)
        assert_equal(new_name, result.name)
        # Restore instance name because other tests depend on it
        dbaas.instances.edit(instance_info.id, name=instance_info.name)
        assert_equal(202, dbaas.last_http_code)

    @test
    def test_update_name_to_invalid_instance(self):
        # test assigning to an instance that does not exist
        invalid_id = "invalid-inst-id"
        assert_raises(exceptions.NotFound, instance_info.dbaas.instances.edit,
                      invalid_id, name='name')
        assert_equal(404, instance_info.dbaas.last_http_code)
