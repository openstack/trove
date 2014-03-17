# Copyright (c) 2011 OpenStack Foundation
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


from nose.tools import assert_equal
from troveclient.compat import exceptions

from proboscis import before_class
from proboscis import test
from proboscis.asserts import assert_raises
from proboscis.asserts import assert_true

from trove import tests
from trove.tests.util import create_dbaas_client
from trove.tests.util import test_config
from trove.tests.util.users import Requirements
from trove.tests.util.check import TypeCheck

GROUP = "dbaas.api.datastores"
NAME = "nonexistent"


@test(groups=[tests.DBAAS_API, GROUP, tests.PRE_INSTANCES],
      depends_on_groups=["services.initialize"])
class Datastores(object):

    @before_class
    def setUp(self):
        rd_user = test_config.users.find_user(
            Requirements(is_admin=False, services=["trove"]))
        rd_admin = test_config.users.find_user(
            Requirements(is_admin=True, services=["trove"]))
        self.rd_client = create_dbaas_client(rd_user)
        self.rd_admin = create_dbaas_client(rd_admin)

    @test
    def test_datastore_list_attrs(self):
        datastores = self.rd_client.datastores.list()
        for datastore in datastores:
            with TypeCheck('Datastore', datastore) as check:
                check.has_field("id", basestring)
                check.has_field("name", basestring)
                check.has_field("links", list)

    @test
    def test_datastore_get_attrs(self):
        datastore = self.rd_client.datastores.get(test_config.
                                                  dbaas_datastore)
        with TypeCheck('Datastore', datastore) as check:
            check.has_field("id", basestring)
            check.has_field("name", basestring)
            check.has_field("links", list)
        assert_equal(datastore.name, test_config.dbaas_datastore)

    @test
    def test_datastore_not_found(self):
        try:
            assert_raises(exceptions.NotFound,
                          self.rd_client.datastores.get, NAME)
        except exceptions.BadRequest as e:
            assert_equal(e.message,
                         "Datastore '%s' cannot be found." % NAME)

    @test
    def test_datastore_version_list_attrs(self):
        versions = self.rd_client.datastore_versions.list(test_config.
                                                          dbaas_datastore)
        for version in versions:
            with TypeCheck('DatastoreVersion', version) as check:
                check.has_field("id", basestring)
                check.has_field("name", basestring)
                check.has_field("links", list)

    @test
    def test_datastore_version_get_attrs(self):
        version = self.rd_client.datastore_versions.get(
            test_config.dbaas_datastore, test_config.dbaas_datastore_version)
        with TypeCheck('DatastoreVersion', version) as check:
            check.has_field("id", basestring)
            check.has_field("name", basestring)
            check.has_field("datastore", basestring)
            check.has_field("links", list)
        assert_equal(version.name, test_config.dbaas_datastore_version)

    @test
    def test_datastore_version_get_by_uuid_attrs(self):
        version = self.rd_client.datastore_versions.get_by_uuid(
            test_config.dbaas_datastore_version_id)
        with TypeCheck('DatastoreVersion', version) as check:
            check.has_field("id", basestring)
            check.has_field("name", basestring)
            check.has_field("datastore", basestring)
            check.has_field("links", list)
        assert_equal(version.name, test_config.dbaas_datastore_version)

    @test
    def test_datastore_version_not_found(self):
        try:
            assert_raises(exceptions.NotFound,
                          self.rd_client.datastore_versions.get,
                          test_config.dbaas_datastore, NAME)
        except exceptions.BadRequest as e:
            assert_equal(e.message,
                         "Datastore version '%s' cannot be found." % NAME)

    @test
    def test_datastore_get_by_uuid(self):
        datastore = self.rd_client.datastores.get(
            test_config.dbaas_datastore_id)
        with TypeCheck('Datastore', datastore) as check:
            check.has_field("id", basestring)
            check.has_field("name", basestring)
            check.has_field("links", list)
        assert_equal(datastore.id, test_config.dbaas_datastore_id)

    @test
    def test_datastore_version_list_by_uuid(self):
        versions = self.rd_client.datastore_versions.list(
            test_config.dbaas_datastore_id)
        for version in versions:
            with TypeCheck('DatastoreVersion', version) as check:
                check.has_field("id", basestring)
                check.has_field("name", basestring)
                check.has_field("links", list)

    @test
    def test_datastore_version_get_by_uuid(self):
        version = self.rd_client.datastore_versions.get(
            test_config.dbaas_datastore_id,
            test_config.dbaas_datastore_version)
        with TypeCheck('DatastoreVersion', version) as check:
            check.has_field("id", basestring)
            check.has_field("name", basestring)
            check.has_field("datastore", basestring)
            check.has_field("links", list)
        assert_equal(version.name, test_config.dbaas_datastore_version)

    @test
    def test_datastore_version_invalid_uuid(self):
        try:
            self.rd_client.datastore_versions.get_by_uuid(
                test_config.dbaas_datastore_version)
        except exceptions.BadRequest as e:
            assert_equal(e.message,
                         "Datastore version '%s' cannot be found." %
                         test_config.dbaas_datastore_version)

    @test
    def test_datastore_with_no_active_versions_is_hidden(self):
        datastores = self.rd_client.datastores.list()
        id_list = [datastore.id for datastore in datastores]
        id_no_versions = test_config.dbaas_datastore_id_no_versions
        assert_true(id_no_versions not in id_list)

    @test
    def test_datastore_with_no_active_versions_is_visible_for_admin(self):
        datastores = self.rd_admin.datastores.list()
        id_list = [datastore.id for datastore in datastores]
        id_no_versions = test_config.dbaas_datastore_id_no_versions
        assert_true(id_no_versions in id_list)
