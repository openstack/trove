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

from proboscis import after_class
from proboscis import before_class
from proboscis import test
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_raises
from proboscis.asserts import assert_true
from proboscis.asserts import fail

from trove import tests
from trove.tests.api.databases import TestDatabases
from trove.tests.api.instances import instance_info
from trove.tests import util
from trove.tests.util import test_config
from trove.tests.api.databases import TestMysqlAccess

import urllib


GROUP = "dbaas.api.users"
FAKE = test_config.values['fake_mode']


@test(depends_on_classes=[TestMysqlAccess],
      groups=[tests.DBAAS_API, GROUP, tests.INSTANCES],
      runs_after=[TestDatabases])
class TestUsers(object):
    """
    Test the creation and deletion of users
    """

    username = "tes!@#tuser"
    password = "testpa$^%ssword"
    username1 = "anous*&^er"
    password1 = "anopas*?.sword"
    db1 = "usersfirstdb"
    db2 = "usersseconddb"

    created_users = [username, username1]
    system_users = ['root', 'debian_sys_maint']

    def __init__(self):
        self.dbaas = util.create_dbaas_client(instance_info.user)
        self.dbaas_admin = util.create_dbaas_client(instance_info.admin_user)

    @before_class
    def setUp(self):
        databases = [{"name": self.db1, "character_set": "latin2",
                      "collate": "latin2_general_ci"},
                     {"name": self.db2}]
        try:
            self.dbaas.databases.create(instance_info.id, databases)
        except exceptions.BadRequest as e:
            if "Validation error" in e.message:
                raise e
        if not FAKE:
            time.sleep(5)

    @after_class
    def tearDown(self):
        self.dbaas.databases.delete(instance_info.id, self.db1)
        self.dbaas.databases.delete(instance_info.id, self.db2)

    @test()
    def test_delete_nonexistent_user(self):
        assert_raises(exceptions.NotFound, self.dbaas.users.delete,
                      instance_info.id, "thisuserDNE")
        assert_equal(404, self.dbaas.last_http_code)

    @test()
    def test_create_users(self):
        users = []
        users.append({"name": self.username, "password": self.password,
                      "databases": [{"name": self.db1}]})
        users.append({"name": self.username1, "password": self.password1,
                     "databases": [{"name": self.db1}, {"name": self.db2}]})
        self.dbaas.users.create(instance_info.id, users)
        assert_equal(202, self.dbaas.last_http_code)

        # Do we need this?
        if not FAKE:
            time.sleep(5)

        self.check_database_for_user(self.username, self.password,
                                     [self.db1])
        self.check_database_for_user(self.username1, self.password1,
                                     [self.db1, self.db2])

    @test(depends_on=[test_create_users])
    def test_create_users_list(self):
        #tests for users that should be listed
        users = self.dbaas.users.list(instance_info.id)
        assert_equal(200, self.dbaas.last_http_code)
        found = False
        for user in self.created_users:
            for result in users:
                if user == result.name:
                    found = True
            assert_true(found, "User '%s' not found in result" % user)
            found = False

    @test(depends_on=[test_create_users])
    def test_fails_when_creating_user_twice(self):
        users = []
        users.append({"name": self.username, "password": self.password,
                      "databases": [{"name": self.db1}]})
        users.append({"name": self.username1, "password": self.password1,
                     "databases": [{"name": self.db1}, {"name": self.db2}]})
        assert_raises(exceptions.BadRequest, self.dbaas.users.create,
                      instance_info.id, users)
        assert_equal(400, self.dbaas.last_http_code)

    @test(depends_on=[test_create_users_list])
    def test_cannot_create_root_user(self):
        # Tests that the user root (in Config:ignore_users) cannot be created.
        users = [{"name": "root", "password": "12345",
                  "databases": [{"name": self.db1}]}]
        assert_raises(exceptions.BadRequest, self.dbaas.users.create,
                      instance_info.id, users)

    @test(depends_on=[test_create_users_list])
    def test_get_one_user(self):
        user = self.dbaas.users.get(instance_info.id, username=self.username,
                                    hostname='%')
        assert_equal(200, self.dbaas.last_http_code)
        assert_equal(user.name, self.username)
        assert_equal(1, len(user.databases))
        for db in user.databases:
            assert_equal(db["name"], self.db1)
        self.check_database_for_user(self.username, self.password, [self.db1])

    @test(depends_on=[test_create_users_list])
    def test_create_users_list_system(self):
        #tests for users that should not be listed
        users = self.dbaas.users.list(instance_info.id)
        assert_equal(200, self.dbaas.last_http_code)
        for user in self.system_users:
            found = any(result.name == user for result in users)
            msg = "User '%s' SHOULD NOT BE found in result" % user
            assert_false(found, msg)

    @test(depends_on=[test_create_users_list],
          runs_after=[test_fails_when_creating_user_twice])
    def test_delete_users(self):
        self.dbaas.users.delete(instance_info.id, self.username, hostname='%')
        assert_equal(202, self.dbaas.last_http_code)
        self.dbaas.users.delete(instance_info.id, self.username1, hostname='%')
        assert_equal(202, self.dbaas.last_http_code)
        if not FAKE:
            time.sleep(5)

        self._check_connection(self.username, self.password)
        self._check_connection(self.username1, self.password1)

    @test(depends_on=[test_create_users_list, test_delete_users])
    def test_hostnames_default_if_not_present(self):
        # These tests rely on test_delete_users as they create users only
        # they use.
        username = "testuser_nohost"
        user = {"name": username, "password": "password", "databases": []}

        self.dbaas.users.create(instance_info.id, [user])

        user["host"] = "%"
        # Can't create the user a second time if it already exists.
        assert_raises(exceptions.BadRequest, self.dbaas.users.create,
                      instance_info.id, [user])

        self.dbaas.users.delete(instance_info.id, username)

    @test(depends_on=[test_create_users_list, test_delete_users])
    def test_hostnames_make_users_unique(self):
        # These tests rely on test_delete_users as they create users only
        # they use.
        username = "testuser_unique"
        hostnames = ["192.168.0.1", "192.168.0.2"]
        users = [{"name": username, "password": "password", "databases": [],
                  "host": hostname}
                 for hostname in hostnames]

        # Nothing wrong with creating two users with the same name, so long
        # as their hosts are different.
        self.dbaas.users.create(instance_info.id, users)
        for hostname in hostnames:
            self.dbaas.users.delete(instance_info.id, username,
                                    hostname=hostname)

    @test()
    def test_updateduser_newname_host_unique(self):
        #The updated_username@hostname should not exist already
        users = []
        old_name = "testuser1"
        hostname = "192.168.0.1"
        users.append({"name": old_name, "password": "password",
                      "host": hostname, "databases": []})
        users.append({"name": "testuser2", "password": "password",
                      "host": hostname, "databases": []})
        self.dbaas.users.create(instance_info.id, users)
        user_new = {"name": "testuser2"}
        assert_raises(exceptions.BadRequest,
                      self.dbaas.users.update_attributes, instance_info.id,
                      old_name, user_new, hostname)
        assert_equal(400, self.dbaas.last_http_code)
        self.dbaas.users.delete(instance_info.id, old_name, hostname=hostname)
        self.dbaas.users.delete(instance_info.id, "testuser2",
                                hostname=hostname)

    @test()
    def test_updateduser_name_newhost_unique(self):
        # The username@updated_hostname should not exist already
        users = []
        username = "testuser"
        hostname1 = "192.168.0.1"
        hostname2 = "192.168.0.2"
        users.append({"name": username, "password": "password",
                      "host": hostname1, "databases": []})
        users.append({"name": username, "password": "password",
                      "host": hostname2, "databases": []})
        self.dbaas.users.create(instance_info.id, users)
        user_new = {"host": "192.168.0.2"}
        assert_raises(exceptions.BadRequest,
                      self.dbaas.users.update_attributes, instance_info.id,
                      username, user_new, hostname1)
        assert_equal(400, self.dbaas.last_http_code)
        self.dbaas.users.delete(instance_info.id, username, hostname=hostname1)
        self.dbaas.users.delete(instance_info.id, username, hostname=hostname2)

    @test()
    def test_updateduser_newname_newhost_unique(self):
        # The updated_username@updated_hostname should not exist already
        users = []
        username = "testuser1"
        hostname1 = "192.168.0.1"
        hostname2 = "192.168.0.2"
        users.append({"name": username, "password": "password",
                      "host": hostname1, "databases": []})
        users.append({"name": "testuser2", "password": "password",
                      "host": hostname2, "databases": []})
        self.dbaas.users.create(instance_info.id, users)
        user_new = {"name": "testuser2", "host": "192.168.0.2"}
        assert_raises(exceptions.BadRequest,
                      self.dbaas.users.update_attributes, instance_info.id,
                      username, user_new, hostname1)
        assert_equal(400, self.dbaas.last_http_code)
        self.dbaas.users.delete(instance_info.id, username, hostname=hostname1)
        self.dbaas.users.delete(instance_info.id, "testuser2",
                                hostname=hostname2)

    @test()
    def test_cannot_change_rootpassword(self):
        # Cannot change password for a root user
        user_new = {"password": "12345"}
        assert_raises(exceptions.BadRequest,
                      self.dbaas.users.update_attributes, instance_info.id,
                      "root", user_new)

    @test()
    def test_updateuser_emptyhost(self):
        # Cannot update the user hostname with an empty string
        users = []
        username = "testuser1"
        hostname = "192.168.0.1"
        users.append({"name": username, "password": "password",
                      "host": hostname, "databases": []})
        self.dbaas.users.create(instance_info.id, users)
        user_new = {"host": ""}
        assert_raises(exceptions.BadRequest,
                      self.dbaas.users.update_attributes, instance_info.id,
                      username, user_new, hostname)
        assert_equal(400, self.dbaas.last_http_code)
        self.dbaas.users.delete(instance_info.id, username, hostname=hostname)

    @test(depends_on=[test_create_users])
    def test_hostname_ipv4_restriction(self):
        # By default, user hostnames are required to be % or IPv4 addresses.
        user = {"name": "ipv4_nodice", "password": "password",
                "databases": [], "host": "disallowed_host"}

        assert_raises(exceptions.BadRequest, self.dbaas.users.create,
                      instance_info.id, [user])

    def show_databases(self, user, password):
        print("Going to connect to %s, %s, %s"
              % (instance_info.get_address(), user, password))
        with util.mysql_connection().create(instance_info.get_address(),
                                            user, password) as db:
            print(db)
            dbs = db.execute("show databases")
            return [row['Database'] for row in dbs]

    def check_database_for_user(self, user, password, dbs):
        if not FAKE:
            # Make the real call to the database to check things.
            actual_list = self.show_databases(user, password)
            for db in dbs:
                assert_true(
                    db in actual_list,
                    "No match for db %s in dblist. %s :(" % (db, actual_list))
        # Confirm via API list.
        result = self.dbaas.users.list(instance_info.id)
        assert_equal(200, self.dbaas.last_http_code)
        for item in result:
            if item.name == user:
                break
        else:
            fail("User %s not added to collection." % user)

        # Confirm via API get.
        result = self.dbaas.users.get(instance_info.id, user, '%')
        assert_equal(200, self.dbaas.last_http_code)
        if result.name != user:
            fail("User %s not found via get." % user)

    @test
    def test_username_too_long(self):
        users = [{"name": "1233asdwer345tyg56", "password": self.password,
                  "database": self.db1}]
        assert_raises(exceptions.BadRequest, self.dbaas.users.create,
                      instance_info.id, users)
        assert_equal(400, self.dbaas.last_http_code)

    @test
    def test_invalid_username(self):
        users = []
        users.append({"name": "user,", "password": self.password,
                      "database": self.db1})
        assert_raises(exceptions.BadRequest, self.dbaas.users.create,
                      instance_info.id, users)
        assert_equal(400, self.dbaas.last_http_code)

    @test(enabled=False)
    #TODO(hub_cap): Make this test work once python-routes is updated, if ever.
    def test_delete_user_with_period_in_name(self):
        """Attempt to create/destroy a user with a period in its name"""
        users = []
        username_with_period = "user.name"
        users.append({"name": username_with_period, "password": self.password,
                      "databases": [{"name": self.db1}]})
        self.dbaas.users.create(instance_info.id, users)
        assert_equal(202, self.dbaas.last_http_code)
        if not FAKE:
            time.sleep(5)

        self.check_database_for_user(username_with_period, self.password,
                                     [self.db1])
        self.dbaas.users.delete(instance_info.id, username_with_period)
        assert_equal(202, self.dbaas.last_http_code)

    @test
    def test_invalid_password(self):
        users = [{"name": "anouser", "password": "sdf,;",
                  "database": self.db1}]
        assert_raises(exceptions.BadRequest, self.dbaas.users.create,
                      instance_info.id, users)
        assert_equal(400, self.dbaas.last_http_code)

    @test
    def test_pagination(self):
        users = []
        users.append({"name": "Jetson", "password": "george",
                      "databases": [{"name": "Sprockets"}]})
        users.append({"name": "Jetson", "password": "george",
                      "host": "127.0.0.1",
                      "databases": [{"name": "Sprockets"}]})
        users.append({"name": "Spacely", "password": "cosmo",
                      "databases": [{"name": "Sprockets"}]})
        users.append({"name": "Spacely", "password": "cosmo",
                      "host": "127.0.0.1",
                      "databases": [{"name": "Sprockets"}]})
        users.append({"name": "Uniblab", "password": "fired",
                      "databases": [{"name": "Sprockets"}]})
        users.append({"name": "Uniblab", "password": "fired",
                      "host": "192.168.0.10",
                      "databases": [{"name": "Sprockets"}]})

        self.dbaas.users.create(instance_info.id, users)
        assert_equal(202, self.dbaas.last_http_code)
        if not FAKE:
            time.sleep(5)
        limit = 2
        users = self.dbaas.users.list(instance_info.id, limit=limit)
        assert_equal(200, self.dbaas.last_http_code)
        marker = users.next

        # Better get only as many as we asked for
        assert_true(len(users) <= limit)
        assert_true(users.next is not None)
        expected_marker = "%s@%s" % (users[-1].name, users[-1].host)
        expected_marker = urllib.quote(expected_marker)
        assert_equal(marker, expected_marker)
        marker = users.next

        # I better get new users if I use the marker I was handed.
        users = self.dbaas.users.list(instance_info.id, limit=limit,
                                      marker=marker)
        assert_equal(200, self.dbaas.last_http_code)
        assert_true(marker not in [user.name for user in users])

        # Now fetch again with a larger limit.
        users = self.dbaas.users.list(instance_info.id)
        assert_equal(200, self.dbaas.last_http_code)
        assert_true(users.next is None)

    def _check_connection(self, username, password):
        if not FAKE:
            util.mysql_connection().assert_fails(username, password,
                                                 instance_info.get_address())
        # Also determine the db is gone via API.
        result = self.dbaas.users.list(instance_info.id)
        assert_equal(200, self.dbaas.last_http_code)
        for item in result:
            if item.name == username:
                fail("User %s was not deleted." % username)
