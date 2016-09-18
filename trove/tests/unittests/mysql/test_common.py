#    Copyright 2013 OpenStack Foundation
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
#
from testtools.matchers import Equals
from testtools.matchers import Is
from trove.common.exception import DatabaseForUserNotInDatabaseListError
from trove.common.exception import DatabaseInitialDatabaseDuplicateError
from trove.common.exception import DatabaseInitialUserDuplicateError
from trove.extensions.mysql.common import populate_users
from trove.extensions.mysql.common import populate_validated_databases
from trove.tests.unittests import trove_testtools


class MySqlCommonTest(trove_testtools.TestCase):

    def setUp(self):
        super(MySqlCommonTest, self).setUp()

    def tearDown(self):
        super(MySqlCommonTest, self).tearDown()

    def test_initial_databases_none(self):
        databases = []
        result = populate_validated_databases(databases)
        self.assertThat(len(result), Is(0))

    def test_initial_databases_single(self):
        databases = [{'name': 'one_db'}]
        result = populate_validated_databases(databases)
        self.assertThat(len(result), Is(1))
        self.assertThat(result[0]['_name'], Equals('one_db'))

    def test_initial_databases_unique(self):
        databases = [{'name': 'one_db'}, {'name': 'diff_db'}]
        result = populate_validated_databases(databases)
        self.assertThat(len(result), Is(2))

    def test_initial_databases_duplicate(self):
        databases = [{'name': 'same_db'}, {'name': 'same_db'}]
        self.assertRaises(DatabaseInitialDatabaseDuplicateError,
                          populate_validated_databases, databases)

    def test_initial_databases_intermingled(self):
        databases = [{'name': 'a_db'}, {'name': 'b_db'}, {'name': 'a_db'}]
        self.assertRaises(DatabaseInitialDatabaseDuplicateError,
                          populate_validated_databases, databases)

    def test_populate_users_single(self):
        users = [{'name': 'bob', 'password': 'x'}]
        result = populate_users(users)
        self.assertThat(len(result), Is(1))
        self.assertThat(result[0]['_name'], Equals('bob'))
        self.assertThat(result[0]['_password'], Equals('x'))

    def test_populate_users_unique_host(self):
        users = [{'name': 'bob', 'password': 'x', 'host': '127.0.0.1'},
                 {'name': 'bob', 'password': 'x', 'host': '128.0.0.1'}]
        result = populate_users(users)
        self.assertThat(len(result), Is(2))

    def test_populate_users_unique_name(self):
        users = [{'name': 'bob', 'password': 'x', 'host': '127.0.0.1'},
                 {'name': 'tom', 'password': 'x', 'host': '127.0.0.1'}]
        result = populate_users(users)
        self.assertThat(len(result), Is(2))

    def test_populate_users_duplicate(self):
        users = [{'name': 'bob', 'password': 'x', 'host': '127.0.0.1'},
                 {'name': 'bob', 'password': 'y', 'host': '127.0.0.1'}]
        self.assertRaises(DatabaseInitialUserDuplicateError,
                          populate_users, users)

    def test_populate_unique_users_unique_host(self):
        users = [{'name': 'bob', 'password': 'x', 'host': '127.0.0.1'},
                 {'name': 'tom', 'password': 'x', 'host': '128.0.0.1'}]
        result = populate_users(users)
        self.assertThat(len(result), Is(2))

    def test_populate_users_intermingled(self):
        users = [{'name': 'bob', 'password': 'x', 'host': '127.0.0.1'},
                 {'name': 'tom', 'password': 'y', 'host': '127.0.0.1'},
                 {'name': 'bob', 'password': 'z', 'host': '127.0.0.1'},
                 {'name': 'bob', 'password': 'x', 'host': '128.0.0.1'},
                 {'name': 'tom', 'password': 'x', 'host': '128.0.0.1'}]
        self.assertRaises(DatabaseInitialUserDuplicateError,
                          populate_users, users)

    def test_populate_users_both_db_list_empty(self):
        initial_databases = []
        users = [{"name": "bob", "password": "x"}]
        result = populate_users(users, initial_databases)
        self.assertThat(len(result), Is(1))

    def test_populate_users_initial_db_list_empty(self):
        initial_databases = []
        users = [{"name": "bob", "password": "x",
                  "databases": [{"name": "my_db"}]}]
        self.assertRaises(DatabaseForUserNotInDatabaseListError,
                          populate_users, users, initial_databases)

    def test_populate_users_user_db_list_empty(self):
        initial_databases = ['my_db']
        users = [{"name": "bob", "password": "x"}]
        result = populate_users(users, initial_databases)
        self.assertThat(len(result), Is(1))

    def test_populate_users_db_in_list(self):
        initial_databases = ['my_db']
        users = [{"name": "bob", "password": "x",
                  "databases": [{"name": "my_db"}]}]
        result = populate_users(users, initial_databases)
        self.assertThat(len(result), Is(1))

    def test_populate_users_db_multi_in_list(self):
        initial_databases = ['a_db', 'b_db', 'c_db', 'd_db']
        users = [{"name": "bob", "password": "x",
                  "databases": [{"name": "a_db"}]},
                 {"name": "tom", "password": "y",
                  "databases": [{"name": "c_db"}]},
                 {"name": "sue", "password": "z",
                  "databases": [{"name": "c_db"}]}]
        result = populate_users(users, initial_databases)
        self.assertThat(len(result), Is(3))

    def test_populate_users_db_not_in_list(self):
        initial_databases = ['a_db', 'b_db', 'c_db', 'd_db']
        users = [{"name": "bob", "password": "x",
                  "databases": [{"name": "fake_db"}]}]
        self.assertRaises(DatabaseForUserNotInDatabaseListError,
                          populate_users, users, initial_databases)

    def test_populate_users_db_multi_not_in_list(self):
        initial_databases = ['a_db', 'b_db', 'c_db', 'd_db']
        users = [{"name": "bob", "password": "x",
                  "databases": [{"name": "a_db"}]},
                 {"name": "tom", "password": "y",
                  "databases": [{"name": "fake_db"}]},
                 {"name": "sue", "password": "z",
                  "databases": [{"name": "d_db"}]}]
        self.assertRaises(DatabaseForUserNotInDatabaseListError,
                          populate_users, users, initial_databases)
