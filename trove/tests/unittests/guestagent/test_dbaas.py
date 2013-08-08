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
from random import randint
import time

from mock import Mock
from mock import MagicMock
from mockito import mock
from mockito import when
from mockito import any
from mockito import unstub
from mockito import verify
from mockito import contains
from mockito import never
from mockito import matchers
from mockito import inorder, verifyNoMoreInteractions
from trove.extensions.mysql.models import RootHistory
import sqlalchemy
import testtools
from testtools.matchers import Is
from testtools.matchers import Equals
from testtools.matchers import Not
import trove
from trove.common.context import TroveContext
from trove.common import utils
import trove.guestagent.manager.mysql_service as dbaas
from trove.guestagent.dbaas import to_gb
from trove.guestagent.dbaas import get_filesystem_volume_stats
from trove.guestagent.manager.mysql_service import MySqlAdmin
from trove.guestagent.manager.mysql_service import MySqlRootAccess
from trove.guestagent.manager.mysql_service import MySqlApp
from trove.guestagent.manager.mysql_service import MySqlAppStatus
from trove.guestagent.manager.mysql_service import KeepAliveConnection
from trove.guestagent.db import models
from trove.instance.models import ServiceStatuses
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
MYCNF = '/etc/mysql/my.cnf'


class FakeAppStatus(MySqlAppStatus):

    def __init__(self, id, status):
        self.id = id
        self.next_fake_status = status

    def _get_actual_db_status(self):
        return self.next_fake_status

    def _load_status(self):
        return InstanceServiceStatus.find_by(instance_id=self.id)

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

        dbaas.utils.execute_with_timeout = \
            Mock(return_value=("password    ", None))

        password = dbaas.get_auth_password()

        self.assertEqual("password", password)

    def test_get_auth_password_error(self):

        dbaas.utils.execute_with_timeout = \
            Mock(return_value=("password", "Error"))

        self.assertRaises(RuntimeError, dbaas.get_auth_password)

    def test_load_mysqld_options(self):

        output = "mysqld would've been started with the these args:\n"\
                 "--user=mysql --port=3306 --basedir=/usr "\
                 "--tmpdir=/tmp --skip-external-locking"
        dbaas.utils.execute = Mock(return_value=(output, None))

        options = dbaas.load_mysqld_options()

        self.assertEqual(5, len(options))
        self.assertEqual(options["user"], "mysql")
        self.assertEqual(options["port"], "3306")
        self.assertEqual(options["basedir"], "/usr")
        self.assertEqual(options["tmpdir"], "/tmp")
        self.assertTrue("skip-external-locking" in options)

    def test_load_mysqld_options_error(self):

        from trove.common.exception import ProcessExecutionError
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
        unstub()

    def test_list_databases(self):
        mock_conn = mock_admin_sql_connection()

        when(mock_conn).execute(
            TextClauseMatcher('schema_name as name')).thenReturn(
                ResultSetStub([('db1', 'utf8', 'utf8_bin'),
                               ('db2', 'utf8', 'utf8_bin'),
                               ('db3', 'utf8', 'utf8_bin')]))

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
        self.orig_MySQLUser_is_valid_user_name = \
            models.MySQLUser._is_valid_user_name
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
        models.MySQLUser._is_valid_user_name = \
            self.orig_MySQLUser_is_valid_user_name

    def test_create_database(self):

        databases = []
        databases.append(FAKE_DB)

        self.mySqlAdmin.create_database(databases)

        args, _ = dbaas.LocalSqlClient.execute.call_args_list[0]
        expected = ("CREATE DATABASE IF NOT EXISTS "
                    "`testDB` CHARACTER SET = 'latin2' "
                    "COLLATE = 'latin2_general_ci';")
        self.assertEquals(args[0].text, expected,
                          "Create database queries are not the same")

        self.assertEqual(1, dbaas.LocalSqlClient.execute.call_count,
                         "The client object was not 2 times")

    def test_create_database_more_than_1(self):

        databases = []
        databases.append(FAKE_DB)
        databases.append(FAKE_DB_2)

        self.mySqlAdmin.create_database(databases)

        args, _ = dbaas.LocalSqlClient.execute.call_args_list[0]
        expected = ("CREATE DATABASE IF NOT EXISTS "
                    "`testDB` CHARACTER SET = 'latin2' "
                    "COLLATE = 'latin2_general_ci';")
        self.assertEquals(args[0].text, expected,
                          "Create database queries are not the same")

        args, _ = dbaas.LocalSqlClient.execute.call_args_list[1]
        expected = ("CREATE DATABASE IF NOT EXISTS "
                    "`testDB2` CHARACTER SET = 'latin2' "
                    "COLLATE = 'latin2_general_ci';")
        self.assertEquals(args[0].text, expected,
                          "Create database queries are not the same")

        self.assertEqual(2, dbaas.LocalSqlClient.execute.call_count,
                         "The client object was not 2 times")

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
        self.assertEquals(args[0].text, expected,
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
            self.assertEquals(args[0].text, expected,
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
            self.assertEquals(args[0].text.strip(), expected,
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


class MySqlAppTest(testtools.TestCase):

    def setUp(self):
        super(MySqlAppTest, self).setUp()
        self.orig_utils_execute_with_timeout = dbaas.utils.execute_with_timeout
        self.orig_time_sleep = time.sleep
        util.init_db()
        self.FAKE_ID = randint(1, 10000)
        InstanceServiceStatus.create(instance_id=self.FAKE_ID,
                                     status=ServiceStatuses.NEW)
        self.appStatus = FakeAppStatus(self.FAKE_ID, ServiceStatuses.NEW)
        self.mySqlApp = MySqlApp(self.appStatus)
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
            self.appStatus.set_next_status(ServiceStatuses.RUNNING)

        self.mySqlApp.start_mysql.side_effect = start

    def mysql_starts_unsuccessfully(self):
        def start():
            raise RuntimeError("MySQL failed to start!")

        self.mySqlApp.start_mysql.side_effect = start

    def mysql_stops_successfully(self):
        def stop():
            self.appStatus.set_next_status(ServiceStatuses.SHUTDOWN)

        self.mySqlApp.stop_db.side_effect = stop

    def mysql_stops_unsuccessfully(self):
        def stop():
            raise RuntimeError("MySQL failed to stop!")

        self.mySqlApp.stop_db.side_effect = stop

    def test_stop_mysql(self):

        dbaas.utils.execute_with_timeout = Mock()
        self.appStatus.set_next_status(ServiceStatuses.SHUTDOWN)

        self.mySqlApp.stop_db()
        self.assert_reported_status(ServiceStatuses.NEW)

    def test_stop_mysql_with_db_update(self):

        dbaas.utils.execute_with_timeout = Mock()
        self.appStatus.set_next_status(ServiceStatuses.SHUTDOWN)

        self.mySqlApp.stop_db(True)
        self.assert_reported_status(ServiceStatuses.SHUTDOWN)

    def test_stop_mysql_error(self):

        dbaas.utils.execute_with_timeout = Mock()
        self.appStatus.set_next_status(ServiceStatuses.RUNNING)
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
        self.assert_reported_status(ServiceStatuses.RUNNING)

    def test_restart_mysql_wont_start_up(self):

        self.mySqlApp.start_mysql = Mock()
        self.mySqlApp.stop_db = Mock()
        self.mysql_stops_unsuccessfully()
        self.mysql_starts_unsuccessfully()

        self.assertRaises(RuntimeError, self.mySqlApp.restart)

        self.assertTrue(self.mySqlApp.stop_db.called)
        self.assertFalse(self.mySqlApp.start_mysql.called)
        self.assert_reported_status(ServiceStatuses.NEW)

    def test_wipe_ib_logfiles_no_file(self):

        from trove.common.exception import ProcessExecutionError
        processexecerror = ProcessExecutionError('No such file or directory')
        dbaas.utils.execute_with_timeout = Mock(side_effect=processexecerror)

        self.mySqlApp.wipe_ib_logfiles()

    def test_wipe_ib_logfiles_error(self):

        from trove.common.exception import ProcessExecutionError
        mocked = Mock(side_effect=ProcessExecutionError('Error'))
        dbaas.utils.execute_with_timeout = mocked

        self.assertRaises(ProcessExecutionError,
                          self.mySqlApp.wipe_ib_logfiles)

    def test_start_mysql(self):

        dbaas.utils.execute_with_timeout = Mock()
        self.appStatus.set_next_status(ServiceStatuses.RUNNING)

        self.mySqlApp.start_mysql()
        self.assert_reported_status(ServiceStatuses.NEW)

    def test_start_mysql_with_db_update(self):

        dbaas.utils.execute_with_timeout = Mock()
        self.appStatus.set_next_status(ServiceStatuses.RUNNING)

        self.mySqlApp.start_mysql(True)
        self.assert_reported_status(ServiceStatuses.RUNNING)

    def test_start_mysql_runs_forever(self):

        dbaas.utils.execute_with_timeout = Mock()
        self.mySqlApp.state_change_wait_time = 1
        self.appStatus.set_next_status(ServiceStatuses.SHUTDOWN)

        self.assertRaises(RuntimeError, self.mySqlApp.start_mysql)
        self.assert_reported_status(ServiceStatuses.SHUTDOWN)

    def test_start_mysql_error(self):

        self.mySqlApp._enable_mysql_on_boot = Mock()
        from trove.common.exception import ProcessExecutionError
        mocked = Mock(side_effect=ProcessExecutionError('Error'))
        dbaas.utils.execute_with_timeout = mocked

        self.assertRaises(RuntimeError, self.mySqlApp.start_mysql)

    def test_start_db_with_conf_changes(self):

        self.mySqlApp.start_mysql = Mock()
        self.mySqlApp._write_mycnf = Mock()
        self.mysql_starts_successfully()

        self.appStatus.status = ServiceStatuses.SHUTDOWN
        self.mySqlApp.start_db_with_conf_changes(Mock(), Mock())

        self.assertTrue(self.mySqlApp._write_mycnf.called)
        self.assertTrue(self.mySqlApp.start_mysql.called)
        self.assertEqual(self.appStatus._get_actual_db_status(),
                         ServiceStatuses.RUNNING)

    def test_start_db_with_conf_changes_mysql_is_running(self):

        self.mySqlApp.start_mysql = Mock()
        self.mySqlApp._write_mycnf = Mock()

        self.appStatus.status = ServiceStatuses.RUNNING
        self.assertRaises(RuntimeError,
                          self.mySqlApp.start_db_with_conf_changes,
                          Mock(), Mock())


class MySqlAppInstallTest(MySqlAppTest):

    def setUp(self):
        super(MySqlAppInstallTest, self).setUp()
        self.orig_create_engine = sqlalchemy.create_engine
        self.orig_pkg_version = dbaas.packager.pkg_version

    def tearDown(self):
        super(MySqlAppInstallTest, self).tearDown()
        sqlalchemy.create_engine = self.orig_create_engine
        dbaas.packager.pkg_version = self.orig_pkg_version

    def test_install(self):

        self.mySqlApp._install_mysql = Mock()
        self.mySqlApp.is_installed = Mock(return_value=False)
        self.mySqlApp.install_if_needed()
        self.assertTrue(self.mySqlApp._install_mysql.called)
        self.assert_reported_status(ServiceStatuses.NEW)

    def test_secure(self):

        self.mySqlApp.start_mysql = Mock()
        self.mySqlApp.stop_db = Mock()
        self.mySqlApp._write_mycnf = Mock()
        self.mysql_stops_successfully()
        self.mysql_starts_successfully()
        sqlalchemy.create_engine = Mock()

        self.mySqlApp.secure(MYCNF, 'contents')

        self.assertTrue(self.mySqlApp.stop_db.called)
        self.assertTrue(self.mySqlApp._write_mycnf.called)
        self.assertTrue(self.mySqlApp.start_mysql.called)
        self.assert_reported_status(ServiceStatuses.NEW)

    def test_install_install_error(self):

        from trove.guestagent import pkg
        self.mySqlApp.start_mysql = Mock()
        self.mySqlApp.stop_db = Mock()
        self.mySqlApp.is_installed = Mock(return_value=False)
        self.mySqlApp._install_mysql = \
            Mock(side_effect=pkg.PkgPackageStateError("Install error"))

        self.assertRaises(pkg.PkgPackageStateError,
                          self.mySqlApp.install_if_needed)

        self.assert_reported_status(ServiceStatuses.NEW)

    def test_secure_write_conf_error(self):

        from trove.guestagent import pkg
        self.mySqlApp.start_mysql = Mock()
        self.mySqlApp.stop_db = Mock()
        self.mySqlApp._write_mycnf = \
            Mock(side_effect=IOError("Could not write file"))
        self.mysql_stops_successfully()
        self.mysql_starts_successfully()
        sqlalchemy.create_engine = Mock()

        self.assertRaises(IOError,
                          self.mySqlApp.secure, "/etc/mycnf/my.cnf", "foo")

        self.assertTrue(self.mySqlApp.stop_db.called)
        self.assertTrue(self.mySqlApp._write_mycnf.called)
        self.assertFalse(self.mySqlApp.start_mysql.called)
        self.assert_reported_status(ServiceStatuses.NEW)

    def test_is_installed(self):

        dbaas.packager.pkg_version = Mock(return_value=True)

        self.assertTrue(self.mySqlApp.is_installed())

    def test_is_installed_not(self):

        dbaas.packager.pkg_version = Mock(return_value=None)

        self.assertFalse(self.mySqlApp.is_installed())


class TextClauseMatcher(matchers.Matcher):
    def __init__(self, text):
        self.contains = contains(text)

    def __repr__(self):
        return "TextClause(%s)" % self.contains.sub

    def matches(self, arg):
        print("Matching %s" % arg.text)
        return self.contains.matches(arg.text)


def mock_sql_connection():
    mock_engine = mock()
    when(sqlalchemy).create_engine("mysql://root:@localhost:3306",
                                   echo=True).thenReturn(mock_engine)
    mock_conn = mock()
    when(dbaas.LocalSqlClient).__enter__().thenReturn(mock_conn)
    when(dbaas.LocalSqlClient).__exit__(any(), any(), any()).thenReturn(None)
    return mock_conn


def mock_admin_sql_connection():
    when(utils).execute_with_timeout("sudo", "awk", any(), any()).thenReturn(
        ['fake_password', None])
    mock_engine = mock()
    when(sqlalchemy).create_engine("mysql://root:@localhost:3306",
                                   pool_recycle=any(), echo=True,
                                   listeners=[any()]).thenReturn(mock_engine)
    mock_conn = mock()
    when(dbaas.LocalSqlClient).__enter__().thenReturn(mock_conn)
    when(dbaas.LocalSqlClient).__exit__(any(), any(), any()).thenReturn(None)
    return mock_conn


class MySqlAppMockTest(testtools.TestCase):

    def tearDown(self):
        super(MySqlAppMockTest, self).tearDown()
        unstub()

    def test_secure_with_mycnf_error(self):
        mock_conn = mock_sql_connection()
        when(mock_conn).execute(any()).thenReturn(None)
        when(utils).execute_with_timeout("sudo", any(str), "stop").thenReturn(
            None)
        # skip writing the file for now
        when(os.path).isfile(any()).thenReturn(False)
        mock_status = mock(MySqlAppStatus)
        when(mock_status).wait_for_real_status_to_change_to(
            any(), any(), any()).thenReturn(True)
        app = MySqlApp(mock_status)

        self.assertRaises(TypeError, app.secure, MYCNF, None)

        verify(mock_conn, atleast=2).execute(any())
        inorder.verify(mock_status).wait_for_real_status_to_change_to(
            ServiceStatuses.SHUTDOWN, any(), any())
        verifyNoMoreInteractions(mock_status)

    def test_secure_keep_root(self):
        mock_conn = mock_sql_connection()

        when(mock_conn).execute(any()).thenReturn(None)
        when(utils).execute_with_timeout("sudo", any(str), "stop").thenReturn(
            None)
        # skip writing the file for now
        when(os.path).isfile(any()).thenReturn(False)
        when(utils).execute_with_timeout(
            "sudo", "chmod", any(), any()).thenReturn(None)
        mock_status = mock(MySqlAppStatus)
        when(mock_status).wait_for_real_status_to_change_to(
            any(), any(), any()).thenReturn(True)
        app = MySqlApp(mock_status)
        when(app)._write_mycnf(any(), any()).thenReturn(True)
        app.secure(MYCNF, 'foo')
        verify(mock_conn, never).execute(TextClauseMatcher('root'))


class MySqlRootStatusTest(testtools.TestCase):

    def tearDown(self):
        super(MySqlRootStatusTest, self).tearDown()
        unstub()

    def test_root_is_enabled(self):
        mock_conn = mock_admin_sql_connection()

        mock_rs = mock()
        mock_rs.rowcount = 1
        when(mock_conn).execute(
            TextClauseMatcher(
                "User = 'root' AND Host != 'localhost'")).thenReturn(mock_rs)

        self.assertThat(MySqlRootAccess().is_root_enabled(), Is(True))

    def test_root_is_not_enabled(self):
        mock_conn = mock_admin_sql_connection()

        mock_rs = mock()
        mock_rs.rowcount = 0
        when(mock_conn).execute(
            TextClauseMatcher(
                "User = 'root' AND Host != 'localhost'")).thenReturn(mock_rs)

        self.assertThat(MySqlRootAccess.is_root_enabled(), Equals(False))

    def test_enable_root(self):
        mock_conn = mock_admin_sql_connection()
        when(mock_conn).execute(any()).thenReturn(None)
        # invocation
        user_ser = MySqlRootAccess.enable_root()
        # verification
        self.assertThat(user_ser, Not(Is(None)))
        verify(mock_conn).execute(TextClauseMatcher('CREATE USER'),
                                  user='root', host='%')
        verify(mock_conn).execute(TextClauseMatcher(
            'GRANT ALL PRIVILEGES ON *.*'))
        verify(mock_conn).execute(TextClauseMatcher('UPDATE mysql.user'))

    def test_enable_root_failed(self):
        when(models.MySQLUser)._is_valid_user_name(any()).thenReturn(False)
        self.assertRaises(ValueError, MySqlAdmin().enable_root)

    def test_report_root_enabled(self):
        mock_db_api = mock()
        when(trove.extensions.mysql.models).get_db_api().thenReturn(
            mock_db_api)
        when(mock_db_api).find_by(any(), id=None).thenReturn(None)
        root_history = RootHistory('x', 'root')
        when(mock_db_api).save(any(RootHistory)).thenReturn(root_history)
        # invocation
        history = MySqlRootAccess.report_root_enabled(TroveContext())
        # verification
        self.assertThat(history, Is(root_history))
        verify(mock_db_api).save(any(RootHistory))


class MockStats:
    f_blocks = 1024 ** 2
    f_bsize = 4096
    f_bfree = 512 * 1024


class InterrogatorTest(testtools.TestCase):

    def tearDown(self):
        super(InterrogatorTest, self).tearDown()
        unstub()

    def test_to_gb(self):
        result = to_gb(123456789)
        self.assertEqual(result, 0.11)

    def test_to_gb_zero(self):
        result = to_gb(0)
        self.assertEqual(result, 0.0)

    def test_get_filesystem_volume_stats(self):
        when(os).statvfs(any()).thenReturn(MockStats)
        result = get_filesystem_volume_stats('/some/path/')

        self.assertEqual(result['block_size'], 4096)
        self.assertEqual(result['total_blocks'], 1048576)
        self.assertEqual(result['free_blocks'], 524288)
        self.assertEqual(result['total'], 4294967296)
        self.assertEqual(result['free'], 2147483648)
        self.assertEqual(result['used'], 2.0)

    def test_get_filesystem_volume_stats_error(self):
        when(os).statvfs(any()).thenRaise(OSError)
        self.assertRaises(
            RuntimeError,
            get_filesystem_volume_stats, '/nonexistent/path')


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


class MySqlAppStatusTest(testtools.TestCase):

    def setUp(self):
        super(MySqlAppStatusTest, self).setUp()
        util.init_db()
        self.orig_utils_execute_with_timeout = dbaas.utils.execute_with_timeout
        self.orig_load_mysqld_options = dbaas.load_mysqld_options
        self.orig_dbaas_os_path_exists = dbaas.os.path.exists
        self.orig_dbaas_time_sleep = dbaas.time.sleep
        self.FAKE_ID = randint(1, 10000)
        InstanceServiceStatus.create(instance_id=self.FAKE_ID,
                                     status=ServiceStatuses.NEW)
        dbaas.CONF.guest_id = self.FAKE_ID

    def tearDown(self):
        super(MySqlAppStatusTest, self).tearDown()
        dbaas.utils.execute_with_timeout = self.orig_utils_execute_with_timeout
        dbaas.load_mysqld_options = self.orig_load_mysqld_options
        dbaas.os.path.exists = self.orig_dbaas_os_path_exists
        dbaas.time.sleep = self.orig_dbaas_time_sleep
        InstanceServiceStatus.find_by(instance_id=self.FAKE_ID).delete()
        dbaas.CONF.guest_id = None

    def test_being_mysql_install(self):

        self.mySqlAppStatus = MySqlAppStatus()

        self.mySqlAppStatus.begin_mysql_install()

        self.assertEquals(self.mySqlAppStatus.status, ServiceStatuses.BUILDING)

    def test_begin_mysql_restart(self):

        self.mySqlAppStatus = MySqlAppStatus()
        self.mySqlAppStatus.restart_mode = False

        self.mySqlAppStatus.begin_mysql_restart()

        self.assertTrue(self.mySqlAppStatus.restart_mode)

    def test_end_install_or_restart(self):

        self.mySqlAppStatus = MySqlAppStatus()
        self.mySqlAppStatus._get_actual_db_status = \
            Mock(return_value=ServiceStatuses.SHUTDOWN)

        self.mySqlAppStatus.end_install_or_restart()

        self.assertEqual(ServiceStatuses.SHUTDOWN, self.mySqlAppStatus.status)
        self.assertFalse(self.mySqlAppStatus.restart_mode)

    def test_get_actual_db_status(self):

        dbaas.utils.execute_with_timeout = Mock(return_value=(None, None))

        self.mySqlAppStatus = MySqlAppStatus()
        status = self.mySqlAppStatus._get_actual_db_status()

        self.assertEqual(ServiceStatuses.RUNNING, status)

    def test_get_actual_db_status_error_shutdown(self):

        from trove.common.exception import ProcessExecutionError
        mocked = Mock(side_effect=ProcessExecutionError())
        dbaas.utils.execute_with_timeout = mocked
        dbaas.load_mysqld_options = Mock()
        dbaas.os.path.exists = Mock(return_value=False)

        self.mySqlAppStatus = MySqlAppStatus()
        status = self.mySqlAppStatus._get_actual_db_status()

        self.assertEqual(ServiceStatuses.SHUTDOWN, status)

    def test_get_actual_db_status_error_crashed(self):

        from trove.common.exception import ProcessExecutionError
        dbaas.utils.execute_with_timeout = \
            MagicMock(side_effect=[ProcessExecutionError(),
                                   ("some output", None)])
        dbaas.load_mysqld_options = Mock()
        dbaas.os.path.exists = Mock(return_value=True)

        self.mySqlAppStatus = MySqlAppStatus()
        status = self.mySqlAppStatus._get_actual_db_status()

        self.assertEqual(ServiceStatuses.BLOCKED, status)

    def test_is_mysql_installed(self):
        self.mySqlAppStatus = MySqlAppStatus()
        self.mySqlAppStatus.status = ServiceStatuses.RUNNING

        self.assertTrue(self.mySqlAppStatus.is_mysql_installed)

    def test_is_mysql_installed_none(self):
        self.mySqlAppStatus = MySqlAppStatus()
        self.mySqlAppStatus.status = None

        self.assertFalse(self.mySqlAppStatus.is_mysql_installed)

    def test_is_mysql_installed_building(self):
        self.mySqlAppStatus = MySqlAppStatus()
        self.mySqlAppStatus.status = ServiceStatuses.BUILDING

        self.assertFalse(self.mySqlAppStatus.is_mysql_installed)

    def test_is_mysql_installed_new(self):
        self.mySqlAppStatus = MySqlAppStatus()
        self.mySqlAppStatus.status = ServiceStatuses.NEW

        self.assertFalse(self.mySqlAppStatus.is_mysql_installed)

    def test_is_mysql_installed_failed(self):
        self.mySqlAppStatus = MySqlAppStatus()
        self.mySqlAppStatus.status = ServiceStatuses.FAILED

        self.assertFalse(self.mySqlAppStatus.is_mysql_installed)

    def test_is_mysql_restarting(self):
        self.mySqlAppStatus = MySqlAppStatus()
        self.mySqlAppStatus.restart_mode = True

        self.assertTrue(self.mySqlAppStatus._is_mysql_restarting)

    def test_is_mysql_running(self):
        self.mySqlAppStatus = MySqlAppStatus()
        self.mySqlAppStatus.status = ServiceStatuses.RUNNING

        self.assertTrue(self.mySqlAppStatus.is_mysql_running)

    def test_is_mysql_running_not(self):
        self.mySqlAppStatus = MySqlAppStatus()
        self.mySqlAppStatus.status = ServiceStatuses.SHUTDOWN

        self.assertFalse(self.mySqlAppStatus.is_mysql_running)

    def test_wait_for_real_status_to_change_to(self):
        self.mySqlAppStatus = MySqlAppStatus()
        self.mySqlAppStatus._get_actual_db_status = \
            Mock(return_value=ServiceStatuses.RUNNING)
        dbaas.time.sleep = Mock()

        self.assertTrue(self.mySqlAppStatus.
                        wait_for_real_status_to_change_to
                        (ServiceStatuses.RUNNING, 10))

    def test_wait_for_real_status_to_change_to_timeout(self):
        self.mySqlAppStatus = MySqlAppStatus()
        self.mySqlAppStatus._get_actual_db_status = \
            Mock(return_value=ServiceStatuses.RUNNING)
        dbaas.time.sleep = Mock()

        self.assertFalse(self.mySqlAppStatus.
                         wait_for_real_status_to_change_to
                         (ServiceStatuses.SHUTDOWN, 10))
