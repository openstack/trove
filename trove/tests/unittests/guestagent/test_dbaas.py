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

import os
from uuid import uuid4
import time
from mock import Mock
from mock import MagicMock
from mock import patch
from mock import ANY
import sqlalchemy
import testtools
from testtools.matchers import Is
from testtools.matchers import Equals
from testtools.matchers import Not
from trove.common.exception import ProcessExecutionError
from trove.common import utils
from trove.common import instance as rd_instance
from trove.conductor import api as conductor_api
import trove.guestagent.datastore.mysql.service as dbaas
from trove.guestagent import dbaas as dbaas_sr
from trove.guestagent import pkg
from trove.guestagent.common import operating_system
from trove.guestagent.dbaas import to_gb
from trove.guestagent.dbaas import get_filesystem_volume_stats
from trove.guestagent.datastore.service import BaseDbStatus
from trove.guestagent.datastore.redis import service as rservice
from trove.guestagent.datastore.redis.service import RedisApp
from trove.guestagent.datastore.redis import system as RedisSystem
from trove.guestagent.datastore.cassandra import service as cass_service
from trove.guestagent.datastore.mysql.service import MySqlAdmin
from trove.guestagent.datastore.mysql.service import MySqlRootAccess
from trove.guestagent.datastore.mysql.service import MySqlApp
from trove.guestagent.datastore.mysql.service import MySqlAppStatus
from trove.guestagent.datastore.mysql.service import KeepAliveConnection
from trove.guestagent.datastore.couchbase import service as couchservice
from trove.guestagent.datastore.mongodb import service as mongo_service
from trove.guestagent.datastore.mongodb import system as mongo_system
from trove.guestagent.db import models
from trove.instance.models import InstanceServiceStatus
from trove.tests.unittests.util import util


"""
Unit tests for the classes and functions in dbaas.py.
"""

FAKE_DB = {"_name": "testDB", "_character_set": "latin2",
           "_collate": "latin2_general_ci"}
FAKE_DB_2 = {"_name": "testDB2", "_character_set": "latin2",
             "_collate": "latin2_general_ci"}
FAKE_USER = [{"_name": "random", "_password": "guesswhat",
              "_databases": [FAKE_DB]}]


conductor_api.API.heartbeat = Mock()


class FakeAppStatus(BaseDbStatus):

    def __init__(self, id, status):
        self.id = id
        self.next_fake_status = status

    def _get_actual_db_status(self):
        return self.next_fake_status

    def set_next_status(self, next_status):
        self.next_fake_status = next_status


class DbaasTest(testtools.TestCase):

    def setUp(self):
        super(DbaasTest, self).setUp()
        self.orig_utils_execute_with_timeout = dbaas.utils.execute_with_timeout
        self.orig_utils_execute = dbaas.utils.execute

    def tearDown(self):
        super(DbaasTest, self).tearDown()
        dbaas.utils.execute_with_timeout = self.orig_utils_execute_with_timeout
        dbaas.utils.execute = self.orig_utils_execute

    def test_get_auth_password(self):

        dbaas.utils.execute_with_timeout = Mock(
            return_value=("password    ", None))

        password = dbaas.get_auth_password()

        self.assertEqual("password", password)

    def test_get_auth_password_error(self):

        dbaas.utils.execute_with_timeout = Mock(
            return_value=("password", "Error"))

        self.assertRaises(RuntimeError, dbaas.get_auth_password)

    def test_service_discovery(self):
        with patch.object(os.path, 'isfile', return_value=True):
            mysql_service = dbaas.operating_system.service_discovery(["mysql"])
        self.assertIsNotNone(mysql_service['cmd_start'])
        self.assertIsNotNone(mysql_service['cmd_enable'])

    def test_load_mysqld_options(self):

        output = "mysqld would've been started with the these args:\n"\
                 "--user=mysql --port=3306 --basedir=/usr "\
                 "--tmpdir=/tmp --skip-external-locking"

        with patch.object(os.path, 'isfile', return_value=True):
            dbaas.utils.execute = Mock(return_value=(output, None))
            options = dbaas.load_mysqld_options()

        self.assertEqual(5, len(options))
        self.assertEqual(options["user"], "mysql")
        self.assertEqual(options["port"], "3306")
        self.assertEqual(options["basedir"], "/usr")
        self.assertEqual(options["tmpdir"], "/tmp")
        self.assertTrue("skip-external-locking" in options)

    def test_load_mysqld_options_error(self):

        dbaas.utils.execute = Mock(side_effect=ProcessExecutionError())

        self.assertFalse(dbaas.load_mysqld_options())


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

    def tearDown(self):
        super(MySqlAdminMockTest, self).tearDown()

    def test_list_databases(self):
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

    def test_create_database(self):

        databases = []
        databases.append(FAKE_DB)

        self.mySqlAdmin.create_database(databases)

        args, _ = dbaas.LocalSqlClient.execute.call_args_list[0]
        expected = ("CREATE DATABASE IF NOT EXISTS "
                    "`testDB` CHARACTER SET = 'latin2' "
                    "COLLATE = 'latin2_general_ci';")
        self.assertEqual(args[0].text, expected,
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
        self.assertEqual(args[0].text, expected,
                         "Create database queries are not the same")

        args, _ = dbaas.LocalSqlClient.execute.call_args_list[1]
        expected = ("CREATE DATABASE IF NOT EXISTS "
                    "`testDB2` CHARACTER SET = 'latin2' "
                    "COLLATE = 'latin2_general_ci';")
        self.assertEqual(args[0].text, expected,
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
        self.assertEqual(args[0].text, expected,
                         "Delete database queries are not the same")

        self.assertTrue(dbaas.LocalSqlClient.execute.called,
                        "The client object was not called")

    def test_delete_user(self):

        user = {"_name": "testUser"}

        self.mySqlAdmin.delete_user(user)

        # For some reason, call_args is None.
        call_args = dbaas.LocalSqlClient.execute.call_args
        if call_args is not None:
            args, _ = call_args
            expected = "DROP USER `testUser`;"
            self.assertEqual(args[0].text, expected,
                             "Delete user queries are not the same")

            self.assertTrue(dbaas.LocalSqlClient.execute.called,
                            "The client object was not called")

    def test_create_user(self):
        self.mySqlAdmin.create_user(FAKE_USER)
        expected = ("GRANT ALL PRIVILEGES ON `testDB`.* TO `random`@`%` "
                    "IDENTIFIED BY 'guesswhat' "
                    "WITH GRANT OPTION;")
        # For some reason, call_args is None.
        call_args = dbaas.LocalSqlClient.execute.call_args
        if call_args is not None:
            args, _ = call_args
            self.assertEqual(args[0].text.strip(), expected,
                             "Create user queries are not the same")
            self.assertEqual(2, dbaas.LocalSqlClient.execute.call_count)

    def test_list_databases(self):
        self.mySqlAdmin.list_databases()
        args, _ = dbaas.LocalSqlClient.execute.call_args
        expected = ["SELECT schema_name as name,",
                    "default_character_set_name as charset,",
                    "default_collation_name as collation",
                    "FROM information_schema.schemata",
                    ("schema_name NOT IN ("
                     "'mysql', 'information_schema', "
                     "'lost+found', '#mysql50#lost+found'"
                     ")"),
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
                    ("schema_name NOT IN ("
                     "'mysql', 'information_schema', "
                     "'lost+found', '#mysql50#lost+found'"
                     ")"),
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
                    ("schema_name NOT IN ("
                     "'mysql', 'information_schema', "
                     "'lost+found', '#mysql50#lost+found'"
                     ")"),
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
                    ("schema_name NOT IN ("
                     "'mysql', 'information_schema', "
                     "'lost+found', '#mysql50#lost+found'"
                     ")"),
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

    def test_get_user(self):
        """
        Unit tests for mySqlAdmin.get_user.
        This test case checks if the sql query formed by the get_user method
        is correct or not by checking with expected query.
        """
        username = "user1"
        hostname = "host"
        self.mySqlAdmin.get_user(username, hostname)
        args, _ = dbaas.LocalSqlClient.execute.call_args
        expected = ["SELECT User, Host",
                    "FROM mysql.user",
                    "WHERE Host != 'localhost' AND User = 'user1'",
                    "ORDER BY User, Host",
                    ]

        for text in expected:
            self.assertTrue(text in args[0].text, "%s not in query." % text)


class MySqlAppTest(testtools.TestCase):

    def setUp(self):
        super(MySqlAppTest, self).setUp()
        self.orig_utils_execute_with_timeout = dbaas.utils.execute_with_timeout
        self.orig_time_sleep = time.sleep
        util.init_db()
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
                         'bin': Mock()}
        dbaas.operating_system.service_discovery = Mock(return_value=
                                                        mysql_service)
        time.sleep = Mock()

    def tearDown(self):
        super(MySqlAppTest, self).tearDown()
        dbaas.utils.execute_with_timeout = self.orig_utils_execute_with_timeout
        time.sleep = self.orig_time_sleep
        InstanceServiceStatus.find_by(instance_id=self.FAKE_ID).delete()

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

        dbaas.utils.execute_with_timeout = Mock()
        self.appStatus.set_next_status(
            rd_instance.ServiceStatuses.SHUTDOWN)

        self.mySqlApp.stop_db()
        self.assert_reported_status(rd_instance.ServiceStatuses.NEW)

    def test_stop_mysql_with_db_update(self):

        dbaas.utils.execute_with_timeout = Mock()
        self.appStatus.set_next_status(
            rd_instance.ServiceStatuses.SHUTDOWN)

        self.mySqlApp.stop_db(True)
        self.assertTrue(conductor_api.API.heartbeat.called_once_with(
            self.FAKE_ID,
            {'service_status':
             rd_instance.ServiceStatuses.SHUTDOWN.description}))

    def test_stop_mysql_error(self):

        dbaas.utils.execute_with_timeout = Mock()
        self.appStatus.set_next_status(rd_instance.ServiceStatuses.RUNNING)
        self.mySqlApp.state_change_wait_time = 1
        self.assertRaises(RuntimeError, self.mySqlApp.stop_db)

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

    def test_wipe_ib_logfiles_no_file(self):

        processexecerror = ProcessExecutionError('No such file or directory')
        dbaas.utils.execute_with_timeout = Mock(side_effect=processexecerror)

        self.mySqlApp.wipe_ib_logfiles()

    def test_wipe_ib_logfiles_error(self):

        mocked = Mock(side_effect=ProcessExecutionError('Error'))
        dbaas.utils.execute_with_timeout = mocked

        self.assertRaises(ProcessExecutionError,
                          self.mySqlApp.wipe_ib_logfiles)

    def test_start_mysql(self):

        dbaas.utils.execute_with_timeout = Mock()
        self.appStatus.set_next_status(rd_instance.ServiceStatuses.RUNNING)
        self.mySqlApp._enable_mysql_on_boot = Mock()
        self.mySqlApp.start_mysql()
        self.assert_reported_status(rd_instance.ServiceStatuses.NEW)

    def test_start_mysql_with_db_update(self):

        dbaas.utils.execute_with_timeout = Mock()
        self.mySqlApp._enable_mysql_on_boot = Mock()
        self.appStatus.set_next_status(rd_instance.ServiceStatuses.RUNNING)

        self.mySqlApp.start_mysql(update_db=True)
        self.assertTrue(conductor_api.API.heartbeat.called_once_with(
            self.FAKE_ID,
            {'service_status':
             rd_instance.ServiceStatuses.RUNNING.description}))

    def test_start_mysql_runs_forever(self):

        dbaas.utils.execute_with_timeout = Mock()
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
        dbaas.utils.execute_with_timeout = mocked

        self.assertRaises(RuntimeError, self.mySqlApp.start_mysql)

    def test_start_db_with_conf_changes(self):

        self.mySqlApp.start_mysql = Mock()
        self.mySqlApp._write_mycnf = Mock()
        self.mysql_starts_successfully()

        self.appStatus.status = rd_instance.ServiceStatuses.SHUTDOWN
        self.mySqlApp.start_db_with_conf_changes(Mock())

        self.assertTrue(self.mySqlApp._write_mycnf.called)
        self.assertTrue(self.mySqlApp.start_mysql.called)
        self.assertEqual(self.appStatus._get_actual_db_status(),
                         rd_instance.ServiceStatuses.RUNNING)

    def test_start_db_with_conf_changes_mysql_is_running(self):

        self.mySqlApp.start_mysql = Mock()
        self.mySqlApp._write_mycnf = Mock()

        self.appStatus.status = rd_instance.ServiceStatuses.RUNNING
        self.assertRaises(RuntimeError,
                          self.mySqlApp.start_db_with_conf_changes,
                          Mock())

    def test_remove_overrides(self):

        from trove.common.exception import ProcessExecutionError
        mocked = Mock(side_effect=ProcessExecutionError('Error'))
        dbaas.utils.execute_with_timeout = mocked
        self.assertRaises(ProcessExecutionError, self.mySqlApp.start_mysql)


class MySqlAppInstallTest(MySqlAppTest):

    def setUp(self):
        super(MySqlAppInstallTest, self).setUp()
        self.orig_create_engine = sqlalchemy.create_engine
        self.orig_pkg_version = dbaas.packager.pkg_version
        self.orig_utils_execute_with_timeout = utils.execute_with_timeout

    def tearDown(self):
        super(MySqlAppInstallTest, self).tearDown()
        sqlalchemy.create_engine = self.orig_create_engine
        dbaas.packager.pkg_version = self.orig_pkg_version
        utils.execute_with_timeout = self.orig_utils_execute_with_timeout

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

    def test_secure(self):

        dbaas.clear_expired_password = Mock()
        self.mySqlApp.start_mysql = Mock()
        self.mySqlApp.stop_db = Mock()
        self.mySqlApp._write_mycnf = Mock()
        self.mysql_stops_successfully()
        self.mysql_starts_successfully()
        sqlalchemy.create_engine = Mock()

        self.mySqlApp.secure('contents', None)

        self.assertTrue(self.mySqlApp.stop_db.called)
        self.assertTrue(self.mySqlApp._write_mycnf.called)
        self.assertTrue(self.mySqlApp.start_mysql.called)
        self.assert_reported_status(rd_instance.ServiceStatuses.NEW)

    def test_install_install_error(self):

        from trove.guestagent import pkg
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

        dbaas.clear_expired_password = Mock()
        self.mySqlApp.start_mysql = Mock()
        self.mySqlApp.stop_db = Mock()
        self.mySqlApp._write_mycnf = Mock(
            side_effect=IOError("Could not write file"))
        self.mysql_stops_successfully()
        self.mysql_starts_successfully()
        sqlalchemy.create_engine = Mock()

        self.assertRaises(IOError, self.mySqlApp.secure, "foo", None)

        self.assertTrue(self.mySqlApp.stop_db.called)
        self.assertTrue(self.mySqlApp._write_mycnf.called)
        self.assertFalse(self.mySqlApp.start_mysql.called)
        self.assert_reported_status(rd_instance.ServiceStatuses.NEW)


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

    def test_secure_keep_root(self):
        mock_conn = mock_sql_connection()

        with patch.object(mock_conn, 'execute', return_value=None):
            utils.execute_with_timeout = MagicMock(return_value=None)
            # skip writing the file for now
            with patch.object(os.path, 'isfile', return_value=False):
                mock_status = MagicMock()
                mock_status.wait_for_real_status_to_change_to = MagicMock(
                    return_value=True)
                dbaas.clear_expired_password = MagicMock(return_value=None)
                app = MySqlApp(mock_status)
                app._write_mycnf = MagicMock(return_value=True)
                app.start_mysql = MagicMock(return_value=None)
                app.stop_db = MagicMock(return_value=None)
                app.secure('foo', None)
                self.assertTrue(mock_conn.execute.called)

    def test_secure_with_mycnf_error(self):
        mock_conn = mock_sql_connection()

        with patch.object(mock_conn, 'execute', return_value=None):
            operating_system.service_discovery = Mock(return_value={
                'cmd_stop': 'service mysql stop'})
            utils.execute_with_timeout = MagicMock(return_value=None)
            # skip writing the file for now
            with patch.object(os.path, 'isfile', return_value=False):
                mock_status = MagicMock()
                mock_status.wait_for_real_status_to_change_to = MagicMock(
                    return_value=True)
                dbaas.clear_expired_password = MagicMock(return_value=None)
                app = MySqlApp(mock_status)
                dbaas.clear_expired_password = MagicMock(return_value=None)
                self.assertRaises(TypeError, app.secure, None, None)
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

    def tearDown(self):
        super(MySqlRootStatusTest, self).tearDown()
        utils.execute_with_timeout = self.orig_utils_execute_with_timeout

    def test_root_is_enabled(self):
        mock_conn = mock_sql_connection()

        mock_rs = MagicMock()
        mock_rs.rowcount = 1
        with patch.object(mock_conn, 'execute', return_value=mock_rs):
            self.assertThat(MySqlRootAccess().is_root_enabled(), Is(True))

    def test_root_is_not_enabled(self):
        mock_conn = mock_sql_connection()

        mock_rs = MagicMock()
        mock_rs.rowcount = 0
        with patch.object(mock_conn, 'execute', return_value=mock_rs):
            self.assertThat(MySqlRootAccess.is_root_enabled(), Equals(False))

    def test_enable_root(self):
        mock_conn = mock_sql_connection()

        with patch.object(mock_conn, 'execute', return_value=None):
            # invocation
            user_ser = MySqlRootAccess.enable_root()
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
        self.assertEqual(result, 0.11)

    def test_to_gb_zero(self):
        result = to_gb(0)
        self.assertEqual(result, 0.0)

    def test_get_filesystem_volume_stats(self):
        with patch.object(os, 'statvfs', return_value=MockStats):
            result = get_filesystem_volume_stats('/some/path/')

        self.assertEqual(result['block_size'], 4096)
        self.assertEqual(result['total_blocks'], 1048576)
        self.assertEqual(result['free_blocks'], 524288)
        self.assertEqual(result['total'], 4.0)
        self.assertEqual(result['free'], 2147483648)
        self.assertEqual(result['used'], 2.0)

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
        dbaas_sr.get_custom_managers = Mock(return_value=
                                            datastore_registry_ext_test)
        test_dict = dbaas_sr.datastore_registry()
        self.assertEqual(test_dict.get('test'),
                         datastore_registry_ext_test.get('test', None))
        self.assertEqual(test_dict.get('mysql'),
                         'trove.guestagent.datastore.mysql.'
                         'manager.Manager')
        self.assertEqual(test_dict.get('percona'),
                         'trove.guestagent.datastore.mysql.'
                         'manager.Manager')
        self.assertEqual(test_dict.get('redis'),
                         'trove.guestagent.datastore.redis.'
                         'manager.Manager')
        self.assertEqual(test_dict.get('cassandra'),
                         'trove.guestagent.datastore.cassandra.'
                         'manager.Manager')
        self.assertEqual(test_dict.get('couchbase'),
                         'trove.guestagent.datastore.couchbase.manager'
                         '.Manager')
        self.assertEqual('trove.guestagent.datastore.mongodb.'
                         'manager.Manager',
                         test_dict.get('mongodb'))

    def test_datastore_registry_with_existing_manager(self):
        datastore_registry_ext_test = {
            'mysql': 'trove.guestagent.datastore.mysql.'
                     'manager.Manager123',
        }
        dbaas_sr.get_custom_managers = Mock(return_value=
                                            datastore_registry_ext_test)
        test_dict = dbaas_sr.datastore_registry()
        self.assertEqual(test_dict.get('mysql'),
                         'trove.guestagent.datastore.mysql.'
                         'manager.Manager123')
        self.assertEqual(test_dict.get('percona'),
                         'trove.guestagent.datastore.mysql.'
                         'manager.Manager')
        self.assertEqual(test_dict.get('redis'),
                         'trove.guestagent.datastore.redis.manager.Manager')
        self.assertEqual(test_dict.get('cassandra'),
                         'trove.guestagent.datastore.cassandra.'
                         'manager.Manager')
        self.assertEqual(test_dict.get('couchbase'),
                         'trove.guestagent.datastore.couchbase.manager'
                         '.Manager')
        self.assertEqual('trove.guestagent.datastore.mongodb.manager.Manager',
                         test_dict.get('mongodb'))

    def test_datastore_registry_with_blank_dict(self):
        datastore_registry_ext_test = dict()
        dbaas_sr.get_custom_managers = Mock(return_value=
                                            datastore_registry_ext_test)
        test_dict = dbaas_sr.datastore_registry()
        self.assertEqual(test_dict.get('mysql'),
                         'trove.guestagent.datastore.mysql.'
                         'manager.Manager')
        self.assertEqual(test_dict.get('percona'),
                         'trove.guestagent.datastore.mysql.'
                         'manager.Manager')
        self.assertEqual(test_dict.get('redis'),
                         'trove.guestagent.datastore.redis.manager.Manager')
        self.assertEqual(test_dict.get('cassandra'),
                         'trove.guestagent.datastore.cassandra.'
                         'manager.Manager')
        self.assertEqual(test_dict.get('couchbase'),
                         'trove.guestagent.datastore.couchbase.manager'
                         '.Manager')
        self.assertEqual('trove.guestagent.datastore.mongodb.manager.Manager',
                         test_dict.get('mongodb'))


class KeepAliveConnectionTest(testtools.TestCase):

    class OperationalError(Exception):
        def __init__(self, value):
            self.args = [value]

        def __str__(self):
            return repr(self.value)

    def setUp(self):
        super(KeepAliveConnectionTest, self).setUp()
        self.orig_utils_execute_with_timeout = dbaas.utils.execute_with_timeout
        self.orig_LOG_err = dbaas.LOG

    def tearDown(self):
        super(KeepAliveConnectionTest, self).tearDown()
        dbaas.utils.execute_with_timeout = self.orig_utils_execute_with_timeout
        dbaas.LOG = self.orig_LOG_err

    def test_checkout_type_error(self):

        dbapi_con = Mock()
        dbapi_con.ping = Mock(side_effect=TypeError("Type Error"))

        self.keepAliveConn = KeepAliveConnection()
        self.assertRaises(TypeError, self.keepAliveConn.checkout,
                          dbapi_con, Mock(), Mock())

    def test_checkout_disconnection_error(self):

        from sqlalchemy import exc
        dbapi_con = Mock()
        dbapi_con.OperationalError = self.OperationalError
        dbapi_con.ping = Mock(side_effect=dbapi_con.OperationalError(2013))

        self.keepAliveConn = KeepAliveConnection()
        self.assertRaises(exc.DisconnectionError, self.keepAliveConn.checkout,
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

    def tearDown(self):
        super(BaseDbStatusTest, self).tearDown()
        time.sleep = self.orig_dbaas_time_sleep
        InstanceServiceStatus.find_by(instance_id=self.FAKE_ID).delete()
        dbaas.CONF.guest_id = None

    def test_begin_install(self):

        self.baseDbStatus = BaseDbStatus()

        self.baseDbStatus.begin_install()

        self.assertEqual(self.baseDbStatus.status,
                         rd_instance.ServiceStatuses.BUILDING)

    def test_begin_restart(self):

        self.baseDbStatus = BaseDbStatus()
        self.baseDbStatus.restart_mode = False

        self.baseDbStatus.begin_restart()

        self.assertTrue(self.baseDbStatus.restart_mode)

    def test_end_install_or_restart(self):

        self.baseDbStatus = BaseDbStatus()
        self.baseDbStatus._get_actual_db_status = Mock(
            return_value=rd_instance.ServiceStatuses.SHUTDOWN)

        self.baseDbStatus.end_install_or_restart()

        self.assertEqual(rd_instance.ServiceStatuses.SHUTDOWN,
                         self.baseDbStatus.status)
        self.assertFalse(self.baseDbStatus.restart_mode)

    def test_is_installed(self):
        self.baseDbStatus = BaseDbStatus()
        self.baseDbStatus.status = rd_instance.ServiceStatuses.RUNNING

        self.assertTrue(self.baseDbStatus.is_installed)

    def test_is_installed_none(self):
        self.baseDbStatus = BaseDbStatus()
        self.baseDbStatus.status = None

        self.assertFalse(self.baseDbStatus.is_installed)

    def test_is_installed_building(self):
        self.baseDbStatus = BaseDbStatus()
        self.baseDbStatus.status = rd_instance.ServiceStatuses.BUILDING

        self.assertFalse(self.baseDbStatus.is_installed)

    def test_is_installed_new(self):
        self.baseDbStatus = BaseDbStatus()
        self.baseDbStatus.status = rd_instance.ServiceStatuses.NEW

        self.assertFalse(self.baseDbStatus.is_installed)

    def test_is_installed_failed(self):
        self.baseDbStatus = BaseDbStatus()
        self.baseDbStatus.status = rd_instance.ServiceStatuses.FAILED

        self.assertFalse(self.baseDbStatus.is_installed)

    def test_is_restarting(self):
        self.baseDbStatus = BaseDbStatus()
        self.baseDbStatus.restart_mode = True

        self.assertTrue(self.baseDbStatus._is_restarting)

    def test_is_running(self):
        self.baseDbStatus = BaseDbStatus()
        self.baseDbStatus.status = rd_instance.ServiceStatuses.RUNNING

        self.assertTrue(self.baseDbStatus.is_running)

    def test_is_running_not(self):
        self.baseDbStatus = BaseDbStatus()
        self.baseDbStatus.status = rd_instance.ServiceStatuses.SHUTDOWN

        self.assertFalse(self.baseDbStatus.is_running)

    def test_wait_for_real_status_to_change_to(self):
        self.baseDbStatus = BaseDbStatus()
        self.baseDbStatus._get_actual_db_status = Mock(
            return_value=rd_instance.ServiceStatuses.RUNNING)
        time.sleep = Mock()

        self.assertTrue(self.baseDbStatus.
                        wait_for_real_status_to_change_to
                        (rd_instance.ServiceStatuses.RUNNING, 10))

    def test_wait_for_real_status_to_change_to_timeout(self):
        self.baseDbStatus = BaseDbStatus()
        self.baseDbStatus._get_actual_db_status = Mock(
            return_value=rd_instance.ServiceStatuses.RUNNING)
        time.sleep = Mock()

        self.assertFalse(self.baseDbStatus.
                         wait_for_real_status_to_change_to
                         (rd_instance.ServiceStatuses.SHUTDOWN, 10))


class MySqlAppStatusTest(testtools.TestCase):

    def setUp(self):
        super(MySqlAppStatusTest, self).setUp()
        util.init_db()
        self.orig_utils_execute_with_timeout = dbaas.utils.execute_with_timeout
        self.orig_load_mysqld_options = dbaas.load_mysqld_options
        self.orig_dbaas_os_path_exists = dbaas.os.path.exists
        self.orig_dbaas_time_sleep = time.sleep
        self.FAKE_ID = str(uuid4())
        InstanceServiceStatus.create(instance_id=self.FAKE_ID,
                                     status=rd_instance.ServiceStatuses.NEW)
        dbaas.CONF.guest_id = self.FAKE_ID

    def tearDown(self):
        super(MySqlAppStatusTest, self).tearDown()
        dbaas.utils.execute_with_timeout = self.orig_utils_execute_with_timeout
        dbaas.load_mysqld_options = self.orig_load_mysqld_options
        dbaas.os.path.exists = self.orig_dbaas_os_path_exists
        time.sleep = self.orig_dbaas_time_sleep
        InstanceServiceStatus.find_by(instance_id=self.FAKE_ID).delete()
        dbaas.CONF.guest_id = None

    def test_get_actual_db_status(self):

        dbaas.utils.execute_with_timeout = Mock(return_value=(None, None))

        self.mySqlAppStatus = MySqlAppStatus()
        status = self.mySqlAppStatus._get_actual_db_status()

        self.assertEqual(rd_instance.ServiceStatuses.RUNNING, status)

    def test_get_actual_db_status_error_shutdown(self):

        mocked = Mock(side_effect=ProcessExecutionError())
        dbaas.utils.execute_with_timeout = mocked
        dbaas.load_mysqld_options = Mock()
        dbaas.os.path.exists = Mock(return_value=False)

        self.mySqlAppStatus = MySqlAppStatus()
        status = self.mySqlAppStatus._get_actual_db_status()

        self.assertEqual(rd_instance.ServiceStatuses.SHUTDOWN, status)

    def test_get_actual_db_status_error_crashed(self):

        dbaas.utils.execute_with_timeout = MagicMock(
            side_effect=[ProcessExecutionError(), ("some output", None)])
        dbaas.load_mysqld_options = Mock()
        dbaas.os.path.exists = Mock(return_value=True)

        self.mySqlAppStatus = MySqlAppStatus()
        status = self.mySqlAppStatus._get_actual_db_status()

        self.assertEqual(rd_instance.ServiceStatuses.BLOCKED, status)


class TestRedisApp(testtools.TestCase):

    def setUp(self):
        super(TestRedisApp, self).setUp()
        self.FAKE_ID = 1000
        self.appStatus = FakeAppStatus(self.FAKE_ID,
                                       rd_instance.ServiceStatuses.NEW)
        self.app = RedisApp(self.appStatus)
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
                self.assertEqual(RedisApp._install_redis.call_count, 0)

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
        app = RedisApp(mock_status, state_change_wait_time=0)
        RedisApp._disable_redis_on_boot = MagicMock(
            return_value=None)

        with patch.object(utils, 'execute_with_timeout', return_value=None):
            mock_status.wait_for_real_status_to_change_to = MagicMock(
                return_value=True)
            app.stop_db(do_not_start_on_reboot=True)

            utils.execute_with_timeout.assert_any_call(
                'sudo ' + RedisSystem.REDIS_CMD_STOP,
                shell=True)
            self.assertTrue(RedisApp._disable_redis_on_boot.called)
            self.assertTrue(
                mock_status.wait_for_real_status_to_change_to.called)

    def test_stop_db_with_failure(self):
        mock_status = MagicMock()
        mock_status.wait_for_real_status_to_change_to = MagicMock(
            return_value=True)
        app = RedisApp(mock_status, state_change_wait_time=0)
        RedisApp._disable_redis_on_boot = MagicMock(
            return_value=None)

        with patch.object(utils, 'execute_with_timeout', return_value=None):
            mock_status.wait_for_real_status_to_change_to = MagicMock(
                return_value=False)
            app.stop_db(do_not_start_on_reboot=True)

            utils.execute_with_timeout.assert_any_call(
                'sudo ' + RedisSystem.REDIS_CMD_STOP,
                shell=True)
            self.assertTrue(RedisApp._disable_redis_on_boot.called)
            self.assertTrue(mock_status.end_install_or_restart.called)
            self.assertTrue(
                mock_status.wait_for_real_status_to_change_to.called)

    def test_restart(self):
        mock_status = MagicMock()
        app = RedisApp(mock_status, state_change_wait_time=0)
        mock_status.begin_restart = MagicMock(return_value=None)
        with patch.object(RedisApp, 'stop_db', return_value=None):
            with patch.object(RedisApp, 'start_redis', return_value=None):
                mock_status.end_install_or_restart = MagicMock(
                    return_value=None)
                app.restart()
                mock_status.begin_restart.assert_any_call()
                RedisApp.stop_db.assert_any_call()
                RedisApp.start_redis.assert_any_call()
                mock_status.end_install_or_restart.assert_any_call()

    def test_start_redis(self):
        mock_status = MagicMock()
        app = RedisApp(mock_status, state_change_wait_time=0)
        with patch.object(RedisApp, '_enable_redis_on_boot',
                          return_value=None):
            with patch.object(utils, 'execute_with_timeout',
                              return_value=None):
                mock_status.wait_for_real_status_to_change_to = MagicMock(
                    return_value=None)
                mock_status.end_install_or_restart = MagicMock(
                    return_value=None)
                app.start_redis()

                utils.execute_with_timeout.assert_any_call(
                    'sudo ' + RedisSystem.REDIS_CMD_START,
                    shell=True)
                utils.execute_with_timeout.assert_any_call('pkill', '-9',
                                                           'redis-server',
                                                           run_as_root=True,
                                                           root_helper='sudo')
                self.assertTrue(RedisApp._enable_redis_on_boot.called)
                self.assertTrue(mock_status.end_install_or_restart.called)
                self.assertTrue(
                    mock_status.wait_for_real_status_to_change_to.callled)


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

        from trove.guestagent import pkg
        self.cassandra.start_db = Mock()
        self.cassandra.stop_db = Mock()
        self.pkg.pkg_is_installed = Mock(return_value=False)
        self.cassandra._install_db = Mock(
            side_effect=pkg.PkgPackageStateError("Install error"))

        self.assertRaises(pkg.PkgPackageStateError,
                          self.cassandra.install_if_needed,
                          ['cassandra=1.2.10'])

        self.assert_reported_status(rd_instance.ServiceStatuses.NEW)


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
        operating_system.service_discovery = (
            self.fake_couchbase_service_discovery)
        operating_system.get_ip_address = Mock()
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
        from trove.common.exception import ProcessExecutionError
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


class MongoDBAppTest(testtools.TestCase):

    def fake_mongodb_service_discovery(self, candidates):
        return {
            'cmd_start': 'start',
            'cmd_stop': 'stop',
            'cmd_enable': 'enable',
            'cmd_disable': 'disable'
        }

    def setUp(self):
        super(MongoDBAppTest, self).setUp()
        self.orig_utils_execute_with_timeout = (mongo_service.
                                                utils.execute_with_timeout)
        self.orig_time_sleep = time.sleep
        self.orig_packager = mongo_system.PACKAGER
        self.orig_service_discovery = operating_system.service_discovery

        operating_system.service_discovery = (
            self.fake_mongodb_service_discovery)
        util.init_db()
        self.FAKE_ID = str(uuid4())
        InstanceServiceStatus.create(instance_id=self.FAKE_ID,
                                     status=rd_instance.ServiceStatuses.NEW)
        self.appStatus = FakeAppStatus(self.FAKE_ID,
                                       rd_instance.ServiceStatuses.NEW)
        self.mongoDbApp = mongo_service.MongoDBApp(self.appStatus)
        time.sleep = Mock()

    def tearDown(self):
        super(MongoDBAppTest, self).tearDown()
        mongo_service.utils.execute_with_timeout = (
            self.orig_utils_execute_with_timeout)
        time.sleep = self.orig_time_sleep
        mongo_system.PACKAGER = self.orig_packager
        operating_system.service_discovery = self.orig_service_discovery
        InstanceServiceStatus.find_by(instance_id=self.FAKE_ID).delete()

    def assert_reported_status(self, expected_status):
        service_status = InstanceServiceStatus.find_by(
            instance_id=self.FAKE_ID)
        self.assertEqual(expected_status, service_status.status)

    def test_stopdb(self):
        mongo_service.utils.execute_with_timeout = Mock()
        self.appStatus.set_next_status(
            rd_instance.ServiceStatuses.SHUTDOWN)

        self.mongoDbApp.stop_db()
        self.assert_reported_status(rd_instance.ServiceStatuses.NEW)

    def test_stop_db_with_db_update(self):

        mongo_service.utils.execute_with_timeout = Mock()
        self.appStatus.set_next_status(
            rd_instance.ServiceStatuses.SHUTDOWN)

        self.mongoDbApp.stop_db(True)
        self.assertTrue(conductor_api.API.heartbeat.called_once_with(
            self.FAKE_ID, {'service_status': 'shutdown'}))

    def test_stop_db_error(self):

        mongo_service.utils.execute_with_timeout = Mock()
        self.appStatus.set_next_status(rd_instance.ServiceStatuses.RUNNING)
        self.mongoDbApp.state_change_wait_time = 1
        self.assertRaises(RuntimeError, self.mongoDbApp.stop_db)

    def test_restart(self):

        self.appStatus.set_next_status(rd_instance.ServiceStatuses.RUNNING)
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
        self.appStatus.set_next_status(rd_instance.ServiceStatuses.RUNNING)

        self.mongoDbApp.start_db()
        self.assert_reported_status(rd_instance.ServiceStatuses.NEW)

    def test_start_db_with_update(self):

        mongo_service.utils.execute_with_timeout = Mock()
        self.appStatus.set_next_status(rd_instance.ServiceStatuses.RUNNING)

        self.mongoDbApp.start_db(True)
        self.assertTrue(conductor_api.API.heartbeat.called_once_with(
            self.FAKE_ID, {'service_status': 'running'}))

    def test_start_db_runs_forever(self):

        mongo_service.utils.execute_with_timeout = Mock(
            return_value=["ubuntu 17036  0.0  0.1 618960 "
                          "29232 pts/8    Sl+  Jan29   0:07 mongod", ""])
        self.mongoDbApp.state_change_wait_time = 1
        self.appStatus.set_next_status(rd_instance.ServiceStatuses.SHUTDOWN)

        self.assertRaises(RuntimeError, self.mongoDbApp.start_db)
        self.assertTrue(conductor_api.API.heartbeat.called_once_with(
            self.FAKE_ID, {'service_status': 'shutdown'}))

    def test_start_db_error(self):

        self.mongoDbApp._enable_db_on_boot = Mock()
        from trove.common.exception import ProcessExecutionError
        mocked = Mock(side_effect=ProcessExecutionError('Error'))
        mongo_service.utils.execute_with_timeout = mocked

        self.assertRaises(RuntimeError, self.mongoDbApp.start_db)

    def test_start_db_with_conf_changes_db_is_running(self):

        self.mongoDbApp.start_db = Mock()

        self.appStatus.status = rd_instance.ServiceStatuses.RUNNING
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
