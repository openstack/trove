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


@test(depends_on_classes=[TestUsers],
      groups=[tests.DBAAS_API, GROUP, tests.INSTANCES],
      runs_after=[TestUsers])
class TestUserAccess(object):
    """
    Test the creation and deletion of user grants.
    """

    @before_class
    def setUp(self):
        self.dbaas = util.create_dbaas_client(instance_info.user)
        self.users = ["test_access_user"]
        self.databases = [("test_access_db%02i" % i) for i in range(4)]
        # None of the ghosts are real databases or users.
        self.ghostdbs = ["test_user_access_ghost_db"]
        self.ghostusers = ["test_ghostuser"]
        self.revokedbs = self.databases[:1]
        self.remainingdbs = self.databases[1:]

    def _test_access(self, expecteddbs):
        for user in self.users:
            access = self.dbaas.users.list_access(instance_info.id, user)
            assert_equal(200, self.dbaas.last_http_code)
            access = [db.name for db in access]
            assert_equal(set(access), set(expecteddbs))

    def _grant_access(self, databases):
        for user in self.users:
            self.dbaas.users.grant(instance_info.id, user, databases)
            assert_equal(202, self.dbaas.last_http_code)

    def _revoke_access(self, databases):
        for user in self.users:
            for database in databases:
                self.dbaas.users.revoke(instance_info.id, user, database)
                assert_true(self.dbaas.last_http_code in [202, 404])

    def _reset_access(self):
        for user in self.users:
            for database in self.databases + self.ghostdbs:
                try:
                    self.dbaas.users.revoke(instance_info.id, user, database)
                    assert_true(self.dbaas.last_http_code in [202, 404])
                except exceptions.NotFound as nf:
                    # This is all right here, since we're resetting.
                    pass
        self._test_access([])

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
        users = [{"name": user, "password": "password", "databases": []}
                 for user in self.users]
        self.dbaas.users.create(instance_info.id, users)
        assert_equal(202, self.dbaas.last_http_code)

        databases = [{"name": db} for db in self.databases]
        self.dbaas.databases.create(instance_info.id, databases)
        assert_equal(202, self.dbaas.last_http_code)

    @test(depends_on=[test_create_user_and_dbs])
    def test_no_access(self):
        # No users have any access to any database.
        self._reset_access()
        self._test_access([])

    @test(depends_on=[test_no_access])
    def test_grant_full_access(self):
        # The users are granted access to all test databases.
        self._reset_access()
        self._grant_access(self.databases)
        self._test_access(self.databases)

    @test(depends_on=[test_grant_full_access])
    def test_grant_idempotence(self):
        # Grant operations can be repeated with no ill effects.
        self._reset_access()
        self._grant_access(self.databases)
        self._grant_access(self.databases)
        self._test_access(self.databases)

    @test(depends_on=[test_grant_full_access])
    def test_revoke_one_database(self):
        # Revoking permission removes that database from a user's list.
        self._reset_access()
        self._grant_access(self.databases)
        self._test_access(self.databases)
        self._revoke_access(self.revokedbs)
        self._test_access(self.remainingdbs)

    @test(depends_on=[test_grant_full_access])
    def test_revoke_non_idempotence(self):
        # Revoking access cannot be repeated.
        self._reset_access()
        self._grant_access(self.databases)
        self._revoke_access(self.revokedbs)
        assert_raises(exceptions.NotFound,
                      self._revoke_access,
                      self.revokedbs)
        self._test_access(self.remainingdbs)

    @test(depends_on=[test_grant_full_access])
    def test_revoke_all_access(self):
        # Revoking access to all databases will leave their access empty.
        self._reset_access()
        self._grant_access(self.databases)
        self._revoke_access(self.databases)
        self._test_access([])

    @test(depends_on=[test_grant_full_access])
    def test_grant_ghostdbs(self):
        # Grants to imaginary databases are acceptable, and are honored.
        self._reset_access()
        self._ensure_nothing_else_created()
        self._grant_access(self.ghostdbs)
        self._ensure_nothing_else_created()

    @test(depends_on=[test_grant_full_access])
    def test_revoke_ghostdbs(self):
        # Revokes to imaginary databases are acceptable, and are honored.
        self._reset_access()
        self._ensure_nothing_else_created()
        self._grant_access(self.ghostdbs)
        self._revoke_access(self.ghostdbs)
        self._ensure_nothing_else_created()

    @test(depends_on=[test_grant_full_access])
    def test_grant_ghostusers(self):
        # You cannot grant permissions to imaginary users, as imaginary users
        # don't have passwords we can pull from mysql.users
        self._reset_access()
        for user in self.ghostusers:
            assert_raises(exceptions.NotFound,
                          self.dbaas.users.grant,
                          instance_info.id, user, self.databases)
            assert_equal(404, self.dbaas.last_http_code)

    @test(depends_on=[test_grant_full_access])
    def test_revoke_ghostusers(self):
        # You cannot revoke permissions from imaginary users, as imaginary
        # users don't have passwords we can pull from mysql.users
        self._reset_access()
        for user in self.ghostusers:
            for database in self.databases:
                assert_raises(exceptions.NotFound,
                              self.dbaas.users.revoke,
                              instance_info.id, user, database)
                assert_equal(404, self.dbaas.last_http_code)

    @after_class(always_run=True)
    def tearDown(self):
        self._reset_access()

        for database in self.databases:
            self.dbaas.databases.delete(instance_info.id, database)
            assert_equal(202, self.dbaas.last_http_code)
