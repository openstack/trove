#    Copyright 2011 OpenStack Foundation
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

import time

from troveclient.compat import exceptions

from proboscis import before_class
from proboscis import test
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_raises
from proboscis.asserts import assert_true
from proboscis.decorators import time_out

from trove import tests

from trove.tests import util
from trove.tests.api.instances import GROUP_START
from trove.tests.api.instances import instance_info
from trove.tests.util import test_config

GROUP = "dbaas.api.databases"
FAKE = test_config.values['fake_mode']


@test(depends_on_groups=[GROUP_START],
      groups=[tests.INSTANCES, "dbaas.guest.mysql"],
      enabled=not test_config.values['fake_mode'])
class TestMysqlAccess(object):
    """
        Make sure that MySQL server was secured.
    """

    @time_out(60 * 2)
    @test
    def test_mysql_admin(self):
        """Ensure we aren't allowed access with os_admin and wrong password."""
        util.mysql_connection().assert_fails(
            instance_info.get_address(), "os_admin", "asdfd-asdf234")

    @test
    def test_mysql_root(self):
        """Ensure we aren't allowed access with root and wrong password."""
        util.mysql_connection().assert_fails(
            instance_info.get_address(), "root", "dsfgnear")


@test(depends_on_groups=[GROUP_START],
      depends_on_classes=[TestMysqlAccess],
      groups=[tests.DBAAS_API, GROUP, tests.INSTANCES])
class TestDatabases(object):
    """
    Test the creation and deletion of additional MySQL databases
    """

    dbname = "third #?@some_-"
    dbname_urlencoded = "third%20%23%3F%40some_-"

    dbname2 = "seconddb"
    created_dbs = [dbname, dbname2]
    system_dbs = ['information_schema', 'mysql', 'lost+found']

    @before_class
    def setUp(self):
        self.dbaas = util.create_dbaas_client(instance_info.user)
        self.dbaas_admin = util.create_dbaas_client(instance_info.admin_user)

    @test
    def test_cannot_create_taboo_database_names(self):
        for name in self.system_dbs:
            databases = [{"name": name, "character_set": "latin2",
                          "collate": "latin2_general_ci"}]
            assert_raises(exceptions.BadRequest, self.dbaas.databases.create,
                          instance_info.id, databases)
            assert_equal(400, self.dbaas.last_http_code)

    @test
    def test_create_database(self):
        databases = []
        databases.append({"name": self.dbname, "character_set": "latin2",
                          "collate": "latin2_general_ci"})
        databases.append({"name": self.dbname2})

        self.dbaas.databases.create(instance_info.id, databases)
        assert_equal(202, self.dbaas.last_http_code)
        if not FAKE:
            time.sleep(5)

    @test(depends_on=[test_create_database])
    def test_create_database_list(self):
        databases = self.dbaas.databases.list(instance_info.id)
        assert_equal(200, self.dbaas.last_http_code)
        found = False
        for db in self.created_dbs:
            for result in databases:
                if result.name == db:
                    found = True
            assert_true(found, "Database '%s' not found in result" % db)
            found = False

    @test(depends_on=[test_create_database])
    def test_fails_when_creating_a_db_twice(self):
        databases = []
        databases.append({"name": self.dbname, "character_set": "latin2",
                          "collate": "latin2_general_ci"})
        databases.append({"name": self.dbname2})

        assert_raises(exceptions.BadRequest, self.dbaas.databases.create,
                      instance_info.id, databases)
        assert_equal(400, self.dbaas.last_http_code)

    @test
    def test_create_database_list_system(self):
        #Databases that should not be returned in the list
        databases = self.dbaas.databases.list(instance_info.id)
        assert_equal(200, self.dbaas.last_http_code)
        found = False
        for db in self.system_dbs:
            found = any(result.name == db for result in databases)
            msg = "Database '%s' SHOULD NOT be found in result" % db
            assert_false(found, msg)
            found = False

    @test
    def test_create_database_on_missing_instance(self):
        databases = [{"name": "invalid_db", "character_set": "latin2",
                      "collate": "latin2_general_ci"}]
        assert_raises(exceptions.NotFound, self.dbaas.databases.create,
                      -1, databases)
        assert_equal(404, self.dbaas.last_http_code)

    @test(runs_after=[test_create_database])
    def test_delete_database(self):
        self.dbaas.databases.delete(instance_info.id, self.dbname_urlencoded)
        assert_equal(202, self.dbaas.last_http_code)
        if not FAKE:
            time.sleep(5)
        dbs = self.dbaas.databases.list(instance_info.id)
        assert_equal(200, self.dbaas.last_http_code)
        found = any(result.name == self.dbname_urlencoded for result in dbs)
        assert_false(found, "Database '%s' SHOULD NOT be found in result" %
                     self.dbname_urlencoded)

    @test(runs_after=[test_delete_database])
    def test_cannot_delete_taboo_database_names(self):
        for name in self.system_dbs:
            assert_raises(exceptions.BadRequest, self.dbaas.databases.delete,
                          instance_info.id, name)
            assert_equal(400, self.dbaas.last_http_code)

    @test(runs_after=[test_delete_database])
    def test_delete_database_on_missing_instance(self):
        assert_raises(exceptions.NotFound, self.dbaas.databases.delete,
                      -1, self.dbname_urlencoded)
        assert_equal(404, self.dbaas.last_http_code)

    @test
    def test_database_name_too_long(self):
        databases = []
        name = ("aasdlkhaglkjhakjdkjgfakjgadgfkajsg"
                "34523dfkljgasldkjfglkjadsgflkjagsdd")
        databases.append({"name": name})
        assert_raises(exceptions.BadRequest, self.dbaas.databases.create,
                      instance_info.id, databases)
        assert_equal(400, self.dbaas.last_http_code)

    @test
    def test_invalid_database_name(self):
        databases = []
        databases.append({"name": "sdfsd,"})
        assert_raises(exceptions.BadRequest, self.dbaas.databases.create,
                      instance_info.id, databases)
        assert_equal(400, self.dbaas.last_http_code)

    @test
    def test_pagination(self):
        databases = []
        databases.append({"name": "Sprockets", "character_set": "latin2",
                          "collate": "latin2_general_ci"})
        databases.append({"name": "Cogs"})
        databases.append({"name": "Widgets"})

        self.dbaas.databases.create(instance_info.id, databases)
        assert_equal(202, self.dbaas.last_http_code)
        if not FAKE:
            time.sleep(5)
        limit = 2
        databases = self.dbaas.databases.list(instance_info.id, limit=limit)
        assert_equal(200, self.dbaas.last_http_code)
        marker = databases.next

        # Better get only as many as we asked for
        assert_true(len(databases) <= limit)
        assert_true(databases.next is not None)
        assert_equal(marker, databases[-1].name)
        marker = databases.next

        # I better get new databases if I use the marker I was handed.
        databases = self.dbaas.databases.list(instance_info.id, limit=limit,
                                              marker=marker)
        assert_equal(200, self.dbaas.last_http_code)
        assert_true(marker not in [database.name for database in databases])

        # Now fetch again with a larger limit.
        databases = self.dbaas.databases.list(instance_info.id)
        assert_equal(200, self.dbaas.last_http_code)
        assert_true(databases.next is None)
