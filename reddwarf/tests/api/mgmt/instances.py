#    Copyright 2011 OpenStack LLC
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

from reddwarfclient import exceptions

from proboscis import before_class
from proboscis import test
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_raises
from proboscis.asserts import assert_true
from proboscis.check import Check

from reddwarf import tests
from reddwarf.tests.config import CONFIG
from reddwarf.tests.util import create_client
from reddwarf.tests.util import create_dbaas_client
from reddwarf.tests.util.users import Requirements
from reddwarf.tests.util.check import CollectionCheck
from reddwarf.tests.util.check import TypeCheck

from reddwarf.tests.api.instances import CreateInstance
from reddwarf.tests.api.instances import instance_info
from reddwarf.tests.api.instances import GROUP_START
from reddwarf.tests.api.instances import GROUP_TEST
from reddwarf.tests.util import poll_until

GROUP = "dbaas.api.mgmt.instances"


@test(groups=[GROUP])
def mgmt_index_requires_admin_account():
    """ Verify that an admin context is required to call this function. """
    client = create_client(is_admin=False)
    assert_raises(exceptions.Unauthorized, client.management.index)


# These functions check some dictionaries in the returned response.
def flavor_check(flavor):
    with CollectionCheck("flavor", flavor) as check:
        check.has_element("id", basestring)
        check.has_element("links", list)


def guest_status_check(guest_status):
    with CollectionCheck("guest_status", guest_status) as check:
        check.has_element("state_description", basestring)


def volume_check(volume):
    with CollectionCheck("volume", volume) as check:
        check.has_element("id", basestring)
        check.has_element("size", int)
        check.has_element("used", float)


@test(depends_on_groups=[GROUP_START], groups=[GROUP, GROUP_TEST])
def mgmt_instance_get():
    """ Tests the mgmt instances index method. """
    reqs = Requirements(is_admin=True)
    user = CONFIG.users.find_user(reqs)
    client = create_dbaas_client(user)
    mgmt = client.management
    # Grab the info.id created by the main instance test which is stored in
    # a global.
    id = instance_info.id
    api_instance = mgmt.show(id)

    # Print out all fields for extra info if the test fails.
    for name in dir(api_instance):
        print(str(name) + "=" + str(getattr(api_instance, name)))
    with TypeCheck("instance", api_instance) as instance:
        instance.has_field('created', basestring)
        instance.has_field('deleted', bool)
        # If the instance hasn't been deleted, this should be false... but
        # lets avoid creating more ordering work.
        instance.has_field('deleted_at', (basestring, None))
        instance.has_field('flavor', dict, flavor_check)
        instance.has_field('guest_status', dict, guest_status_check)
        instance.has_field('id', basestring)
        instance.has_field('links', list)
        instance.has_field('name', basestring)
        #instance.has_field('server_status', basestring)
        instance.has_field('status', basestring)
        instance.has_field('tenant_id', basestring)
        instance.has_field('updated', basestring)
        # Can be None if no volume is given on this instance.
        if CONFIG.reddwarf_main_instance_has_volume:
            instance.has_field('volume', dict, volume_check)
        else:
            instance.has_field('volume', None)
        #TODO: Validate additional fields, assert no extra fields exist.
    with CollectionCheck("server", api_instance.server) as server:
        server.has_element("addresses", dict)
        server.has_element("deleted", bool)
        server.has_element("deleted_at", (basestring, None))
        server.has_element("host", basestring)
        server.has_element("id", basestring)
        server.has_element("local_id", int)
        server.has_element("name", basestring)
        server.has_element("status", basestring)
        server.has_element("tenant_id", basestring)
    if CONFIG.reddwarf_main_instance_has_volume:
        with CollectionCheck("volume", api_instance.volume) as volume:
            volume.has_element("attachments", list)
            volume.has_element("availability_zone", basestring)
            volume.has_element("created_at", (basestring, None))
            volume.has_element("id", basestring)
            volume.has_element("size", int)
            volume.has_element("status", basestring)


@test(groups=["fake." + GROUP])
class WhenMgmtInstanceGetIsCalledButServerIsNotReady(object):

    @before_class
    def set_up(self):
        """Create client for mgmt instance test (2)."""
        if not CONFIG.fake_mode:
            raise SkipTest("This test only works in fake mode.")
        self.client = create_client(is_admin=True)
        self.mgmt = self.client.management
        # Fake nova will fail a server ending with 'test_SERVER_ERROR'."
        # Fake volume will fail if the size is 13.
        # TODO(tim.simpson): This would be a lot nicer looking if we used a
        #                    traditional mock framework.
        response = self.client.instances.create('test_SERVER_ERROR', 1,
                                                {'size': 13}, [])
        poll_until(lambda: self.client.instances.get(response.id),
                   lambda instance: instance.status == 'ERROR',
                   time_out=10)
        self.id = response.id

    @test
    def mgmt_instance_get(self):
        """Tests the mgmt get call works when the Nova server isn't ready."""
        api_instance = self.mgmt.show(self.id)
        # Print out all fields for extra info if the test fails.
        for name in dir(api_instance):
            print(str(name) + "=" + str(getattr(api_instance, name)))
        # Print out all fields for extra info if the test fails.
        for name in dir(api_instance):
            print(str(name) + "=" + str(getattr(api_instance, name)))
        with TypeCheck("instance", api_instance) as instance:
            instance.has_field('created', basestring)
            instance.has_field('deleted', bool)
            # If the instance hasn't been deleted, this should be false... but
            # lets avoid creating more ordering work.
            instance.has_field('deleted_at', (basestring, None))
            instance.has_field('flavor', dict, flavor_check)
            instance.has_field('guest_status', dict, guest_status_check)
            instance.has_field('id', basestring)
            instance.has_field('links', list)
            instance.has_field('name', basestring)
            #instance.has_field('server_status', basestring)
            instance.has_field('status', basestring)
            instance.has_field('tenant_id', basestring)
            instance.has_field('updated', basestring)
            # Can be None if no volume is given on this instance.
            instance.has_field('server', None)
            instance.has_field('volume', None)
            #TODO: Validate additional fields, assert no extra fields exist.


@test(depends_on_classes=[CreateInstance], groups=[GROUP])
class MgmtInstancesIndex(object):
    """ Tests the mgmt instances index method. """

    @before_class
    def setUp(self):
        """Create client for mgmt instance test."""
        reqs = Requirements(is_admin=True)
        self.user = CONFIG.users.find_user(reqs)
        self.client = create_dbaas_client(self.user)

    @test
    def test_mgmt_instance_index_fields_present(self):
        """
        Verify that all the expected fields are returned by the index method.
        """
        expected_fields = [
            'created',
            'deleted',
            'deleted_at',
            'flavor',
            'id',
            'links',
            'name',
            'server',
            'status',
            'task_description',
            'tenant_id',
            'updated',
            'volume',
        ]
        index = self.client.management.index()
        for instance in index:
            with Check() as check:
                for field in expected_fields:
                    check.true(hasattr(instance, field),
                               "Index lacks field %s" % field)

    @test
    def test_mgmt_instance_index_check_filter(self):
        """
        Make sure that the deleted= filter works as expected, and no instances
        are excluded.
        """
        instance_counts = []
        for deleted_filter in (True, False):
            filtered_index = self.client.management.index(
                deleted=deleted_filter)
            instance_counts.append(len(filtered_index))
        for instance in filtered_index:
                # Every instance listed here should have the proper value
                # for 'deleted'.
                assert_equal(deleted_filter, instance.deleted)
        full_index = self.client.management.index()
        # There should be no instances that are neither deleted or not-deleted.
        assert_equal(len(full_index), sum(instance_counts))
