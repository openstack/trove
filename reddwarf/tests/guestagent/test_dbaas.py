#    Copyright 2012 OpenStack LLC
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

import testtools
from mock import Mock
from proboscis import test
import reddwarf.guestagent.dbaas as dbaas

"""
Unit tests for the classes and functions in dbaas.py.
"""


@test(groups=["dbaas.guestagent.dbaas"])
class MySqlAdminTest(testtools.TestCase):

    def setUp(self):

        super(MySqlAdminTest, self).setUp()
        self.orig_get_engine = dbaas.get_engine
        self.orig_LocalSqlClient = dbaas.LocalSqlClient
        self.orig_LocalSqlClient_enter = dbaas.LocalSqlClient.__enter__
        self.orig_LocalSqlClient_exit = dbaas.LocalSqlClient.__exit__
        self.orig_LocalSqlClient_execute = dbaas.LocalSqlClient.execute
        dbaas.get_engine = Mock(return_value=None)
        dbaas.LocalSqlClient = Mock
        dbaas.LocalSqlClient.__enter__ = Mock()
        dbaas.LocalSqlClient.__exit__ = Mock()
        dbaas.LocalSqlClient.execute = Mock()

    def tearDown(self):

        super(MySqlAdminTest, self).tearDown()
        dbaas.get_engine = self.orig_get_engine
        dbaas.LocalSqlClient = self.orig_LocalSqlClient
        dbaas.LocalSqlClient.__enter__ = self.orig_LocalSqlClient_enter
        dbaas.LocalSqlClient.__exit__ = self.orig_LocalSqlClient_exit
        dbaas.LocalSqlClient.execute = self.orig_LocalSqlClient_execute

    def test_create_database(self):

        # setup test
        databases = []
        databases.append({"_name": "testDB", "_character_set": "latin2",
                          "_collate": "latin2_general_ci"})

        # execute test
        dbaas.MySqlAdmin().create_database(databases)

        # verify arg passed correctly
        args, _ = dbaas.LocalSqlClient.execute.call_args_list[0]
        expected = "CREATE DATABASE IF NOT EXISTS\n                    " \
                   "        `testDB` CHARACTER SET = latin2 COLLATE = " \
                   "latin2_general_ci;"
        self.assertEquals(args[0].text, expected,
                          "Create database queries are not the same")

        # verify client object is called 2 times
        self.assertEqual(1, dbaas.LocalSqlClient.execute.call_count,
                         "The client object was not 2 times")

    def test_create_database_more_than_1(self):

        # setup test
        databases = []
        databases.append({"_name": "testDB", "_character_set": "latin2",
                          "_collate": "latin2_general_ci"})
        databases.append({"_name": "testDB2", "_character_set": "latin2",
                          "_collate": "latin2_general_ci"})

        # execute test
        dbaas.MySqlAdmin().create_database(databases)

        # verify arg passed correctly
        args, _ = dbaas.LocalSqlClient.execute.call_args_list[0]
        expected = "CREATE DATABASE IF NOT EXISTS\n                     " \
                   "       `testDB` CHARACTER SET = latin2 COLLATE = " \
                   "latin2_general_ci;"
        self.assertEquals(args[0].text, expected,
                          "Create database queries are not the same")

        args, _ = dbaas.LocalSqlClient.execute.call_args_list[1]
        expected = "CREATE DATABASE IF NOT EXISTS\n                      " \
                   "      `testDB2` CHARACTER SET = latin2 COLLATE = " \
                   "latin2_general_ci;"
        self.assertEquals(args[0].text, expected,
                          "Create database queries are not the same")

        # verify client object is called 2 times
        self.assertEqual(2, dbaas.LocalSqlClient.execute.call_count,
                         "The client object was not 2 times")

    def test_create_database_no_db(self):

        # setup test
        databases = []

        # execute test
        dbaas.MySqlAdmin().create_database(databases)

        # verify client object was not called
        self.assertFalse(dbaas.LocalSqlClient.execute.called,
                         "The client object was called when it wasn't " +
                         "supposed to")

    def test_delete_database(self):

        # setup test
        database = {"_name": "testDB"}

        # execute test
        dbaas.MySqlAdmin().delete_database(database)

        # verify arg passed correctly
        args, _ = dbaas.LocalSqlClient.execute.call_args
        expected = "DROP DATABASE `testDB`;"
        self.assertEquals(args[0].text, expected,
                          "Delete database queries are not the same")

        # verify client object is called
        self.assertTrue(dbaas.LocalSqlClient.execute.called,
                        "The client object was not called")

    def test_delete_user(self):

        # setup test
        user = {"_name": "testUser"}

        # execute test
        dbaas.MySqlAdmin().delete_user(user)

        # verify arg passed correctly
        args, _ = dbaas.LocalSqlClient.execute.call_args
        expected = "DROP USER `testUser`"
        self.assertEquals(args[0].text, expected,
                          "Delete user queries are not the same")

        # verify client object is called
        self.assertTrue(dbaas.LocalSqlClient.execute.called,
                        "The client object was not called")
