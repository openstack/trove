# Copyright 2011 OpenStack LLC.
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
import hashlib

import os
import re
import string
import time
import unittest
from reddwarf.tests import util
import urlparse


GROUP = "dbaas.guest"
GROUP_START = "dbaas.guest.initialize"
GROUP_START_SIMPLE = "dbaas.guest.initialize.simple"
GROUP_TEST = "dbaas.guest.test"
GROUP_STOP = "dbaas.guest.shutdown"
GROUP_USERS = "dbaas.api.users"
GROUP_ROOT = "dbaas.api.root"
GROUP_DATABASES = "dbaas.api.databases"

from datetime import datetime
from nose.plugins.skip import SkipTest
from nose.tools import assert_true

from reddwarfclient import exceptions

from proboscis.decorators import time_out
from proboscis import before_class
from proboscis import test
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_not_equal
from proboscis.asserts import assert_raises
from proboscis.asserts import assert_is
from proboscis.asserts import assert_is_none
from proboscis.asserts import assert_is_not
from proboscis.asserts import assert_true
from proboscis.asserts import Check
from proboscis.asserts import fail

from reddwarf import tests
from reddwarf.tests.config import CONFIG
from reddwarf.tests.util import create_client
from reddwarf.tests.util import create_dbaas_client
from reddwarf.tests.util import create_nova_client
from reddwarf.tests.util import process
from reddwarf.tests.util.users import Requirements
from reddwarf.tests.util import string_in_list
from reddwarf.tests.util import poll_until
from reddwarf.tests.util.check import AttrCheck


class InstanceTestInfo(object):
    """Stores new instance information used by dependent tests."""

    def __init__(self):
        self.dbaas = None  # The rich client instance used by these tests.
        self.dbaas_admin = None  # The rich client with admin access.
        self.dbaas_flavor = None  # The flavor object of the instance.
        self.dbaas_flavor_href = None  # The flavor of the instance.
        self.dbaas_image = None  # The image used to create the instance.
        self.dbaas_image_href = None  # The link of the image.
        self.id = None  # The ID of the instance in the database.
        self.local_id = None
        self.address = None
        self.initial_result = None  # The initial result from the create call.
        self.user_ip = None  # The IP address of the instance, given to user.
        self.infra_ip = None  # The infrastructure network IP address.
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

    def get_address(self):
        result = self.dbaas_admin.mgmt.instances.show(self.id)
        return result.ip[0]

    def get_local_id(self):
        mgmt_instance = self.dbaas_admin.management.show(self.id)
        return mgmt_instance.server["local_id"]


# The two variables are used below by tests which depend on an instance
# existing.
instance_info = InstanceTestInfo()
dbaas = None  # Rich client used throughout this test.
dbaas_admin = None  # Same as above, with admin privs.


# This is like a cheat code which allows the tests to skip creating a new
# instance and use an old one.
def existing_instance():
    return os.environ.get("TESTS_USE_INSTANCE_ID", None)


def do_not_delete_instance():
    return os.environ.get("TESTS_DO_NOT_DELETE_INSTANCE", None) is not None


def create_new_instance():
    return existing_instance() is None


@test(groups=[GROUP, GROUP_START, GROUP_START_SIMPLE, 'dbaas.setup'],
      depends_on_groups=["services.initialize"])
class InstanceSetup(object):
    """Makes sure the client can hit the ReST service.

    This test also uses the API to find the image and flavor to use.

    """

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
        if CONFIG.white_box:
            instance_info.nova_client = create_nova_client(instance_info.user)
            instance_info.volume_client = create_nova_client(
                instance_info.user,
                service_type=CONFIG.nova_client['volume_service_type'])
        global dbaas
        dbaas = instance_info.dbaas

        if CONFIG.white_box:
            user = instance_info.user.auth_user
            tenant = instance_info.user.tenant
            instance_info.user_context = context.RequestContext(user, tenant)

    @test(enabled=CONFIG.white_box)
    def find_image(self):
        result = dbaas_admin.find_image_and_self_href(CONFIG.dbaas_image)
        instance_info.dbaas_image, instance_info.dbaas_image_href = result

    @test
    def test_find_flavor(self):
        flavor_name = CONFIG.values.get('instance_flavor_name', 'm1.tiny')
        flavors = dbaas.find_flavors_by_name(flavor_name)
        assert_equal(len(flavors), 1, "Number of flavors with name '%s' "
                     "found was '%d'." % (flavor_name, len(flavors)))
        flavor = flavors[0]
        assert_true(flavor is not None, "Flavor '%s' not found!" % flavor_name)
        flavor_href = dbaas.find_flavor_self_href(flavor)
        assert_true(flavor_href is not None,
                    "Flavor href '%s' not found!" % flavor_name)
        instance_info.dbaas_flavor = flavor
        instance_info.dbaas_flavor_href = flavor_href

    @test(enabled=CONFIG.white_box)
    def test_add_imageref_config(self):
        #TODO(tim.simpson): I'm not sure why this is here. The default image
        # setup should be in initialization test code that lives somewhere
        # else, probably with the code that uploads the image.
        key = "reddwarf_imageref"
        value = 1
        description = "Default Image for Reddwarf"
        config = {'key': key, 'value': value, 'description': description}
        try:
            dbaas_admin.configs.create([config])
        except exceptions.ClientException as e:
            # configs.create will throw an exception if the config already
            # exists we will check the value after to make sure it is correct
            # and set
            pass
        result = dbaas_admin.configs.get(key)
        assert_equal(result.value, str(value))

    @test
    def create_instance_name(self):
        id = existing_instance()
        if id is None:
            instance_info.name = "TEST_" + str(datetime.now())
        else:
            instance_info.name = dbaas.instances.get(id).name


@test(depends_on_classes=[InstanceSetup], groups=[GROUP])
def test_delete_instance_not_found():
    """Deletes an instance that does not exist."""
    # Looks for a random UUID that (most probably) does not exist.
    assert_raises(exceptions.NotFound, dbaas.instances.delete,
                  "7016efb6-c02c-403e-9628-f6f57d0920d0")


@test(depends_on_classes=[InstanceSetup],
      groups=[GROUP, GROUP_START, GROUP_START_SIMPLE, tests.INSTANCES],
      runs_after_groups=[tests.PRE_INSTANCES])
class CreateInstance(unittest.TestCase):
    """Test to create a Database Instance

    If the call returns without raising an exception this test passes.

    """

    def test_instance_size_too_big(self):
        vol_ok = CONFIG.get('reddwarf_can_have_volume', False)
        if 'reddwarf_max_accepted_volume_size' in CONFIG.values and vol_ok:
            too_big = CONFIG.values['reddwarf_max_accepted_volume_size']
            assert_raises(exceptions.OverLimit, dbaas.instances.create,
                          "way_too_large", instance_info.dbaas_flavor_href,
                          {'size': too_big + 1}, [])
            assert_equal(413, dbaas.last_http_code)

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
        if CONFIG.values['reddwarf_main_instance_has_volume']:
            instance_info.volume = {'size': 1}
        else:
            instance_info.volume = None

        if create_new_instance():
            instance_info.initial_result = dbaas.instances.create(
                instance_info.name,
                instance_info.dbaas_flavor_href,
                instance_info.volume,
                databases,
                users)
            assert_equal(200, dbaas.last_http_code)
        else:
            id = existing_instance()
            instance_info.initial_result = dbaas.instances.get(id)

        result = instance_info.initial_result
        instance_info.id = result.id
        if CONFIG.white_box:
            instance_info.local_id = dbapi.localid_from_uuid(result.id)

        report = CONFIG.get_report()
        report.log("Instance UUID = %s" % instance_info.id)
        if create_new_instance():
            if CONFIG.white_box:
                building = dbaas_mapping[power_state.BUILDING]
                assert_equal(result.status, building)
            assert_equal("BUILD", instance_info.initial_result.status)

        else:
            report.log("Test was invoked with TESTS_USE_INSTANCE_ID=%s, so no "
                       "instance was actually created." % id)

        # Check these attrs only are returned in create response
        expected_attrs = ['created', 'flavor', 'addresses', 'id', 'links',
                          'name', 'status', 'updated']
        if CONFIG.values['reddwarf_can_have_volume']:
            expected_attrs.append('volume')
        if CONFIG.values['reddwarf_dns_support']:
            expected_attrs.append('hostname')

        with CheckInstance(result._info) as check:
            if create_new_instance():
                check.attrs_exist(result._info, expected_attrs,
                                  msg="Create response")
            # Don't CheckInstance if the instance already exists.
            check.flavor()
            check.links(result._info['links'])
            if CONFIG.values['reddwarf_can_have_volume']:
                check.volume()

    def test_create_failure_with_empty_volume(self):
        if CONFIG.values['reddwarf_must_have_volume']:
            instance_name = "instance-failure-with-no-volume-size"
            databases = []
            volume = {}
            assert_raises(exceptions.BadRequest, dbaas.instances.create,
                          instance_name, instance_info.dbaas_flavor_href,
                          volume, databases)
            assert_equal(400, dbaas.last_http_code)

    def test_create_failure_with_no_volume_size(self):
        if CONFIG.values['reddwarf_must_have_volume']:
            instance_name = "instance-failure-with-no-volume-size"
            databases = []
            volume = {'size': None}
            assert_raises(exceptions.BadRequest, dbaas.instances.create,
                          instance_name, instance_info.dbaas_flavor_href,
                          volume, databases)
            assert_equal(400, dbaas.last_http_code)

    def test_create_failure_with_no_name(self):
        if CONFIG.values['reddwarf_main_instance_has_volume']:
            volume = {'size': 1}
        else:
            volume = None
        instance_name = ""
        databases = []
        assert_raises(exceptions.BadRequest, dbaas.instances.create,
                      instance_name, instance_info.dbaas_flavor_href,
                      volume, databases)
        assert_equal(400, dbaas.last_http_code)

    def test_create_failure_with_spaces_for_name(self):
        if CONFIG.values['reddwarf_main_instance_has_volume']:
            volume = {'size': 1}
        else:
            volume = None
        instance_name = "      "
        databases = []
        assert_raises(exceptions.BadRequest, dbaas.instances.create,
                      instance_name, instance_info.dbaas_flavor_href,
                      volume, databases)
        assert_equal(400, dbaas.last_http_code)

    def test_mgmt_get_instance_on_create(self):
        if CONFIG.test_mgmt:
            result = dbaas_admin.management.show(instance_info.id)
            expected_attrs = ['account_id', 'addresses', 'created',
                              'databases', 'flavor', 'guest_status', 'host',
                              'hostname', 'id', 'name',
                              'server_state_description', 'status', 'updated',
                              'users', 'volume', 'root_enabled_at',
                              'root_enabled_by']
            with CheckInstance(result._info) as check:
                check.attrs_exist(result._info, expected_attrs,
                                  msg="Mgmt get instance")
                check.flavor()
                check.guest_status()


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


@test(depends_on_classes=[CreateInstance],
      groups=[GROUP,
              GROUP_START,
              GROUP_START_SIMPLE,
              'dbaas.mgmt.hosts_post_install'],
      enabled=create_new_instance())
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
                      "database": "testdb"})
        assert_unprocessable(dbaas.users.create, instance_info.id, users)

    def test_resize_instance_after_create(self):
        assert_unprocessable(dbaas.instances.resize_instance,
                             instance_info.id, 8)

    def test_resize_volume_after_create(self):
        assert_unprocessable(dbaas.instances.resize_volume,
                             instance_info.id, 2)


@test(depends_on_classes=[CreateInstance],
      runs_after=[AfterInstanceCreation],
      groups=[GROUP, GROUP_START, GROUP_START_SIMPLE],
      enabled=create_new_instance())
class WaitForGuestInstallationToFinish(object):
    """
        Wait until the Guest is finished installing.  It takes quite a while...
    """

    @test
    @time_out(60 * 32)
    def test_instance_created(self):
        # This version just checks the REST API status.
        def result_is_active():
            instance = dbaas.instances.get(instance_info.id)
            if instance.status == "ACTIVE":
                return True
            else:
                # If its not ACTIVE, anything but BUILD must be
                # an error.
                assert_equal("BUILD", instance.status)
                if instance_info.volume is not None:
                    assert_equal(instance.volume.get('used', None), None)
                return False

        poll_until(result_is_active)
        result = dbaas.instances.get(instance_info.id)

        report = CONFIG.get_report()
        report.log("Created an instance, ID = %s." % instance_info.id)
        report.log("TIP:")
        report.log("Rerun the tests with TESTS_USE_INSTANCE_ID=%s "
                   "to skip ahead to this point." % instance_info.id)
        report.log("Add TESTS_DO_NOT_DELETE_INSTANCE=True to avoid deleting "
                   "the instance at the end of the tests.")


@test(depends_on_classes=[WaitForGuestInstallationToFinish],
      groups=[GROUP, GROUP_START, GROUP_START_SIMPLE],
      enabled=CONFIG.white_box and create_new_instance())
class VerifyGuestStarted(unittest.TestCase):
    """
        Test to verify the guest instance is started and we can get the init
        process pid.
    """

    def test_instance_created(self):
        def check_status_of_instance():
            status, err = process("sudo vzctl status %s | awk '{print $5}'"
                                  % str(instance_info.local_id))
            if string_in_list(status, ["running"]):
                self.assertEqual("running", status.strip())
                return True
            else:
                return False
        poll_until(check_status_of_instance, sleep_time=5, time_out=(60 * 8))

    def test_get_init_pid(self):
        def get_the_pid():
            out, err = process("pgrep init | vzpid - | awk '/%s/{print $1}'"
                               % str(instance_info.local_id))
            instance_info.pid = out.strip()
            return len(instance_info.pid) > 0
        poll_until(get_the_pid, sleep_time=10, time_out=(60 * 10))


@test(depends_on_classes=[WaitForGuestInstallationToFinish],
      groups=[GROUP, GROUP_START], enabled=create_new_instance())
class TestGuestProcess(object):
    """
        Test that the guest process is started with all the right parameters
    """

    @test(enabled=CONFIG.values['use_local_ovz'])
    @time_out(60 * 10)
    def check_process_alive_via_local_ovz(self):
        init_re = ("[\w\W\|\-\s\d,]*nova-guest "
                   "--flagfile=/etc/nova/nova.conf nova[\W\w\s]*")
        init_proc = re.compile(init_re)
        guest_re = ("[\w\W\|\-\s]*/usr/bin/nova-guest "
                    "--flagfile=/etc/nova/nova.conf[\W\w\s]*")
        guest_proc = re.compile(guest_re)
        apt = re.compile("[\w\W\|\-\s]*apt-get[\w\W\|\-\s]*")
        while True:
            guest_process, err = process("pstree -ap %s | grep nova-guest"
                                         % instance_info.pid)
            if not string_in_list(guest_process, ["nova-guest"]):
                time.sleep(10)
            else:
                if apt.match(guest_process):
                    time.sleep(10)
                else:
                    init = init_proc.match(guest_process)
                    guest = guest_proc.match(guest_process)
                    if init and guest:
                        assert_true(True, init.group())
                    else:
                        assert_false(False, guest_process)
                    break

    @test
    def check_hwinfo_before_tests(self):
        if CONFIG.test_mgmt:
            hwinfo = dbaas_admin.hwinfo.get(instance_info.id)
            print("hwinfo : %r" % hwinfo._info)
            expected_attrs = ['hwinfo']
            CheckInstance(None).attrs_exist(hwinfo._info, expected_attrs,
                                            msg="Hardware information")
            # TODO(pdmars): instead of just checking that these are int's, get
            # the instance flavor and verify that the values are correct for
            # the flavor
            assert_true(isinstance(hwinfo.hwinfo['mem_total'], int))
            assert_true(isinstance(hwinfo.hwinfo['num_cpus'], int))

    @test
    def grab_diagnostics_before_tests(self):
        if CONFIG.test_mgmt:
            diagnostics = dbaas_admin.diagnostics.get(instance_info.id)
            diagnostic_tests_helper(diagnostics)


@test(depends_on_classes=[CreateInstance],
      groups=[GROUP, GROUP_START,
      GROUP_START_SIMPLE, GROUP_TEST, "nova.volumes.instance"],
      enabled=CONFIG.white_box)
class TestVolume(unittest.TestCase):
    """Make sure the volume is attached to instance correctly."""

    def test_db_should_have_instance_to_volume_association(self):
        """The compute manager should associate a volume to the instance."""
        volumes = db.volume_get_all_by_instance(context.get_admin_context(),
                                                instance_info.local_id)
        self.assertEqual(1, len(volumes))


@test(depends_on_classes=[WaitForGuestInstallationToFinish],
      groups=[GROUP, GROUP_TEST, "dbaas.guest.start.test"])
class TestAfterInstanceCreatedGuestData(object):
    """
    Test the optional parameters (databases and users) passed in to create
    instance call were created.
    """

    @test
    def test_databases(self):
        databases = dbaas.databases.list(instance_info.id)
        dbs = [database.name for database in databases]
        for db in instance_info.databases:
            assert_true(db["name"] in dbs)

    @test
    def test_users(self):
        users = dbaas.users.list(instance_info.id)
        usernames = [user.name for user in users]
        for user in instance_info.users:
            assert_true(user["name"] in usernames)


@test(depends_on_classes=[WaitForGuestInstallationToFinish],
      groups=[GROUP, GROUP_START, GROUP_START_SIMPLE, "dbaas.listing"])
class TestInstanceListing(object):
    """ Test the listing of the instance information """

    @before_class
    def setUp(self):
        reqs = Requirements(is_admin=False)
        self.other_user = CONFIG.users.find_user(
            reqs,
            black_list=[instance_info.user.auth_user])
        self.other_client = create_dbaas_client(self.other_user)

    @test
    def test_index_list(self):
        expected_attrs = ['id', 'links', 'name', 'status', 'flavor', 'volume']
        instances = dbaas.instances.list()
        assert_equal(200, dbaas.last_http_code)
        for instance in instances:
            instance_dict = instance._info
            with CheckInstance(instance_dict) as check:
                print("testing instance_dict=%s" % instance_dict)
                check.attrs_exist(instance_dict, expected_attrs,
                                  msg="Instance Index")
                check.links(instance_dict['links'])
                check.flavor()
                check.volume()

    @test
    def test_get_instance(self):
        expected_attrs = ['created', 'databases', 'flavor', 'hostname', 'id',
                          'links', 'name', 'status', 'updated', 'volume', 'ip']
        instance = dbaas.instances.get(instance_info.id)
        assert_equal(200, dbaas.last_http_code)
        instance_dict = instance._info
        print("instance_dict=%s" % instance_dict)
        with CheckInstance(instance_dict) as check:
            check.attrs_exist(instance_dict, expected_attrs,
                              msg="Get Instance")
            check.flavor()
            check.links(instance_dict['links'])
            check.used_volume()

    @test
    def test_get_instance_status(self):
        result = dbaas.instances.get(instance_info.id)
        assert_equal(200, dbaas.last_http_code)
        assert_equal("ACTIVE", result.status)

    @test
    def test_get_legacy_status(self):
        result = dbaas.instances.get(instance_info.id)
        assert_equal(200, dbaas.last_http_code)
        assert_true(result is not None)

    @test
    def test_get_legacy_status_notfound(self):
        assert_raises(exceptions.NotFound, dbaas.instances.get, -2)

    @test(enabled=CONFIG.values["reddwarf_main_instance_has_volume"])
    def test_volume_found(self):
        instance = dbaas.instances.get(instance_info.id)
        if create_new_instance():
            assert_equal(instance_info.volume['size'], instance.volume['size'])
        else:
            assert_true(isinstance(instance_info.volume['size'], int))
        if create_new_instance():
            assert_true(0.12 < instance.volume['used'] < 0.25)

    @test(enabled=do_not_delete_instance())
    def test_instance_not_shown_to_other_user(self):
        daffy_ids = [instance.id for instance in
                     self.other_client.instances.list()]
        assert_equal(200, self.other_client.last_http_code)
        admin_ids = [instance.id for instance in dbaas.instances.list()]
        assert_equal(200, dbaas.last_http_code)
        assert_equal(len(daffy_ids), 0)
        assert_not_equal(sorted(admin_ids), sorted(daffy_ids))
        assert_raises(exceptions.NotFound,
                      self.other_client.instances.get, instance_info.id)
        for id in admin_ids:
            assert_equal(daffy_ids.count(id), 0)

    @test(enabled=do_not_delete_instance())
    def test_instance_not_deleted_by_other_user(self):
        assert_raises(exceptions.NotFound,
                      self.other_client.instances.get, instance_info.id)
        assert_raises(exceptions.NotFound,
                      self.other_client.instances.delete, instance_info.id)

    @test(enabled=CONFIG.values['test_mgmt'])
    def test_mgmt_get_instance_after_started(self):
        result = dbaas_admin.management.show(instance_info.id)
        expected_attrs = ['account_id', 'addresses', 'created', 'databases',
                          'flavor', 'guest_status', 'host', 'hostname', 'id',
                          'name', 'root_enabled_at', 'root_enabled_by',
                          'server_state_description', 'status',
                          'updated', 'users', 'volume']
        with CheckInstance(result._info) as check:
            check.attrs_exist(result._info, expected_attrs,
                              msg="Mgmt get instance")
            check.flavor()
            check.guest_status()
            check.addresses()
            check.volume_mgmt()


@test(depends_on_groups=['dbaas.api.instances.actions'],
      groups=[GROUP, tests.INSTANCES, "dbaas.diagnostics"])
class CheckDiagnosticsAfterTests(object):
    """ Check the diagnostics after running api commands on an instance. """
    @test
    def test_check_diagnostics_on_instance_after_tests(self):
        diagnostics = dbaas_admin.diagnostics.get(instance_info.id)
        assert_equal(200, dbaas.last_http_code)
        diagnostic_tests_helper(diagnostics)
        msg = "Fat Pete has emerged. size (%s > 30MB)" % diagnostics.vmPeak
        assert_true(diagnostics.vmPeak < (30 * 1024), msg)


@test(depends_on=[WaitForGuestInstallationToFinish],
      depends_on_groups=[GROUP_USERS, GROUP_DATABASES, GROUP_ROOT],
      groups=[GROUP, GROUP_STOP])
class DeleteInstance(object):
    """ Delete the created instance """

    @time_out(3 * 60)
    @test(runs_after_groups=[GROUP_START,
                             GROUP_START_SIMPLE, GROUP_TEST, tests.INSTANCES])
    def test_delete(self):
        if do_not_delete_instance():
            CONFIG.get_report().log("TESTS_DO_NOT_DELETE_INSTANCE=True was "
                                    "specified, skipping delete...")
            raise SkipTest("TESTS_DO_NOT_DELETE_INSTANCE was specified.")
        global dbaas
        if not hasattr(instance_info, "initial_result"):
            raise SkipTest("Instance was never created, skipping test...")
        if CONFIG.white_box:
            # Change this code to get the volume using the API.
            # That way we can keep it while keeping it black box.
            admin_context = context.get_admin_context()
            volumes = db.volume_get_all_by_instance(admin_context(),
                                                    instance_info.local_id)
            instance_info.volume_id = volumes[0].id
        # Update the report so the logs inside the instance will be saved.
        CONFIG.get_report().update()
        dbaas.instances.delete(instance_info.id)

        attempts = 0
        try:
            time.sleep(1)
            result = True
            while result is not None:
                attempts += 1
                time.sleep(1)
                result = dbaas.instances.get(instance_info.id)
                assert_equal(200, dbaas.last_http_code)
                assert_equal("SHUTDOWN", result.status)
        except exceptions.NotFound:
            pass
        except Exception as ex:
            fail("A failure occured when trying to GET instance %s for the %d "
                 "time: %s" % (str(instance_info.id), attempts, str(ex)))

    @time_out(30)
    @test(enabled=CONFIG.values["reddwarf_can_have_volume"],
          depends_on=[test_delete])
    def test_volume_is_deleted(self):
        raise SkipTest("Cannot test volume is deleted from db.")
        try:
            while True:
                db.volume_get(instance_info.user_context,
                              instance_info.volume_id)
                time.sleep(1)
        except backend_exception.VolumeNotFound:
            pass

    #TODO: make sure that the actual instance, volume, guest status, and DNS
    #      entries are deleted.


@test(depends_on_classes=[CreateInstance, VerifyGuestStarted,
      WaitForGuestInstallationToFinish],
      groups=[GROUP, GROUP_START, GROUP_START_SIMPLE],
      enabled=CONFIG.values['test_mgmt'])
class VerifyInstanceMgmtInfo(object):

    @before_class
    def set_up(self):
        self.mgmt_details = dbaas_admin.management.show(instance_info.id)

    def _assert_key(self, k, expected):
        v = getattr(self.mgmt_details, k)
        err = "Key %r does not match expected value of %r (was %r)." \
              % (k, expected, v)
        assert_equal(str(v), str(expected), err)

    @test
    def test_id_matches(self):
        self._assert_key('id', instance_info.id)

    @test
    def test_bogus_instance_mgmt_data(self):
        # Make sure that a management call to a bogus API 500s.
        # The client reshapes the exception into just an OpenStackException.
        assert_raises(exceptions.NotFound,
                      dbaas_admin.management.show, -1)

    @test
    def test_mgmt_ips_associated(self):
        # Test that the management index properly associates an instances with
        # ONLY its IPs.
        mgmt_index = dbaas_admin.management.index()
        # Every instances has exactly one address.
        for instance in mgmt_index:
            assert_equal(1, len(instance.ips))

    @test
    def test_mgmt_data(self):
        # Test that the management API returns all the values we expect it to.
        info = instance_info
        ir = info.initial_result
        cid = ir.id
        instance_id = instance_info.local_id
        expected = {
            'id': ir.id,
            'name': ir.name,
            'account_id': info.user.auth_user,
            # TODO(hub-cap): fix this since its a flavor object now
            #'flavorRef': info.dbaas_flavor_href,
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

        if CONFIG.white_box:
            admin_context = context.get_admin_context()
            volumes = db.volume_get_all_by_instance(admin_context(),
                                                    instance_id)
            assert_equal(len(volumes), 1)
            volume = volumes[0]
            expected['volume'] = {
                'id': volume.id,
                'name': volume.display_name,
                'size': volume.size,
                'description': volume.display_description,
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


class CheckInstance(AttrCheck):
    """Class to check various attributes of Instance details"""

    def __init__(self, instance):
        super(CheckInstance, self).__init__()
        self.instance = instance

    def flavor(self):
        if 'flavor' not in self.instance:
            self.fail("'flavor' not found in instance.")
        else:
            expected_attrs = ['id', 'links']
            self.attrs_exist(self.instance['flavor'], expected_attrs,
                             msg="Flavor")
            self.links(self.instance['flavor']['links'])

    def volume_key_exists(self):
        if CONFIG.values['reddwarf_main_instance_has_volume']:
            if 'volume' not in self.instance:
                self.fail("'volume' not found in instance.")
                return False
            return True

    def volume(self):
        if not CONFIG.values["reddwarf_can_have_volume"]:
            return
        if self.volume_key_exists():
            expected_attrs = ['size']
            if not create_new_instance():
                expected_attrs.append('used')
            self.attrs_exist(self.instance['volume'], expected_attrs,
                             msg="Volumes")

    def used_volume(self):
        if not CONFIG.values["reddwarf_can_have_volume"]:
            return
        if self.volume_key_exists():
            expected_attrs = ['size', 'used']
            print self.instance
            self.attrs_exist(self.instance['volume'], expected_attrs,
                             msg="Volumes")

    def volume_mgmt(self):
        if self.volume_key_exists():
            expected_attrs = ['description', 'id', 'name', 'size']
            self.attrs_exist(self.instance['volume'], expected_attrs,
                             msg="Volumes")

    def addresses(self):
        expected_attrs = ['addr', 'version']
        print self.instance
        networks = ['usernet']
        for network in networks:
            for address in self.instance['addresses'][network]:
                self.attrs_exist(address, expected_attrs,
                                 msg="Address")

    def guest_status(self):
        expected_attrs = ['created_at', 'deleted', 'deleted_at', 'instance_id',
                          'state', 'state_description', 'updated_at']
        self.attrs_exist(self.instance['guest_status'], expected_attrs,
                         msg="Guest status")

    def mgmt_volume(self):
        expected_attrs = ['description', 'id', 'name', 'size']
        self.attrs_exist(self.instance['volume'], expected_attrs,
                         msg="Volume")


def diagnostic_tests_helper(diagnostics):
    print("diagnostics : %r" % diagnostics._info)
    expected_attrs = ['version', 'fdSize', 'vmSize', 'vmHwm', 'vmRss',
                      'vmPeak', 'threads']
    CheckInstance(None).attrs_exist(diagnostics._info, expected_attrs,
                                    msg="Diagnostics")
    assert_true(isinstance(diagnostics.fdSize, int))
    assert_true(isinstance(diagnostics.threads, int))
    assert_true(isinstance(diagnostics.vmHwm, int))
    assert_true(isinstance(diagnostics.vmPeak, int))
    assert_true(isinstance(diagnostics.vmRss, int))
    assert_true(isinstance(diagnostics.vmSize, int))
    actual_version = diagnostics.version
    update_test_conf = CONFIG.values.get("guest-update-test", None)
    if update_test_conf is not None:
        if actual_version == update_test_conf['next-version']:
            return  # This is acceptable but may not match the regex.
    version_pattern = re.compile(r'[a-f0-9]+')
    msg = "Version %s does not match pattern %s." % (actual_version,
                                                     version_pattern)
    assert_true(version_pattern.match(actual_version), msg)
