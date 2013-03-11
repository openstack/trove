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

import time
import re
from random import choice

from reddwarfclient import exceptions

from proboscis import after_class
from proboscis import before_class
from proboscis import test
from proboscis.asserts import *

from reddwarf import tests
from reddwarf.tests.api.instances import instance_info
from reddwarf.tests import util
from reddwarf.tests.util import test_config
from reddwarf.tests.api.users import TestUsers

GROUP = "dbaas.api.useraccess"
GROUP_POSITIVE = GROUP + ".positive"
GROUP_NEGATIVE = GROUP + ".negative"

FAKE = test_config.values['fake_mode']


class UserAccessBase(object):
    """
    Base class for Positive and Negative TestUserAccess classes
    """
    users = []
    databases = []

    def set_up(self):
        self.dbaas = util.create_dbaas_client(instance_info.user)
        self.users = ["test_access_user"]
        self.databases = [("test_access_db%02i" % i) for i in range(4)]

    def _user_list_from_names(self, usernames):
        return [{"name": name,
                 "password": "password",
                 "databases": []} for name in usernames]

    def _grant_access_singular(self, user, databases, expected_response=202):
        """ Grant a single user access to the databases listed.
            Potentially, expect an exception in the process."""
        try:
            self.dbaas.users.grant(instance_info.id, user, databases)
        except exceptions.BadRequest as br:
            assert_equal(400, expected_response)
        except exceptions.NotFound as nf:
            assert_equal(404, expected_response)
        except exceptions.ClientException as ce:
            assert_equal(500, expected_response)
        finally:
            assert_equal(expected_response, self.dbaas.last_http_code)

    def _grant_access_plural(self, users, databases, expected_response=202):
        """ Grant each user in the list access to all the databases listed.
            Potentially, expect an exception in the process."""
        for user in users:
            self._grant_access_singular(user, databases, expected_response)

    def _revoke_access_singular(self, user, database, expected_response=202):
        """ Revoke from a user access to the given database .
            Potentially, expect an exception in the process."""
        try:
            self.dbaas.users.revoke(instance_info.id, user, database)
            assert_true(expected_response, self.dbaas.last_http_code)
        except exceptions.BadRequest as nf:
            assert_equal(400, self.dbaas.last_http_code)
        except exceptions.NotFound as nf:
            assert_equal(404, self.dbaas.last_http_code)

    def _revoke_access_plural(self, users, databases, expected_response=202):
        """ Revoke from each user access to each database.
            Potentially, expect an exception in the process."""
        for user in users:
            for database in databases:
                self._revoke_access_singular(user,
                                             database,
                                             expected_response)

    def _test_access(self, users, databases, expected_response=200):
        """ Verify that each user in the list has access to each database in
            the list."""
        for user in users:
            access = self.dbaas.users.list_access(instance_info.id, user)
            assert_equal(expected_response, self.dbaas.last_http_code)
            access = [db.name for db in access]
            assert_equal(set(access), set(databases))

    def _reset_access(self):
        for user in self.users:
            for database in self.databases + self.ghostdbs:
                try:
                    self.dbaas.users.revoke(instance_info.id, user, database)
                    assert_true(self.dbaas.last_http_code in [202, 404])
                except exceptions.NotFound as nf:
                    # This is all right here, since we're resetting.
                    pass
        self._test_access(self.users, [])


@test(depends_on_classes=[TestUsers],
      groups=[tests.DBAAS_API, GROUP, tests.INSTANCES],
      runs_after=[TestUsers])
class TestUserAccessPasswordChange(UserAccessBase):
    """
    Test that change_password works.
    """

    @before_class
    def setUp(self):
        super(TestUserAccessPasswordChange, self).set_up()

    def _check_mysql_connection(self, username, password, success=True):
        # This can only test connections for users with the host %.
        # Much more difficult to simulate connection attempts from other hosts.
        if FAKE:
            # "Fake mode; cannot test mysql connection."
            return

        conn = util.mysql_connection()
        if success:
            conn.create(username, password, instance_info.get_address())
        else:
            conn.assert_fails(username, password, instance_info.get_address())

    def _pick_a_user(self):
        users = self._user_list_from_names(self.users)
        return choice(users)  # Pick one, it doesn't matter.

    @test()
    def test_create_user_and_dbs(self):
        users = self._user_list_from_names(self.users)
        # Default password for everyone is 'password'.
        self.dbaas.users.create(instance_info.id, users)
        assert_equal(202, self.dbaas.last_http_code)

        databases = [{"name": db}
                     for db in self.databases]
        self.dbaas.databases.create(instance_info.id, databases)
        assert_equal(202, self.dbaas.last_http_code)

    @test(depends_on=[test_create_user_and_dbs])
    def test_initial_connection(self):
        user = self._pick_a_user()
        self._check_mysql_connection(user["name"], "password")

    @test(depends_on=[test_initial_connection])
    def test_change_password(self):
        # Doesn't actually change anything, just tests that the call doesn't
        # have any problems. As an aside, also checks that a user can
        # change its password to the same thing again.
        user = self._pick_a_user()
        password = user["password"]
        self.dbaas.users.change_passwords(instance_info.id, [user])
        self._check_mysql_connection(user["name"], password)

    @test(depends_on=[test_change_password])
    def test_change_password_back(self):
        user = self._pick_a_user()
        old_password = user["password"]
        new_password = "NEWPASSWORD"

        user["password"] = new_password
        self.dbaas.users.change_passwords(instance_info.id, [user])
        self._check_mysql_connection(user["name"], new_password)

        user["password"] = old_password
        self.dbaas.users.change_passwords(instance_info.id, [user])
        self._check_mysql_connection(user["name"], old_password)

    @test(depends_on=[test_change_password_back])
    def test_change_password_twice(self):
        # Changing the password twice isn't a problem.
        user = self._pick_a_user()
        password = "NEWPASSWORD"
        user["password"] = password
        self.dbaas.users.change_passwords(instance_info.id, [user])
        self.dbaas.users.change_passwords(instance_info.id, [user])
        self._check_mysql_connection(user["name"], password)

    @after_class(always_run=True)
    def tearDown(self):
        for database in self.databases:
            self.dbaas.databases.delete(instance_info.id, database)
            assert_equal(202, self.dbaas.last_http_code)
        for username in self.users:
            self.dbaas.users.delete(instance_info.id, username)


@test(depends_on_classes=[TestUsers],
      groups=[tests.DBAAS_API, GROUP, GROUP_POSITIVE, tests.INSTANCES],
      runs_after=[TestUsers])
class TestUserAccessPositive(UserAccessBase):
    """
    Test the creation and deletion of user grants.
    """

    @before_class
    def setUp(self):
        super(TestUserAccessPositive, self).set_up()
        # None of the ghosts are real databases or users.
        self.ghostdbs = ["test_user_access_ghost_db"]
        self.ghostusers = ["test_ghostuser"]
        self.revokedbs = self.databases[:1]
        self.remainingdbs = self.databases[1:]

    def _ensure_nothing_else_created(self):
        # Make sure grants and revokes do not create users or databases.
        databases = self.dbaas.databases.list(instance_info.id)
        database_names = [db.name for db in databases]
        for ghost in self.ghostdbs:
            assert_true(ghost not in database_names)
        users = self.dbaas.users.list(instance_info.id)
        user_names = [user.name for user in users]
        for ghost in self.ghostusers:
            assert_true(ghost not in user_names)

    @test()
    def test_create_user_and_dbs(self):
        users = self._user_list_from_names(self.users)
        self.dbaas.users.create(instance_info.id, users)
        assert_equal(202, self.dbaas.last_http_code)

        databases = [{"name": db}
                     for db in self.databases]
        self.dbaas.databases.create(instance_info.id, databases)
        assert_equal(202, self.dbaas.last_http_code)

    @test(depends_on=[test_create_user_and_dbs])
    def test_no_access(self):
        # No users have any access to any database.
        self._reset_access()
        self._test_access(self.users, [])

    @test(depends_on=[test_no_access])
    def test_grant_full_access(self):
        # The users are granted access to all test databases.
        self._reset_access()
        self._grant_access_plural(self.users, self.databases)
        self._test_access(self.users, self.databases)

    @test(depends_on=[test_grant_full_access])
    def test_grant_idempotence(self):
        # Grant operations can be repeated with no ill effects.
        self._reset_access()
        for repeat in range(3):
            self._grant_access_plural(self.users, self.databases)
        self._test_access(self.users, self.databases)

    @test(depends_on=[test_grant_full_access])
    def test_revoke_one_database(self):
        # Revoking permission removes that database from a user's list.
        self._reset_access()
        self._grant_access_plural(self.users, self.databases)
        self._test_access(self.users, self.databases)
        self._revoke_access_plural(self.users, self.revokedbs)
        self._test_access(self.users, self.remainingdbs)

    @test(depends_on=[test_grant_full_access])
    def test_revoke_non_idempotence(self):
        # Revoking access cannot be repeated.
        self._reset_access()
        self._grant_access_plural(self.users, self.databases)
        self._revoke_access_plural(self.users, self.revokedbs)
        self._revoke_access_plural(self.users, self.revokedbs, 404)
        self._test_access(self.users, self.remainingdbs)

    @test(depends_on=[test_grant_full_access])
    def test_revoke_all_access(self):
        # Revoking access to all databases will leave their access empty.
        self._reset_access()
        self._grant_access_plural(self.users, self.databases)
        self._revoke_access_plural(self.users, self.revokedbs)
        self._test_access(self.users, self.remainingdbs)

    @test(depends_on=[test_grant_full_access])
    def test_grant_ghostdbs(self):
        # Grants to imaginary databases are acceptable, and are honored.
        self._reset_access()
        self._ensure_nothing_else_created()
        self._grant_access_plural(self.users, self.ghostdbs)
        self._ensure_nothing_else_created()

    @test(depends_on=[test_grant_full_access])
    def test_revoke_ghostdbs(self):
        # Revokes to imaginary databases are acceptable, and are honored.
        self._reset_access()
        self._ensure_nothing_else_created()
        self._grant_access_plural(self.users, self.ghostdbs)
        self._revoke_access_plural(self.users, self.ghostdbs)
        self._ensure_nothing_else_created()

    @test(depends_on=[test_grant_full_access])
    def test_grant_ghostusers(self):
        # You cannot grant permissions to imaginary users, as imaginary users
        # don't have passwords we can pull from mysql.users
        self._reset_access()
        self._grant_access_plural(self.ghostusers, self.databases, 404)

    @test(depends_on=[test_grant_full_access])
    def test_revoke_ghostusers(self):
        # You cannot revoke permissions from imaginary users, as imaginary
        # users don't have passwords we can pull from mysql.users
        self._reset_access()
        self._revoke_access_plural(self.ghostusers, self.databases, 404)

    @after_class(always_run=True)
    def tearDown(self):
        self._reset_access()
        for database in self.databases:
            self.dbaas.databases.delete(instance_info.id, database)
            assert_equal(202, self.dbaas.last_http_code)
        for username in self.users:
            self.dbaas.users.delete(instance_info.id, username)


@test(depends_on_classes=[TestUserAccessPositive],
      groups=[tests.DBAAS_API, GROUP, GROUP_NEGATIVE, tests.INSTANCES],
      depends_on=[TestUserAccessPositive])
class TestUserAccessNegative(UserAccessBase):
    """
    Negative tests for the creation and deletion of user grants.
    """

    @before_class
    def setUp(self):
        super(TestUserAccessNegative, self).set_up()
        self.users = ["qe_user?neg3F", "qe_user#neg23"]
        self.databases = [("qe_user_neg_db%02i" % i) for i in range(2)]
        self.ghostdbs = []

    def _add_users(self, users, expected_response=202):
        user_list = self._user_list_from_names(users)
        try:
            self.dbaas.users.create(instance_info.id, user_list)
            assert_equal(self.dbaas.last_http_code, 202)
        except exceptions.BadRequest as br:
            assert_equal(self.dbaas.last_http_code, 400)
        assert_equal(expected_response, self.dbaas.last_http_code)

    @test()
    def test_create_duplicate_user_and_dbs(self):
        '''
        create the same user to the first DB - allowed, not part of change
        '''
        users = self._user_list_from_names(self.users)
        self.dbaas.users.create(instance_info.id, users)
        assert_equal(202, self.dbaas.last_http_code)
        databases = [{"name": db} for db in self.databases]
        self.dbaas.databases.create(instance_info.id, databases)
        assert_equal(202, self.dbaas.last_http_code)

    @test(depends_on=[test_create_duplicate_user_and_dbs])
    def test_neg_duplicate_useraccess(self):
        '''
        Grant duplicate users access to all database.
        '''
        username = "qe_user.neg2E"
        self._add_users([username])
        self._add_users([username], 400)
        for repeat in range(3):
            self._grant_access_plural(self.users, self.databases)
        self._test_access(self.users, self.databases)

    @test()
    def test_re_create_user(self):
        user_list = ["re_create_user"]
        # create, grant, then check a new user
        self._add_users(user_list)
        self._test_access(user_list, [])
        self._grant_access_singular(user_list[0], self.databases)
        self._test_access(user_list, self.databases)
        # drop the user temporarily
        self.dbaas.users.delete(instance_info.id, user_list[0])
        # check his access - user should not be found
        assert_raises(exceptions.NotFound,
                      self.dbaas.users.list_access,
                      instance_info.id,
                      user_list[0])
        # re-create the user
        self._add_users(user_list)
        # check his access - should not exist
        self._test_access(user_list, [])
        # grant user access to all database.
        self._grant_access_singular(user_list[0], self.databases)
        # check his access - user should exist
        self._test_access(user_list, self.databases)
        # revoke users access
        self._revoke_access_plural(user_list, self.databases)

    def _negative_user_test(self, username, databases,
                            create_response=202, grant_response=202,
                            access_response=200, revoke_response=202):
        # Try and fail to create the user.
        self._add_users([username], create_response)
        self._grant_access_singular(username, databases, grant_response)
        access = None
        try:
            access = self.dbaas.users.list_access(instance_info.id, username)
            assert_equal(200, self.dbaas.last_http_code)
        except exceptions.BadRequest as br:
            assert_equal(400, self.dbaas.last_http_code)
        except exceptions.NotFound as nf:
            assert_equal(404, self.dbaas.last_http_code)
        finally:
            assert_equal(access_response, self.dbaas.last_http_code)
        if access is not None:
            access = [db.name for db in access]
            assert_equal(set(access), set(self.databases))

        self._revoke_access_plural([username], databases, revoke_response)

    @test
    def test_user_withperiod(self):
        # This is actually fine; we escape dots in the user-host pairing.
        self._negative_user_test("test.user", self.databases)

    @test
    def test_user_empty(self):
        # This creates a request to .../<instance-id>/users//databases,
        # which is parsed to mean "show me user 'databases', which in this
        # case is a valid username, but not one of an extant user.
        self._negative_user_test("", self.databases, 400, 400, 400, 400)

    @test
    def test_user_nametoolong(self):
        # You cannot create a user with this name.
        # Grant revoke, and access filter this username as invalid.
        self._negative_user_test("exceed_limit_user", self.databases,
                                 400, 400, 400, 400)

    @test
    def test_user_allspaces(self):
        self._negative_user_test("     ", self.databases, 400, 400, 400, 400)

    @after_class(always_run=True)
    def tearDown(self):
        self._reset_access()

        for database in self.databases:
            self.dbaas.databases.delete(instance_info.id, database)
            assert_equal(202, self.dbaas.last_http_code)
        for username in self.users:
            self.dbaas.users.delete(instance_info.id, username)
