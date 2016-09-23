# Copyright (c) 2011 OpenStack Foundation
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
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

from nose.tools import assert_equal
from nose.tools import assert_false
from nose.tools import assert_true
from proboscis.asserts import assert_raises
from proboscis import before_class
from proboscis.decorators import time_out
from proboscis import test
from trove.common.utils import poll_until
from trove import tests
from trove.tests.api.instances import TIMEOUT_INSTANCE_CREATE
from trove.tests.util.check import AttrCheck
from trove.tests.util import create_dbaas_client
from trove.tests.util import create_nova_client
from trove.tests.util import test_config
from trove.tests.util.users import Requirements
from troveclient.compat import exceptions
from troveclient.v1.flavors import Flavor

GROUP = "dbaas.api.flavors"
GROUP_DS = "dbaas.api.datastores"
FAKE_MODE = test_config.values['fake_mode']

servers_flavors = None
dbaas_flavors = None
user = None


def assert_attributes_equal(name, os_flavor, dbaas_flavor):
    """Given an attribute name and two objects,
        ensures the attribute is equal.
    """
    assert_true(hasattr(os_flavor, name),
                "open stack flavor did not have attribute %s" % name)
    assert_true(hasattr(dbaas_flavor, name),
                "dbaas flavor did not have attribute %s" % name)
    expected = getattr(os_flavor, name)
    actual = getattr(dbaas_flavor, name)
    assert_equal(expected, actual,
                 'DBaas flavor differs from Open Stack on attribute ' + name)


def assert_flavors_roughly_equivalent(os_flavor, dbaas_flavor):
    assert_attributes_equal('name', os_flavor, dbaas_flavor)
    assert_attributes_equal('ram', os_flavor, dbaas_flavor)


def assert_link_list_is_equal(flavor):
    assert_true(hasattr(flavor, 'links'))
    assert_true(flavor.links)

    if flavor.id:
        flavor_id = str(flavor.id)
    else:
        flavor_id = flavor.str_id

    for link in flavor.links:
        href = link['href']

        if "self" in link['rel']:
            expected_href = os.path.join(test_config.dbaas_url, "flavors",
                                         str(flavor.id))
            url = test_config.dbaas_url.replace('http:', 'https:', 1)
            msg = ("REL HREF %s doesn't start with %s" %
                   (href, test_config.dbaas_url))
            assert_true(href.startswith(url), msg)
            url = os.path.join("flavors", flavor_id)
            msg = "REL HREF %s doesn't end in '%s'" % (href, url)
            assert_true(href.endswith(url), msg)
        elif "bookmark" in link['rel']:
            base_url = test_config.version_url.replace('http:', 'https:', 1)
            expected_href = os.path.join(base_url, "flavors", flavor_id)
            msg = 'bookmark "href" must be %s, not %s' % (expected_href, href)
            assert_equal(href, expected_href, msg)
        else:
            assert_false(True, "Unexpected rel - %s" % link['rel'])


@test(groups=[tests.DBAAS_API, GROUP, GROUP_DS, tests.PRE_INSTANCES],
      depends_on_groups=["services.initialize"])
class Flavors(object):
    @before_class
    def setUp(self):
        rd_user = test_config.users.find_user(
            Requirements(is_admin=False, services=["trove"]))
        self.rd_client = create_dbaas_client(rd_user)

        if test_config.nova_client is not None:
            nova_user = test_config.users.find_user(
                Requirements(services=["nova"]))
            self.nova_client = create_nova_client(nova_user)

    def get_expected_flavors(self):
        # If we have access to the client, great! Let's use that as the flavors
        # returned by Trove should be identical.
        if test_config.nova_client is not None:
            return self.nova_client.flavors.list()
        # If we don't have access to the client the flavors need to be spelled
        # out in the config file.
        flavors = [Flavor(Flavors, flavor_dict, loaded=True)
                   for flavor_dict in test_config.flavors]
        return flavors

    @test
    def confirm_flavors_lists_nearly_identical(self):
        os_flavors = self.get_expected_flavors()
        dbaas_flavors = self.rd_client.flavors.list()

        print("Open Stack Flavors:")
        print(os_flavors)
        print("DBaaS Flavors:")
        print(dbaas_flavors)
        # Length of both flavors list should be identical.
        assert_equal(len(os_flavors), len(dbaas_flavors))
        for os_flavor in os_flavors:
            found_index = None
            for index, dbaas_flavor in enumerate(dbaas_flavors):
                if os_flavor.name == dbaas_flavor.name:
                    msg = ("Flavor ID '%s' appears in elements #%s and #%d." %
                           (dbaas_flavor.id, str(found_index), index))
                    assert_true(found_index is None, msg)
                    assert_flavors_roughly_equivalent(os_flavor, dbaas_flavor)
                    found_index = index
            msg = "Some flavors from OS list were missing in DBAAS list."
            assert_false(found_index is None, msg)
        for flavor in dbaas_flavors:
            assert_link_list_is_equal(flavor)

    @test
    def test_flavor_list_attrs(self):
        allowed_attrs = ['id', 'name', 'ram', 'vcpus', 'disk', 'links',
                         'ephemeral', 'local_storage', 'str_id']
        flavors = self.rd_client.flavors.list()
        attrcheck = AttrCheck()
        for flavor in flavors:
            flavor_dict = flavor._info
            attrcheck.contains_allowed_attrs(
                flavor_dict, allowed_attrs,
                msg="Flavors list")
            attrcheck.links(flavor_dict['links'])

    @test
    def test_flavor_get_attrs(self):
        allowed_attrs = ['id', 'name', 'ram', 'vcpus', 'disk', 'links',
                         'ephemeral', 'local_storage', 'str_id']
        flavor = self.rd_client.flavors.get(1)
        attrcheck = AttrCheck()
        flavor_dict = flavor._info
        attrcheck.contains_allowed_attrs(
            flavor_dict, allowed_attrs,
            msg="Flavor Get 1")
        attrcheck.links(flavor_dict['links'])

    @test
    def test_flavor_not_found(self):
        assert_raises(exceptions.NotFound,
                      self.rd_client.flavors.get, "foo")

    @test
    def test_flavor_list_datastore_version_associated_flavors(self):
        datastore = self.rd_client.datastores.get(
            test_config.dbaas_datastore)
        dbaas_flavors = (self.rd_client.flavors.
                         list_datastore_version_associated_flavors(
                             datastore=test_config.dbaas_datastore,
                             version_id=datastore.default_version))
        os_flavors = self.get_expected_flavors()
        assert_equal(len(dbaas_flavors), len(os_flavors))
        # verify flavor lists are identical
        for os_flavor in os_flavors:
            found_index = None
            for index, dbaas_flavor in enumerate(dbaas_flavors):
                if os_flavor.name == dbaas_flavor.name:
                    msg = ("Flavor ID '%s' appears in elements #%s and #%d." %
                           (dbaas_flavor.id, str(found_index), index))
                    assert_true(found_index is None, msg)
                    assert_flavors_roughly_equivalent(os_flavor, dbaas_flavor)
                    found_index = index
            msg = "Some flavors from OS list were missing in DBAAS list."
            assert_false(found_index is None, msg)
        for flavor in dbaas_flavors:
            assert_link_list_is_equal(flavor)


@test(runs_after=[Flavors],
      groups=[tests.DBAAS_API, GROUP, GROUP_DS],
      depends_on_groups=["services.initialize"],
      enabled=FAKE_MODE)
class DatastoreFlavorAssociation(object):
    @before_class
    def setUp(self):
        rd_user = test_config.users.find_user(
            Requirements(is_admin=False, services=["trove"]))
        self.rd_client = create_dbaas_client(rd_user)

        self.datastore = self.rd_client.datastores.get(
            test_config.dbaas_datastore)
        self.name1 = "test_instance1"
        self.name2 = "test_instance2"
        self.volume = {'size': 2}
        self.instance_id = None

    @test
    @time_out(TIMEOUT_INSTANCE_CREATE)
    def test_create_instance_with_valid_flavor_association(self):
        # all the nova flavors are associated with the default datastore
        result = self.rd_client.instances.create(
            name=self.name1, flavor_id='1', volume=self.volume,
            datastore=self.datastore.id)
        self.instance_id = result.id
        assert_equal(200, self.rd_client.last_http_code)

        def result_is_active():
            instance = self.rd_client.instances.get(self.instance_id)
            if instance.status == "ACTIVE":
                return True
            else:
                # If its not ACTIVE, anything but BUILD must be
                # an error.
                assert_equal("BUILD", instance.status)
                return False

        poll_until(result_is_active)
        self.rd_client.instances.delete(self.instance_id)

    @test(runs_after=[test_create_instance_with_valid_flavor_association])
    def test_create_instance_with_invalid_flavor_association(self):
        dbaas_flavors = (self.rd_client.flavors.
                         list_datastore_version_associated_flavors(
                             datastore=test_config.dbaas_datastore,
                             version_id=self.datastore.default_version))
        self.flavor_not_associated = None
        os_flavors = Flavors().get_expected_flavors()
        for os_flavor in os_flavors:
            if os_flavor not in dbaas_flavors:
                    self.flavor_not_associated = os_flavor.id
            break
        if self.flavor_not_associated is not None:
            assert_raises(exceptions.BadRequest,
                          self.rd_client.instances.create, self.name2,
                          flavor_not_associated, self.volume,
                          datastore=self.datastore.id)
