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

from mock import Mock, MagicMock
from proboscis import test
import testtools
import reddwarf.guestagent.dbaas as dbaas
from reddwarf.guestagent.db import models
from reddwarf.guestagent.dbaas import MySqlAdmin

"""
Unit tests for the classes and functions in dbaas.py.
"""

FAKE_DB = {"_name": "testDB", "_character_set": "latin2",
           "_collate": "latin2_general_ci"}
FAKE_DB_2 = {"_name": "testDB2", "_character_set": "latin2",
             "_collate": "latin2_general_ci"}
FAKE_USER = [{"_name": "random", "_password": "guesswhat",
              "_databases": [FAKE_DB]}]


@test(groups=["dbaas.guestagent.dbaas"])
class MySqlAdminTest(testtools.TestCase):

    def setUp(self):

        super(MySqlAdminTest, self).setUp()

        self.orig_get_engine = dbaas.get_engine
        self.orig_LocalSqlClient = dbaas.LocalSqlClient
        self.orig_LocalSqlClient_enter = dbaas.LocalSqlClient.__enter__
        self.orig_LocalSqlClient_exit = dbaas.LocalSqlClient.__exit__
        self.orig_LocalSqlClient_execute = dbaas.LocalSqlClient.execute
        dbaas.get_engine = MagicMock(name='get_engine')
        dbaas.LocalSqlClient = Mock
        dbaas.LocalSqlClient.__enter__ = Mock()
        dbaas.LocalSqlClient.__exit__ = Mock()
        dbaas.LocalSqlClient.execute = Mock()
        self.mySqlAdmin = MySqlAdmin()

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
        databases.append(FAKE_DB)

        # execute test
        self.mySqlAdmin.create_database(databases)

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
        databases.append(FAKE_DB)
        databases.append(FAKE_DB_2)

        # execute test
        self.mySqlAdmin.create_database(databases)

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
        self.mySqlAdmin.create_database(databases)

        # verify client object was not called
        self.assertFalse(dbaas.LocalSqlClient.execute.called,
                         "The client object was called when it wasn't " +
                         "supposed to")

    def test_delete_database(self):

        # setup test
        database = {"_name": "testDB"}

        # execute test
        self.mySqlAdmin.delete_database(database)

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
        self.mySqlAdmin.delete_user(user)

        # verify arg passed correctly
        args, _ = dbaas.LocalSqlClient.execute.call_args
        expected = "DROP USER `testUser`"
        self.assertEquals(args[0].text, expected,
                          "Delete user queries are not the same")

        # verify client object is called
        self.assertTrue(dbaas.LocalSqlClient.execute.called,
                        "The client object was not called")

    def test_create_user(self):
        self.mySqlAdmin.create_user(FAKE_USER)
        self.assertEqual(2, dbaas.LocalSqlClient.execute.call_count)

    def test_enable_root(self):
        models.MySQLUser._is_valid_user_name = \
            MagicMock(return_value=True)
        self.mySqlAdmin.enable_root()
        self.assertEqual(3, dbaas.LocalSqlClient.execute.call_count)

    def test_enable_root_failed(self):
        models.MySQLUser._is_valid_user_name = \
            MagicMock(return_value=False)
        self.assertRaises(ValueError, self.mySqlAdmin.enable_root)
