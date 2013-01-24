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
import testtools
from random import randint
import time
import reddwarf.guestagent.dbaas as dbaas
from reddwarf.guestagent.db import models
from reddwarf.guestagent.dbaas import MySqlAdmin
from reddwarf.guestagent.dbaas import MySqlApp
from reddwarf.guestagent.dbaas import MySqlAppStatus
from reddwarf.guestagent.dbaas import Interrogator
from reddwarf.guestagent.dbaas import KeepAliveConnection
from reddwarf.instance.models import ServiceStatuses
from reddwarf.instance.models import InstanceServiceStatus
from reddwarf.tests.unittests.util import util

"""
Unit tests for the classes and functions in dbaas.py.
"""

FAKE_DB = {"_name": "testDB", "_character_set": "latin2",
           "_collate": "latin2_general_ci"}
FAKE_DB_2 = {"_name": "testDB2", "_character_set": "latin2",
             "_collate": "latin2_general_ci"}
FAKE_USER = [{"_name": "random", "_password": "guesswhat",
              "_databases": [FAKE_DB]}]


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

        from reddwarf.common.exception import ProcessExecutionError
        dbaas.utils.execute = Mock(side_effect=ProcessExecutionError())

        self.assertFalse(dbaas.load_mysqld_options())


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

        args, _ = dbaas.LocalSqlClient.execute.call_args
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
        args, _ = dbaas.LocalSqlClient.execute.call_args
        self.assertEquals(args[0].text.strip(), expected,
                          "Create user queries are not the same")
        self.assertEqual(2, dbaas.LocalSqlClient.execute.call_count)


class EnableRootTest(MySqlAdminTest):
    def setUp(self):
        super(EnableRootTest, self).setUp()
        self.origin_is_valid_user_name = models.MySQLUser._is_valid_user_name
        self.mySqlAdmin = MySqlAdmin()

    def tearDown(self):
        super(EnableRootTest, self).tearDown()
        models.MySQLUser._is_valid_user_name = self.origin_is_valid_user_name

    def test_enable_root(self):
        models.MySQLUser._is_valid_user_name =\
            MagicMock(return_value=True)
        self.mySqlAdmin.enable_root()
        args_list = dbaas.LocalSqlClient.execute.call_args_list
        args, keyArgs = args_list[0]

        self.assertEquals(args[0].text.strip(), "CREATE USER :user@:host;",
                          "Create user queries are not the same")
        self.assertEquals(keyArgs['user'], 'root')
        self.assertEquals(keyArgs['host'], '%')

        args, keyArgs = args_list[1]
        self.assertTrue("UPDATE mysql.user" in args[0].text)
        args, keyArgs = args_list[2]
        self.assertTrue("GRANT ALL PRIVILEGES ON *.*" in args[0].text)

        self.assertEqual(3, dbaas.LocalSqlClient.execute.call_count)

    def test_enable_root_failed(self):
        models.MySQLUser._is_valid_user_name =\
            MagicMock(return_value=False)
        self.assertRaises(ValueError, self.mySqlAdmin.enable_root)

    def test_is_root_enable(self):
        self.mySqlAdmin.is_root_enabled()
        args, _ = dbaas.LocalSqlClient.execute.call_args
        expected = ("""SELECT User FROM mysql.user WHERE User = 'root' """
                    """AND host != 'localhost';""")
        self.assertTrue(expected in args[0].text,
                        "%s not in query." % expected)

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

        self.assertTrue("AND schema_name >= '" + marker + "'" in args[0].text)

    def test_list_users(self):
        self.mySqlAdmin.list_users()
        args, _ = dbaas.LocalSqlClient.execute.call_args

        expected = ["SELECT User",
                    "FROM mysql.user",
                    "WHERE host != 'localhost'",
                    "ORDER BY User",
                    ]
        for text in expected:
            self.assertTrue(text in args[0].text, "%s not in query." % text)

        self.assertFalse("LIMIT " in args[0].text)
        self.assertFalse("AND User > '" in args[0].text)

    def test_list_users_with_limit(self):
        limit = 2
        self.mySqlAdmin.list_users(limit)
        args, _ = dbaas.LocalSqlClient.execute.call_args

        expected = ["SELECT User",
                    "FROM mysql.user",
                    "WHERE host != 'localhost'",
                    "ORDER BY User",
                    ("LIMIT " + str(limit + 1)),
                    ]
        for text in expected:
            self.assertTrue(text in args[0].text, "%s not in query." % text)

    def test_list_users_with_marker(self):
        marker = "aMarker"
        self.mySqlAdmin.list_users(marker=marker)
        args, _ = dbaas.LocalSqlClient.execute.call_args

        expected = ["SELECT User",
                    "FROM mysql.user",
                    "WHERE host != 'localhost'",
                    "ORDER BY User",
                    ]

        for text in expected:
            self.assertTrue(text in args[0].text, "%s not in query." % text)

        self.assertFalse("LIMIT " in args[0].text)
        self.assertTrue("AND User > '" + marker + "'" in args[0].text)

    def test_list_users_with_include_marker(self):
        marker = "aMarker"
        self.mySqlAdmin.list_users(marker=marker, include_marker=True)
        args, _ = dbaas.LocalSqlClient.execute.call_args

        expected = ["SELECT User",
                    "FROM mysql.user",
                    "WHERE host != 'localhost'",
                    "ORDER BY User",
                    ]

        for text in expected:
            self.assertTrue(text in args[0].text, "%s not in query." % text)

        self.assertFalse("LIMIT " in args[0].text)

        self.assertTrue("AND User >= '" + marker + "'" in args[0].text)


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

        self.mySqlApp.stop_mysql.side_effect = stop

    def mysql_stops_unsuccessfully(self):
        def stop():
            raise RuntimeError("MySQL failed to stop!")

        self.mySqlApp.stop_mysql.side_effect = stop

    def test_stop_mysql(self):

        dbaas.utils.execute_with_timeout = Mock()
        self.appStatus.set_next_status(ServiceStatuses.SHUTDOWN)

        self.mySqlApp.stop_mysql()
        self.assert_reported_status(ServiceStatuses.NEW)

    def test_stop_mysql_with_db_update(self):

        dbaas.utils.execute_with_timeout = Mock()
        self.appStatus.set_next_status(ServiceStatuses.SHUTDOWN)

        self.mySqlApp.stop_mysql(True)
        self.assert_reported_status(ServiceStatuses.SHUTDOWN)

    def test_stop_mysql_error(self):

        dbaas.utils.execute_with_timeout = Mock()
        self.appStatus.set_next_status(ServiceStatuses.RUNNING)
        self.mySqlApp.state_change_wait_time = 1
        self.assertRaises(RuntimeError, self.mySqlApp.stop_mysql)

    def test_restart_is_successful(self):

        self.mySqlApp.start_mysql = Mock()
        self.mySqlApp.stop_mysql = Mock()
        self.mysql_stops_successfully()
        self.mysql_starts_successfully()

        self.mySqlApp.restart()

        self.assertTrue(self.mySqlApp.stop_mysql.called)
        self.assertTrue(self.mySqlApp.start_mysql.called)
        self.assert_reported_status(ServiceStatuses.RUNNING)

    def test_restart_mysql_wont_start_up(self):

        self.mySqlApp.start_mysql = Mock()
        self.mySqlApp.stop_mysql = Mock()
        self.mysql_stops_unsuccessfully()
        self.mysql_starts_unsuccessfully()

        self.assertRaises(RuntimeError, self.mySqlApp.restart)

        self.assertTrue(self.mySqlApp.stop_mysql.called)
        self.assertFalse(self.mySqlApp.start_mysql.called)
        self.assert_reported_status(ServiceStatuses.NEW)

    def test_wipe_ib_logfiles_no_file(self):

        from reddwarf.common.exception import ProcessExecutionError
        processexecerror = ProcessExecutionError('No such file or directory')
        dbaas.utils.execute_with_timeout = Mock(side_effect=processexecerror)

        self.mySqlApp.wipe_ib_logfiles()

    def test_wipe_ib_logfiles_error(self):

        from reddwarf.common.exception import ProcessExecutionError
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
        from reddwarf.common.exception import ProcessExecutionError
        mocked = Mock(side_effect=ProcessExecutionError('Error'))
        dbaas.utils.execute_with_timeout = mocked

        self.assertRaises(RuntimeError, self.mySqlApp.start_mysql)

    def test_start_mysql_with_conf_changes(self):

        self.mySqlApp.start_mysql = Mock()
        self.mySqlApp._write_mycnf = Mock()
        self.mysql_starts_successfully()

        self.appStatus.status = ServiceStatuses.SHUTDOWN
        self.mySqlApp.start_mysql_with_conf_changes(Mock())

        self.assertTrue(self.mySqlApp._write_mycnf.called)
        self.assertTrue(self.mySqlApp.start_mysql.called)
        self.assertEqual(self.appStatus._get_actual_db_status(),
                         ServiceStatuses.RUNNING)

    def test_start_mysql_with_conf_changes_mysql_is_running(self):

        self.mySqlApp.start_mysql = Mock()
        self.mySqlApp._write_mycnf = Mock()

        self.appStatus.status = ServiceStatuses.RUNNING
        self.assertRaises(RuntimeError,
                          self.mySqlApp.start_mysql_with_conf_changes, Mock())


class MySqlAppInstallTest(MySqlAppTest):

    def setUp(self):
        super(MySqlAppInstallTest, self).setUp()
        self.orig_create_engine = dbaas.create_engine
        self.orig_pkg_version = dbaas.pkg.pkg_version

    def tearDown(self):
        super(MySqlAppInstallTest, self).tearDown()
        dbaas.create_engine = self.orig_create_engine
        dbaas.pkg.pkg_version = self.orig_pkg_version

    def test_install_and_secure(self):

        self.mySqlApp.start_mysql = Mock()
        self.mySqlApp.stop_mysql = Mock()
        self.mySqlApp._install_mysql = Mock()
        self.mySqlApp._write_mycnf = Mock()
        self.mysql_stops_successfully()
        self.mysql_starts_successfully()
        dbaas.create_engine = Mock()

        self.mySqlApp.install_and_secure(100)

        self.assertTrue(self.mySqlApp._install_mysql.called)
        self.assertTrue(self.mySqlApp.stop_mysql.called)
        self.assertTrue(self.mySqlApp._write_mycnf.called)
        self.assertTrue(self.mySqlApp.start_mysql.called)
        self.assert_reported_status(ServiceStatuses.RUNNING)

    def test_install_and_secure_install_error(self):

        from reddwarf.guestagent import pkg
        self.mySqlApp.start_mysql = Mock()
        self.mySqlApp.stop_mysql = Mock()
        self.mySqlApp._install_mysql = \
            Mock(side_effect=pkg.PkgPackageStateError("Install error"))

        self.assertRaises(pkg.PkgPackageStateError,
                          self.mySqlApp.install_and_secure, 100)

        self.assert_reported_status(ServiceStatuses.BUILDING)

    def test_install_and_secure_write_conf_error(self):

        from reddwarf.guestagent import pkg
        self.mySqlApp.start_mysql = Mock()
        self.mySqlApp.stop_mysql = Mock()
        self.mySqlApp._install_mysql = Mock()
        self.mySqlApp._write_mycnf = \
            Mock(side_effect=pkg.PkgPackageStateError("Install error"))
        self.mysql_stops_successfully()
        self.mysql_starts_successfully()
        dbaas.create_engine = Mock()

        self.assertRaises(pkg.PkgPackageStateError,
                          self.mySqlApp.install_and_secure, 100)

        self.assertTrue(self.mySqlApp._install_mysql.called)
        self.assertTrue(self.mySqlApp.stop_mysql.called)
        self.assertTrue(self.mySqlApp._write_mycnf.called)
        self.assert_reported_status(ServiceStatuses.BUILDING)

    def test_is_installed(self):

        dbaas.pkg.pkg_version = Mock(return_value=True)

        self.assertTrue(self.mySqlApp.is_installed())

    def test_is_installed_not(self):

        dbaas.pkg.pkg_version = Mock(return_value=None)

        self.assertFalse(self.mySqlApp.is_installed())


class InterrogatorTest(testtools.TestCase):

    def setUp(self):
        super(InterrogatorTest, self).setUp()
        self.orig_utils_execute_with_timeout = dbaas.utils.execute_with_timeout
        self.orig_LOG_err = dbaas.LOG

    def tearDown(self):
        super(InterrogatorTest, self).tearDown()
        dbaas.utils.execute_with_timeout = self.orig_utils_execute_with_timeout
        dbaas.LOG = self.orig_LOG_err

    def test_get_filesystem_volume_stats(self):

        path = 'aPath'
        block_size = 4096
        total_block = 2582828
        free_block = 767118
        total = total_block * block_size
        free = free_block * block_size
        used = total - free
        out = " ".join(str(x) for x in (path, 'fb518d79428291bb', 255, 'ef53',
                                        block_size, '4096', total_block,
                                        free_block, 636216, 655360, 583768))
        err = None
        return_exp = out, err
        dbaas.utils.execute_with_timeout = Mock(return_value=return_exp)

        self.interrogator = Interrogator()
        result = self.interrogator.get_filesystem_volume_stats(path)

        self.assertTrue(dbaas.utils.execute_with_timeout.called)
        self.assertTrue('stat' in
                        dbaas.utils.execute_with_timeout.call_args[0])
        self.assertTrue(path in dbaas.utils.execute_with_timeout.call_args[0])

        self.assertEqual(result['block_size'], block_size)
        self.assertEqual(result['total_blocks'], total_block)
        self.assertEqual(result['free_blocks'], free_block)
        self.assertEqual(result['total'], total)
        self.assertEqual(result['free'], free)
        self.assertEqual(result['used'], used)

    def test_get_filesystem_volume_stats_error(self):

        path = 'aPath'
        block_size = 4096
        total_block = 2582828
        free_block = 767118

        out = " ".join(str(x) for x in (path, 'fb518d79428291bb', 255, 'ef53',
                                        block_size, '4096', total_block,
                                        free_block, 636216, 655360, 583768))
        err = "Error found"
        return_exp = out, err
        dbaas.utils.execute_with_timeout = Mock(return_value=return_exp)
        dbaas.LOG.err = Mock()

        self.interrogator = Interrogator()
        self.assertRaises(RuntimeError,
                          self.interrogator.get_filesystem_volume_stats, path)


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

        from reddwarf.common.exception import ProcessExecutionError
        mocked = Mock(side_effect=ProcessExecutionError())
        dbaas.utils.execute_with_timeout = mocked
        dbaas.load_mysqld_options = Mock()
        dbaas.os.path.exists = Mock(return_value=False)

        self.mySqlAppStatus = MySqlAppStatus()
        status = self.mySqlAppStatus._get_actual_db_status()

        self.assertEqual(ServiceStatuses.SHUTDOWN, status)

    def test_get_actual_db_status_error_crashed(self):

        from reddwarf.common.exception import ProcessExecutionError
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
