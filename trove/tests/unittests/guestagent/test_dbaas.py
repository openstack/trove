#    Copyright 2012 OpenStack Foundation
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

import ConfigParser
import os
import subprocess
import tempfile
import time
from uuid import uuid4

from mock import ANY
from mock import call
from mock import DEFAULT
from mock import MagicMock
from mock import Mock
from mock import patch
from mock import PropertyMock
from oslo_utils import netutils
import sqlalchemy
import testtools
from testtools.matchers import Equals
from testtools.matchers import Is
from testtools.matchers import Not

from trove.common import cfg
from trove.common import context as trove_context
from trove.common.exception import BadRequest
from trove.common.exception import GuestError
from trove.common.exception import PollTimeOut
from trove.common.exception import ProcessExecutionError
from trove.common import instance as rd_instance
from trove.common import utils
from trove.conductor import api as conductor_api
from trove.guestagent.common import operating_system
from trove.guestagent.common.operating_system import FileMode
from trove.guestagent.datastore.experimental.cassandra import (
    service as cass_service)
from trove.guestagent.datastore.experimental.cassandra import (
    system as cass_system)
from trove.guestagent.datastore.experimental.couchbase import (
    service as couchservice)
from trove.guestagent.datastore.experimental.couchdb import (
    service as couchdb_service)
from trove.guestagent.datastore.experimental.db2 import (
    service as db2service)
from trove.guestagent.datastore.experimental.mongodb import (
    service as mongo_service)
from trove.guestagent.datastore.experimental.mongodb import (
    system as mongo_system)
from trove.guestagent.datastore.experimental.pxc import (
    service as pxc_service)
from trove.guestagent.datastore.experimental.pxc import (
    system as pxc_system)
from trove.guestagent.datastore.experimental.redis import service as rservice
from trove.guestagent.datastore.experimental.redis.service import RedisApp
from trove.guestagent.datastore.experimental.redis import system as RedisSystem
from trove.guestagent.datastore.experimental.vertica import (
    system as vertica_system)
from trove.guestagent.datastore.experimental.vertica.service import (
    VerticaAppStatus)
from trove.guestagent.datastore.experimental.vertica.service import VerticaApp
import trove.guestagent.datastore.mysql.service as dbaas
from trove.guestagent.datastore.mysql.service import KeepAliveConnection
from trove.guestagent.datastore.mysql.service import MySqlAdmin
from trove.guestagent.datastore.mysql.service import MySqlApp
from trove.guestagent.datastore.mysql.service import MySqlAppStatus
from trove.guestagent.datastore.mysql.service import MySqlRootAccess
import trove.guestagent.datastore.mysql.service_base as dbaas_base
import trove.guestagent.datastore.service as base_datastore_service
from trove.guestagent.datastore.service import BaseDbStatus
from trove.guestagent.db import models
from trove.guestagent import dbaas as dbaas_sr
from trove.guestagent.dbaas import get_filesystem_volume_stats
from trove.guestagent.dbaas import to_gb
from trove.guestagent import pkg
from trove.guestagent.volume import VolumeDevice
from trove.instance.models import InstanceServiceStatus
from trove.tests.unittests.util import util

CONF = cfg.CONF


"""
Unit tests for the classes and functions in dbaas.py.
"""

FAKE_DB = {"_name": "testDB", "_character_set": "latin2",
           "_collate": "latin2_general_ci"}
FAKE_DB_2 = {"_name": "testDB2", "_character_set": "latin2",
             "_collate": "latin2_general_ci"}
FAKE_USER = [{"_name": "random", "_password": "guesswhat",
              "_host": "%", "_databases": [FAKE_DB]}]

conductor_api.API.get_client = Mock()
conductor_api.API.heartbeat = Mock()


class FakeAppStatus(BaseDbStatus):

    def __init__(self, id, status):
        self.id = id
        self.status = status
        self.next_fake_status = status

    def _get_actual_db_status(self):
        return self.next_fake_status

    def set_next_status(self, next_status):
        self.next_fake_status = next_status

    def _is_query_router(self):
        return False


class DbaasTest(testtools.TestCase):

    def setUp(self):
        super(DbaasTest, self).setUp()
        self.orig_utils_execute_with_timeout = \
            dbaas_base.utils.execute_with_timeout
        self.orig_utils_execute = dbaas_base.utils.execute

    def tearDown(self):
        super(DbaasTest, self).tearDown()
        dbaas_base.utils.execute_with_timeout = \
            self.orig_utils_execute_with_timeout
        dbaas_base.utils.execute = self.orig_utils_execute

    @patch.object(operating_system, 'remove')
    def test_clear_expired_password(self, mock_remove):
        secret_content = ("# The random password set for the "
                          "root user at Wed May 14 14:06:38 2014 "
                          "(local time): somepassword")
        with patch.object(dbaas_base.utils, 'execute',
                          return_value=(secret_content, None)):
            dbaas_base.clear_expired_password()
            self.assertEqual(2, dbaas_base.utils.execute.call_count)
            self.assertEqual(1, mock_remove.call_count)

    @patch.object(operating_system, 'remove')
    def test_no_secret_content_clear_expired_password(self, mock_remove):
        with patch.object(dbaas_base.utils, 'execute',
                          return_value=('', None)):
            dbaas_base.clear_expired_password()
            self.assertEqual(1, dbaas_base.utils.execute.call_count)
            mock_remove.assert_not_called()

    @patch.object(operating_system, 'remove')
    def test_fail_password_update_content_clear_expired_password(self,
                                                                 mock_remove):
        secret_content = ("# The random password set for the "
                          "root user at Wed May 14 14:06:38 2014 "
                          "(local time): somepassword")
        with patch.object(dbaas_base.utils, 'execute',
                          side_effect=[(secret_content, None),
                                       ProcessExecutionError]):
            dbaas_base.clear_expired_password()
            self.assertEqual(2, dbaas_base.utils.execute.call_count)
            mock_remove.assert_not_called()

    @patch.object(operating_system, 'remove')
    @patch.object(dbaas_base.utils, 'execute',
                  side_effect=ProcessExecutionError)
    def test_fail_retrieve_secret_content_clear_expired_password(self,
                                                                 mock_execute,
                                                                 mock_remove):
        dbaas_base.clear_expired_password()
        self.assertEqual(1, mock_execute.call_count)
        mock_remove.assert_not_called()

    @patch.object(MySqlApp.configuration_manager, 'get_value',
                  return_value=MagicMock({'get': 'some password'}))
    def test_get_auth_password(self, get_cnf_mock):
        password = MySqlApp.get_auth_password()
        get_cnf_mock.assert_called_once_with('client')
        get_cnf_mock.return_value.get.assert_called_once_with('password')
        self.assertEqual(get_cnf_mock.return_value.get.return_value, password)

    @patch.object(MySqlApp.configuration_manager, 'get_value',
                  side_effect=RuntimeError('Error'))
    def test_get_auth_password_error(self, get_cnf_mock):
        self.assertRaises(RuntimeError, MySqlApp.get_auth_password)

    def test_service_discovery(self):
        with patch.object(os.path, 'isfile', return_value=True):
            mysql_service = \
                dbaas_base.operating_system.service_discovery(["mysql"])
        self.assertIsNotNone(mysql_service['cmd_start'])
        self.assertIsNotNone(mysql_service['cmd_enable'])

    def test_load_mysqld_options(self):

        output = "mysqld would've been started with the these args:\n"\
                 "--user=mysql --port=3306 --basedir=/usr "\
                 "--tmpdir=/tmp --skip-external-locking"

        with patch.object(os.path, 'isfile', return_value=True):
            dbaas_base.utils.execute = Mock(return_value=(output, None))
            options = dbaas_base.load_mysqld_options()

        self.assertEqual(5, len(options))
        self.assertEqual(["mysql"], options["user"])
        self.assertEqual(["3306"], options["port"])
        self.assertEqual(["/usr"], options["basedir"])
        self.assertEqual(["/tmp"], options["tmpdir"])
        self.assertTrue("skip-external-locking" in options)

    def test_load_mysqld_options_contains_plugin_loads_options(self):
        output = ("mysqld would've been started with the these args:\n"
                  "--plugin-load=blackhole=ha_blackhole.so "
                  "--plugin-load=federated=ha_federated.so")

        with patch.object(os.path, 'isfile', return_value=True):
            dbaas_base.utils.execute = Mock(return_value=(output, None))
            options = dbaas_base.load_mysqld_options()

        self.assertEqual(1, len(options))
        self.assertEqual(["blackhole=ha_blackhole.so",
                          "federated=ha_federated.so"],
                         options["plugin-load"])

    @patch.object(os.path, 'isfile', return_value=True)
    def test_load_mysqld_options_error(self, mock_exists):

        dbaas_base.utils.execute = Mock(side_effect=ProcessExecutionError())

        self.assertFalse(dbaas_base.load_mysqld_options())


class ResultSetStub(object):

    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        return self._rows.__iter__()

    @property
    def rowcount(self):
        return len(self._rows)

    def __repr__(self):
        return self._rows.__repr__()


class MySqlAdminMockTest(testtools.TestCase):

    def setUp(self):
        super(MySqlAdminMockTest, self).setUp()
        dbaas.orig_configuration_manager = dbaas.MySqlApp.configuration_manager
        dbaas.MySqlApp.configuration_manager = Mock()

    def tearDown(self):
        super(MySqlAdminMockTest, self).tearDown()
        dbaas.MySqlApp.configuration_manager = \
            dbaas.orig_configuration_manager

    @patch('trove.guestagent.datastore.mysql.service.MySqlApp'
           '.get_auth_password', return_value='some_password')
    def test_list_databases(self, auth_pwd_mock):
        mock_conn = mock_sql_connection()

        with patch.object(mock_conn, 'execute',
                          return_value=ResultSetStub(
                [('db1', 'utf8', 'utf8_bin'),
                 ('db2', 'utf8', 'utf8_bin'),
                 ('db3', 'utf8', 'utf8_bin')])):
            databases, next_marker = MySqlAdmin().list_databases(limit=10)

        self.assertThat(next_marker, Is(None))
        self.assertThat(len(databases), Is(3))


class MySqlAdminTest(testtools.TestCase):

    def setUp(self):

        super(MySqlAdminTest, self).setUp()

        self.orig_get_engine = dbaas.get_engine
        self.orig_LocalSqlClient = dbaas.LocalSqlClient
        self.orig_LocalSqlClient_enter = dbaas.LocalSqlClient.__enter__
        self.orig_LocalSqlClient_exit = dbaas.LocalSqlClient.__exit__
        self.orig_LocalSqlClient_execute = dbaas.LocalSqlClient.execute
        self.orig_MySQLUser_is_valid_user_name = (
            models.MySQLUser._is_valid_user_name)
        dbaas.get_engine = MagicMock(name='get_engine')
        dbaas.LocalSqlClient = Mock
        dbaas.LocalSqlClient.__enter__ = Mock()
        dbaas.LocalSqlClient.__exit__ = Mock()
        dbaas.LocalSqlClient.execute = Mock()
        # trove.guestagent.common.configuration import ConfigurationManager
        dbaas.orig_configuration_manager = dbaas.MySqlApp.configuration_manager
        dbaas.MySqlApp.configuration_manager = Mock()

        self.mySqlAdmin = MySqlAdmin()

    def tearDown(self):

        super(MySqlAdminTest, self).tearDown()
        dbaas.get_engine = self.orig_get_engine
        dbaas.LocalSqlClient = self.orig_LocalSqlClient
        dbaas.LocalSqlClient.__enter__ = self.orig_LocalSqlClient_enter
        dbaas.LocalSqlClient.__exit__ = self.orig_LocalSqlClient_exit
        dbaas.LocalSqlClient.execute = self.orig_LocalSqlClient_execute
        models.MySQLUser._is_valid_user_name = (
            self.orig_MySQLUser_is_valid_user_name)
        dbaas.MySqlApp.configuration_manager = \
            dbaas.orig_configuration_manager

    def test__associate_dbs(self):
        db_result = [{"grantee": "'test_user'@'%'", "table_schema": "db1"},
                     {"grantee": "'test_user'@'%'", "table_schema": "db2"},
                     {"grantee": "'test_user'@'%'", "table_schema": "db3"},
                     {"grantee": "'test_user1'@'%'", "table_schema": "db1"},
                     {"grantee": "'test_user1'@'%'", "table_schema": "db3"}]
        user = MagicMock()
        user.name = "test_user"
        user.host = "%"
        user.databases = []
        expected = ("SELECT grantee, table_schema FROM "
                    "information_schema.SCHEMA_PRIVILEGES WHERE privilege_type"
                    " != 'USAGE' GROUP BY grantee, table_schema;")

        with patch.object(dbaas.LocalSqlClient, 'execute',
                          Mock(return_value=db_result)):
            self.mySqlAdmin._associate_dbs(user)
            args, _ = dbaas.LocalSqlClient.execute.call_args_list[0]

            self.assertEqual(3, len(user.databases))
            self.assertEqual(expected, args[0].text,
                             "Associate database queries are not the same")

            self.assertTrue(dbaas.LocalSqlClient.execute.called,
                            "The client object was not called")

    def test_change_passwords(self):
        user = [{"name": "test_user", "host": "%", "password": "password"}]
        self.mySqlAdmin.change_passwords(user)
        args, _ = dbaas.LocalSqlClient.execute.call_args_list[0]
        expected = ("UPDATE mysql.user SET Password="
                    "PASSWORD('password') WHERE User = 'test_user' "
                    "AND Host = '%';")
        self.assertEqual(expected, args[0].text,
                         "Change password queries are not the same")

        self.assertTrue(dbaas.LocalSqlClient.execute.called,
                        "The client object was not called")

    def test_update_attributes_password(self):
        db_result = [{"grantee": "'test_user'@'%'", "table_schema": "db1"},
                     {"grantee": "'test_user'@'%'", "table_schema": "db2"}]
        user = MagicMock()
        user.name = "test_user"
        user.host = "%"
        user_attrs = {"password": "password"}
        with patch.object(dbaas.LocalSqlClient, 'execute',
                          Mock(return_value=db_result)):
            with patch.object(self.mySqlAdmin, '_get_user', return_value=user):
                with patch.object(self.mySqlAdmin, 'grant_access'):
                    self.mySqlAdmin.update_attributes('test_user', '%',
                                                      user_attrs)
                    self.assertEqual(0,
                                     self.mySqlAdmin.grant_access.call_count)
            args, _ = dbaas.LocalSqlClient.execute.call_args_list[1]
            expected = ("UPDATE mysql.user SET Password="
                        "PASSWORD('password') WHERE User = 'test_user' "
                        "AND Host = '%';")
            self.assertEqual(expected, args[0].text,
                             "Update attributes queries are not the same")

            self.assertTrue(dbaas.LocalSqlClient.execute.called,
                            "The client object was not called")

    def test_update_attributes_name(self):
        user = MagicMock()
        user.name = "test_user"
        user.host = "%"
        user_attrs = {"name": "new_name"}
        with patch.object(self.mySqlAdmin, '_get_user', return_value=user):
            with patch.object(self.mySqlAdmin, 'grant_access'):
                self.mySqlAdmin.update_attributes('test_user', '%', user_attrs)
                self.mySqlAdmin.grant_access.assert_called_with(
                    'new_name', '%', set([]))
        args, _ = dbaas.LocalSqlClient.execute.call_args_list[1]
        expected = ("UPDATE mysql.user SET User='new_name' "
                    "WHERE User = 'test_user' AND Host = '%';")
        self.assertEqual(expected, args[0].text,
                         "Update attributes queries are not the same")

        self.assertTrue(dbaas.LocalSqlClient.execute.called,
                        "The client object was not called")

    def test_update_attributes_host(self):
        user = MagicMock()
        user.name = "test_user"
        user.host = "%"
        user_attrs = {"host": "new_host"}
        with patch.object(self.mySqlAdmin, '_get_user', return_value=user):
            with patch.object(self.mySqlAdmin, 'grant_access'):
                self.mySqlAdmin.update_attributes('test_user', '%', user_attrs)
                self.mySqlAdmin.grant_access.assert_called_with(
                    'test_user', 'new_host', set([]))
        args, _ = dbaas.LocalSqlClient.execute.call_args_list[1]
        expected = ("UPDATE mysql.user SET Host='new_host' "
                    "WHERE User = 'test_user' AND Host = '%';")
        self.assertEqual(expected, args[0].text,
                         "Update attributes queries are not the same")

        self.assertTrue(dbaas.LocalSqlClient.execute.called,
                        "The client object was not called")

    def test_create_database(self):

        databases = []
        databases.append(FAKE_DB)

        self.mySqlAdmin.create_database(databases)

        args, _ = dbaas.LocalSqlClient.execute.call_args_list[0]
        expected = ("CREATE DATABASE IF NOT EXISTS "
                    "`testDB` CHARACTER SET = 'latin2' "
                    "COLLATE = 'latin2_general_ci';")
        self.assertEqual(expected, args[0].text,
                         "Create database queries are not the same")

        self.assertEqual(1, dbaas.LocalSqlClient.execute.call_count,
                         "The client object was not called exactly once, " +
                         "it was called %d times"
                         % dbaas.LocalSqlClient.execute.call_count)

    def test_create_database_more_than_1(self):

        databases = []
        databases.append(FAKE_DB)
        databases.append(FAKE_DB_2)

        self.mySqlAdmin.create_database(databases)

        args, _ = dbaas.LocalSqlClient.execute.call_args_list[0]
        expected = ("CREATE DATABASE IF NOT EXISTS "
                    "`testDB` CHARACTER SET = 'latin2' "
                    "COLLATE = 'latin2_general_ci';")
        self.assertEqual(expected, args[0].text,
                         "Create database queries are not the same")

        args, _ = dbaas.LocalSqlClient.execute.call_args_list[1]
        expected = ("CREATE DATABASE IF NOT EXISTS "
                    "`testDB2` CHARACTER SET = 'latin2' "
                    "COLLATE = 'latin2_general_ci';")
        self.assertEqual(expected, args[0].text,
                         "Create database queries are not the same")

        self.assertEqual(2, dbaas.LocalSqlClient.execute.call_count,
                         "The client object was not called exactly twice, " +
                         "it was called %d times"
                         % dbaas.LocalSqlClient.execute.call_count)

    def test_create_database_no_db(self):

        databases = []

        self.mySqlAdmin.create_database(databases)

        self.assertFalse(dbaas.LocalSqlClient.execute.called,
                         "The client object was called when it wasn't " +
                         "supposed to")

    def test_delete_database(self):

        database = {"_name": "testDB"}

        self.mySqlAdmin.delete_database(database)

        args, _ = dbaas.LocalSqlClient.execute.call_args
        expected = "DROP DATABASE `testDB`;"
        self.assertEqual(expected, args[0].text,
                         "Delete database queries are not the same")

        self.assertTrue(dbaas.LocalSqlClient.execute.called,
                        "The client object was not called")

    def test_delete_user(self):

        user = {"_name": "testUser", "_host": None}

        self.mySqlAdmin.delete_user(user)

        # For some reason, call_args is None.
        call_args = dbaas.LocalSqlClient.execute.call_args
        if call_args is not None:
            args, _ = call_args
            expected = "DROP USER `testUser`@`%`;"
            self.assertEqual(expected, args[0].text,
                             "Delete user queries are not the same")

            self.assertTrue(dbaas.LocalSqlClient.execute.called,
                            "The client object was not called")

    def test_create_user(self):
        self.mySqlAdmin.create_user(FAKE_USER)
        access_grants_expected = ("GRANT ALL PRIVILEGES ON `testDB`.* TO "
                                  "`random`@`%` IDENTIFIED BY 'guesswhat';")
        create_user_expected = ("GRANT USAGE ON *.* TO `random`@`%` "
                                "IDENTIFIED BY 'guesswhat';")

        create_user, _ = dbaas.LocalSqlClient.execute.call_args_list[0]
        self.assertEqual(create_user_expected, create_user[0].text,
                         "Create user queries are not the same")

        access_grants, _ = dbaas.LocalSqlClient.execute.call_args_list[1]
        self.assertEqual(access_grants_expected, access_grants[0].text,
                         "Create user queries are not the same")
        self.assertEqual(2, dbaas.LocalSqlClient.execute.call_count)

    @patch('trove.guestagent.datastore.mysql.service.MySqlApp'
           '.get_auth_password', return_value='some_password')
    def test_list_databases(self, auth_pwd_mock):
        self.mySqlAdmin.list_databases()
        args, _ = dbaas.LocalSqlClient.execute.call_args
        expected = ["SELECT schema_name as name,",
                    "default_character_set_name as charset,",
                    "default_collation_name as collation",
                    "FROM information_schema.schemata",
                    ("schema_name NOT IN ('" + "', '".join(CONF.ignore_dbs) +
                     "')"),
                    "ORDER BY schema_name ASC",
                    ]
        for text in expected:
            self.assertTrue(text in args[0].text, "%s not in query." % text)
        self.assertFalse("LIMIT " in args[0].text)

    def test_list_databases_with_limit(self):
        limit = 2
        self.mySqlAdmin.list_databases(limit)
        args, _ = dbaas.LocalSqlClient.execute.call_args
        expected = ["SELECT schema_name as name,",
                    "default_character_set_name as charset,",
                    "default_collation_name as collation",
                    "FROM information_schema.schemata",
                    ("schema_name NOT IN ('" + "', '".join(CONF.ignore_dbs) +
                     "')"),
                    "ORDER BY schema_name ASC",
                    ]
        for text in expected:
            self.assertTrue(text in args[0].text, "%s not in query." % text)

        self.assertTrue("LIMIT " + str(limit + 1) in args[0].text)

    def test_list_databases_with_marker(self):
        marker = "aMarker"
        self.mySqlAdmin.list_databases(marker=marker)
        args, _ = dbaas.LocalSqlClient.execute.call_args
        expected = ["SELECT schema_name as name,",
                    "default_character_set_name as charset,",
                    "default_collation_name as collation",
                    "FROM information_schema.schemata",
                    ("schema_name NOT IN ('" + "', '".join(CONF.ignore_dbs) +
                     "')"),
                    "ORDER BY schema_name ASC",
                    ]

        for text in expected:
            self.assertTrue(text in args[0].text, "%s not in query." % text)

        self.assertFalse("LIMIT " in args[0].text)

        self.assertTrue("AND schema_name > '" + marker + "'" in args[0].text)

    def test_list_databases_with_include_marker(self):
        marker = "aMarker"
        self.mySqlAdmin.list_databases(marker=marker, include_marker=True)
        args, _ = dbaas.LocalSqlClient.execute.call_args
        expected = ["SELECT schema_name as name,",
                    "default_character_set_name as charset,",
                    "default_collation_name as collation",
                    "FROM information_schema.schemata",
                    ("schema_name NOT IN ('" + "', '".join(CONF.ignore_dbs) +
                     "')"),
                    "ORDER BY schema_name ASC",
                    ]
        for text in expected:
            self.assertTrue(text in args[0].text, "%s not in query." % text)

        self.assertFalse("LIMIT " in args[0].text)

        self.assertTrue(("AND schema_name >= '%s'" % marker) in args[0].text)

    def test_list_users(self):
        self.mySqlAdmin.list_users()
        args, _ = dbaas.LocalSqlClient.execute.call_args

        expected = ["SELECT User, Host",
                    "FROM mysql.user",
                    "WHERE Host != 'localhost'",
                    "ORDER BY User",
                    ]
        for text in expected:
            self.assertTrue(text in args[0].text, "%s not in query." % text)

        self.assertFalse("LIMIT " in args[0].text)
        self.assertFalse("AND Marker > '" in args[0].text)

    def test_list_users_with_limit(self):
        limit = 2
        self.mySqlAdmin.list_users(limit)
        args, _ = dbaas.LocalSqlClient.execute.call_args

        expected = ["SELECT User, Host",
                    "FROM mysql.user",
                    "WHERE Host != 'localhost'",
                    "ORDER BY User",
                    ("LIMIT " + str(limit + 1)),
                    ]
        for text in expected:
            self.assertTrue(text in args[0].text, "%s not in query." % text)

    def test_list_users_with_marker(self):
        marker = "aMarker"
        self.mySqlAdmin.list_users(marker=marker)
        args, _ = dbaas.LocalSqlClient.execute.call_args

        expected = ["SELECT User, Host, Marker",
                    "FROM mysql.user",
                    "WHERE Host != 'localhost'",
                    "ORDER BY User",
                    ]

        for text in expected:
            self.assertTrue(text in args[0].text, "%s not in query." % text)

        self.assertFalse("LIMIT " in args[0].text)
        self.assertTrue("AND Marker > '" + marker + "'" in args[0].text)

    def test_list_users_with_include_marker(self):
        marker = "aMarker"
        self.mySqlAdmin.list_users(marker=marker, include_marker=True)
        args, _ = dbaas.LocalSqlClient.execute.call_args

        expected = ["SELECT User, Host",
                    "FROM mysql.user",
                    "WHERE Host != 'localhost'",
                    "ORDER BY User",
                    ]

        for text in expected:
            self.assertTrue(text in args[0].text, "%s not in query." % text)

        self.assertFalse("LIMIT " in args[0].text)

        self.assertTrue("AND Marker >= '" + marker + "'" in args[0].text)

    @patch.object(dbaas.MySqlAdmin, '_associate_dbs')
    def test_get_user(self, mock_associate_dbs):
        """
        Unit tests for mySqlAdmin.get_user.
        This test case checks if the sql query formed by the get_user method
        is correct or not by checking with expected query.
        """
        username = "user1"
        hostname = "%"
        user = [{"User": "user1", "Host": "%", 'Password': 'some_thing'}]
        dbaas.LocalSqlClient.execute.return_value.fetchall = Mock(
            return_value=user)
        self.mySqlAdmin.get_user(username, hostname)
        args, _ = dbaas.LocalSqlClient.execute.call_args
        expected = ["SELECT User, Host",
                    "FROM mysql.user",
                    "WHERE Host != 'localhost' AND User = 'user1'",
                    "ORDER BY User, Host",
                    ]

        for text in expected:
            self.assertTrue(text in args[0].text, "%s not in query." % text)
        self.assertEqual(1, mock_associate_dbs.call_count)

    def test_fail_get_user(self):
        username = "os_admin"
        hostname = "host"
        self.assertRaisesRegexp(BadRequest, "Username os_admin is not valid",
                                self.mySqlAdmin.get_user, username, hostname)

    def test_grant_access(self):
        user = MagicMock()
        user.name = "test_user"
        user.host = "%"
        user.password = 'some_password'
        databases = ['db1']
        with patch.object(self.mySqlAdmin, '_get_user', return_value=user):
            self.mySqlAdmin.grant_access('test_user', '%', databases)
        args, _ = dbaas.LocalSqlClient.execute.call_args_list[0]
        expected = ("GRANT ALL PRIVILEGES ON `db1`.* TO `test_user`@`%` "
                    "IDENTIFIED BY PASSWORD 'some_password';")
        self.assertEqual(expected, args[0].text,
                         "Grant access queries are not the same")

        self.assertTrue(dbaas.LocalSqlClient.execute.called,
                        "The client object was not called")

    def test_fail_grant_access(self):
        user = MagicMock()
        user.name = "test_user"
        user.host = "%"
        user.password = 'some_password'
        databases = ['mysql']
        with patch.object(self.mySqlAdmin, '_get_user', return_value=user):
            self.mySqlAdmin.grant_access('test_user', '%', databases)
        # since mysql is not a database to be provided access to,
        # testing that executed was not called in grant access.
        dbaas.LocalSqlClient.execute.assert_not_called()

    def test_is_root_enabled(self):
        self.mySqlAdmin.is_root_enabled()
        args, _ = dbaas.LocalSqlClient.execute.call_args_list[0]
        expected = ("SELECT User FROM mysql.user WHERE "
                    "User = 'root' AND Host != 'localhost';")
        self.assertEqual(expected, args[0].text,
                         "Find root enabled queries are not the same")

        self.assertTrue(dbaas.LocalSqlClient.execute.called,
                        "The client object was not called")

    def test_revoke_access(self):
        user = MagicMock()
        user.name = "test_user"
        user.host = "%"
        user.password = 'some_password'
        databases = ['db1']
        with patch.object(self.mySqlAdmin, '_get_user', return_value=user):
            self.mySqlAdmin.revoke_access('test_usr', '%', databases)
        args, _ = dbaas.LocalSqlClient.execute.call_args_list[0]
        expected = ("REVOKE ALL ON `['db1']`.* FROM `test_user`@`%`;")
        self.assertEqual(expected, args[0].text,
                         "Revoke access queries are not the same")

    def test_list_access(self):
        user = MagicMock()
        user.name = "test_user"
        user.host = "%"
        user.databases = ['db1', 'db2']
        with patch.object(self.mySqlAdmin, '_get_user', return_value=user):
            databases = self.mySqlAdmin.list_access('test_usr', '%')
        self.assertEqual(2, len(databases),
                         "List access queries are not the same")


class MySqlAppTest(testtools.TestCase):

    def setUp(self):
        super(MySqlAppTest, self).setUp()
        self.orig_utils_execute_with_timeout = \
            dbaas_base.utils.execute_with_timeout
        self.orig_time_sleep = time.sleep
        self.orig_unlink = os.unlink
        self.orig_get_auth_password = MySqlApp.get_auth_password
        self.orig_service_discovery = operating_system.service_discovery
        self.FAKE_ID = str(uuid4())
        InstanceServiceStatus.create(instance_id=self.FAKE_ID,
                                     status=rd_instance.ServiceStatuses.NEW)
        self.appStatus = FakeAppStatus(self.FAKE_ID,
                                       rd_instance.ServiceStatuses.NEW)
        self.mySqlApp = MySqlApp(self.appStatus)
        mysql_service = {'cmd_start': Mock(),
                         'cmd_stop': Mock(),
                         'cmd_enable': Mock(),
                         'cmd_disable': Mock(),
                         'cmd_bootstrap_pxc_cluster': Mock(),
                         'bin': Mock()}
        operating_system.service_discovery = Mock(
            return_value=mysql_service)
        pxc_system.service_discovery = Mock(
            return_value=mysql_service)
        time.sleep = Mock()
        os.unlink = Mock()
        MySqlApp.get_auth_password = Mock()
        self.mock_client = Mock()
        self.mock_execute = Mock()
        self.mock_client.__enter__ = Mock()
        self.mock_client.__exit__ = Mock()
        self.mock_client.__enter__.return_value.execute = self.mock_execute
        dbaas.orig_configuration_manager = dbaas.MySqlApp.configuration_manager
        dbaas.MySqlApp.configuration_manager = Mock()
        self.orig_create_engine = sqlalchemy.create_engine

    def tearDown(self):
        super(MySqlAppTest, self).tearDown()
        dbaas_base.utils.execute_with_timeout = \
            self.orig_utils_execute_with_timeout
        time.sleep = self.orig_time_sleep
        os.unlink = self.orig_unlink
        operating_system.service_discovery = self.orig_service_discovery
        MySqlApp.get_auth_password = self.orig_get_auth_password
        InstanceServiceStatus.find_by(instance_id=self.FAKE_ID).delete()
        dbaas.MySqlApp.configuration_manager = \
            dbaas.orig_configuration_manager
        sqlalchemy.create_engine = self.orig_create_engine

    def assert_reported_status(self, expected_status):
        service_status = InstanceServiceStatus.find_by(
            instance_id=self.FAKE_ID)
        self.assertEqual(expected_status, service_status.status)

    def mysql_starts_successfully(self):
        def start(update_db=False):
            self.appStatus.set_next_status(
                rd_instance.ServiceStatuses.RUNNING)

        self.mySqlApp.start_mysql.side_effect = start

    def mysql_starts_unsuccessfully(self):
        def start():
            raise RuntimeError("MySQL failed to start!")

        self.mySqlApp.start_mysql.side_effect = start

    def mysql_stops_successfully(self):
        def stop():
            self.appStatus.set_next_status(
                rd_instance.ServiceStatuses.SHUTDOWN)

        self.mySqlApp.stop_db.side_effect = stop

    def mysql_stops_unsuccessfully(self):
        def stop():
            raise RuntimeError("MySQL failed to stop!")

        self.mySqlApp.stop_db.side_effect = stop

    def test_stop_mysql(self):

        dbaas_base.utils.execute_with_timeout = Mock()
        self.appStatus.set_next_status(
            rd_instance.ServiceStatuses.SHUTDOWN)

        self.mySqlApp.stop_db()
        self.assert_reported_status(rd_instance.ServiceStatuses.NEW)

    def test_stop_mysql_with_db_update(self):

        dbaas_base.utils.execute_with_timeout = Mock()
        self.appStatus.set_next_status(
            rd_instance.ServiceStatuses.SHUTDOWN)

        self.mySqlApp.stop_db(True)
        self.assertTrue(conductor_api.API.heartbeat.called_once_with(
            self.FAKE_ID,
            {'service_status':
             rd_instance.ServiceStatuses.SHUTDOWN.description}))

    @patch.object(utils, 'execute_with_timeout')
    def test_stop_mysql_do_not_start_on_reboot(self, mock_execute):

        self.appStatus.set_next_status(
            rd_instance.ServiceStatuses.SHUTDOWN)

        self.mySqlApp.stop_db(True, True)
        self.assertTrue(conductor_api.API.heartbeat.called_once_with(
            self.FAKE_ID,
            {'service_status':
             rd_instance.ServiceStatuses.SHUTDOWN.description}))
        self.assertEqual(2, mock_execute.call_count)

    def test_stop_mysql_error(self):
        dbaas_base.utils.execute_with_timeout = Mock()
        self.appStatus.set_next_status(rd_instance.ServiceStatuses.RUNNING)
        self.mySqlApp.state_change_wait_time = 1
        self.assertRaises(RuntimeError, self.mySqlApp.stop_db)

    @patch.object(operating_system, 'service_discovery',
                  side_effect=KeyError('error'))
    @patch.object(utils, 'execute_with_timeout')
    def test_stop_mysql_key_error(self, mock_execute, mock_service):
        self.assertRaisesRegexp(RuntimeError, 'Service is not discovered.',
                                self.mySqlApp.stop_db)
        self.assertEqual(0, mock_execute.call_count)

    def test_restart_is_successful(self):

        self.mySqlApp.start_mysql = Mock()
        self.mySqlApp.stop_db = Mock()
        self.mysql_stops_successfully()
        self.mysql_starts_successfully()

        self.mySqlApp.restart()

        self.assertTrue(self.mySqlApp.stop_db.called)
        self.assertTrue(self.mySqlApp.start_mysql.called)
        self.assertTrue(conductor_api.API.heartbeat.called_once_with(
            self.FAKE_ID,
            {'service_status':
             rd_instance.ServiceStatuses.RUNNING.description}))

    def test_restart_mysql_wont_start_up(self):

        self.mySqlApp.start_mysql = Mock()
        self.mySqlApp.stop_db = Mock()
        self.mysql_stops_unsuccessfully()
        self.mysql_starts_unsuccessfully()

        self.assertRaises(RuntimeError, self.mySqlApp.restart)

        self.assertTrue(self.mySqlApp.stop_db.called)
        self.assertFalse(self.mySqlApp.start_mysql.called)
        self.assert_reported_status(rd_instance.ServiceStatuses.NEW)

    @patch.object(dbaas.MySqlApp, 'get_data_dir', return_value='some path')
    def test_wipe_ib_logfiles_error(self, get_datadir_mock):

        mocked = Mock(side_effect=ProcessExecutionError('Error'))
        dbaas_base.utils.execute_with_timeout = mocked

        self.assertRaises(ProcessExecutionError,
                          self.mySqlApp.wipe_ib_logfiles)

    def test_start_mysql(self):

        dbaas_base.utils.execute_with_timeout = Mock()
        self.appStatus.set_next_status(rd_instance.ServiceStatuses.RUNNING)
        self.mySqlApp._enable_mysql_on_boot = Mock()
        self.mySqlApp.start_mysql()
        self.assert_reported_status(rd_instance.ServiceStatuses.NEW)

    def test_start_mysql_with_db_update(self):

        dbaas_base.utils.execute_with_timeout = Mock()
        self.mySqlApp._enable_mysql_on_boot = Mock()
        self.appStatus.set_next_status(rd_instance.ServiceStatuses.RUNNING)

        self.mySqlApp.start_mysql(update_db=True)
        self.assertTrue(conductor_api.API.heartbeat.called_once_with(
            self.FAKE_ID,
            {'service_status':
             rd_instance.ServiceStatuses.RUNNING.description}))

    def test_start_mysql_runs_forever(self):

        dbaas_base.utils.execute_with_timeout = Mock()
        self.mySqlApp._enable_mysql_on_boot = Mock()
        self.mySqlApp.state_change_wait_time = 1
        self.appStatus.set_next_status(rd_instance.ServiceStatuses.SHUTDOWN)

        self.assertRaises(RuntimeError, self.mySqlApp.start_mysql)
        self.assertTrue(conductor_api.API.heartbeat.called_once_with(
            self.FAKE_ID,
            {'service_status':
             rd_instance.ServiceStatuses.SHUTDOWN.description}))

    def test_start_mysql_error(self):

        self.mySqlApp._enable_mysql_on_boot = Mock()
        mocked = Mock(side_effect=ProcessExecutionError('Error'))
        dbaas_base.utils.execute_with_timeout = mocked

        self.assertRaises(RuntimeError, self.mySqlApp.start_mysql)

    def test_start_db_with_conf_changes(self):
        self.mySqlApp.start_mysql = Mock()
        self.mysql_starts_successfully()

        self.appStatus.status = rd_instance.ServiceStatuses.SHUTDOWN
        with patch.object(self.mySqlApp, '_reset_configuration') as cfg_reset:
            configuration = 'some junk'
            self.mySqlApp.start_db_with_conf_changes(configuration)
            cfg_reset.assert_called_once_with(configuration)

        self.assertTrue(self.mySqlApp.start_mysql.called)
        self.assertEqual(rd_instance.ServiceStatuses.RUNNING,
                         self.appStatus._get_actual_db_status())

    def test_start_db_with_conf_changes_mysql_is_running(self):
        self.mySqlApp.start_mysql = Mock()

        self.appStatus.status = rd_instance.ServiceStatuses.RUNNING
        self.assertRaises(RuntimeError,
                          self.mySqlApp.start_db_with_conf_changes,
                          Mock())

    def test_configuration_reset(self):
        with patch.object(self.mySqlApp, '_reset_configuration') as cfg_reset:
            configuration = {'config_contents': 'some junk'}
            self.mySqlApp.reset_configuration(configuration=configuration)
            cfg_reset.assert_called_once_with('some junk')

    @patch.object(dbaas.MySqlApp, 'get_auth_password',
                  return_value='some_password')
    def test_reset_configuration(self, auth_pwd_mock):
        save_cfg_mock = Mock()
        apply_mock = Mock()
        wipe_ib_mock = Mock()

        configuration = {'config_contents': 'some junk'}

        self.mySqlApp.configuration_manager.save_configuration = save_cfg_mock
        self.mySqlApp.configuration_manager.apply_system_override = apply_mock
        self.mySqlApp.wipe_ib_logfiles = wipe_ib_mock
        self.mySqlApp.reset_configuration(configuration=configuration)

        save_cfg_mock.assert_called_once_with('some junk')
        apply_mock.assert_called_once_with(
            {'client': {'user': dbaas_base.ADMIN_USER_NAME,
                        'password': auth_pwd_mock.return_value}})
        wipe_ib_mock.assert_called_once_with()

    @patch.object(utils, 'execute_with_timeout')
    def test__enable_mysql_on_boot(self, mock_execute):
        mysql_service = \
            dbaas_base.operating_system.service_discovery(["mysql"])
        self.mySqlApp._enable_mysql_on_boot()
        self.assertEqual(1, mock_execute.call_count)
        mock_execute.assert_called_with(mysql_service['cmd_enable'],
                                        shell=True)

    @patch.object(operating_system, 'service_discovery',
                  side_effect=KeyError('error'))
    @patch.object(utils, 'execute_with_timeout')
    def test_fail__enable_mysql_on_boot(self, mock_execute, mock_service):
        self.assertRaisesRegexp(RuntimeError, 'Service is not discovered.',
                                self.mySqlApp._enable_mysql_on_boot)
        self.assertEqual(0, mock_execute.call_count)

    @patch.object(utils, 'execute_with_timeout')
    def test__disable_mysql_on_boot(self, mock_execute):
        mysql_service = \
            dbaas_base.operating_system.service_discovery(["mysql"])
        self.mySqlApp._disable_mysql_on_boot()
        self.assertEqual(1, mock_execute.call_count)
        mock_execute.assert_called_with(mysql_service['cmd_disable'],
                                        shell=True)

    @patch.object(operating_system, 'service_discovery',
                  side_effect=KeyError('error'))
    @patch.object(utils, 'execute_with_timeout')
    def test_fail__disable_mysql_on_boot(self, mock_execute, mock_service):
        self.assertRaisesRegexp(RuntimeError, 'Service is not discovered.',
                                self.mySqlApp._disable_mysql_on_boot)
        self.assertEqual(0, mock_execute.call_count)

    def test_update_overrides(self):
        override_value = {'key': 'value'}
        with patch.object(self.mySqlApp.configuration_manager,
                          'apply_user_override') as apply_usr_mock:
            self.mySqlApp.update_overrides(override_value)
            apply_usr_mock.assert_called_once_with({'mysqld': override_value})

    def test_remove_override(self):
        with patch.object(self.mySqlApp.configuration_manager,
                          'remove_user_override') as remove_usr_mock:
            self.mySqlApp.remove_overrides()
            remove_usr_mock.assert_called_once_with()

    def test_write_replication_source_overrides(self):
        with patch.object(self.mySqlApp.configuration_manager,
                          'apply_system_override') as apply_sys_mock:
            self.mySqlApp.write_replication_source_overrides('something')
            apply_sys_mock.assert_called_once_with('something',
                                                   dbaas_base.CNF_MASTER)

    def test_write_replication_replica_overrides(self):
        with patch.object(self.mySqlApp.configuration_manager,
                          'apply_system_override') as apply_sys_mock:
            self.mySqlApp.write_replication_replica_overrides('something')
            apply_sys_mock.assert_called_once_with('something',
                                                   dbaas_base.CNF_SLAVE)

    def test_remove_replication_source_overrides(self):
        with patch.object(self.mySqlApp.configuration_manager,
                          'remove_system_override') as remove_sys_mock:
            self.mySqlApp.remove_replication_source_overrides()
            remove_sys_mock.assert_called_once_with(dbaas_base.CNF_MASTER)

    def test_remove_replication_replica_overrides(self):
        with patch.object(self.mySqlApp.configuration_manager,
                          'remove_system_override') as remove_sys_mock:
            self.mySqlApp.remove_replication_replica_overrides()
            remove_sys_mock.assert_called_once_with(dbaas_base.CNF_SLAVE)

    def test_exists_replication_source_overrides(self):
        with patch.object(self.mySqlApp.configuration_manager,
                          'has_system_override',
                          return_value=Mock()) as exists_mock:
            self.assertEqual(
                exists_mock.return_value,
                self.mySqlApp.exists_replication_source_overrides())

    @patch.object(dbaas, 'get_engine',
                  return_value=MagicMock(name='get_engine'))
    def test_grant_replication_privilege(self, *args):
        replication_user = {'name': 'testUSr', 'password': 'somePwd'}
        with patch.object(dbaas.MySqlApp, 'local_sql_client',
                          return_value=self.mock_client):
            self.mySqlApp.grant_replication_privilege(replication_user)
        args, _ = self.mock_execute.call_args_list[0]
        expected = ("GRANT REPLICATION SLAVE ON *.* TO `testUSr`@`%` "
                    "IDENTIFIED BY 'somePwd';")
        self.assertEqual(expected, args[0].text,
                         "Replication grant statements are not the same")

    @patch.object(dbaas, 'get_engine',
                  return_value=MagicMock(name='get_engine'))
    def test_get_port(self, *args):
        with patch.object(dbaas.MySqlApp, 'local_sql_client',
                          return_value=self.mock_client):
            self.mySqlApp.get_port()
        args, _ = self.mock_execute.call_args_list[0]
        expected = ("SELECT @@port")
        self.assertEqual(expected, args[0],
                         "Port queries are not the same")

    @patch.object(dbaas, 'get_engine',
                  return_value=MagicMock(name='get_engine'))
    def test_get_binlog_position(self, *args):
        result = {'File': 'mysql-bin.003', 'Position': '73'}
        self.mock_execute.return_value.first = Mock(return_value=result)
        with patch.object(dbaas.MySqlApp, 'local_sql_client',
                          return_value=self.mock_client):
            found_result = self.mySqlApp.get_binlog_position()

        self.assertEqual(result['File'], found_result['log_file'])
        self.assertEqual(result['Position'], found_result['position'])

        args, _ = self.mock_execute.call_args_list[0]
        expected = ("SHOW MASTER STATUS")
        self.assertEqual(expected, args[0],
                         "Master status queries are not the same")

    @patch.object(dbaas, 'get_engine',
                  return_value=MagicMock(name='get_engine'))
    def test_execute_on_client(self, *args):
        with patch.object(dbaas.MySqlApp, 'local_sql_client',
                          return_value=self.mock_client):
            self.mySqlApp.execute_on_client('show tables')
        args, _ = self.mock_execute.call_args_list[0]
        expected = ("show tables")
        self.assertEqual(expected, args[0],
                         "Sql statements are not the same")

    @patch.object(dbaas, 'get_engine',
                  return_value=MagicMock(name='get_engine'))
    @patch.object(dbaas.MySqlApp, '_wait_for_slave_status')
    def test_start_slave(self, *args):
        with patch.object(dbaas.MySqlApp, 'local_sql_client',
                          return_value=self.mock_client):
            self.mySqlApp.start_slave()
        args, _ = self.mock_execute.call_args_list[0]
        expected = ("START SLAVE")
        self.assertEqual(expected, args[0],
                         "Sql statements are not the same")

    @patch.object(dbaas, 'get_engine',
                  return_value=MagicMock(name='get_engine'))
    @patch.object(dbaas.MySqlApp, '_wait_for_slave_status')
    def test_stop_slave_with_failover(self, *args):
        self.mock_execute.return_value.first = Mock(
            return_value={'Master_User': 'root'})
        with patch.object(dbaas.MySqlApp, 'local_sql_client',
                          return_value=self.mock_client):
            result = self.mySqlApp.stop_slave(True)
        self.assertEqual('root', result['replication_user'])

        expected = ["SHOW SLAVE STATUS", "STOP SLAVE", "RESET SLAVE ALL"]
        self.assertEqual(len(expected), len(self.mock_execute.call_args_list))
        for i in range(len(self.mock_execute.call_args_list)):
            args, _ = self.mock_execute.call_args_list[i]
            self.assertEqual(expected[i], args[0],
                             "Sql statements are not the same")

    @patch.object(dbaas, 'get_engine',
                  return_value=MagicMock(name='get_engine'))
    @patch.object(dbaas.MySqlApp, '_wait_for_slave_status')
    def test_stop_slave_without_failover(self, *args):
        self.mock_execute.return_value.first = Mock(
            return_value={'Master_User': 'root'})
        with patch.object(dbaas.MySqlApp, 'local_sql_client',
                          return_value=self.mock_client):
            result = self.mySqlApp.stop_slave(False)
        self.assertEqual('root', result['replication_user'])

        expected = ["SHOW SLAVE STATUS", "STOP SLAVE", "RESET SLAVE ALL",
                    "DROP USER root"]
        self.assertEqual(len(expected), len(self.mock_execute.call_args_list))
        for i in range(len(self.mock_execute.call_args_list)):
            args, _ = self.mock_execute.call_args_list[i]
            self.assertEqual(expected[i], args[0],
                             "Sql statements are not the same")

    @patch.object(dbaas, 'get_engine',
                  return_value=MagicMock(name='get_engine'))
    def test_stop_master(self, *args):
        with patch.object(dbaas.MySqlApp, 'local_sql_client',
                          return_value=self.mock_client):
            self.mySqlApp.stop_master()
        args, _ = self.mock_execute.call_args_list[0]
        expected = ("RESET MASTER")
        self.assertEqual(expected, args[0],
                         "Sql statements are not the same")

    @patch.object(dbaas, 'get_engine',
                  return_value=MagicMock(name='get_engine'))
    def test__wait_for_slave_status(self, *args):
        mock_client = Mock()
        mock_client.execute = Mock()
        result = ['Slave_running', 'on']
        mock_client.execute.return_value.first = Mock(return_value=result)
        self.mySqlApp._wait_for_slave_status('ON', mock_client, 5)
        args, _ = mock_client.execute.call_args_list[0]
        expected = ("SHOW GLOBAL STATUS like 'slave_running'")
        self.assertEqual(expected, args[0],
                         "Sql statements are not the same")

    @patch.object(dbaas, 'get_engine',
                  return_value=MagicMock(name='get_engine'))
    @patch.object(utils, 'poll_until', side_effect=PollTimeOut)
    def test_fail__wait_for_slave_status(self, *args):
        self.assertRaisesRegexp(RuntimeError,
                                "Replication is not on after 5 seconds.",
                                self.mySqlApp._wait_for_slave_status, 'ON',
                                Mock(), 5)

    @patch.object(dbaas, 'get_engine',
                  return_value=MagicMock(name='get_engine'))
    def test__get_slave_status(self, *args):
        self.mock_execute.return_value.first = Mock(return_value='some_thing')
        with patch.object(dbaas.MySqlApp, 'local_sql_client',
                          return_value=self.mock_client):
            result = self.mySqlApp._get_slave_status()
        self.assertEqual('some_thing', result)
        args, _ = self.mock_execute.call_args_list[0]
        expected = ("SHOW SLAVE STATUS")
        self.assertEqual(expected, args[0],
                         "Sql statements are not the same")

    @patch.object(dbaas, 'get_engine',
                  return_value=MagicMock(name='get_engine'))
    def test_get_latest_txn_id(self, *args):
        self.mock_execute.return_value.first = Mock(return_value=['some_thing']
                                                    )
        with patch.object(dbaas.MySqlApp, 'local_sql_client',
                          return_value=self.mock_client):
            result = self.mySqlApp.get_latest_txn_id()
        self.assertEqual('some_thing', result)
        args, _ = self.mock_execute.call_args_list[0]
        expected = ("SELECT @@global.gtid_executed")
        self.assertEqual(expected, args[0],
                         "Sql statements are not the same")

    @patch.object(dbaas, 'get_engine',
                  return_value=MagicMock(name='get_engine'))
    def test_wait_for_txn(self, *args):
        with patch.object(dbaas.MySqlApp, 'local_sql_client',
                          return_value=self.mock_client):
            self.mySqlApp.wait_for_txn('abcd')
        args, _ = self.mock_execute.call_args_list[0]
        expected = ("SELECT WAIT_UNTIL_SQL_THREAD_AFTER_GTIDS('abcd')")
        self.assertEqual(expected, args[0],
                         "Sql statements are not the same")

    @patch.object(dbaas, 'get_engine',
                  return_value=MagicMock(name='get_engine'))
    def test_get_txn_count(self, *args):
        self.mock_execute.return_value.first = Mock(
            return_value=['b1f3f33a-0789-ee1c-43f3-f8373e12f1ea:1'])
        with patch.object(dbaas.MySqlApp, 'local_sql_client',
                          return_value=self.mock_client):
            result = self.mySqlApp.get_txn_count()
        self.assertEqual(1, result)
        args, _ = self.mock_execute.call_args_list[0]
        expected = ("SELECT @@global.gtid_executed")
        self.assertEqual(expected, args[0],
                         "Sql statements are not the same")

    def test_install(self):

        self.mySqlApp._install_mysql = Mock()
        pkg.Package.pkg_is_installed = Mock(return_value=False)
        utils.execute_with_timeout = Mock()
        pkg.Package.pkg_install = Mock()
        self.mySqlApp._clear_mysql_config = Mock()
        self.mySqlApp._create_mysql_confd_dir = Mock()
        self.mySqlApp.start_mysql = Mock()
        self.mySqlApp.install_if_needed(["package"])
        self.assertTrue(pkg.Package.pkg_install.called)
        self.assert_reported_status(rd_instance.ServiceStatuses.NEW)

    @patch.object(utils, 'generate_random_password',
                  return_value='some_password')
    def test_secure(self, auth_pwd_mock):

        dbaas_base.clear_expired_password = Mock()
        self.mySqlApp.start_mysql = Mock()
        self.mySqlApp.stop_db = Mock()
        self.mySqlApp._reset_configuration = Mock()
        self.mySqlApp._apply_user_overrides = Mock()
        self.mysql_stops_successfully()
        self.mysql_starts_successfully()
        sqlalchemy.create_engine = Mock()

        self.mySqlApp.secure('contents', 'overrides')

        self.assertTrue(self.mySqlApp.stop_db.called)
        reset_config_calls = [call('contents', auth_pwd_mock.return_value),
                              call('contents', auth_pwd_mock.return_value)]
        self.mySqlApp._reset_configuration.has_calls(reset_config_calls)

        apply_overrides_calls = [call('overrides'),
                                 call('overrides')]
        self.mySqlApp._reset_configuration.has_calls(apply_overrides_calls)
        self.assertTrue(self.mySqlApp.start_mysql.called)
        self.assert_reported_status(rd_instance.ServiceStatuses.NEW)

    @patch.object(dbaas, 'get_engine',
                  return_value=MagicMock(name='get_engine'))
    @patch.object(utils, 'generate_random_password',
                  return_value='some_password')
    def test_secure_root(self, *args):
        with patch.object(dbaas.MySqlApp, 'local_sql_client',
                          return_value=self.mock_client):
            self.mySqlApp.secure_root()
        update_root_password, _ = self.mock_execute.call_args_list[0]
        update_expected = ("UPDATE mysql.user SET Password="
                           "PASSWORD('some_password') "
                           "WHERE User = 'root' AND Host = 'localhost';")

        remove_root, _ = self.mock_execute.call_args_list[1]
        remove_expected = ("DELETE FROM mysql.user WHERE "
                           "User = 'root' AND Host != 'localhost';")

        self.assertEqual(update_expected, update_root_password[0].text,
                         "Update root password queries are not the same")
        self.assertEqual(remove_expected, remove_root[0].text,
                         "Remove root queries are not the same")

    @patch.object(operating_system, 'create_directory')
    def test__create_mysql_confd_dir(self, mkdir_mock):
        self.mySqlApp._create_mysql_confd_dir()
        mkdir_mock.assert_called_once_with('/etc/mysql/conf.d', as_root=True)

    @patch.object(operating_system, 'move')
    def test__clear_mysql_config(self, mock_move):
        self.mySqlApp._clear_mysql_config()
        self.assertEqual(3, mock_move.call_count)

    @patch.object(operating_system, 'move', side_effect=ProcessExecutionError)
    def test_exception__clear_mysql_config(self, mock_move):
        self.mySqlApp._clear_mysql_config()
        # call-count needs to be same as normal,
        # because exception is eaten to make the flow goto next file-move.
        self.assertEqual(3, mock_move.call_count)

    @patch.object(dbaas, 'get_engine',
                  return_value=MagicMock(name='get_engine'))
    def test_apply_overrides(self, *args):
        overrides = {'sort_buffer_size': 1000000}
        with patch.object(dbaas.MySqlApp, 'local_sql_client',
                          return_value=self.mock_client):
            self.mySqlApp.apply_overrides(overrides)
        args, _ = self.mock_execute.call_args_list[0]
        expected = ("SET GLOBAL sort_buffer_size=1000000")
        self.assertEqual(expected, args[0].text,
                         "Set global statements are not the same")

    @patch.object(dbaas, 'get_engine',
                  return_value=MagicMock(name='get_engine'))
    def test_make_read_only(self, *args):
        with patch.object(dbaas.MySqlApp, 'local_sql_client',
                          return_value=self.mock_client):
            self.mySqlApp.make_read_only('ON')
        args, _ = self.mock_execute.call_args_list[0]
        expected = ("set global read_only = ON")
        self.assertEqual(expected, args[0].text,
                         "Set read_only statements are not the same")

    def test_install_install_error(self):

        self.mySqlApp.start_mysql = Mock()
        self.mySqlApp.stop_db = Mock()
        pkg.Package.pkg_is_installed = Mock(return_value=False)
        self.mySqlApp._clear_mysql_config = Mock()
        self.mySqlApp._create_mysql_confd_dir = Mock()
        pkg.Package.pkg_install = \
            Mock(side_effect=pkg.PkgPackageStateError("Install error"))

        self.assertRaises(pkg.PkgPackageStateError,
                          self.mySqlApp.install_if_needed, ["package"])

        self.assert_reported_status(rd_instance.ServiceStatuses.NEW)

    def test_secure_write_conf_error(self):

        dbaas_base.clear_expired_password = Mock()
        self.mySqlApp.start_mysql = Mock()
        self.mySqlApp.stop_db = Mock()
        self.mySqlApp._reset_configuration = Mock(
            side_effect=IOError("Could not write file"))
        self.mySqlApp._apply_user_overrides = Mock()
        self.mysql_stops_successfully()
        self.mysql_starts_successfully()
        sqlalchemy.create_engine = Mock()

        self.assertRaises(IOError, self.mySqlApp.secure, "foo", None)

        self.assertTrue(self.mySqlApp.stop_db.called)
        self.assertFalse(self.mySqlApp.start_mysql.called)
        self.assert_reported_status(rd_instance.ServiceStatuses.NEW)

    @patch.object(dbaas, 'get_engine',
                  return_value=MagicMock(name='get_engine'))
    def test_reset_admin_password(self, mock_engine):
        with patch.object(dbaas.MySqlApp, 'local_sql_client',
                          return_value=self.mock_client):
            config_manager = self.mySqlApp.configuration_manager
            config_manager.apply_system_override = Mock()
            self.mySqlApp._create_admin_user = Mock()
            self.mySqlApp.reset_admin_password("newpassword")
            self.assertEqual(1,
                             config_manager.apply_system_override.call_count)
            self.assertEqual(1, self.mySqlApp._create_admin_user.call_count)


class TextClauseMatcher(object):

    def __init__(self, text):
        self.text = text

    def __repr__(self):
        return "TextClause(%s)" % self.text

    def __eq__(self, arg):
        print("Matching %s" % arg.text)
        return self.text in arg.text


def mock_sql_connection():
    utils.execute_with_timeout = MagicMock(return_value=['fake_password',
                                                         None])
    mock_engine = MagicMock()
    sqlalchemy.create_engine = MagicMock(return_value=mock_engine)
    mock_conn = MagicMock()
    dbaas.LocalSqlClient.__enter__ = MagicMock(return_value=mock_conn)
    dbaas.LocalSqlClient.__exit__ = MagicMock(return_value=None)
    return mock_conn


class MySqlAppMockTest(testtools.TestCase):

    def setUp(self):
        super(MySqlAppMockTest, self).setUp()
        self.orig_utils_execute_with_timeout = utils.execute_with_timeout

    def tearDown(self):
        super(MySqlAppMockTest, self).tearDown()
        utils.execute_with_timeout = self.orig_utils_execute_with_timeout

    @patch.object(utils, 'generate_random_password',
                  return_value='some_password')
    def test_secure_keep_root(self, auth_pwd_mock):
        mock_conn = mock_sql_connection()

        with patch.object(mock_conn, 'execute', return_value=None):
            utils.execute_with_timeout = MagicMock(return_value=None)
            # skip writing the file for now
            with patch.object(os.path, 'isfile', return_value=False):
                mock_status = MagicMock()
                mock_status.wait_for_real_status_to_change_to = MagicMock(
                    return_value=True)
                dbaas_base.clear_expired_password = \
                    MagicMock(return_value=None)
                app = MySqlApp(mock_status)
                app._reset_configuration = MagicMock()
                app.start_mysql = MagicMock(return_value=None)
                app._wait_for_mysql_to_be_really_alive = MagicMock(
                    return_value=True)
                app.stop_db = MagicMock(return_value=None)
                app.secure('foo', None)
                reset_config_calls = [call('foo', auth_pwd_mock.return_value)]
                app._reset_configuration.assert_has_calls(reset_config_calls)
                self.assertTrue(mock_conn.execute.called)

    @patch('trove.guestagent.datastore.mysql.service.MySqlApp'
           '.get_auth_password', return_value='some_password')
    def test_secure_with_mycnf_error(self, auth_pwd_mock):
        mock_conn = mock_sql_connection()

        with patch.object(mock_conn, 'execute', return_value=None):
            with patch.object(operating_system, 'service_discovery',
                              return_value={'cmd_stop': 'service mysql stop'}):
                utils.execute_with_timeout = MagicMock(return_value=None)
                # skip writing the file for now
                with patch.object(dbaas.MySqlApp, '_reset_configuration',
                                  side_effect=RuntimeError('Error')):
                    mock_status = MagicMock()
                    mock_status.wait_for_real_status_to_change_to = MagicMock(
                        return_value=True)
                    dbaas_base.clear_expired_password = \
                        MagicMock(return_value=None)
                    app = MySqlApp(mock_status)
                    dbaas_base.clear_expired_password = \
                        MagicMock(return_value=None)
                    self.assertRaises(RuntimeError, app.secure, None, None)
                    self.assertTrue(mock_conn.execute.called)
                    # At least called twice
                    self.assertTrue(mock_conn.execute.call_count >= 2)
                    (mock_status.wait_for_real_status_to_change_to.
                     assert_called_with(rd_instance.ServiceStatuses.SHUTDOWN,
                                        app.state_change_wait_time, False))


class MySqlRootStatusTest(testtools.TestCase):

    def setUp(self):
        super(MySqlRootStatusTest, self).setUp()
        self.orig_utils_execute_with_timeout = utils.execute_with_timeout
        dbaas.orig_configuration_manager = dbaas.MySqlApp.configuration_manager
        dbaas.MySqlApp.configuration_manager = Mock()

    def tearDown(self):
        super(MySqlRootStatusTest, self).tearDown()
        utils.execute_with_timeout = self.orig_utils_execute_with_timeout
        dbaas.MySqlApp.configuration_manager = \
            dbaas.orig_configuration_manager

    @patch.object(dbaas.MySqlApp, 'get_auth_password',
                  return_value='some_password')
    def test_root_is_enabled(self, auth_pwd_mock):
        mock_conn = mock_sql_connection()

        mock_rs = MagicMock()
        mock_rs.rowcount = 1
        with patch.object(mock_conn, 'execute', return_value=mock_rs):
            self.assertThat(MySqlRootAccess().is_root_enabled(), Is(True))

    @patch.object(dbaas.MySqlApp, 'get_auth_password',
                  return_value='some_password')
    def test_root_is_not_enabled(self, auth_pwd_mock):
        mock_conn = mock_sql_connection()

        mock_rs = MagicMock()
        mock_rs.rowcount = 0
        with patch.object(mock_conn, 'execute', return_value=mock_rs):
            self.assertThat(MySqlRootAccess().is_root_enabled(), Equals(False))

    @patch.object(dbaas.MySqlApp, 'get_auth_password',
                  return_value='some_password')
    def test_enable_root(self, auth_pwd_mock):
        mock_conn = mock_sql_connection()

        with patch.object(mock_conn, 'execute', return_value=None):
            # invocation
            user_ser = MySqlRootAccess().enable_root()
            # verification
            self.assertThat(user_ser, Not(Is(None)))
            mock_conn.execute.assert_any_call(TextClauseMatcher('CREATE USER'),
                                              user='root', host='%')
            mock_conn.execute.assert_any_call(TextClauseMatcher(
                'GRANT ALL PRIVILEGES ON *.*'))
            mock_conn.execute.assert_any_call(TextClauseMatcher(
                'UPDATE mysql.user'))

    def test_enable_root_failed(self):
        with patch.object(models.MySQLUser, '_is_valid_user_name',
                          return_value=False):
            self.assertRaises(ValueError, MySqlAdmin().enable_root)


class MockStats:
    f_blocks = 1024 ** 2
    f_bsize = 4096
    f_bfree = 512 * 1024


class InterrogatorTest(testtools.TestCase):

    def tearDown(self):
        super(InterrogatorTest, self).tearDown()

    def test_to_gb(self):
        result = to_gb(123456789)
        self.assertEqual(0.11, result)

    def test_to_gb_zero(self):
        result = to_gb(0)
        self.assertEqual(0.0, result)

    def test_get_filesystem_volume_stats(self):
        with patch.object(os, 'statvfs', return_value=MockStats):
            result = get_filesystem_volume_stats('/some/path/')

        self.assertEqual(4096, result['block_size'])
        self.assertEqual(1048576, result['total_blocks'])
        self.assertEqual(524288, result['free_blocks'])
        self.assertEqual(4.0, result['total'])
        self.assertEqual(2147483648, result['free'])
        self.assertEqual(2.0, result['used'])

    def test_get_filesystem_volume_stats_error(self):
        with patch.object(os, 'statvfs', side_effect=OSError):
            self.assertRaises(
                RuntimeError,
                get_filesystem_volume_stats, '/nonexistent/path')


class ServiceRegistryTest(testtools.TestCase):

    def setUp(self):
        super(ServiceRegistryTest, self).setUp()

    def tearDown(self):
        super(ServiceRegistryTest, self).tearDown()

    def test_datastore_registry_with_extra_manager(self):
        datastore_registry_ext_test = {
            'test': 'trove.guestagent.datastore.test.manager.Manager',
        }
        dbaas_sr.get_custom_managers = Mock(
            return_value=datastore_registry_ext_test)
        test_dict = dbaas_sr.datastore_registry()
        self.assertEqual(datastore_registry_ext_test.get('test', None),
                         test_dict.get('test'))
        self.assertEqual('trove.guestagent.datastore.mysql.'
                         'manager.Manager',
                         test_dict.get('mysql'))
        self.assertEqual('trove.guestagent.datastore.experimental.'
                         'percona.manager.Manager',
                         test_dict.get('percona'))
        self.assertEqual('trove.guestagent.datastore.experimental.redis.'
                         'manager.Manager',
                         test_dict.get('redis'))
        self.assertEqual('trove.guestagent.datastore.experimental.cassandra.'
                         'manager.Manager',
                         test_dict.get('cassandra'))
        self.assertEqual('trove.guestagent.datastore.experimental.'
                         'couchbase.manager.Manager',
                         test_dict.get('couchbase'))
        self.assertEqual('trove.guestagent.datastore.experimental.mongodb.'
                         'manager.Manager',
                         test_dict.get('mongodb'))
        self.assertEqual('trove.guestagent.datastore.experimental.couchdb.'
                         'manager.Manager',
                         test_dict.get('couchdb'))
        self.assertEqual('trove.guestagent.datastore.experimental.db2.'
                         'manager.Manager',
                         test_dict.get('db2'))

    def test_datastore_registry_with_existing_manager(self):
        datastore_registry_ext_test = {
            'mysql': 'trove.guestagent.datastore.mysql.'
                     'manager.Manager123',
        }
        dbaas_sr.get_custom_managers = Mock(
            return_value=datastore_registry_ext_test)
        test_dict = dbaas_sr.datastore_registry()
        self.assertEqual('trove.guestagent.datastore.mysql.'
                         'manager.Manager123',
                         test_dict.get('mysql'))
        self.assertEqual('trove.guestagent.datastore.experimental.'
                         'percona.manager.Manager',
                         test_dict.get('percona'))
        self.assertEqual('trove.guestagent.datastore.experimental.redis.'
                         'manager.Manager',
                         test_dict.get('redis'))
        self.assertEqual('trove.guestagent.datastore.experimental.cassandra.'
                         'manager.Manager',
                         test_dict.get('cassandra'))
        self.assertEqual('trove.guestagent.datastore.experimental.couchbase.'
                         'manager.Manager',
                         test_dict.get('couchbase'))
        self.assertEqual('trove.guestagent.datastore.experimental.mongodb.'
                         'manager.Manager',
                         test_dict.get('mongodb'))
        self.assertEqual('trove.guestagent.datastore.experimental.couchdb.'
                         'manager.Manager',
                         test_dict.get('couchdb'))
        self.assertEqual('trove.guestagent.datastore.experimental.vertica.'
                         'manager.Manager',
                         test_dict.get('vertica'))
        self.assertEqual('trove.guestagent.datastore.experimental.db2.'
                         'manager.Manager',
                         test_dict.get('db2'))
        self.assertEqual('trove.guestagent.datastore.experimental.mariadb.'
                         'manager.Manager',
                         test_dict.get('mariadb'))

    def test_datastore_registry_with_blank_dict(self):
        datastore_registry_ext_test = dict()
        dbaas_sr.get_custom_managers = Mock(
            return_value=datastore_registry_ext_test)
        test_dict = dbaas_sr.datastore_registry()
        self.assertEqual('trove.guestagent.datastore.mysql.'
                         'manager.Manager',
                         test_dict.get('mysql'))
        self.assertEqual('trove.guestagent.datastore.experimental.'
                         'percona.manager.Manager',
                         test_dict.get('percona'))
        self.assertEqual('trove.guestagent.datastore.experimental.redis.'
                         'manager.Manager',
                         test_dict.get('redis'))
        self.assertEqual('trove.guestagent.datastore.experimental.cassandra.'
                         'manager.Manager',
                         test_dict.get('cassandra'))
        self.assertEqual('trove.guestagent.datastore.experimental.couchbase.'
                         'manager.Manager',
                         test_dict.get('couchbase'))
        self.assertEqual('trove.guestagent.datastore.experimental.mongodb.'
                         'manager.Manager',
                         test_dict.get('mongodb'))
        self.assertEqual('trove.guestagent.datastore.experimental.couchdb.'
                         'manager.Manager',
                         test_dict.get('couchdb'))
        self.assertEqual('trove.guestagent.datastore.experimental.vertica.'
                         'manager.Manager',
                         test_dict.get('vertica'))
        self.assertEqual('trove.guestagent.datastore.experimental.db2.'
                         'manager.Manager',
                         test_dict.get('db2'))
        self.assertEqual('trove.guestagent.datastore.experimental.mariadb.'
                         'manager.Manager',
                         test_dict.get('mariadb'))


class KeepAliveConnectionTest(testtools.TestCase):

    class OperationalError(Exception):

        def __init__(self, value):
            self.args = [value]

        def __str__(self):
            return repr(self.value)

    def setUp(self):
        super(KeepAliveConnectionTest, self).setUp()
        self.orig_utils_execute_with_timeout = \
            dbaas_base.utils.execute_with_timeout
        self.orig_LOG_err = dbaas.LOG

    def tearDown(self):
        super(KeepAliveConnectionTest, self).tearDown()
        dbaas_base.utils.execute_with_timeout = \
            self.orig_utils_execute_with_timeout
        dbaas.LOG = self.orig_LOG_err

    def test_checkout_type_error(self):

        dbapi_con = Mock()
        dbapi_con.ping = Mock(side_effect=TypeError("Type Error"))

        self.keepAliveConn = KeepAliveConnection()
        self.assertRaises(TypeError, self.keepAliveConn.checkout,
                          dbapi_con, Mock(), Mock())

    def test_checkout_disconnection_error(self):

        dbapi_con = Mock()
        dbapi_con.OperationalError = self.OperationalError
        dbapi_con.ping = Mock(side_effect=dbapi_con.OperationalError(2013))

        self.keepAliveConn = KeepAliveConnection()
        self.assertRaises(sqlalchemy.exc.DisconnectionError,
                          self.keepAliveConn.checkout,
                          dbapi_con, Mock(), Mock())

    def test_checkout_operation_error(self):

        dbapi_con = Mock()
        dbapi_con.OperationalError = self.OperationalError
        dbapi_con.ping = Mock(side_effect=dbapi_con.OperationalError(1234))

        self.keepAliveConn = KeepAliveConnection()
        self.assertRaises(self.OperationalError, self.keepAliveConn.checkout,
                          dbapi_con, Mock(), Mock())


class BaseDbStatusTest(testtools.TestCase):

    def setUp(self):
        super(BaseDbStatusTest, self).setUp()
        util.init_db()
        self.orig_dbaas_time_sleep = time.sleep
        self.FAKE_ID = str(uuid4())
        InstanceServiceStatus.create(instance_id=self.FAKE_ID,
                                     status=rd_instance.ServiceStatuses.NEW)
        dbaas.CONF.guest_id = self.FAKE_ID
        patcher_log = patch.object(base_datastore_service, 'LOG')
        patcher_context = patch.object(trove_context, 'TroveContext')
        patcher_api = patch.object(conductor_api, 'API')
        patcher_log.start()
        patcher_context.start()
        patcher_api.start()
        self.addCleanup(patcher_log.stop)
        self.addCleanup(patcher_context.stop)
        self.addCleanup(patcher_api.stop)

    def tearDown(self):
        super(BaseDbStatusTest, self).tearDown()
        time.sleep = self.orig_dbaas_time_sleep
        InstanceServiceStatus.find_by(instance_id=self.FAKE_ID).delete()
        dbaas.CONF.guest_id = None

    def test_begin_install(self):
        base_db_status = BaseDbStatus()

        base_db_status.begin_install()

        self.assertEqual(rd_instance.ServiceStatuses.BUILDING,
                         base_db_status.status)

    def test_begin_restart(self):
        base_db_status = BaseDbStatus()
        base_db_status.restart_mode = False

        base_db_status.begin_restart()

        self.assertTrue(base_db_status.restart_mode)

    def test_end_install_or_restart(self):
        base_db_status = BaseDbStatus()
        base_db_status._get_actual_db_status = Mock(
            return_value=rd_instance.ServiceStatuses.SHUTDOWN)

        base_db_status.end_install_or_restart()

        self.assertEqual(rd_instance.ServiceStatuses.SHUTDOWN,
                         base_db_status.status)
        self.assertFalse(base_db_status.restart_mode)

    def test_is_installed(self):
        base_db_status = BaseDbStatus()
        base_db_status.status = rd_instance.ServiceStatuses.RUNNING

        self.assertTrue(base_db_status.is_installed)

    def test_is_installed_none(self):
        base_db_status = BaseDbStatus()
        base_db_status.status = None

        self.assertTrue(base_db_status.is_installed)

    def test_is_installed_building(self):
        base_db_status = BaseDbStatus()
        base_db_status.status = rd_instance.ServiceStatuses.BUILDING

        self.assertFalse(base_db_status.is_installed)

    def test_is_installed_new(self):
        base_db_status = BaseDbStatus()
        base_db_status.status = rd_instance.ServiceStatuses.NEW

        self.assertFalse(base_db_status.is_installed)

    def test_is_installed_failed(self):
        base_db_status = BaseDbStatus()
        base_db_status.status = rd_instance.ServiceStatuses.FAILED

        self.assertFalse(base_db_status.is_installed)

    def test_is_restarting(self):
        base_db_status = BaseDbStatus()
        base_db_status.restart_mode = True

        self.assertTrue(base_db_status._is_restarting)

    def test_is_running(self):
        base_db_status = BaseDbStatus()
        base_db_status.status = rd_instance.ServiceStatuses.RUNNING

        self.assertTrue(base_db_status.is_running)

    def test_is_running_not(self):
        base_db_status = BaseDbStatus()
        base_db_status.status = rd_instance.ServiceStatuses.SHUTDOWN

        self.assertFalse(base_db_status.is_running)

    def test_wait_for_real_status_to_change_to(self):
        base_db_status = BaseDbStatus()
        base_db_status._get_actual_db_status = Mock(
            return_value=rd_instance.ServiceStatuses.RUNNING)
        time.sleep = Mock()

        self.assertTrue(base_db_status.
                        wait_for_real_status_to_change_to
                        (rd_instance.ServiceStatuses.RUNNING, 10))

    def test_wait_for_real_status_to_change_to_timeout(self):
        base_db_status = BaseDbStatus()
        base_db_status._get_actual_db_status = Mock(
            return_value=rd_instance.ServiceStatuses.RUNNING)
        time.sleep = Mock()

        self.assertFalse(base_db_status.
                         wait_for_real_status_to_change_to
                         (rd_instance.ServiceStatuses.SHUTDOWN, 10))

    def _test_set_status(self, initial_status, new_status,
                         expected_status, force=False):
        base_db_status = BaseDbStatus()
        base_db_status.status = initial_status
        base_db_status.set_status(new_status, force=force)

        self.assertEqual(expected_status,
                         base_db_status.status)

    def test_set_status_force_heartbeat(self):
        self._test_set_status(rd_instance.ServiceStatuses.BUILDING,
                              rd_instance.ServiceStatuses.RUNNING,
                              rd_instance.ServiceStatuses.RUNNING,
                              force=True)

    def test_set_status_skip_heartbeat_with_building(self):
        self._test_set_status(rd_instance.ServiceStatuses.BUILDING,
                              rd_instance.ServiceStatuses.RUNNING,
                              rd_instance.ServiceStatuses.BUILDING)

    def test_set_status_skip_heartbeat_with_new(self):
        self._test_set_status(rd_instance.ServiceStatuses.NEW,
                              rd_instance.ServiceStatuses.RUNNING,
                              rd_instance.ServiceStatuses.NEW)

    def test_set_status_to_failed(self):
        self._test_set_status(rd_instance.ServiceStatuses.BUILDING,
                              rd_instance.ServiceStatuses.FAILED,
                              rd_instance.ServiceStatuses.FAILED)

    def test_set_status_to_build_pending(self):
        self._test_set_status(rd_instance.ServiceStatuses.BUILDING,
                              rd_instance.ServiceStatuses.BUILD_PENDING,
                              rd_instance.ServiceStatuses.BUILD_PENDING)


class MySqlAppStatusTest(testtools.TestCase):

    def setUp(self):
        super(MySqlAppStatusTest, self).setUp()
        util.init_db()
        self.orig_utils_execute_with_timeout = \
            dbaas_base.utils.execute_with_timeout
        self.orig_load_mysqld_options = dbaas_base.load_mysqld_options
        self.orig_dbaas_base_os_path_exists = dbaas_base.os.path.exists
        self.orig_dbaas_time_sleep = time.sleep
        self.FAKE_ID = str(uuid4())
        InstanceServiceStatus.create(instance_id=self.FAKE_ID,
                                     status=rd_instance.ServiceStatuses.NEW)
        dbaas.CONF.guest_id = self.FAKE_ID

    def tearDown(self):
        super(MySqlAppStatusTest, self).tearDown()
        dbaas_base.utils.execute_with_timeout = \
            self.orig_utils_execute_with_timeout
        dbaas_base.load_mysqld_options = self.orig_load_mysqld_options
        dbaas_base.os.path.exists = self.orig_dbaas_base_os_path_exists
        time.sleep = self.orig_dbaas_time_sleep
        InstanceServiceStatus.find_by(instance_id=self.FAKE_ID).delete()
        dbaas.CONF.guest_id = None

    def test_get_actual_db_status(self):

        dbaas_base.utils.execute_with_timeout = Mock(return_value=(None, None))

        self.mySqlAppStatus = MySqlAppStatus.get()
        status = self.mySqlAppStatus._get_actual_db_status()

        self.assertEqual(rd_instance.ServiceStatuses.RUNNING, status)

    @patch.object(utils, 'execute_with_timeout',
                  side_effect=ProcessExecutionError())
    @patch.object(os.path, 'exists', return_value=True)
    def test_get_actual_db_status_error_crashed(self, mock_exists,
                                                mock_execute):
        dbaas_base.load_mysqld_options = Mock(return_value={})
        self.mySqlAppStatus = MySqlAppStatus.get()
        status = self.mySqlAppStatus._get_actual_db_status()
        self.assertEqual(rd_instance.ServiceStatuses.CRASHED, status)

    def test_get_actual_db_status_error_shutdown(self):

        mocked = Mock(side_effect=ProcessExecutionError())
        dbaas_base.utils.execute_with_timeout = mocked
        dbaas_base.load_mysqld_options = Mock(return_value={})
        dbaas_base.os.path.exists = Mock(return_value=False)

        self.mySqlAppStatus = MySqlAppStatus.get()
        status = self.mySqlAppStatus._get_actual_db_status()

        self.assertEqual(rd_instance.ServiceStatuses.SHUTDOWN, status)

    def test_get_actual_db_status_error_blocked(self):

        dbaas_base.utils.execute_with_timeout = MagicMock(
            side_effect=[ProcessExecutionError(), ("some output", None)])
        dbaas_base.load_mysqld_options = Mock()
        dbaas_base.os.path.exists = Mock(return_value=True)

        self.mySqlAppStatus = MySqlAppStatus.get()
        status = self.mySqlAppStatus._get_actual_db_status()

        self.assertEqual(rd_instance.ServiceStatuses.BLOCKED, status)


class TestRedisApp(testtools.TestCase):

    def setUp(self):
        super(TestRedisApp, self).setUp()
        self.FAKE_ID = 1000
        self.appStatus = FakeAppStatus(self.FAKE_ID,
                                       rd_instance.ServiceStatuses.NEW)

        with patch.multiple(RedisApp, _build_admin_client=DEFAULT,
                            _init_overrides_dir=DEFAULT):
            self.app = RedisApp(state_change_wait_time=0)

        self.orig_os_path_isfile = os.path.isfile
        self.orig_utils_execute_with_timeout = utils.execute_with_timeout
        utils.execute_with_timeout = Mock()
        rservice.utils.execute_with_timeout = Mock()

    def tearDown(self):
        super(TestRedisApp, self).tearDown()
        self.app = None
        os.path.isfile = self.orig_os_path_isfile
        utils.execute_with_timeout = self.orig_utils_execute_with_timeout
        rservice.utils.execute_with_timeout = \
            self.orig_utils_execute_with_timeout

    def test_install_if_needed_installed(self):
        with patch.object(pkg.Package, 'pkg_is_installed', return_value=True):
            with patch.object(RedisApp, '_install_redis', return_value=None):
                self.app.install_if_needed('bar')
                pkg.Package.pkg_is_installed.assert_any_call('bar')
                self.assertEqual(0, RedisApp._install_redis.call_count)

    def test_install_if_needed_not_installed(self):
        with patch.object(pkg.Package, 'pkg_is_installed', return_value=False):
            with patch.object(RedisApp, '_install_redis', return_value=None):
                self.app.install_if_needed('asdf')
                pkg.Package.pkg_is_installed.assert_any_call('asdf')
                RedisApp._install_redis.assert_any_call('asdf')

    def test_install_redis(self):
        with patch.object(utils, 'execute_with_timeout'):
            with patch.object(pkg.Package, 'pkg_install', return_value=None):
                with patch.object(RedisApp, 'start_redis', return_value=None):
                    self.app._install_redis('redis')
                    pkg.Package.pkg_install.assert_any_call('redis', {}, 1200)
                    RedisApp.start_redis.assert_any_call()
                    self.assertTrue(utils.execute_with_timeout.called)

    def test_enable_redis_on_boot_without_upstart(self):
        cmd = '123'
        with patch.object(operating_system, 'service_discovery',
                          return_value={'cmd_enable': cmd}):
            with patch.object(utils, 'execute_with_timeout',
                              return_value=None):
                self.app._enable_redis_on_boot()
                operating_system.service_discovery.assert_any_call(
                    RedisSystem.SERVICE_CANDIDATES)
                utils.execute_with_timeout.assert_any_call(
                    cmd, shell=True)

    def test_enable_redis_on_boot_with_upstart(self):
        cmd = '123'
        with patch.object(operating_system, 'service_discovery',
                          return_value={'cmd_enable': cmd}):
            with patch.object(utils, 'execute_with_timeout',
                              return_value=None):
                self.app._enable_redis_on_boot()
                operating_system.service_discovery.assert_any_call(
                    RedisSystem.SERVICE_CANDIDATES)
                utils.execute_with_timeout.assert_any_call(
                    cmd, shell=True)

    def test_disable_redis_on_boot_with_upstart(self):
        cmd = '123'
        with patch.object(operating_system, 'service_discovery',
                          return_value={'cmd_disable': cmd}):
            with patch.object(utils, 'execute_with_timeout',
                              return_value=None):
                self.app._disable_redis_on_boot()
                operating_system.service_discovery.assert_any_call(
                    RedisSystem.SERVICE_CANDIDATES)
                utils.execute_with_timeout.assert_any_call(
                    cmd, shell=True)

    def test_disable_redis_on_boot_without_upstart(self):
        cmd = '123'
        with patch.object(operating_system, 'service_discovery',
                          return_value={'cmd_disable': cmd}):
            with patch.object(utils, 'execute_with_timeout',
                              return_value=None):
                self.app._disable_redis_on_boot()
                operating_system.service_discovery.assert_any_call(
                    RedisSystem.SERVICE_CANDIDATES)
                utils.execute_with_timeout.assert_any_call(
                    cmd, shell=True)

    def test_stop_db_without_fail(self):
        mock_status = MagicMock()
        mock_status.wait_for_real_status_to_change_to = MagicMock(
            return_value=True)
        self.app.status = mock_status
        RedisApp._disable_redis_on_boot = MagicMock(
            return_value=None)

        with patch.object(operating_system, 'stop_service') as stop_srv_mock:
            mock_status.wait_for_real_status_to_change_to = MagicMock(
                return_value=True)
            self.app.stop_db(do_not_start_on_reboot=True)

            stop_srv_mock.assert_called_once_with(
                RedisSystem.SERVICE_CANDIDATES)
            self.assertTrue(RedisApp._disable_redis_on_boot.called)
            self.assertTrue(
                mock_status.wait_for_real_status_to_change_to.called)

    def test_stop_db_with_failure(self):
        mock_status = MagicMock()
        mock_status.wait_for_real_status_to_change_to = MagicMock(
            return_value=True)
        self.app.status = mock_status
        RedisApp._disable_redis_on_boot = MagicMock(
            return_value=None)

        with patch.object(operating_system, 'stop_service') as stop_srv_mock:
            mock_status.wait_for_real_status_to_change_to = MagicMock(
                return_value=False)
            self.app.stop_db(do_not_start_on_reboot=True)

            stop_srv_mock.assert_called_once_with(
                RedisSystem.SERVICE_CANDIDATES)
            self.assertTrue(RedisApp._disable_redis_on_boot.called)
            self.assertTrue(mock_status.end_install_or_restart.called)
            self.assertTrue(
                mock_status.wait_for_real_status_to_change_to.called)

    def test_restart(self):
        mock_status = MagicMock()
        self.app.status = mock_status
        mock_status.begin_restart = MagicMock(return_value=None)
        with patch.object(RedisApp, 'stop_db', return_value=None):
            with patch.object(RedisApp, 'start_redis', return_value=None):
                mock_status.end_install_or_restart = MagicMock(
                    return_value=None)
                self.app.restart()
                mock_status.begin_restart.assert_any_call()
                RedisApp.stop_db.assert_any_call()
                RedisApp.start_redis.assert_any_call()
                mock_status.end_install_or_restart.assert_any_call()

    def test_start_redis(self):
        mock_status = MagicMock()
        mock_status.wait_for_real_status_to_change_to = MagicMock(
            return_value=True)

        self._assert_start_redis(mock_status)

    @patch.object(utils, 'execute_with_timeout')
    def test_start_redis_with_failure(self, exec_mock):
        mock_status = MagicMock()
        mock_status.wait_for_real_status_to_change_to = MagicMock(
            return_value=False)
        mock_status.end_install_or_restart = MagicMock()

        self._assert_start_redis(mock_status)

        exec_mock.assert_called_once_with('pkill', '-9', 'redis-server',
                                          run_as_root=True, root_helper='sudo')

        mock_status.end_install_or_restart.assert_called_once_with()

    @patch.multiple(operating_system, start_service=DEFAULT,
                    enable_service_on_boot=DEFAULT)
    def _assert_start_redis(self, mock_status, start_service,
                            enable_service_on_boot):
        self.app.status = mock_status

        self.app.start_redis()

        mock_status.wait_for_real_status_to_change_to.assert_called_once_with(
            rd_instance.ServiceStatuses.RUNNING, ANY, False)
        enable_service_on_boot.assert_called_once_with(
            RedisSystem.SERVICE_CANDIDATES)
        start_service.assert_called_once_with(RedisSystem.SERVICE_CANDIDATES)


class CassandraDBAppTest(testtools.TestCase):

    def setUp(self):
        super(CassandraDBAppTest, self).setUp()
        self.utils_execute_with_timeout = (
            cass_service.utils.execute_with_timeout)
        self.sleep = time.sleep
        self.pkg_version = cass_service.packager.pkg_version
        self.pkg = cass_service.packager
        util.init_db()
        self.FAKE_ID = str(uuid4())
        InstanceServiceStatus.create(instance_id=self.FAKE_ID,
                                     status=rd_instance.ServiceStatuses.NEW)
        self.appStatus = FakeAppStatus(self.FAKE_ID,
                                       rd_instance.ServiceStatuses.NEW)
        self.cassandra = cass_service.CassandraApp(self.appStatus)
        self.orig_unlink = os.unlink

    def tearDown(self):

        super(CassandraDBAppTest, self).tearDown()
        cass_service.utils.execute_with_timeout = (self.
                                                   utils_execute_with_timeout)
        time.sleep = self.sleep
        cass_service.packager.pkg_version = self.pkg_version
        cass_service.packager = self.pkg
        InstanceServiceStatus.find_by(instance_id=self.FAKE_ID).delete()

    def assert_reported_status(self, expected_status):
        service_status = InstanceServiceStatus.find_by(
            instance_id=self.FAKE_ID)
        self.assertEqual(expected_status, service_status.status)

    def test_stop_db(self):

        cass_service.utils.execute_with_timeout = Mock()
        self.appStatus.set_next_status(
            rd_instance.ServiceStatuses.SHUTDOWN)

        self.cassandra.stop_db()
        self.assert_reported_status(rd_instance.ServiceStatuses.NEW)

    def test_stop_db_with_db_update(self):

        cass_service.utils.execute_with_timeout = Mock()
        self.appStatus.set_next_status(
            rd_instance.ServiceStatuses.SHUTDOWN)

        self.cassandra.stop_db(True)
        self.assertTrue(conductor_api.API.heartbeat.called_once_with(
            self.FAKE_ID,
            {'service_status':
             rd_instance.ServiceStatuses.SHUTDOWN.description}))

    def test_stop_db_error(self):

        cass_service.utils.execute_with_timeout = Mock()
        self.appStatus.set_next_status(rd_instance.ServiceStatuses.RUNNING)
        self.cassandra.state_change_wait_time = 1
        self.assertRaises(RuntimeError, self.cassandra.stop_db)

    def test_restart(self):

        self.cassandra.stop_db = Mock()
        self.cassandra.start_db = Mock()
        self.appStatus.set_next_status(rd_instance.ServiceStatuses.RUNNING)

        self.cassandra.restart()

        self.assertTrue(conductor_api.API.heartbeat.called_once_with(
            self.FAKE_ID,
            {'service_status':
             rd_instance.ServiceStatuses.RUNNING.description}))
        self.assert_reported_status(rd_instance.ServiceStatuses.NEW)

    def test_start_cassandra(self):

        cass_service.utils.execute_with_timeout = Mock()
        self.appStatus.set_next_status(rd_instance.ServiceStatuses.RUNNING)

        self.cassandra.start_db()
        self.assert_reported_status(rd_instance.ServiceStatuses.NEW)

    def test_start_cassandra_runs_forever(self):

        cass_service.utils.execute_with_timeout = Mock()
        (self.cassandra.status.
         wait_for_real_status_to_change_to) = Mock(return_value=False)
        self.appStatus.set_next_status(rd_instance.ServiceStatuses.SHUTDOWN)

        self.assertRaises(RuntimeError, self.cassandra.stop_db)
        self.assertTrue(conductor_api.API.heartbeat.called_once_with(
            self.FAKE_ID,
            {'service_status':
             rd_instance.ServiceStatuses.SHUTDOWN.description}))

    def test_start_db_with_db_update(self):

        cass_service.utils.execute_with_timeout = Mock()
        self.appStatus.set_next_status(
            rd_instance.ServiceStatuses.RUNNING)

        self.cassandra.start_db(True)
        self.assertTrue(conductor_api.API.heartbeat.called_once_with(
            self.FAKE_ID,
            {'service_status':
             rd_instance.ServiceStatuses.RUNNING.description}))
        self.assert_reported_status(rd_instance.ServiceStatuses.NEW)

    def test_start_cassandra_error(self):
        self.cassandra._enable_db_on_boot = Mock()
        self.cassandra.state_change_wait_time = 1
        cass_service.utils.execute_with_timeout = Mock(
            side_effect=ProcessExecutionError('Error'))

        self.assertRaises(RuntimeError, self.cassandra.start_db)

    def test_install(self):

        self.cassandra._install_db = Mock()
        self.pkg.pkg_is_installed = Mock(return_value=False)
        self.cassandra.install_if_needed(['cassandra'])
        self.assertTrue(self.cassandra._install_db.called)
        self.assert_reported_status(rd_instance.ServiceStatuses.NEW)

    def test_install_install_error(self):

        self.cassandra.start_db = Mock()
        self.cassandra.stop_db = Mock()
        self.pkg.pkg_is_installed = Mock(return_value=False)
        self.cassandra._install_db = Mock(
            side_effect=pkg.PkgPackageStateError("Install error"))

        self.assertRaises(pkg.PkgPackageStateError,
                          self.cassandra.install_if_needed,
                          ['cassandra=1.2.10'])

        self.assert_reported_status(rd_instance.ServiceStatuses.NEW)

    def test_cassandra_error_in_write_config_verify_unlink(self):
        # this test verifies not only that the write_config
        # method properly invoked execute, but also that it properly
        # attempted to unlink the file (as a result of the exception)

        mock_unlink = Mock(return_value=0)

        # We call tempfile.mkstemp() here and Mock() the mkstemp()
        # parameter to write_config for testability.
        (temp_handle, temp_config_name) = tempfile.mkstemp()
        mock_mkstemp = MagicMock(return_value=(temp_handle, temp_config_name))

        configuration = 'this is my configuration'

        with patch('trove.guestagent.common.operating_system.move',
                   side_effect=ProcessExecutionError('some exception')):
            self.assertRaises(ProcessExecutionError,
                              self.cassandra.write_config,
                              config_contents=configuration,
                              execute_function=Mock(),
                              mkstemp_function=mock_mkstemp,
                              unlink_function=mock_unlink)

            self.assertEqual(1, mock_unlink.call_count)

        # really delete the temporary_config_file
        os.unlink(temp_config_name)

    @patch.multiple('trove.guestagent.common.operating_system',
                    chown=DEFAULT, chmod=DEFAULT, move=DEFAULT)
    def test_cassandra_write_config(self, chown, chmod, move):
        # ensure that write_config creates a temporary file, and then
        # moves the file to the final place. Also validate the
        # contents of the file written.

        # We call tempfile.mkstemp() here and Mock() the mkstemp()
        # parameter to write_config for testability.
        (temp_handle, temp_config_name) = tempfile.mkstemp()
        mock_mkstemp = MagicMock(return_value=(temp_handle, temp_config_name))

        configuration = 'some arbitrary configuration text'

        mock_execute = MagicMock(return_value=('', ''))

        self.cassandra.write_config(configuration,
                                    execute_function=mock_execute,
                                    mkstemp_function=mock_mkstemp)

        move.assert_called_with(temp_config_name, cass_system.CASSANDRA_CONF,
                                as_root=True)
        chown.assert_called_with(cass_system.CASSANDRA_CONF,
                                 "cassandra", "cassandra", recursive=False,
                                 as_root=True)
        chmod.assert_called_with(
            cass_system.CASSANDRA_CONF, FileMode.ADD_READ_ALL, as_root=True)

        self.assertEqual(1, mock_mkstemp.call_count)

        with open(temp_config_name, 'r') as config_file:
            configuration_data = config_file.read()

        self.assertEqual(configuration, configuration_data)

        # really delete the temporary_config_file
        os.unlink(temp_config_name)


class CouchbaseAppTest(testtools.TestCase):

    def fake_couchbase_service_discovery(self, candidates):
        return {
            'cmd_start': 'start',
            'cmd_stop': 'stop',
            'cmd_enable': 'enable',
            'cmd_disable': 'disable'
        }

    def setUp(self):
        super(CouchbaseAppTest, self).setUp()
        self.orig_utils_execute_with_timeout = (
            couchservice.utils.execute_with_timeout)
        self.orig_time_sleep = time.sleep
        time.sleep = Mock()
        self.orig_service_discovery = operating_system.service_discovery
        self.orig_get_ip = netutils.get_my_ipv4
        operating_system.service_discovery = (
            self.fake_couchbase_service_discovery)
        netutils.get_my_ipv4 = Mock()
        self.FAKE_ID = str(uuid4())
        InstanceServiceStatus.create(instance_id=self.FAKE_ID,
                                     status=rd_instance.ServiceStatuses.NEW)
        self.appStatus = FakeAppStatus(self.FAKE_ID,
                                       rd_instance.ServiceStatuses.NEW)
        self.couchbaseApp = couchservice.CouchbaseApp(self.appStatus)
        dbaas.CONF.guest_id = self.FAKE_ID

    def tearDown(self):
        super(CouchbaseAppTest, self).tearDown()
        couchservice.utils.execute_with_timeout = (
            self.orig_utils_execute_with_timeout)
        netutils.get_my_ipv4 = self.orig_get_ip
        operating_system.service_discovery = self.orig_service_discovery
        time.sleep = self.orig_time_sleep
        InstanceServiceStatus.find_by(instance_id=self.FAKE_ID).delete()
        dbaas.CONF.guest_id = None

    def assert_reported_status(self, expected_status):
        service_status = InstanceServiceStatus.find_by(
            instance_id=self.FAKE_ID)
        self.assertEqual(expected_status, service_status.status)

    def test_stop_db(self):
        couchservice.utils.execute_with_timeout = Mock()
        self.appStatus.set_next_status(rd_instance.ServiceStatuses.SHUTDOWN)

        self.couchbaseApp.stop_db()
        self.assert_reported_status(rd_instance.ServiceStatuses.NEW)

    def test_stop_db_error(self):
        couchservice.utils.execute_with_timeout = Mock()
        self.appStatus.set_next_status(rd_instance.ServiceStatuses.RUNNING)
        self.couchbaseApp.state_change_wait_time = 1

        self.assertRaises(RuntimeError, self.couchbaseApp.stop_db)

    def test_restart(self):
        self.appStatus.set_next_status(rd_instance.ServiceStatuses.RUNNING)
        self.couchbaseApp.stop_db = Mock()
        self.couchbaseApp.start_db = Mock()

        self.couchbaseApp.restart()

        self.assertTrue(self.couchbaseApp.stop_db.called)
        self.assertTrue(self.couchbaseApp.start_db.called)
        self.assertTrue(conductor_api.API.heartbeat.called)

    def test_start_db(self):
        couchservice.utils.execute_with_timeout = Mock()
        self.appStatus.set_next_status(rd_instance.ServiceStatuses.RUNNING)
        self.couchbaseApp._enable_db_on_boot = Mock()

        self.couchbaseApp.start_db()
        self.assert_reported_status(rd_instance.ServiceStatuses.NEW)

    def test_start_db_error(self):
        mocked = Mock(side_effect=ProcessExecutionError('Error'))
        couchservice.utils.execute_with_timeout = mocked
        self.couchbaseApp._enable_db_on_boot = Mock()

        self.assertRaises(RuntimeError, self.couchbaseApp.start_db)

    def test_start_db_runs_forever(self):
        couchservice.utils.execute_with_timeout = Mock()
        self.couchbaseApp._enable_db_on_boot = Mock()
        self.couchbaseApp.state_change_wait_time = 1
        self.appStatus.set_next_status(rd_instance.ServiceStatuses.SHUTDOWN)

        self.assertRaises(RuntimeError, self.couchbaseApp.start_db)
        self.assertTrue(conductor_api.API.heartbeat.called)

    def test_install_when_couchbase_installed(self):
        couchservice.packager.pkg_is_installed = Mock(return_value=True)
        couchservice.utils.execute_with_timeout = Mock()

        self.couchbaseApp.install_if_needed(["package"])
        self.assertTrue(couchservice.packager.pkg_is_installed.called)
        self.assert_reported_status(rd_instance.ServiceStatuses.NEW)


class CouchDBAppTest(testtools.TestCase):

    def fake_couchdb_service_discovery(self, candidates):
        return {
            'cmd_start': 'start',
            'cmd_stop': 'stop',
            'cmd_enable': 'enable',
            'cmd_disable': 'disable'
        }

    def setUp(self):
        super(CouchDBAppTest, self).setUp()
        self.orig_utils_execute_with_timeout = (
            couchdb_service.utils.execute_with_timeout)
        self.orig_time_sleep = time.sleep
        time.sleep = Mock()
        self.orig_service_discovery = operating_system.service_discovery
        self.orig_get_ip = netutils.get_my_ipv4
        operating_system.service_discovery = (
            self.fake_couchdb_service_discovery)
        netutils.get_my_ipv4 = Mock()
        util.init_db()
        self.FAKE_ID = str(uuid4())
        InstanceServiceStatus.create(instance_id=self.FAKE_ID,
                                     status=rd_instance.ServiceStatuses.NEW)
        self.appStatus = FakeAppStatus(self.FAKE_ID,
                                       rd_instance.ServiceStatuses.NEW)
        self.couchdbApp = couchdb_service.CouchDBApp(self.appStatus)
        dbaas.CONF.guest_id = self.FAKE_ID

    def tearDown(self):
        super(CouchDBAppTest, self).tearDown()
        couchdb_service.utils.execute_with_timeout = (
            self.orig_utils_execute_with_timeout)
        netutils.get_my_ipv4 = self.orig_get_ip
        operating_system.service_discovery = self.orig_service_discovery
        time.sleep = self.orig_time_sleep
        InstanceServiceStatus.find_by(instance_id=self.FAKE_ID).delete()
        dbaas.CONF.guest_id = None

    def assert_reported_status(self, expected_status):
        service_status = InstanceServiceStatus.find_by(
            instance_id=self.FAKE_ID)
        self.assertEqual(expected_status, service_status.status)

    def test_stop_db(self):
        couchdb_service.utils.execute_with_timeout = Mock()
        self.appStatus.set_next_status(rd_instance.ServiceStatuses.SHUTDOWN)

        self.couchdbApp.stop_db()
        self.assert_reported_status(rd_instance.ServiceStatuses.NEW)

    def test_stop_db_error(self):
        couchdb_service.utils.execute_with_timeout = Mock()
        self.appStatus.set_next_status(rd_instance.ServiceStatuses.RUNNING)
        self.couchdbApp.state_change_wait_time = 1

        self.assertRaises(RuntimeError, self.couchdbApp.stop_db)

    def test_restart(self):
        self.appStatus.set_next_status(rd_instance.ServiceStatuses.RUNNING)
        self.couchdbApp.stop_db = Mock()
        self.couchdbApp.start_db = Mock()

        self.couchdbApp.restart()

        self.assertTrue(self.couchdbApp.stop_db.called)
        self.assertTrue(self.couchdbApp.start_db.called)
        self.assertTrue(conductor_api.API.heartbeat.called)

    def test_start_db(self):
        couchdb_service.utils.execute_with_timeout = Mock()
        self.appStatus.set_next_status(rd_instance.ServiceStatuses.RUNNING)
        self.couchdbApp._enable_db_on_boot = Mock()

        self.couchdbApp.start_db()
        self.assert_reported_status(rd_instance.ServiceStatuses.NEW)

    def test_start_db_error(self):
        couchdb_service.utils.execute_with_timeout = Mock(
            side_effect=ProcessExecutionError('Error'))
        self.couchdbApp._enable_db_on_boot = Mock()

        self.assertRaises(RuntimeError, self.couchdbApp.start_db)

    def test_install_when_couchdb_installed(self):
        couchdb_service.packager.pkg_is_installed = Mock(return_value=True)
        couchdb_service.utils.execute_with_timeout = Mock()

        self.couchdbApp.install_if_needed(["package"])
        self.assertTrue(couchdb_service.packager.pkg_is_installed.called)
        self.assert_reported_status(rd_instance.ServiceStatuses.NEW)


class MongoDBAppTest(testtools.TestCase):

    def fake_mongodb_service_discovery(self, candidates):
        return {
            'cmd_start': 'start',
            'cmd_stop': 'stop',
            'cmd_enable': 'enable',
            'cmd_disable': 'disable'
        }

    @patch.object(mongo_service.MongoDBApp, '_init_overrides_dir')
    def setUp(self, _):
        super(MongoDBAppTest, self).setUp()
        self.orig_utils_execute_with_timeout = (mongo_service.
                                                utils.execute_with_timeout)
        self.orig_time_sleep = time.sleep
        self.orig_packager = mongo_system.PACKAGER
        self.orig_service_discovery = operating_system.service_discovery
        self.orig_os_unlink = os.unlink

        operating_system.service_discovery = (
            self.fake_mongodb_service_discovery)
        util.init_db()
        self.FAKE_ID = str(uuid4())
        InstanceServiceStatus.create(instance_id=self.FAKE_ID,
                                     status=rd_instance.ServiceStatuses.NEW)

        self.mongoDbApp = mongo_service.MongoDBApp()
        self.mongoDbApp.status = FakeAppStatus(self.FAKE_ID,
                                               rd_instance.ServiceStatuses.NEW)
        time.sleep = Mock()
        os.unlink = Mock()

    def tearDown(self):
        super(MongoDBAppTest, self).tearDown()
        mongo_service.utils.execute_with_timeout = (
            self.orig_utils_execute_with_timeout)
        time.sleep = self.orig_time_sleep
        mongo_system.PACKAGER = self.orig_packager
        operating_system.service_discovery = self.orig_service_discovery
        os.unlink = self.orig_os_unlink
        InstanceServiceStatus.find_by(instance_id=self.FAKE_ID).delete()

    def assert_reported_status(self, expected_status):
        service_status = InstanceServiceStatus.find_by(
            instance_id=self.FAKE_ID)
        self.assertEqual(expected_status, service_status.status)

    def test_stopdb(self):
        mongo_service.utils.execute_with_timeout = Mock()
        self.mongoDbApp.status.set_next_status(
            rd_instance.ServiceStatuses.SHUTDOWN)

        self.mongoDbApp.stop_db()
        self.assert_reported_status(rd_instance.ServiceStatuses.NEW)

    def test_stop_db_with_db_update(self):

        mongo_service.utils.execute_with_timeout = Mock()
        self.mongoDbApp.status.set_next_status(
            rd_instance.ServiceStatuses.SHUTDOWN)

        self.mongoDbApp.stop_db(True)
        self.assertTrue(conductor_api.API.heartbeat.called_once_with(
            self.FAKE_ID, {'service_status': 'shutdown'}))

    def test_stop_db_error(self):

        mongo_service.utils.execute_with_timeout = Mock()
        self.mongoDbApp.status.set_next_status(
            rd_instance.ServiceStatuses.RUNNING)
        self.mongoDbApp.state_change_wait_time = 1
        self.assertRaises(RuntimeError, self.mongoDbApp.stop_db)

    def test_restart(self):

        self.mongoDbApp.status.set_next_status(
            rd_instance.ServiceStatuses.RUNNING)
        self.mongoDbApp.stop_db = Mock()
        self.mongoDbApp.start_db = Mock()

        self.mongoDbApp.restart()

        self.assertTrue(self.mongoDbApp.stop_db.called)
        self.assertTrue(self.mongoDbApp.start_db.called)

        self.assertTrue(conductor_api.API.heartbeat.called_once_with(
            self.FAKE_ID, {'service_status': 'shutdown'}))

        self.assertTrue(conductor_api.API.heartbeat.called_once_with(
            self.FAKE_ID, {'service_status': 'running'}))

    def test_start_db(self):

        mongo_service.utils.execute_with_timeout = Mock()
        self.mongoDbApp.status.set_next_status(
            rd_instance.ServiceStatuses.RUNNING)

        self.mongoDbApp.start_db()
        self.assert_reported_status(rd_instance.ServiceStatuses.NEW)

    def test_start_db_with_update(self):

        mongo_service.utils.execute_with_timeout = Mock()
        self.mongoDbApp.status.set_next_status(
            rd_instance.ServiceStatuses.RUNNING)

        self.mongoDbApp.start_db(True)
        self.assertTrue(conductor_api.API.heartbeat.called_once_with(
            self.FAKE_ID, {'service_status': 'running'}))

    def test_start_db_runs_forever(self):

        mongo_service.utils.execute_with_timeout = Mock(
            return_value=["ubuntu 17036  0.0  0.1 618960 "
                          "29232 pts/8    Sl+  Jan29   0:07 mongod", ""])
        self.mongoDbApp.state_change_wait_time = 1
        self.mongoDbApp.status.set_next_status(
            rd_instance.ServiceStatuses.SHUTDOWN)

        self.assertRaises(RuntimeError, self.mongoDbApp.start_db)
        self.assertTrue(conductor_api.API.heartbeat.called_once_with(
            self.FAKE_ID, {'service_status': 'shutdown'}))

    def test_start_db_error(self):

        self.mongoDbApp._enable_db_on_boot = Mock()
        mocked = Mock(side_effect=ProcessExecutionError('Error'))
        mongo_service.utils.execute_with_timeout = mocked

        self.assertRaises(RuntimeError, self.mongoDbApp.start_db)

    def test_start_db_with_conf_changes_db_is_running(self):

        self.mongoDbApp.start_db = Mock()

        self.mongoDbApp.status.status = rd_instance.ServiceStatuses.RUNNING
        self.assertRaises(RuntimeError,
                          self.mongoDbApp.start_db_with_conf_changes,
                          Mock())

    def test_install_when_db_installed(self):
        packager_mock = MagicMock()
        packager_mock.pkg_is_installed = MagicMock(return_value=True)
        mongo_system.PACKAGER = packager_mock
        self.mongoDbApp.install_if_needed(['package'])
        self.assert_reported_status(rd_instance.ServiceStatuses.NEW)

    def test_install_when_db_not_installed(self):
        packager_mock = MagicMock()
        packager_mock.pkg_is_installed = MagicMock(return_value=False)
        mongo_system.PACKAGER = packager_mock
        self.mongoDbApp.install_if_needed(['package'])
        packager_mock.pkg_install.assert_any_call(ANY, {}, ANY)
        self.assert_reported_status(rd_instance.ServiceStatuses.NEW)


class VerticaAppStatusTest(testtools.TestCase):

    def setUp(self):
        super(VerticaAppStatusTest, self).setUp()
        util.init_db()
        self.FAKE_ID = str(uuid4())
        InstanceServiceStatus.create(instance_id=self.FAKE_ID,
                                     status=rd_instance.ServiceStatuses.NEW)
        self.appStatus = FakeAppStatus(self.FAKE_ID,
                                       rd_instance.ServiceStatuses.NEW)

    def tearDown(self):

        super(VerticaAppStatusTest, self).tearDown()
        InstanceServiceStatus.find_by(instance_id=self.FAKE_ID).delete()

    def test_get_actual_db_status(self):
        self.verticaAppStatus = VerticaAppStatus()
        with patch.object(vertica_system, 'shell_execute',
                          MagicMock(return_value=['db_srvr', None])):
            status = self.verticaAppStatus._get_actual_db_status()
        self.assertEqual(rd_instance.ServiceStatuses.RUNNING, status)

    def test_get_actual_db_status_shutdown(self):
        self.verticaAppStatus = VerticaAppStatus()
        with patch.object(vertica_system, 'shell_execute',
                          MagicMock(side_effect=[['', None],
                                                 ['db_srvr', None]])):
            status = self.verticaAppStatus._get_actual_db_status()
        self.assertEqual(rd_instance.ServiceStatuses.SHUTDOWN, status)

    def test_get_actual_db_status_error_crashed(self):
        self.verticaAppStatus = VerticaAppStatus()
        with patch.object(vertica_system, 'shell_execute',
                          MagicMock(side_effect=ProcessExecutionError('problem'
                                                                      ))):
            status = self.verticaAppStatus._get_actual_db_status()
        self.assertEqual(rd_instance.ServiceStatuses.CRASHED, status)


class VerticaAppTest(testtools.TestCase):

    def setUp(self):
        super(VerticaAppTest, self).setUp()
        self.FAKE_ID = 1000
        self.appStatus = FakeAppStatus(self.FAKE_ID,
                                       rd_instance.ServiceStatuses.NEW)
        self.app = VerticaApp(self.appStatus)
        self.setread = VolumeDevice.set_readahead_size
        self.Popen = subprocess.Popen
        vertica_system.shell_execute = MagicMock(return_value=('', ''))

        VolumeDevice.set_readahead_size = Mock()
        subprocess.Popen = Mock()
        self.test_config = ConfigParser.ConfigParser()
        self.test_config.add_section('credentials')
        self.test_config.set('credentials',
                             'dbadmin_password', 'some_password')

    def tearDown(self):
        super(VerticaAppTest, self).tearDown()
        self.app = None
        VolumeDevice.set_readahead_size = self.setread
        subprocess.Popen = self.Popen

    def test_install_if_needed_installed(self):
        with patch.object(pkg.Package, 'pkg_is_installed', return_value=True):
            with patch.object(pkg.Package, 'pkg_install', return_value=None):
                self.app.install_if_needed('vertica')
                pkg.Package.pkg_is_installed.assert_any_call('vertica')
                self.assertEqual(0, pkg.Package.pkg_install.call_count)

    def test_install_if_needed_not_installed(self):
        with patch.object(pkg.Package, 'pkg_is_installed', return_value=False):
            with patch.object(pkg.Package, 'pkg_install', return_value=None):
                self.app.install_if_needed('vertica')
                pkg.Package.pkg_is_installed.assert_any_call('vertica')
                self.assertEqual(1, pkg.Package.pkg_install.call_count)

    def test_prepare_for_install_vertica(self):
        self.app.prepare_for_install_vertica()
        arguments = vertica_system.shell_execute.call_args_list[0]
        self.assertEqual(1, VolumeDevice.set_readahead_size.call_count)
        expected_command = (
            "VERT_DBA_USR=dbadmin VERT_DBA_HOME=/home/dbadmin "
            "VERT_DBA_GRP=verticadba /opt/vertica/oss/python/bin/python"
            " -m vertica.local_coerce")
        arguments.assert_called_with(expected_command)

    def test_failure_prepare_for_install_vertica(self):
        with patch.object(vertica_system, 'shell_execute',
                          side_effect=ProcessExecutionError('Error')):
            self.assertRaises(ProcessExecutionError,
                              self.app.prepare_for_install_vertica)

    def test_install_vertica(self):
        with patch.object(self.app, 'write_config',
                          return_value=None):
            self.app.install_vertica(members='10.0.0.2')
        arguments = vertica_system.shell_execute.call_args_list[0]
        expected_command = (
            vertica_system.INSTALL_VERTICA % ('10.0.0.2', '/var/lib/vertica'))
        arguments.assert_called_with(expected_command)

    def test_failure_install_vertica(self):
        with patch.object(vertica_system, 'shell_execute',
                          side_effect=ProcessExecutionError('some exception')):
            self.assertRaisesRegexp(RuntimeError, 'install_vertica failed.',
                                    self.app.install_vertica,
                                    members='10.0.0.2')

    def test_create_db(self):
        with patch.object(self.app, 'read_config',
                          return_value=self.test_config):
            self.app.create_db(members='10.0.0.2')
        arguments = vertica_system.shell_execute.call_args_list[0]
        expected_command = (vertica_system.CREATE_DB % ('10.0.0.2', 'db_srvr',
                                                        '/var/lib/vertica',
                                                        '/var/lib/vertica',
                                                        'some_password'))
        arguments.assert_called_with(expected_command, 'dbadmin')

    def test_failure_create_db(self):
        with patch.object(self.app, 'read_config',
                          side_effect=RuntimeError('Error')):
            self.assertRaisesRegexp(RuntimeError,
                                    'Vertica database create failed.',
                                    self.app.create_db)
        # Because of an exception in read_config there was no shell execution.
        self.assertEqual(0, vertica_system.shell_execute.call_count)

    def test_vertica_write_config(self):
        temp_file_handle = tempfile.NamedTemporaryFile(delete=False)
        mock_mkstemp = MagicMock(return_value=(temp_file_handle))
        mock_unlink = Mock(return_value=0)
        self.app.write_config(config=self.test_config,
                              temp_function=mock_mkstemp,
                              unlink_function=mock_unlink)

        arguments = vertica_system.shell_execute.call_args_list[0]
        expected_command = (
            ("install -o root -g root -m 644 %(source)s %(target)s"
             ) % {'source': temp_file_handle.name,
                  'target': vertica_system.VERTICA_CONF})
        arguments.assert_called_with(expected_command)
        self.assertEqual(1, mock_mkstemp.call_count)

        configuration_data = ConfigParser.ConfigParser()
        configuration_data.read(temp_file_handle.name)
        self.assertEqual(
            self.test_config.get('credentials', 'dbadmin_password'),
            configuration_data.get('credentials', 'dbadmin_password'))
        self.assertEqual(1, mock_unlink.call_count)
        # delete the temporary_config_file
        os.unlink(temp_file_handle.name)

    def test_vertica_error_in_write_config_verify_unlink(self):
        mock_unlink = Mock(return_value=0)
        temp_file_handle = tempfile.NamedTemporaryFile(delete=False)
        mock_mkstemp = MagicMock(return_value=temp_file_handle)

        with patch.object(vertica_system, 'shell_execute',
                          side_effect=ProcessExecutionError('some exception')):
            self.assertRaises(ProcessExecutionError,
                              self.app.write_config,
                              config=self.test_config,
                              temp_function=mock_mkstemp,
                              unlink_function=mock_unlink)

        self.assertEqual(1, mock_unlink.call_count)

        # delete the temporary_config_file
        os.unlink(temp_file_handle.name)

    def test_restart(self):
        mock_status = MagicMock()
        app = VerticaApp(mock_status)
        mock_status.begin_restart = MagicMock(return_value=None)
        with patch.object(VerticaApp, 'stop_db', return_value=None):
            with patch.object(VerticaApp, 'start_db', return_value=None):
                mock_status.end_install_or_restart = MagicMock(
                    return_value=None)
                app.restart()
                mock_status.begin_restart.assert_any_call()
                VerticaApp.stop_db.assert_any_call()
                VerticaApp.start_db.assert_any_call()

    def test_start_db(self):
        mock_status = MagicMock()
        type(mock_status)._is_restarting = PropertyMock(return_value=False)
        app = VerticaApp(mock_status)
        with patch.object(app, '_enable_db_on_boot', return_value=None):
            with patch.object(app, 'read_config',
                              return_value=self.test_config):
                mock_status.end_install_or_restart = MagicMock(
                    return_value=None)
                app.start_db()
                agent_start, db_start = subprocess.Popen.call_args_list
                agent_expected_command = [
                    'sudo', 'su', '-', 'root', '-c',
                    (vertica_system.VERTICA_AGENT_SERVICE_COMMAND % 'start')]
                db_expected_cmd = [
                    'sudo', 'su', '-', 'dbadmin', '-c',
                    (vertica_system.START_DB % ('db_srvr', 'some_password'))]
                self.assertTrue(mock_status.end_install_or_restart.called)
                agent_start.assert_called_with(agent_expected_command)
                db_start.assert_called_with(db_expected_cmd)

    def test_start_db_failure(self):
        mock_status = MagicMock()
        app = VerticaApp(mock_status)
        with patch.object(app, '_enable_db_on_boot',
                          side_effect=RuntimeError()):
            with patch.object(app, 'read_config',
                              return_value=self.test_config):
                self.assertRaises(RuntimeError, app.start_db)

    def test_stop_db(self):
        mock_status = MagicMock()
        type(mock_status)._is_restarting = PropertyMock(return_value=False)
        app = VerticaApp(mock_status)
        with patch.object(app, '_disable_db_on_boot', return_value=None):
            with patch.object(app, 'read_config',
                              return_value=self.test_config):
                with patch.object(vertica_system, 'shell_execute',
                                  MagicMock(side_effect=[['', ''],
                                                         ['db_srvr', None],
                                                         ['', '']])):
                    mock_status.wait_for_real_status_to_change_to = MagicMock(
                        return_value=True)
                    mock_status.end_install_or_restart = MagicMock(
                        return_value=None)
                    app.stop_db()

                    self.assertEqual(
                        3, vertica_system.shell_execute.call_count)
                    # There are 3 shell-executions:
                    # a) stop vertica-agent service
                    # b) check daatabase status
                    # c) stop_db
                    # We are matcing that 3rd command called was stop_db
                    arguments = vertica_system.shell_execute.call_args_list[2]
                    expected_cmd = (vertica_system.STOP_DB % ('db_srvr',
                                                              'some_password'))
                    self.assertTrue(
                        mock_status.wait_for_real_status_to_change_to.called)
                    arguments.assert_called_with(expected_cmd, 'dbadmin')

    def test_stop_db_do_not_start_on_reboot(self):
        mock_status = MagicMock()
        type(mock_status)._is_restarting = PropertyMock(return_value=True)
        app = VerticaApp(mock_status)
        with patch.object(app, '_disable_db_on_boot', return_value=None):
            with patch.object(app, 'read_config',
                              return_value=self.test_config):
                with patch.object(vertica_system, 'shell_execute',
                                  MagicMock(side_effect=[['', ''],
                                                         ['db_srvr', None],
                                                         ['', '']])):
                    app.stop_db(do_not_start_on_reboot=True)

                    self.assertEqual(
                        3, vertica_system.shell_execute.call_count)
                    app._disable_db_on_boot.assert_any_call()

    def test_stop_db_database_not_running(self):
        mock_status = MagicMock()
        app = VerticaApp(mock_status)
        with patch.object(app, '_disable_db_on_boot', return_value=None):
            with patch.object(app, 'read_config',
                              return_value=self.test_config):
                app.stop_db()
                # Since database stop command does not gets executed,
                # so only 2 shell calls were there.
                self.assertEqual(
                    2, vertica_system.shell_execute.call_count)

    def test_stop_db_failure(self):
        mock_status = MagicMock()
        type(mock_status)._is_restarting = PropertyMock(return_value=False)
        app = VerticaApp(mock_status)
        with patch.object(app, '_disable_db_on_boot', return_value=None):
            with patch.object(app, 'read_config',
                              return_value=self.test_config):
                with patch.object(vertica_system, 'shell_execute',
                                  MagicMock(side_effect=[['', ''],
                                                         ['db_srvr', None],
                                                         ['', '']])):
                    mock_status.wait_for_real_status_to_change_to = MagicMock(
                        return_value=None)
                    mock_status.end_install_or_restart = MagicMock(
                        return_value=None)
                    self.assertRaises(RuntimeError, app.stop_db)

    def test_export_conf_to_members(self):
        self.app._export_conf_to_members(members=['member1', 'member2'])
        self.assertEqual(2, vertica_system.shell_execute.call_count)

    def test_fail__export_conf_to_members(self):
        app = VerticaApp(MagicMock())
        with patch.object(vertica_system, 'shell_execute',
                          side_effect=ProcessExecutionError('Error')):
            self.assertRaises(ProcessExecutionError,
                              app._export_conf_to_members,
                              ['member1', 'member2'])

    def test_authorize_public_keys(self):
        user = 'test_user'
        keys = ['test_key@machine1', 'test_key@machine2']
        with patch.object(os.path, 'expanduser',
                          return_value=('/home/' + user)):
            self.app.authorize_public_keys(user=user, public_keys=keys)
        self.assertEqual(2, vertica_system.shell_execute.call_count)
        vertica_system.shell_execute.assert_any_call(
            'cat ' + '/home/' + user + '/.ssh/authorized_keys')

    def test_authorize_public_keys_authorized_file_not_exists(self):
        user = 'test_user'
        keys = ['test_key@machine1', 'test_key@machine2']
        with patch.object(os.path, 'expanduser',
                          return_value=('/home/' + user)):
            with patch.object(
                    vertica_system, 'shell_execute',
                    MagicMock(side_effect=[ProcessExecutionError('Some Error'),
                                           ['', '']])):
                self.app.authorize_public_keys(user=user, public_keys=keys)
                self.assertEqual(2, vertica_system.shell_execute.call_count)
                vertica_system.shell_execute.assert_any_call(
                    'cat ' + '/home/' + user + '/.ssh/authorized_keys')

    def test_fail_authorize_public_keys(self):
        user = 'test_user'
        keys = ['test_key@machine1', 'test_key@machine2']
        with patch.object(os.path, 'expanduser',
                          return_value=('/home/' + user)):
            with patch.object(
                    vertica_system, 'shell_execute',
                    MagicMock(side_effect=[ProcessExecutionError('Some Error'),
                                           ProcessExecutionError('Some Error')
                                           ])):
                self.assertRaises(ProcessExecutionError,
                                  self.app.authorize_public_keys, user, keys)

    def test_get_public_keys(self):
        user = 'test_user'
        with patch.object(os.path, 'expanduser',
                          return_value=('/home/' + user)):
            self.app.get_public_keys(user=user)
        self.assertEqual(2, vertica_system.shell_execute.call_count)
        vertica_system.shell_execute.assert_any_call(
            (vertica_system.SSH_KEY_GEN % ('/home/' + user)), user)
        vertica_system.shell_execute.assert_any_call(
            'cat ' + '/home/' + user + '/.ssh/id_rsa.pub')

    def test_get_public_keys_if_key_exists(self):
        user = 'test_user'
        with patch.object(os.path, 'expanduser',
                          return_value=('/home/' + user)):
            with patch.object(
                    vertica_system, 'shell_execute',
                    MagicMock(side_effect=[ProcessExecutionError('Some Error'),
                                           ['some_key', None]])):
                key = self.app.get_public_keys(user=user)
                self.assertEqual(2, vertica_system.shell_execute.call_count)
                self.assertEqual('some_key', key)

    def test_fail_get_public_keys(self):
        user = 'test_user'
        with patch.object(os.path, 'expanduser',
                          return_value=('/home/' + user)):
            with patch.object(
                    vertica_system, 'shell_execute',
                    MagicMock(side_effect=[ProcessExecutionError('Some Error'),
                                           ProcessExecutionError('Some Error')
                                           ])):
                self.assertRaises(ProcessExecutionError,
                                  self.app.get_public_keys, user)

    def test_install_cluster(self):
        with patch.object(self.app, 'read_config',
                          return_value=self.test_config):
            self.app.install_cluster(members=['member1', 'member2'])
        # Verifying the number of shell calls,
        # as command has already been tested in preceding tests
        self.assertEqual(5, vertica_system.shell_execute.call_count)

    def test__enable_db_on_boot(self):
        app = VerticaApp(MagicMock())
        app._enable_db_on_boot()

        restart_policy, agent_enable = subprocess.Popen.call_args_list
        expected_restart_policy = [
            'sudo', 'su', '-', 'dbadmin', '-c',
            (vertica_system.SET_RESTART_POLICY % ('db_srvr', 'always'))]
        expected_agent_enable = [
            'sudo', 'su', '-', 'root', '-c',
            (vertica_system.VERTICA_AGENT_SERVICE_COMMAND % 'enable')]

        self.assertEqual(2, subprocess.Popen.call_count)
        restart_policy.assert_called_with(expected_restart_policy)
        agent_enable.assert_called_with(expected_agent_enable)

    def test_failure__enable_db_on_boot(self):
        with patch.object(subprocess, 'Popen', side_effect=OSError):
            self.assertRaisesRegexp(RuntimeError,
                                    'Could not enable db on boot.',
                                    self.app._enable_db_on_boot)

    def test__disable_db_on_boot(self):
        app = VerticaApp(MagicMock())
        app._disable_db_on_boot()

        restart_policy, agent_disable = (
            vertica_system.shell_execute.call_args_list)
        expected_restart_policy = (
            vertica_system.SET_RESTART_POLICY % ('db_srvr', 'never'))
        expected_agent_disable = (
            vertica_system.VERTICA_AGENT_SERVICE_COMMAND % 'disable')

        self.assertEqual(2, vertica_system.shell_execute.call_count)
        restart_policy.assert_called_with(expected_restart_policy, 'dbadmin')
        agent_disable.assert_called_with(expected_agent_disable, 'root')

    def test_failure__disable_db_on_boot(self):
        with patch.object(vertica_system, 'shell_execute',
                          side_effect=ProcessExecutionError('Error')):
            self.assertRaisesRegexp(RuntimeError,
                                    'Could not disable db on boot.',
                                    self.app._disable_db_on_boot)

    def test_read_config(self):
        app = VerticaApp(MagicMock())
        with patch.object(ConfigParser, 'ConfigParser',
                          return_value=self.test_config):
            test_config = app.read_config()
            self.assertEqual('some_password',
                             test_config.get('credentials', 'dbadmin_password')
                             )

    def test_fail_read_config(self):
        with patch.object(ConfigParser.ConfigParser, 'read',
                          side_effect=ConfigParser.Error()):
            self.assertRaises(RuntimeError, self.app.read_config)

    def test_complete_install_or_restart(self):
        app = VerticaApp(MagicMock())
        app.complete_install_or_restart()
        app.status.end_install_or_restart.assert_any_call()

    def test_start_db_with_conf_changes(self):
        mock_status = MagicMock()
        type(mock_status)._is_restarting = PropertyMock(return_value=False)
        app = VerticaApp(mock_status)
        with patch.object(app, 'read_config',
                          return_value=self.test_config):
            app.start_db_with_conf_changes('test_config_contents')
            app.status.end_install_or_restart.assert_any_call()


class DB2AppTest(testtools.TestCase):

    def setUp(self):
        super(DB2AppTest, self).setUp()
        self.orig_utils_execute_with_timeout = (
            db2service.utils.execute_with_timeout)
        util.init_db()
        self.FAKE_ID = str(uuid4())
        InstanceServiceStatus.create(instance_id=self.FAKE_ID,
                                     status=rd_instance.ServiceStatuses.NEW)
        self.appStatus = FakeAppStatus(self.FAKE_ID,
                                       rd_instance.ServiceStatuses.NEW)
        self.db2App = db2service.DB2App(self.appStatus)
        dbaas.CONF.guest_id = self.FAKE_ID

    def tearDown(self):
        super(DB2AppTest, self).tearDown()
        db2service.utils.execute_with_timeout = (
            self.orig_utils_execute_with_timeout)
        InstanceServiceStatus.find_by(instance_id=self.FAKE_ID).delete()
        dbaas.CONF.guest_id = None
        self.db2App = None

    def assert_reported_status(self, expected_status):
        service_status = InstanceServiceStatus.find_by(
            instance_id=self.FAKE_ID)
        self.assertEqual(expected_status, service_status.status)

    def test_stop_db(self):
        db2service.utils.execute_with_timeout = MagicMock(return_value=None)
        self.appStatus.set_next_status(rd_instance.ServiceStatuses.SHUTDOWN)
        self.db2App.stop_db()
        self.assert_reported_status(rd_instance.ServiceStatuses.NEW)

    def test_restart_server(self):
        self.appStatus.set_next_status(rd_instance.ServiceStatuses.RUNNING)
        mock_status = MagicMock(return_value=None)
        app = db2service.DB2App(mock_status)
        mock_status.begin_restart = MagicMock(return_value=None)
        app.stop_db = MagicMock(return_value=None)
        app.start_db = MagicMock(return_value=None)
        app.restart()

        self.assertTrue(mock_status.begin_restart.called)
        self.assertTrue(app.stop_db.called)
        self.assertTrue(app.start_db.called)

    def test_start_db(self):
        db2service.utils.execute_with_timeout = MagicMock(return_value=None)
        self.appStatus.set_next_status(rd_instance.ServiceStatuses.RUNNING)
        with patch.object(self.db2App, '_enable_db_on_boot',
                          return_value=None):
            self.db2App.start_db()
            self.assert_reported_status(rd_instance.ServiceStatuses.NEW)


class DB2AdminTest(testtools.TestCase):

    def setUp(self):
        super(DB2AdminTest, self).setUp()
        self.db2Admin = db2service.DB2Admin()
        self.orig_utils_execute_with_timeout = (
            db2service.utils.execute_with_timeout)

    def tearDown(self):
        super(DB2AdminTest, self).tearDown()
        db2service.utils.execute_with_timeout = (
            self.orig_utils_execute_with_timeout)

    def test_delete_database(self):
        with patch.object(
            db2service, 'run_command',
            MagicMock(
                return_value=None,
                side_effect=ProcessExecutionError('Error'))):
            self.assertRaises(GuestError,
                              self.db2Admin.delete_database,
                              FAKE_DB)
            self.assertTrue(db2service.run_command.called)
            args, _ = db2service.run_command.call_args_list[0]
            expected = "db2 drop database testDB"
            self.assertEqual(expected, args[0],
                             "Delete database queries are not the same")

    def test_list_databases(self):
        with patch.object(db2service, 'run_command', MagicMock(
                          side_effect=ProcessExecutionError('Error'))):
            self.db2Admin.list_databases()
            self.assertTrue(db2service.run_command.called)
            args, _ = db2service.run_command.call_args_list[0]
            expected = "db2 list database directory " \
                "| grep -B6 -i indirect | grep 'Database name' | " \
                "sed 's/.*= //'"
            self.assertEqual(expected, args[0],
                             "Delete database queries are not the same")

    def test_create_users(self):
        with patch.object(db2service, 'run_command', MagicMock(
                          return_value=None)):
            db2service.utils.execute_with_timeout = MagicMock(
                return_value=None)
            self.db2Admin.create_user(FAKE_USER)
            self.assertTrue(db2service.utils.execute_with_timeout.called)
            self.assertTrue(db2service.run_command.called)
            args, _ = db2service.run_command.call_args_list[0]
            expected = "db2 connect to testDB; " \
                "db2 GRANT DBADM,CREATETAB,BINDADD,CONNECT,DATAACCESS " \
                "ON DATABASE TO USER random; db2 connect reset"
            self.assertEqual(
                expected, args[0],
                "Granting database access queries are not the same")
            self.assertEqual(1, db2service.run_command.call_count)

    def test_delete_users_with_db(self):
        with patch.object(db2service, 'run_command',
                          MagicMock(return_value=None)):
            with patch.object(db2service.DB2Admin, 'list_access',
                              MagicMock(return_value=None)):
                utils.execute_with_timeout = MagicMock(return_value=None)
                self.db2Admin.delete_user(FAKE_USER[0])
                self.assertTrue(db2service.run_command.called)
                self.assertTrue(db2service.utils.execute_with_timeout.called)
                self.assertFalse(db2service.DB2Admin.list_access.called)
                args, _ = db2service.run_command.call_args_list[0]
                expected = "db2 connect to testDB; " \
                    "db2 REVOKE DBADM,CREATETAB,BINDADD,CONNECT,DATAACCESS " \
                    "ON DATABASE FROM USER random; db2 connect reset"
                self.assertEqual(
                    expected, args[0],
                    "Revoke database access queries are not the same")
                self.assertEqual(1, db2service.run_command.call_count)

    def test_delete_users_without_db(self):
        FAKE_USER.append(
            {"_name": "random2", "_password": "guesswhat", "_databases": []})
        with patch.object(db2service, 'run_command',
                          MagicMock(return_value=None)):
            with patch.object(db2service.DB2Admin, 'list_access',
                              MagicMock(return_value=[FAKE_DB])):
                utils.execute_with_timeout = MagicMock(return_value=None)
                self.db2Admin.delete_user(FAKE_USER[1])
                self.assertTrue(db2service.run_command.called)
                self.assertTrue(db2service.DB2Admin.list_access.called)
                self.assertTrue(
                    db2service.utils.execute_with_timeout.called)
                args, _ = db2service.run_command.call_args_list[0]
                expected = "db2 connect to testDB; " \
                    "db2 REVOKE DBADM,CREATETAB,BINDADD,CONNECT," \
                    "DATAACCESS ON DATABASE FROM USER random2; " \
                    "db2 connect reset"
                self.assertEqual(
                    expected, args[0],
                    "Revoke database access queries are not the same")
                self.assertEqual(1, db2service.run_command.call_count)

    def test_list_users(self):
        databases = []
        databases.append(FAKE_DB)
        with patch.object(db2service, 'run_command', MagicMock(
                          side_effect=ProcessExecutionError('Error'))):
            with patch.object(self.db2Admin, "list_databases",
                              MagicMock(return_value=(databases, None))):
                self.db2Admin.list_users()
                self.assertTrue(db2service.run_command.called)
                args, _ = db2service.run_command.call_args_list[0]
                expected = "db2 +o  connect to testDB; " \
                    "db2 -x  select grantee, dataaccessauth " \
                    "from sysibm.sysdbauth; db2 connect reset"
            self.assertEqual(expected, args[0],
                             "List database queries are not the same")

    def test_get_user(self):
        databases = []
        databases.append(FAKE_DB)
        with patch.object(db2service, 'run_command', MagicMock(
                          side_effect=ProcessExecutionError('Error'))):
            with patch.object(self.db2Admin, "list_databases",
                              MagicMock(return_value=(databases, None))):
                self.db2Admin._get_user('random', None)
                self.assertTrue(db2service.run_command.called)
                args, _ = db2service.run_command.call_args_list[0]
                expected = "db2 +o  connect to testDB; " \
                    "db2 -x  select grantee, dataaccessauth " \
                    "from sysibm.sysdbauth; db2 connect reset"
                self.assertEqual(args[0], expected,
                                 "Delete database queries are not the same")


class PXCAppTest(testtools.TestCase):

    def setUp(self):
        super(PXCAppTest, self).setUp()
        self.orig_utils_execute_with_timeout = \
            dbaas_base.utils.execute_with_timeout
        self.orig_time_sleep = time.sleep
        self.orig_unlink = os.unlink
        self.orig_get_auth_password = pxc_service.PXCApp.get_auth_password
        self.orig_service_discovery = operating_system.service_discovery
        self.orig_pxc_system_service_discovery = pxc_system.service_discovery
        self.FAKE_ID = str(uuid4())
        InstanceServiceStatus.create(instance_id=self.FAKE_ID,
                                     status=rd_instance.ServiceStatuses.NEW)
        self.appStatus = FakeAppStatus(self.FAKE_ID,
                                       rd_instance.ServiceStatuses.NEW)
        self.PXCApp = pxc_service.PXCApp(self.appStatus)
        mysql_service = {'cmd_start': Mock(),
                         'cmd_stop': Mock(),
                         'cmd_enable': Mock(),
                         'cmd_disable': Mock(),
                         'cmd_bootstrap_pxc_cluster': Mock(),
                         'bin': Mock()}
        pxc_system.service_discovery = Mock(
            return_value=mysql_service)
        time.sleep = Mock()
        os.unlink = Mock()
        pxc_service.PXCApp.get_auth_password = Mock()
        self.mock_client = Mock()
        self.mock_execute = Mock()
        self.mock_client.__enter__ = Mock()
        self.mock_client.__exit__ = Mock()
        self.mock_client.__enter__.return_value.execute = self.mock_execute
        pxc_service.orig_configuration_manager = (
            pxc_service.PXCApp.configuration_manager)
        pxc_service.PXCApp.configuration_manager = Mock()
        self.orig_create_engine = sqlalchemy.create_engine

    def tearDown(self):
        super(PXCAppTest, self).tearDown()
        self.PXCApp = None
        dbaas_base.utils.execute_with_timeout = \
            self.orig_utils_execute_with_timeout
        time.sleep = self.orig_time_sleep
        os.unlink = self.orig_unlink
        operating_system.service_discovery = self.orig_service_discovery
        pxc_system.service_discovery = self.orig_pxc_system_service_discovery
        pxc_service.PXCApp.get_auth_password = self.orig_get_auth_password
        InstanceServiceStatus.find_by(instance_id=self.FAKE_ID).delete()
        pxc_service.PXCApp.configuration_manager = \
            pxc_service.orig_configuration_manager
        sqlalchemy.create_engine = self.orig_create_engine

    @patch.object(pxc_service.PXCApp, 'get_engine',
                  return_value=MagicMock(name='get_engine'))
    def test__grant_cluster_replication_privilege(self, mock_engine):
        repl_user = {
            'name': 'test-user',
            'password': 'test-user-password',
        }
        with patch.object(pxc_service.PXCApp, 'local_sql_client',
                          return_value=self.mock_client):
            self.PXCApp._grant_cluster_replication_privilege(repl_user)
        args, _ = self.mock_execute.call_args_list[0]
        expected = ("GRANT LOCK TABLES, RELOAD, REPLICATION CLIENT ON *.* "
                    "TO `test-user`@`%` IDENTIFIED BY 'test-user-password';")
        self.assertEqual(expected, args[0].text,
                         "Sql statements are not the same")

    @patch.object(utils, 'execute_with_timeout')
    def test__bootstrap_cluster(self, mock_execute):
        pxc_service_cmds = pxc_system.service_discovery(['mysql'])
        self.PXCApp._bootstrap_cluster(timeout=20)
        self.assertEqual(1, mock_execute.call_count)
        mock_execute.assert_called_with(
            pxc_service_cmds['cmd_bootstrap_pxc_cluster'],
            shell=True,
            timeout=20)

    def test_install_cluster(self):
        repl_user = {
            'name': 'test-user',
            'password': 'test-user-password',
        }
        apply_mock = Mock()
        self.PXCApp.configuration_manager.apply_system_override = apply_mock
        self.PXCApp.stop_db = Mock()
        self.PXCApp._grant_cluster_replication_privilege = Mock()
        self.PXCApp.wipe_ib_logfiles = Mock()
        self.PXCApp.start_mysql = Mock()
        self.PXCApp.install_cluster(repl_user, "something")
        self.assertEqual(1, self.PXCApp.stop_db.call_count)
        self.assertEqual(
            1, self.PXCApp._grant_cluster_replication_privilege.call_count)
        self.assertEqual(1, apply_mock.call_count)
        self.assertEqual(1, self.PXCApp.wipe_ib_logfiles.call_count)
        self.assertEqual(1, self.PXCApp.start_mysql.call_count)

    def test_install_cluster_with_bootstrap(self):
        repl_user = {
            'name': 'test-user',
            'password': 'test-user-password',
        }
        apply_mock = Mock()
        self.PXCApp.configuration_manager.apply_system_override = apply_mock
        self.PXCApp.stop_db = Mock()
        self.PXCApp._grant_cluster_replication_privilege = Mock()
        self.PXCApp.wipe_ib_logfiles = Mock()
        self.PXCApp._bootstrap_cluster = Mock()
        self.PXCApp.install_cluster(repl_user, "something", bootstrap=True)
        self.assertEqual(1, self.PXCApp.stop_db.call_count)
        self.assertEqual(
            1, self.PXCApp._grant_cluster_replication_privilege.call_count)
        self.assertEqual(1, self.PXCApp.wipe_ib_logfiles.call_count)
        self.assertEqual(1, apply_mock.call_count)
        self.assertEqual(1, self.PXCApp._bootstrap_cluster.call_count)
