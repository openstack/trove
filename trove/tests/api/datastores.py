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
from proboscis.asserts import assert_raises
from proboscis.asserts import assert_true
from proboscis import before_class
from proboscis import test
from troveclient.compat import exceptions

from trove import tests
from trove.tests.util.check import TypeCheck
from trove.tests.util import create_dbaas_client
from trove.tests.util import test_config
from trove.tests.util.users import Requirements

NAME = "nonexistent"


@test(groups=[tests.DBAAS_API_DATASTORES],
      depends_on_groups=[tests.DBAAS_API_VERSIONS])
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
                check.has_field("id", str)
                check.has_field("name", str)
                check.has_field("links", list)
                check.has_field("versions", list)

    @test
    def test_datastore_get(self):
        # Test get by name
        datastore_by_name = self.rd_client.datastores.get(
            test_config.dbaas_datastore)
        with TypeCheck('Datastore', datastore_by_name) as check:
            check.has_field("id", str)
            check.has_field("name", str)
            check.has_field("links", list)
        assert_equal(datastore_by_name.name, test_config.dbaas_datastore)

        # test get by id
        datastore_by_id = self.rd_client.datastores.get(
            datastore_by_name.id)
        with TypeCheck('Datastore', datastore_by_id) as check:
            check.has_field("id", str)
            check.has_field("name", str)
            check.has_field("links", list)
            check.has_field("versions", list)
        assert_equal(datastore_by_id.id, datastore_by_name.id)

    @test
    def test_datastore_not_found(self):
        try:
            assert_raises(exceptions.NotFound,
                          self.rd_client.datastores.get, NAME)
        except exceptions.BadRequest as e:
            assert_equal(e.message,
                         "Datastore '%s' cannot be found." % NAME)

    @test
    def test_create_inactive_datastore_by_admin(self):
        datastores = self.rd_client.datastores.list()
        for ds in datastores:
            if ds.name == test_config.dbaas_datastore_name_no_versions:
                for version in ds.versions:
                    if version['name'] == 'inactive_version':
                        return

        # Create datastore version for testing
        # 'Test_Datastore_1' is also used in other test cases.
        # Will be deleted in test_delete_datastore_version
        self.rd_admin.mgmt_datastore_versions.create(
            "inactive_version", test_config.dbaas_datastore_name_no_versions,
            "test_manager", None, image_tags=['trove'],
            active='false', default='false'
        )

    @test(depends_on=[test_create_inactive_datastore_by_admin])
    def test_datastore_with_no_active_versions_is_hidden(self):
        datastores = self.rd_client.datastores.list()
        name_list = [datastore.name for datastore in datastores]

        assert_true(
            test_config.dbaas_datastore_name_no_versions not in name_list)

    @test(depends_on=[test_create_inactive_datastore_by_admin])
    def test_datastore_with_no_active_versions_is_visible_for_admin(self):
        datastores = self.rd_admin.datastores.list()
        name_list = [datastore.name for datastore in datastores]
        assert_true(test_config.dbaas_datastore_name_no_versions in name_list)


@test(groups=[tests.DBAAS_API_DATASTORES])
class DatastoreVersions(object):
    @before_class
    def setUp(self):
        rd_user = test_config.users.find_user(
            Requirements(is_admin=False, services=["trove"]))
        self.rd_client = create_dbaas_client(rd_user)
        self.datastore_active = self.rd_client.datastores.get(
            test_config.dbaas_datastore)
        self.datastore_version_active = self.rd_client.datastore_versions.list(
            self.datastore_active.id)[0]

    @test
    def test_datastore_version_list_attrs(self):
        versions = self.rd_client.datastore_versions.list(
            self.datastore_active.name)
        for version in versions:
            with TypeCheck('DatastoreVersion', version) as check:
                check.has_field("id", str)
                check.has_field("name", str)
                check.has_field("links", list)

    @test
    def test_datastore_version_get_attrs(self):
        version = self.rd_client.datastore_versions.get(
            self.datastore_active.name, self.datastore_version_active.name)
        with TypeCheck('DatastoreVersion', version) as check:
            check.has_field("id", str)
            check.has_field("name", str)
            check.has_field("datastore", str)
            check.has_field("links", list)
        assert_equal(version.name, self.datastore_version_active.name)

    @test
    def test_datastore_version_get_by_uuid_attrs(self):
        version = self.rd_client.datastore_versions.get_by_uuid(
            self.datastore_version_active.id)
        with TypeCheck('DatastoreVersion', version) as check:
            check.has_field("id", str)
            check.has_field("name", str)
            check.has_field("datastore", str)
            check.has_field("links", list)
        assert_equal(version.name, self.datastore_version_active.name)

    @test
    def test_datastore_version_not_found(self):
        try:
            assert_raises(exceptions.NotFound,
                          self.rd_client.datastore_versions.get,
                          self.datastore_active.name, NAME)
        except exceptions.BadRequest as e:
            assert_equal(e.message,
                         "Datastore version '%s' cannot be found." % NAME)

    @test
    def test_datastore_version_list_by_uuid(self):
        versions = self.rd_client.datastore_versions.list(
            self.datastore_active.id)
        for version in versions:
            with TypeCheck('DatastoreVersion', version) as check:
                check.has_field("id", str)
                check.has_field("name", str)
                check.has_field("links", list)

    @test
    def test_datastore_version_get_by_uuid(self):
        version = self.rd_client.datastore_versions.get(
            self.datastore_active.id, self.datastore_version_active.id)
        with TypeCheck('DatastoreVersion', version) as check:
            check.has_field("id", str)
            check.has_field("name", str)
            check.has_field("datastore", str)
            check.has_field("links", list)
        assert_equal(version.name, self.datastore_version_active.name)

    @test
    def test_datastore_version_invalid_uuid(self):
        try:
            self.rd_client.datastore_versions.get_by_uuid(
                self.datastore_version_active.id)
        except exceptions.BadRequest as e:
            assert_equal(e.message,
                         "Datastore version '%s' cannot be found." %
                         test_config.dbaas_datastore_version)
