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

import abc
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

from trove.common import cfg
from trove.common import context as trove_context
from trove.common.exception import BadRequest
from trove.common.exception import GuestError
from trove.common.exception import PollTimeOut
from trove.common.exception import ProcessExecutionError
from trove.common import instance as rd_instance
from trove.common import utils
from trove.conductor import api as conductor_api
from trove.guestagent.common.configuration import ImportOverrideStrategy
from trove.guestagent.common import operating_system
from trove.guestagent.common import sql_query
from trove.guestagent.datastore.experimental.cassandra import (
    service as cass_service)
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
from trove.guestagent.datastore.experimental.postgresql import (
    manager as pg_manager)
from trove.guestagent.datastore.experimental.postgresql.service import (
    config as pg_config)
from trove.guestagent.datastore.experimental.postgresql.service import (
    status as pg_status)
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
import trove.guestagent.datastore.mysql_common.service as dbaas_base
import trove.guestagent.datastore.service as base_datastore_service
from trove.guestagent.datastore.service import BaseDbStatus
from trove.guestagent.db import models
from trove.guestagent import dbaas as dbaas_sr
from trove.guestagent.dbaas import get_filesystem_volume_stats
from trove.guestagent.dbaas import to_gb
from trove.guestagent.dbaas import to_mb
from trove.guestagent import pkg
from trove.guestagent.volume import VolumeDevice
from trove.instance.models import InstanceServiceStatus
from trove.tests.unittests import trove_testtools
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


class FakeTime:
    COUNTER = 0

    @classmethod
    def time(cls):
        cls.COUNTER += 1
        return cls.COUNTER


def faketime(*args, **kwargs):
    return FakeTime.time()


class FakeAppStatus(BaseDbStatus):

    def __init__(self, id, status):
        self.id = id
        self.status = status
        self.next_fake_status = status
        self._prepare_completed = None
        self.start_db_service = MagicMock()
        self.stop_db_service = MagicMock()
        self.restart_db_service = MagicMock()

    def _get_actual_db_status(self):
        return self.next_fake_status

    def set_next_status(self, next_status):
        self.next_fake_status = next_status

    def _is_query_router(self):
        return False


class DbaasTest(trove_testtools.TestCase):

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
    @patch('trove.guestagent.datastore.mysql_common.service.LOG')
    def test_fail_password_update_content_clear_expired_password(self,
                                                                 mock_logging,
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

    @patch('trove.guestagent.datastore.mysql_common.service.LOG')
    @patch.object(operating_system, 'remove')
    @patch.object(dbaas_base.utils, 'execute',
                  side_effect=ProcessExecutionError)
    def test_fail_retrieve_secret_content_clear_expired_password(self,
                                                                 mock_execute,
                                                                 mock_remove,
                                                                 mock_logging):
        dbaas_base.clear_expired_password()
        self.assertEqual(1, mock_execute.call_count)
        mock_remove.assert_not_called()

    @patch.object(operating_system, 'read_file',
                  return_value={'client':
                                {'password': 'some password'}})
    def test_get_auth_password(self, read_file_mock):
        password = MySqlApp.get_auth_password()
        read_file_mock.assert_called_once_with(MySqlApp.get_client_auth_file(),
                                               codec=MySqlApp.CFG_CODEC)
        self.assertEqual("some password", password)

    @patch.object(operating_system, 'read_file',
                  side_effect=RuntimeError('read_file error'))
    def test_get_auth_password_error(self, _):
        self.assertRaisesRegexp(RuntimeError, "read_file error",
                                MySqlApp.get_auth_password)

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


class BaseAppTest(object):
    """A wrapper to inhibit the base test methods from executing during a
    normal test run.
    """

    class AppTestCase(trove_testtools.TestCase):

        def setUp(self, fake_id):
            super(BaseAppTest.AppTestCase, self).setUp()
            self.FAKE_ID = fake_id
            InstanceServiceStatus.create(
                instance_id=self.FAKE_ID,
                status=rd_instance.ServiceStatuses.NEW)

        def tearDown(self):
            InstanceServiceStatus.find_by(instance_id=self.FAKE_ID).delete()
            super(BaseAppTest.AppTestCase, self).tearDown()

        @abc.abstractproperty
        def appStatus(self):
            pass

        @abc.abstractproperty
        def expected_state_change_timeout(self):
            pass

        @abc.abstractproperty
        def expected_service_candidates(self):
            pass

        def test_start_db(self):
            with patch.object(BaseDbStatus, 'prepare_completed') as patch_pc:
                patch_pc.__get__ = Mock(return_value=True)
                self.appStatus.set_next_status(
                    rd_instance.ServiceStatuses.RUNNING)
                self.app.start_db()
                self.appStatus.start_db_service.assert_called_once_with(
                    self.expected_service_candidates,
                    self.expected_state_change_timeout,
                    enable_on_boot=True, update_db=False)
                self.assert_reported_status(rd_instance.ServiceStatuses.NEW)

        def test_stop_db(self):
            with patch.object(BaseDbStatus, 'prepare_completed') as patch_pc:
                patch_pc.__get__ = Mock(return_value=True)
                self.appStatus.set_next_status(
                    rd_instance.ServiceStatuses.SHUTDOWN)
                self.app.stop_db()
                self.appStatus.stop_db_service.assert_called_once_with(
                    self.expected_service_candidates,
                    self.expected_state_change_timeout,
                    disable_on_boot=False, update_db=False)
                self.assert_reported_status(rd_instance.ServiceStatuses.NEW)

        def test_restart_db(self):
            self.appStatus.set_next_status(rd_instance.ServiceStatuses.RUNNING)
            with patch.object(BaseDbStatus, 'prepare_completed') as patch_pc:
                patch_pc.__get__ = Mock(return_value=True)
                self.app.restart()
                self.appStatus.restart_db_service.assert_called_once_with(
                    self.expected_service_candidates,
                    self.expected_state_change_timeout)

        def assert_reported_status(self, expected_status):
            service_status = InstanceServiceStatus.find_by(
                instance_id=self.FAKE_ID)
            self.assertEqual(expected_status, service_status.status)


class MySqlAdminMockTest(trove_testtools.TestCase):

    def setUp(self):
        super(MySqlAdminMockTest, self).setUp()
        mysql_app_patcher = patch.multiple(MySqlApp, get_engine=DEFAULT,
                                           configuration_manager=DEFAULT)
        self.addCleanup(mysql_app_patcher.stop)
        mysql_app_patcher.start()
        create_engine_patcher = patch.object(sqlalchemy, 'create_engine')
        self.addCleanup(create_engine_patcher.stop)
        create_engine_patcher.start()
        exec_timeout_patcher = patch.object(utils, 'execute_with_timeout')
        self.addCleanup(exec_timeout_patcher.stop)
        exec_timeout_patcher.start()

        self.mock_cli_ctx_mgr = Mock()
        self.mock_client = MagicMock()
        self.mock_cli_ctx_mgr.__enter__ = Mock(return_value=self.mock_client)
        self.mock_cli_ctx_mgr.__exit__ = Mock()

        local_client_patcher = patch.object(dbaas.MySqlAdmin,
                                            'local_sql_client',
                                            return_value=self.mock_cli_ctx_mgr)
        self.addCleanup(local_client_patcher.stop)
        local_client_patcher.start()

    def tearDown(self):
        super(MySqlAdminMockTest, self).tearDown()

    @patch('trove.guestagent.datastore.mysql.service.MySqlApp'
           '.get_auth_password', return_value='some_password')
    def test_list_databases(self, auth_pwd_mock):
        with patch.object(self.mock_client, 'execute',
                          return_value=ResultSetStub(
                [('db1', 'utf8', 'utf8_bin'),
                 ('db2', 'utf8', 'utf8_bin'),
                 ('db3', 'utf8', 'utf8_bin')])):
            databases, next_marker = MySqlAdmin().list_databases(limit=10)

            self.assertIsNone(next_marker)
            self.assertEqual(3, len(databases))


class MySqlAdminTest(trove_testtools.TestCase):

    def setUp(self):

        super(MySqlAdminTest, self).setUp()

        self.orig_get_engine = dbaas.get_engine
        self.mock_cli_ctx_mgr = Mock()
        self.mock_client = MagicMock()
        self.mock_cli_ctx_mgr.__enter__ = Mock(return_value=self.mock_client)
        self.mock_cli_ctx_mgr.__exit__ = Mock()

        local_client_patcher = patch.object(dbaas.MySqlAdmin,
                                            'local_sql_client',
                                            return_value=self.mock_cli_ctx_mgr)
        self.addCleanup(local_client_patcher.stop)
        local_client_patcher.start()

        self.orig_MySQLUser_is_valid_user_name = (
            models.MySQLUser._is_valid_user_name)
        dbaas.get_engine = MagicMock(name='get_engine')

        # trove.guestagent.common.configuration import ConfigurationManager
        dbaas.orig_configuration_manager = dbaas.MySqlApp.configuration_manager
        dbaas.MySqlApp.configuration_manager = Mock()
        dbaas.orig_get_auth_password = dbaas.MySqlApp.get_auth_password
        dbaas.MySqlApp.get_auth_password = Mock()

        self.mySqlAdmin = MySqlAdmin()

    def tearDown(self):
        dbaas.get_engine = self.orig_get_engine
        models.MySQLUser._is_valid_user_name = (
            self.orig_MySQLUser_is_valid_user_name)
        dbaas.MySqlApp.configuration_manager = \
            dbaas.orig_configuration_manager
        dbaas.MySqlApp.get_auth_password = \
            dbaas.orig_get_auth_password
        super(MySqlAdminTest, self).tearDown()

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

        with patch.object(self.mock_client, 'execute',
                          return_value=db_result) as mock_execute:
            self.mySqlAdmin._associate_dbs(user)
            self.assertEqual(3, len(user.databases))
            self._assert_execute_call(expected, mock_execute)

    def _assert_execute_call(self, expected_query, execute_mock, call_idx=0):
        args, _ = execute_mock.call_args_list[call_idx]
        self.assertTrue(execute_mock.called,
                        "The client object was not called.")
        self.assertEqual(expected_query, args[0].text,
                         "Queries are not the same.")

    def test_change_passwords(self):
        user = [{"name": "test_user", "host": "%", "password": "password"}]
        expected = ("UPDATE mysql.user SET Password="
                    "PASSWORD('password') WHERE User = 'test_user' "
                    "AND Host = '%';")
        with patch.object(self.mock_client, 'execute') as mock_execute:
            self.mySqlAdmin.change_passwords(user)
            self._assert_execute_call(expected, mock_execute)

    def test_update_attributes_password(self):
        db_result = [{"grantee": "'test_user'@'%'", "table_schema": "db1"},
                     {"grantee": "'test_user'@'%'", "table_schema": "db2"}]
        expected = ("UPDATE mysql.user SET Password="
                    "PASSWORD('password') WHERE User = 'test_user' "
                    "AND Host = '%';")
        user = MagicMock()
        user.name = "test_user"
        user.host = "%"
        user_attrs = {"password": "password"}
        with patch.object(self.mock_client, 'execute',
                          return_value=db_result) as mock_execute:
            with patch.object(self.mySqlAdmin, '_get_user', return_value=user):
                with patch.object(self.mySqlAdmin, 'grant_access'):
                    self.mySqlAdmin.update_attributes('test_user', '%',
                                                      user_attrs)
                    self.assertEqual(0,
                                     self.mySqlAdmin.grant_access.call_count)
                    self._assert_execute_call(expected, mock_execute,
                                              call_idx=1)

    def test_update_attributes_name(self):
        user = MagicMock()
        user.name = "test_user"
        user.host = "%"
        user_attrs = {"name": "new_name"}
        expected = ("UPDATE mysql.user SET User='new_name' "
                    "WHERE User = 'test_user' AND Host = '%';")
        with patch.object(self.mock_client, 'execute') as mock_execute:
            with patch.object(self.mySqlAdmin, '_get_user', return_value=user):
                with patch.object(self.mySqlAdmin, 'grant_access'):
                    self.mySqlAdmin.update_attributes('test_user', '%',
                                                      user_attrs)
                    self.mySqlAdmin.grant_access.assert_called_with(
                        'new_name', '%', set([]))
                    self._assert_execute_call(expected, mock_execute,
                                              call_idx=1)

    def test_update_attributes_host(self):
        user = MagicMock()
        user.name = "test_user"
        user.host = "%"
        user_attrs = {"host": "new_host"}
        expected = ("UPDATE mysql.user SET Host='new_host' "
                    "WHERE User = 'test_user' AND Host = '%';")
        with patch.object(self.mock_client, 'execute') as mock_execute:
            with patch.object(self.mySqlAdmin, '_get_user', return_value=user):
                with patch.object(self.mySqlAdmin, 'grant_access'):
                    self.mySqlAdmin.update_attributes('test_user', '%',
                                                      user_attrs)
                    self.mySqlAdmin.grant_access.assert_called_with(
                        'test_user', 'new_host', set([]))
                    self._assert_execute_call(expected, mock_execute,
                                              call_idx=1)

    def test_create_database(self):
        databases = []
        databases.append(FAKE_DB)
        expected = ("CREATE DATABASE IF NOT EXISTS "
                    "`testDB` CHARACTER SET = 'latin2' "
                    "COLLATE = 'latin2_general_ci';")

        with patch.object(self.mock_client, 'execute') as mock_execute:
            self.mySqlAdmin.create_database(databases)
            self._assert_execute_call(expected, mock_execute)

    def test_create_database_more_than_1(self):
        databases = []
        databases.append(FAKE_DB)
        databases.append(FAKE_DB_2)
        expected_1 = ("CREATE DATABASE IF NOT EXISTS "
                      "`testDB` CHARACTER SET = 'latin2' "
                      "COLLATE = 'latin2_general_ci';")
        expected_2 = ("CREATE DATABASE IF NOT EXISTS "
                      "`testDB2` CHARACTER SET = 'latin2' "
                      "COLLATE = 'latin2_general_ci';")

        with patch.object(self.mock_client, 'execute') as mock_execute:
            self.mySqlAdmin.create_database(databases)
            self._assert_execute_call(expected_1, mock_execute, call_idx=0)
            self._assert_execute_call(expected_2, mock_execute, call_idx=1)

    def test_create_database_no_db(self):
        databases = []

        with patch.object(self.mock_client, 'execute') as mock_execute:
            self.mySqlAdmin.create_database(databases)
            mock_execute.assert_not_called()

    def test_delete_database(self):
        database = {"_name": "testDB"}
        expected = "DROP DATABASE `testDB`;"

        with patch.object(self.mock_client, 'execute') as mock_execute:
            self.mySqlAdmin.delete_database(database)
            self._assert_execute_call(expected, mock_execute)

    def test_delete_user(self):
        user = {"_name": "testUser", "_host": None}
        expected = "DROP USER `testUser`@`%`;"

        with patch.object(self.mock_client, 'execute') as mock_execute:
            self.mySqlAdmin.delete_user(user)
            self._assert_execute_call(expected, mock_execute)

    def test_create_user(self):
        access_grants_expected = ("GRANT ALL PRIVILEGES ON `testDB`.* TO "
                                  "`random`@`%` IDENTIFIED BY 'guesswhat';")
        create_user_expected = ("GRANT USAGE ON *.* TO `random`@`%` "
                                "IDENTIFIED BY 'guesswhat';")

        with patch.object(self.mock_client, 'execute') as mock_execute:
            self.mySqlAdmin.create_user(FAKE_USER)
            self._assert_execute_call(create_user_expected,
                                      mock_execute, call_idx=0)
            self._assert_execute_call(access_grants_expected,
                                      mock_execute, call_idx=1)

    @patch('trove.guestagent.datastore.mysql.service.MySqlApp'
           '.get_auth_password', return_value='some_password')
    def test_list_databases(self, auth_pwd_mock):
        expected = ("SELECT schema_name as name,"
                    " default_character_set_name as charset,"
                    " default_collation_name as collation"
                    " FROM information_schema.schemata WHERE"
                    " schema_name NOT IN ('" +
                    "', '".join(cfg.get_ignored_dbs()) +
                    "')"
                    " ORDER BY schema_name ASC;"
                    )
        with patch.object(self.mock_client, 'execute') as mock_execute:
            self.mySqlAdmin.list_databases()
            self._assert_execute_call(expected, mock_execute)

    def test_list_databases_with_limit(self):
        limit = 2
        expected = ("SELECT schema_name as name,"
                    " default_character_set_name as charset,"
                    " default_collation_name as collation"
                    " FROM information_schema.schemata WHERE"
                    " schema_name NOT IN ('" +
                    "', '".join(cfg.get_ignored_dbs()) + "')"
                    " ORDER BY schema_name ASC LIMIT " + str(limit + 1) + ";"
                    )
        with patch.object(self.mock_client, 'execute') as mock_execute:
            self.mySqlAdmin.list_databases(limit)
            self._assert_execute_call(expected, mock_execute)

    def test_list_databases_with_marker(self):
        marker = "aMarker"
        expected = ("SELECT schema_name as name,"
                    " default_character_set_name as charset,"
                    " default_collation_name as collation"
                    " FROM information_schema.schemata WHERE"
                    " schema_name NOT IN ('" +
                    "', '".join(cfg.get_ignored_dbs()) + "')"
                    " AND schema_name > '" + marker + "'"
                    " ORDER BY schema_name ASC;"
                    )

        with patch.object(self.mock_client, 'execute') as mock_execute:
            self.mySqlAdmin.list_databases(marker=marker)
            self._assert_execute_call(expected, mock_execute)

    def test_list_databases_with_include_marker(self):
        marker = "aMarker"
        expected = ("SELECT schema_name as name,"
                    " default_character_set_name as charset,"
                    " default_collation_name as collation"
                    " FROM information_schema.schemata WHERE"
                    " schema_name NOT IN ('" +
                    "', '".join(cfg.get_ignored_dbs()) + "')"
                    " AND schema_name >= '" + marker + "'"
                    " ORDER BY schema_name ASC;"
                    )

        with patch.object(self.mock_client, 'execute') as mock_execute:
            self.mySqlAdmin.list_databases(marker=marker, include_marker=True)
            self._assert_execute_call(expected, mock_execute)

    def test_list_users(self):
        expected = ("SELECT User, Host, Marker FROM"
                    " (SELECT User, Host, CONCAT(User, '@', Host) as Marker"
                    " FROM mysql.user ORDER BY User, Host) as innerquery WHERE"
                    " Host != 'localhost' AND User NOT IN ('os_admin', 'root')"
                    " ORDER BY Marker;"
                    )

        with patch.object(self.mock_client, 'execute') as mock_execute:
            self.mySqlAdmin.list_users()
            self._assert_execute_call(expected, mock_execute)

    def test_list_users_with_limit(self):
        limit = 2
        expected = ("SELECT User, Host, Marker FROM"
                    " (SELECT User, Host, CONCAT(User, '@', Host) as Marker"
                    " FROM mysql.user ORDER BY User, Host) as innerquery WHERE"
                    " Host != 'localhost' AND User NOT IN ('os_admin', 'root')"
                    " ORDER BY Marker"
                    " LIMIT " + str(limit + 1) + ";"
                    )

        with patch.object(self.mock_client, 'execute') as mock_execute:
            self.mySqlAdmin.list_users(limit)
            self._assert_execute_call(expected, mock_execute)

    def test_list_users_with_marker(self):
        marker = "aMarker"
        expected = ("SELECT User, Host, Marker FROM"
                    " (SELECT User, Host, CONCAT(User, '@', Host) as Marker"
                    " FROM mysql.user ORDER BY User, Host) as innerquery WHERE"
                    " Host != 'localhost' AND User NOT IN ('os_admin', 'root')"
                    " AND Marker > '" + marker + "'"
                    " ORDER BY Marker;"
                    )

        with patch.object(self.mock_client, 'execute') as mock_execute:
            self.mySqlAdmin.list_users(marker=marker)
            self._assert_execute_call(expected, mock_execute)

    def test_list_users_with_include_marker(self):
        marker = "aMarker"
        expected = ("SELECT User, Host, Marker FROM"
                    " (SELECT User, Host, CONCAT(User, '@', Host) as Marker"
                    " FROM mysql.user ORDER BY User, Host) as innerquery WHERE"
                    " Host != 'localhost' AND User NOT IN ('os_admin', 'root')"
                    " AND Marker >= '" + marker + "'"
                    " ORDER BY Marker;"
                    )

        with patch.object(self.mock_client, 'execute') as mock_execute:
            self.mySqlAdmin.list_users(marker=marker, include_marker=True)
            self._assert_execute_call(expected, mock_execute)

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
        expected = ("SELECT User, Host, Password FROM mysql.user "
                    "WHERE Host != 'localhost' AND User = 'user1' "
                    "AND Host = '%' ORDER BY User, Host;")

        with patch.object(self.mock_client, 'execute') as mock_execute:
            fa_mock = Mock(return_value=user)
            mock_execute.return_value = Mock()
            mock_execute.return_value.fetchall = fa_mock
            self.mySqlAdmin.get_user(username, hostname)
            self.assertEqual(1, mock_associate_dbs.call_count)
            self._assert_execute_call(expected, mock_execute)

    @patch('trove.guestagent.datastore.mysql_common.service.LOG')
    def test_fail_get_user(self, *args):
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
        expected = ("GRANT ALL PRIVILEGES ON `db1`.* TO `test_user`@`%` "
                    "IDENTIFIED BY PASSWORD 'some_password';")
        with patch.object(self.mock_client, 'execute') as mock_execute:
            with patch.object(self.mySqlAdmin, '_get_user', return_value=user):
                self.mySqlAdmin.grant_access('test_user', '%', databases)
                self._assert_execute_call(expected, mock_execute)

    @patch('trove.guestagent.datastore.mysql_common.service.LOG')
    def test_fail_grant_access(self, *args):
        user = MagicMock()
        user.name = "test_user"
        user.host = "%"
        user.password = 'some_password'
        databases = ['mysql']
        with patch.object(self.mock_client, 'execute') as mock_execute:
            with patch.object(self.mySqlAdmin, '_get_user', return_value=user):
                self.mySqlAdmin.grant_access('test_user', '%', databases)
                # since mysql is not a database to be provided access to,
                # testing that executed was not called in grant access.
                mock_execute.assert_not_called()

    def test_is_root_enabled(self):
        expected = ("SELECT User FROM mysql.user WHERE "
                    "User = 'root' AND Host != 'localhost';")

        with patch.object(dbaas.MySqlRootAccess, 'local_sql_client',
                          return_value=self.mock_cli_ctx_mgr):
            with patch.object(self.mock_client, 'execute') as mock_execute:
                self.mySqlAdmin.is_root_enabled()
                self._assert_execute_call(expected, mock_execute)

    def test_revoke_access(self):
        user = MagicMock()
        user.name = "test_user"
        user.host = "%"
        user.password = 'some_password'
        databases = ['db1']
        expected = ("REVOKE ALL ON `['db1']`.* FROM `test_user`@`%`;")
        with patch.object(self.mock_client, 'execute') as mock_execute:
            with patch.object(self.mySqlAdmin, '_get_user', return_value=user):
                self.mySqlAdmin.revoke_access('test_usr', '%', databases)
                self._assert_execute_call(expected, mock_execute)

    def test_list_access(self):
        user = MagicMock()
        user.name = "test_user"
        user.host = "%"
        user.databases = ['db1', 'db2']
        with patch.object(self.mock_client, 'execute'):
            with patch.object(self.mySqlAdmin, '_get_user', return_value=user):
                databases = self.mySqlAdmin.list_access('test_usr', '%')
                self.assertEqual(2, len(databases),
                                 "List access queries are not the same")


class MySqlAppTest(trove_testtools.TestCase):

    def setUp(self):
        super(MySqlAppTest, self).setUp()
        self.orig_utils_execute_with_timeout = \
            dbaas_base.utils.execute_with_timeout
        self.orig_time_sleep = time.sleep
        self.orig_time_time = time.time
        self.orig_unlink = os.unlink
        self.orig_get_auth_password = MySqlApp.get_auth_password
        self.orig_service_discovery = operating_system.service_discovery
        mysql_app_patcher = patch.multiple(MySqlApp, get_engine=DEFAULT,
                                           get_auth_password=DEFAULT,
                                           configuration_manager=DEFAULT)
        self.addCleanup(mysql_app_patcher.stop)
        mysql_app_patcher.start()
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
        time.sleep = Mock()
        time.time = Mock(side_effect=faketime)
        os.unlink = Mock()
        self.mock_client = Mock()
        self.mock_execute = Mock()
        self.mock_client.__enter__ = Mock()
        self.mock_client.__exit__ = Mock()
        self.mock_client.__enter__.return_value.execute = self.mock_execute
        self.orig_create_engine = sqlalchemy.create_engine

    def tearDown(self):
        dbaas_base.utils.execute_with_timeout = \
            self.orig_utils_execute_with_timeout
        time.sleep = self.orig_time_sleep
        time.time = self.orig_time_time
        os.unlink = self.orig_unlink
        operating_system.service_discovery = self.orig_service_discovery
        InstanceServiceStatus.find_by(instance_id=self.FAKE_ID).delete()
        sqlalchemy.create_engine = self.orig_create_engine
        super(MySqlAppTest, self).tearDown()

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

        with patch.object(BaseDbStatus, 'prepare_completed') as patch_pc:
            patch_pc.__get__ = Mock(return_value=True)
            self.mySqlApp.stop_db()
            self.assert_reported_status(rd_instance.ServiceStatuses.NEW)

    def test_stop_mysql_with_db_update(self):

        dbaas_base.utils.execute_with_timeout = Mock()
        self.appStatus.set_next_status(
            rd_instance.ServiceStatuses.SHUTDOWN)

        with patch.object(BaseDbStatus, 'prepare_completed') as patch_pc:
            patch_pc.__get__ = Mock(return_value=True)
            self.mySqlApp.stop_db(True)
            self.assertTrue(conductor_api.API.heartbeat.called_once_with(
                self.FAKE_ID,
                {'service_status':
                 rd_instance.ServiceStatuses.SHUTDOWN.description}))

    @patch.object(utils, 'execute_with_timeout', return_value=('0', ''))
    def test_stop_mysql_do_not_start_on_reboot(self, mock_execute):

        self.appStatus.set_next_status(
            rd_instance.ServiceStatuses.SHUTDOWN)

        with patch.object(BaseDbStatus, 'prepare_completed') as patch_pc:
            patch_pc.__get__ = Mock(return_value=True)
            self.mySqlApp.stop_db(True, True)
            self.assertTrue(conductor_api.API.heartbeat.called_once_with(
                self.FAKE_ID,
                {'service_status':
                 rd_instance.ServiceStatuses.SHUTDOWN.description}))
            self.assertEqual(2, mock_execute.call_count)

    @patch('trove.guestagent.datastore.service.LOG')
    @patch('trove.guestagent.datastore.mysql_common.service.LOG')
    def test_stop_mysql_error(self, *args):
        dbaas_base.utils.execute_with_timeout = Mock()
        self.appStatus.set_next_status(rd_instance.ServiceStatuses.RUNNING)
        self.mySqlApp.state_change_wait_time = 1
        with patch.object(BaseDbStatus, 'prepare_completed') as patch_pc:
            patch_pc.__get__ = Mock(return_value=True)
            self.assertRaises(RuntimeError, self.mySqlApp.stop_db)

    @patch('trove.guestagent.datastore.mysql_common.service.LOG')
    @patch.object(operating_system, 'service_discovery',
                  side_effect=KeyError('error'))
    @patch.object(utils, 'execute_with_timeout', return_value=('0', ''))
    def test_stop_mysql_key_error(self, mock_execute, mock_service,
                                  mock_logging):
        with patch.object(BaseDbStatus, 'prepare_completed') as patch_pc:
            patch_pc.__get__ = Mock(return_value=True)
            self.assertRaisesRegexp(RuntimeError, 'Service is not discovered.',
                                    self.mySqlApp.stop_db)
            self.assertEqual(0, mock_execute.call_count)

    def test_restart_is_successful(self):

        self.mySqlApp.start_mysql = Mock()
        self.mySqlApp.stop_db = Mock()
        self.mysql_stops_successfully()
        self.mysql_starts_successfully()

        with patch.object(BaseDbStatus, 'prepare_completed') as patch_pc:
            patch_pc.__get__ = Mock(return_value=True)
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

        with patch.object(BaseDbStatus, 'prepare_completed') as patch_pc:
            patch_pc.__get__ = Mock(return_value=True)
            self.assertRaises(RuntimeError, self.mySqlApp.restart)

            self.assertTrue(self.mySqlApp.stop_db.called)
            self.assertFalse(self.mySqlApp.start_mysql.called)
            self.assert_reported_status(rd_instance.ServiceStatuses.NEW)

    @patch('trove.guestagent.datastore.mysql_common.service.LOG')
    @patch.object(dbaas.MySqlApp, 'get_data_dir', return_value='some path')
    def test_wipe_ib_logfiles_error(self, get_datadir_mock, mock_logging):

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

        with patch.object(BaseDbStatus, 'prepare_completed') as patch_pc:
            patch_pc.__get__ = Mock(return_value=True)
            self.mySqlApp.start_mysql(update_db=True)
            self.assertTrue(conductor_api.API.heartbeat.called_once_with(
                self.FAKE_ID,
                {'service_status':
                 rd_instance.ServiceStatuses.RUNNING.description}))

    @patch('trove.guestagent.datastore.mysql_common.service.LOG')
    @patch('trove.guestagent.datastore.service.LOG')
    def test_start_mysql_runs_forever(self, *args):

        dbaas_base.utils.execute_with_timeout = Mock()
        self.mySqlApp._enable_mysql_on_boot = Mock()
        self.mySqlApp.state_change_wait_time = 1
        self.appStatus.set_next_status(rd_instance.ServiceStatuses.SHUTDOWN)

        with patch.object(BaseDbStatus, 'prepare_completed') as patch_pc:
            patch_pc.__get__ = Mock(return_value=True)
            self.assertRaises(RuntimeError, self.mySqlApp.start_mysql)
            self.assertTrue(conductor_api.API.heartbeat.called_once_with(
                self.FAKE_ID,
                {'service_status':
                 rd_instance.ServiceStatuses.SHUTDOWN.description}))

    @patch('trove.guestagent.datastore.service.LOG')
    @patch('trove.guestagent.datastore.mysql_common.service.LOG')
    def test_start_mysql_error(self, *args):

        self.mySqlApp._enable_mysql_on_boot = Mock()
        mocked = Mock(side_effect=ProcessExecutionError('Error'))
        dbaas_base.utils.execute_with_timeout = mocked

        with patch.object(BaseDbStatus, 'prepare_completed') as patch_pc:
            patch_pc.__get__ = Mock(return_value=True)
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

    @patch('trove.guestagent.datastore.mysql_common.service.LOG')
    def test_start_db_with_conf_changes_mysql_is_running(self, *args):
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
        save_auth_mock = Mock()
        wipe_ib_mock = Mock()

        configuration = {'config_contents': 'some junk'}

        self.mySqlApp.configuration_manager.save_configuration = save_cfg_mock
        self.mySqlApp._save_authentication_properties = save_auth_mock
        self.mySqlApp.wipe_ib_logfiles = wipe_ib_mock
        self.mySqlApp.reset_configuration(configuration=configuration)

        save_cfg_mock.assert_called_once_with('some junk')
        save_auth_mock.assert_called_once_with(
            auth_pwd_mock.return_value)
        wipe_ib_mock.assert_called_once_with()

    @patch.object(utils, 'execute_with_timeout', return_value=('0', ''))
    def test__enable_mysql_on_boot(self, mock_execute):
        mysql_service = \
            dbaas_base.operating_system.service_discovery(["mysql"])
        self.mySqlApp._enable_mysql_on_boot()
        self.assertEqual(1, mock_execute.call_count)
        mock_execute.assert_called_with(mysql_service['cmd_enable'],
                                        shell=True)

    @patch('trove.guestagent.datastore.mysql_common.service.LOG')
    @patch.object(operating_system, 'service_discovery',
                  side_effect=KeyError('error'))
    @patch.object(utils, 'execute_with_timeout', return_value=('0', ''))
    def test_fail__enable_mysql_on_boot(self, mock_execute, mock_service,
                                        mock_logging):
        self.assertRaisesRegexp(RuntimeError, 'Service is not discovered.',
                                self.mySqlApp._enable_mysql_on_boot)
        self.assertEqual(0, mock_execute.call_count)

    @patch.object(utils, 'execute_with_timeout', return_value=('0', ''))
    def test__disable_mysql_on_boot(self, mock_execute):
        mysql_service = \
            dbaas_base.operating_system.service_discovery(["mysql"])
        self.mySqlApp._disable_mysql_on_boot()
        self.assertEqual(1, mock_execute.call_count)
        mock_execute.assert_called_with(mysql_service['cmd_disable'],
                                        shell=True)

    @patch('trove.guestagent.datastore.mysql_common.service.LOG')
    @patch.object(operating_system, 'service_discovery',
                  side_effect=KeyError('error'))
    @patch.object(utils, 'execute_with_timeout', return_value=('0', ''))
    def test_fail__disable_mysql_on_boot(self, mock_execute, mock_service,
                                         mock_logging):
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

    @patch.multiple(pkg.Package, pkg_is_installed=Mock(return_value=False),
                    pkg_install=DEFAULT)
    def test_install(self, pkg_install):
        self.mySqlApp._install_mysql = Mock()
        utils.execute_with_timeout = Mock()
        self.mySqlApp._clear_mysql_config = Mock()
        self.mySqlApp._create_mysql_confd_dir = Mock()
        self.mySqlApp.start_mysql = Mock()
        self.mySqlApp.install_if_needed(["package"])
        self.assertTrue(pkg_install.called)
        self.assert_reported_status(rd_instance.ServiceStatuses.NEW)

    @patch.object(operating_system, 'write_file')
    def test_save_authentication_properties(self, write_file_mock):
        self.mySqlApp._save_authentication_properties("some_password")
        write_file_mock.assert_called_once_with(
            MySqlApp.get_client_auth_file(),
            {'client': {'host': '127.0.0.1',
                        'password': 'some_password',
                        'user': dbaas_base.ADMIN_USER_NAME}},
            codec=MySqlApp.CFG_CODEC)

    @patch.object(utils, 'generate_random_password',
                  return_value='some_password')
    @patch.object(dbaas_base, 'clear_expired_password')
    def test_secure(self, clear_pwd_mock, auth_pwd_mock):

        self.mySqlApp.start_mysql = Mock()
        self.mySqlApp.stop_db = Mock()
        self.mySqlApp._reset_configuration = Mock()
        self.mySqlApp._apply_user_overrides = Mock()
        self.mysql_stops_successfully()
        self.mysql_starts_successfully()
        sqlalchemy.create_engine = Mock()

        with patch.object(BaseDbStatus, 'prepare_completed') as patch_pc:
            patch_pc.__get__ = Mock(return_value=True)
            self.mySqlApp.secure('contents')

            self.assertTrue(self.mySqlApp.stop_db.called)
            self.mySqlApp._reset_configuration.assert_has_calls(
                [call('contents', auth_pwd_mock.return_value)])

            self.assertTrue(self.mySqlApp.start_mysql.called)
            self.assert_reported_status(rd_instance.ServiceStatuses.NEW)

    @patch.object(dbaas, 'get_engine')
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

    @patch.multiple(pkg.Package, pkg_is_installed=Mock(return_value=False),
                    pkg_install=Mock(
                        side_effect=pkg.PkgPackageStateError("Install error")))
    def test_install_install_error(self):
        self.mySqlApp.start_mysql = Mock()
        self.mySqlApp.stop_db = Mock()
        self.mySqlApp._clear_mysql_config = Mock()
        self.mySqlApp._create_mysql_confd_dir = Mock()

        self.assertRaises(pkg.PkgPackageStateError,
                          self.mySqlApp.install_if_needed, ["package"])

        self.assert_reported_status(rd_instance.ServiceStatuses.NEW)

    @patch.object(dbaas_base, 'clear_expired_password')
    def test_secure_write_conf_error(self, clear_pwd_mock):

        self.mySqlApp.start_mysql = Mock()
        self.mySqlApp.stop_db = Mock()
        self.mySqlApp._reset_configuration = Mock(
            side_effect=IOError("Could not write file"))
        self.mySqlApp._apply_user_overrides = Mock()
        self.mysql_stops_successfully()
        self.mysql_starts_successfully()
        sqlalchemy.create_engine = Mock()

        self.assertRaises(IOError, self.mySqlApp.secure, "foo")

        self.assertTrue(self.mySqlApp.stop_db.called)
        self.assertFalse(self.mySqlApp.start_mysql.called)
        self.assert_reported_status(rd_instance.ServiceStatuses.NEW)

    @patch.object(dbaas.MySqlApp, '_save_authentication_properties')
    @patch.object(dbaas, 'get_engine',
                  return_value=MagicMock(name='get_engine'))
    def test_reset_admin_password(self, mock_engine, mock_save_auth):
        with patch.object(dbaas.MySqlApp, 'local_sql_client',
                          return_value=self.mock_client):
            self.mySqlApp._create_admin_user = Mock()
            self.mySqlApp.reset_admin_password("newpassword")
            self.assertEqual(1, self.mySqlApp._create_admin_user.call_count)
            mock_save_auth.assert_called_once_with("newpassword")


class TextClauseMatcher(object):

    def __init__(self, text):
        self.text = text

    def __repr__(self):
        return "TextClause(%s)" % self.text

    def __eq__(self, arg):
        print("Matching %s" % arg.text)
        return self.text in arg.text


class MySqlAppMockTest(trove_testtools.TestCase):

    def setUp(self):
        super(MySqlAppMockTest, self).setUp()
        self.orig_utils_execute_with_timeout = utils.execute_with_timeout
        create_engine_patcher = patch.object(sqlalchemy, 'create_engine')
        self.addCleanup(create_engine_patcher.stop)
        create_engine_patcher.start()

        self.mock_cli_ctx_mgr = Mock()
        self.mock_client = MagicMock()
        self.mock_cli_ctx_mgr.__enter__ = Mock(return_value=self.mock_client)
        self.mock_cli_ctx_mgr.__exit__ = Mock()

        local_client_patcher = patch.object(dbaas.MySqlApp,
                                            'local_sql_client',
                                            return_value=self.mock_cli_ctx_mgr)
        self.addCleanup(local_client_patcher.stop)
        local_client_patcher.start()

    def tearDown(self):
        utils.execute_with_timeout = self.orig_utils_execute_with_timeout
        super(MySqlAppMockTest, self).tearDown()

    @patch.object(dbaas_base, 'clear_expired_password')
    @patch.object(utils, 'generate_random_password',
                  return_value='some_password')
    def test_secure_keep_root(self, auth_pwd_mock, clear_pwd_mock):
        with patch.object(self.mock_client,
                          'execute', return_value=None) as mock_execute:
            utils.execute_with_timeout = MagicMock(return_value=None)
            # skip writing the file for now
            with patch.object(os.path, 'isfile', return_value=False):
                mock_status = MagicMock()
                mock_status.wait_for_real_status_to_change_to = MagicMock(
                    return_value=True)
                app = MySqlApp(mock_status)
                app._reset_configuration = MagicMock()
                app.start_mysql = MagicMock(return_value=None)
                app._wait_for_mysql_to_be_really_alive = MagicMock(
                    return_value=True)
                app.stop_db = MagicMock(return_value=None)
                app.secure('foo')
                reset_config_calls = [call('foo', auth_pwd_mock.return_value)]
                app._reset_configuration.assert_has_calls(reset_config_calls)
                self.assertTrue(mock_execute.called)

    @patch.object(dbaas_base, 'clear_expired_password')
    @patch('trove.guestagent.datastore.mysql.service.MySqlApp'
           '.get_auth_password', return_value='some_password')
    def test_secure_with_mycnf_error(self, auth_pwd_mock, clear_pwd_mock):
        with patch.object(self.mock_client,
                          'execute', return_value=None) as mock_execute:
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
                    self.assertRaises(RuntimeError, app.secure, None)
                    self.assertTrue(mock_execute.called)
                    # At least called twice
                    self.assertTrue(mock_execute.call_count >= 2)
                    (mock_status.wait_for_real_status_to_change_to.
                     assert_called_with(rd_instance.ServiceStatuses.SHUTDOWN,
                                        app.state_change_wait_time, False))


class MySqlRootStatusTest(trove_testtools.TestCase):

    def setUp(self):
        super(MySqlRootStatusTest, self).setUp()
        self.orig_utils_execute_with_timeout = utils.execute_with_timeout
        create_engine_patcher = patch.object(sqlalchemy, 'create_engine')
        self.addCleanup(create_engine_patcher.stop)
        create_engine_patcher.start()
        mysql_app_patcher = patch.multiple(MySqlApp, get_engine=DEFAULT,
                                           configuration_manager=DEFAULT)
        self.addCleanup(mysql_app_patcher.stop)
        mysql_app_patcher.start()

        self.mock_cli_ctx_mgr = Mock()
        self.mock_client = MagicMock()
        self.mock_cli_ctx_mgr.__enter__ = Mock(return_value=self.mock_client)
        self.mock_cli_ctx_mgr.__exit__ = Mock()

        local_client_patcher = patch.object(dbaas.MySqlRootAccess,
                                            'local_sql_client',
                                            return_value=self.mock_cli_ctx_mgr)
        self.addCleanup(local_client_patcher.stop)
        local_client_patcher.start()

    def tearDown(self):
        utils.execute_with_timeout = self.orig_utils_execute_with_timeout
        super(MySqlRootStatusTest, self).tearDown()

    @patch.object(dbaas.MySqlApp, 'get_auth_password',
                  return_value='some_password')
    def test_root_is_enabled(self, auth_pwd_mock):
        mock_rs = MagicMock()
        mock_rs.rowcount = 1
        with patch.object(self.mock_client, 'execute', return_value=mock_rs):
            self.assertTrue(MySqlRootAccess().is_root_enabled())

    @patch.object(dbaas.MySqlApp, 'get_auth_password',
                  return_value='some_password')
    def test_root_is_not_enabled(self, auth_pwd_mock):
        mock_rs = MagicMock()
        mock_rs.rowcount = 0
        with patch.object(self.mock_client, 'execute', return_value=mock_rs):
            self.assertFalse(MySqlRootAccess().is_root_enabled())

    @patch.object(dbaas_base, 'clear_expired_password')
    @patch.object(dbaas.MySqlApp, 'get_auth_password',
                  return_value='some_password')
    def test_enable_root(self, auth_pwd_mock, clear_pwd_mock):
        with patch.object(self.mock_client,
                          'execute', return_value=None) as mock_execute:
            # invocation
            user_ser = MySqlRootAccess().enable_root()
            # verification
            self.assertIsNotNone(user_ser)
            mock_execute.assert_any_call(TextClauseMatcher('CREATE USER'),
                                         user='root', host='%')
            mock_execute.assert_any_call(TextClauseMatcher(
                'GRANT ALL PRIVILEGES ON *.*'))
            mock_execute.assert_any_call(TextClauseMatcher(
                'UPDATE mysql.user'))

    def test_root_disable(self):
        with patch.object(self.mock_client,
                          'execute', return_value=None) as mock_execute:
            # invocation
            MySqlRootAccess().disable_root()
            # verification
            mock_execute.assert_any_call(TextClauseMatcher(
                sql_query.REMOVE_ROOT))


class MockStats:
    f_blocks = 1024 ** 2
    f_bsize = 4096
    f_bfree = 512 * 1024


class InterrogatorTest(trove_testtools.TestCase):

    def tearDown(self):
        super(InterrogatorTest, self).tearDown()

    def test_to_gb(self):
        result = to_gb(123456789)
        self.assertEqual(0.11, result)

    def test_to_gb_small(self):
        result = to_gb(2)
        self.assertEqual(0.01, result)

    def test_to_gb_zero(self):
        result = to_gb(0)
        self.assertEqual(0.0, result)

    def test_to_mb(self):
        result = to_mb(123456789)
        self.assertEqual(117.74, result)

    def test_to_mb_small(self):
        result = to_mb(2)
        self.assertEqual(0.01, result)

    def test_to_mb_zero(self):
        result = to_mb(0)
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

    @patch('trove.guestagent.dbaas.LOG')
    def test_get_filesystem_volume_stats_error(self, *args):
        with patch.object(os, 'statvfs', side_effect=OSError):
            self.assertRaises(
                RuntimeError,
                get_filesystem_volume_stats, '/nonexistent/path')


class ServiceRegistryTest(trove_testtools.TestCase):

    def setUp(self):
        super(ServiceRegistryTest, self).setUp()

    def tearDown(self):
        super(ServiceRegistryTest, self).tearDown()

    def test_datastore_registry_with_extra_manager(self):
        datastore_registry_ext_test = {
            'test': 'trove.guestagent.datastore.test.manager.Manager',
        }
        with patch.object(dbaas_sr, 'get_custom_managers',
                          return_value=datastore_registry_ext_test):
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
            self.assertEqual('trove.guestagent.datastore.experimental.'
                             'cassandra.manager.Manager',
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
        with patch.object(dbaas_sr, 'get_custom_managers',
                          return_value=datastore_registry_ext_test):
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
            self.assertEqual('trove.guestagent.datastore.experimental.'
                             'cassandra.manager.Manager',
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
        with patch.object(dbaas_sr, 'get_custom_managers',
                          return_value=datastore_registry_ext_test):
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
            self.assertEqual('trove.guestagent.datastore.experimental.'
                             'cassandra.manager.Manager',
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
            self.assertEqual('trove.guestagent.datastore.experimental.vertica.'
                             'manager.Manager',
                             test_dict.get('vertica'))
            self.assertEqual('trove.guestagent.datastore.experimental.db2.'
                             'manager.Manager',
                             test_dict.get('db2'))
            self.assertEqual('trove.guestagent.datastore.experimental.mariadb.'
                             'manager.Manager',
                             test_dict.get('mariadb'))


class KeepAliveConnectionTest(trove_testtools.TestCase):

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


class BaseDbStatusTest(trove_testtools.TestCase):

    def setUp(self):
        super(BaseDbStatusTest, self).setUp()
        util.init_db()
        self.orig_dbaas_time_sleep = time.sleep
        self.orig_time_time = time.time
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
        time.sleep = self.orig_dbaas_time_sleep
        time.time = self.orig_time_time
        InstanceServiceStatus.find_by(instance_id=self.FAKE_ID).delete()
        dbaas.CONF.guest_id = None
        super(BaseDbStatusTest, self).tearDown()

    @patch.object(operating_system, 'write_file')
    def test_begin_install(self, mock_write_file):
        base_db_status = BaseDbStatus()

        base_db_status.begin_install()

        self.assertEqual(rd_instance.ServiceStatuses.BUILDING,
                         base_db_status.status)

    def test_begin_restart(self):
        base_db_status = BaseDbStatus()
        base_db_status.restart_mode = False

        base_db_status.begin_restart()

        self.assertTrue(base_db_status.restart_mode)

    def test_end_restart(self):
        base_db_status = BaseDbStatus()
        base_db_status._get_actual_db_status = Mock(
            return_value=rd_instance.ServiceStatuses.SHUTDOWN)

        with patch.object(BaseDbStatus, 'prepare_completed') as patch_pc:
            patch_pc.__get__ = Mock(return_value=True)
            base_db_status.end_restart()

            self.assertEqual(rd_instance.ServiceStatuses.SHUTDOWN,
                             base_db_status.status)
            self.assertFalse(base_db_status.restart_mode)

    def test_is_installed(self):
        base_db_status = BaseDbStatus()

        with patch.object(BaseDbStatus, 'prepare_completed') as patch_pc:
            patch_pc.__get__ = Mock(return_value=True)
            self.assertTrue(base_db_status.is_installed)

    def test_is_installed_failed(self):
        base_db_status = BaseDbStatus()

        with patch.object(BaseDbStatus, 'prepare_completed') as patch_pc:
            patch_pc.__get__ = Mock(return_value=False)
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
        time.time = Mock(side_effect=faketime)

        self.assertTrue(base_db_status.
                        wait_for_real_status_to_change_to
                        (rd_instance.ServiceStatuses.RUNNING, 10))

    def test_wait_for_real_status_to_change_to_timeout(self):
        base_db_status = BaseDbStatus()
        base_db_status._get_actual_db_status = Mock(
            return_value=rd_instance.ServiceStatuses.RUNNING)
        time.sleep = Mock()
        time.time = Mock(side_effect=faketime)

        self.assertFalse(base_db_status.
                         wait_for_real_status_to_change_to
                         (rd_instance.ServiceStatuses.SHUTDOWN, 10))

    def _test_set_status(self, initial_status, new_status,
                         expected_status, install_done=False, force=False):
        base_db_status = BaseDbStatus()
        base_db_status.status = initial_status
        with patch.object(BaseDbStatus, 'prepare_completed') as patch_pc:
            patch_pc.__get__ = Mock(return_value=install_done)
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
                              rd_instance.ServiceStatuses.FAILED,
                              force=True)

    def test_set_status_to_build_pending(self):
        self._test_set_status(rd_instance.ServiceStatuses.BUILDING,
                              rd_instance.ServiceStatuses.INSTANCE_READY,
                              rd_instance.ServiceStatuses.INSTANCE_READY,
                              force=True)

    def test_set_status_to_shutdown(self):
        self._test_set_status(rd_instance.ServiceStatuses.RUNNING,
                              rd_instance.ServiceStatuses.SHUTDOWN,
                              rd_instance.ServiceStatuses.SHUTDOWN,
                              install_done=True)

    def test_wait_for_database_service_status(self):
        status = BaseDbStatus()
        expected_status = rd_instance.ServiceStatuses.RUNNING
        timeout = 10
        update_db = False

        # Test a successful call.
        with patch.multiple(
                status,
                wait_for_real_status_to_change_to=Mock(return_value=True),
                cleanup_stalled_db_services=DEFAULT):
            self.assertTrue(
                status._wait_for_database_service_status(
                    expected_status, timeout, update_db))
            status.wait_for_real_status_to_change_to.assert_called_once_with(
                expected_status, timeout, update_db)
            self.assertFalse(status.cleanup_stalled_db_services.called)

        # Test a failing call.
        with patch.multiple(
                status,
                wait_for_real_status_to_change_to=Mock(return_value=False),
                cleanup_stalled_db_services=DEFAULT):
            self.assertFalse(
                status._wait_for_database_service_status(
                    expected_status, timeout, update_db))
            status.wait_for_real_status_to_change_to.assert_called_once_with(
                expected_status, timeout, update_db)
            status.cleanup_stalled_db_services.assert_called_once_with()

        # Test a failing call with an error raised from the cleanup code.
        # No exception should propagate out of the cleanup block.
        with patch.multiple(
                status,
                wait_for_real_status_to_change_to=Mock(return_value=False),
                cleanup_stalled_db_services=Mock(
                    side_effect=Exception("Error in cleanup."))):
            self.assertFalse(
                status._wait_for_database_service_status(
                    expected_status, timeout, update_db))
            status.wait_for_real_status_to_change_to.assert_called_once_with(
                expected_status, timeout, update_db)
            status.cleanup_stalled_db_services.assert_called_once_with()

    def test_start_db_service(self):
        status = BaseDbStatus()
        service_candidates = ['name1', 'name2']

        # Test a successful call with setting auto-start enabled.
        with patch.object(
                status, '_wait_for_database_service_status',
                return_value=True) as service_call:
            with patch.multiple(operating_system, start_service=DEFAULT,
                                enable_service_on_boot=DEFAULT) as os_cmd:
                status.start_db_service(
                    service_candidates, 10, enable_on_boot=True)
                service_call.assert_called_once_with(
                    rd_instance.ServiceStatuses.RUNNING, 10, False)
                os_cmd['start_service'].assert_called_once_with(
                    service_candidates)
                os_cmd['enable_service_on_boot'].assert_called_once_with(
                    service_candidates)

        # Test a successful call without auto-start.
        with patch.object(
                status, '_wait_for_database_service_status',
                return_value=True) as service_call:
            with patch.multiple(operating_system, start_service=DEFAULT,
                                enable_service_on_boot=DEFAULT) as os_cmd:
                status.start_db_service(
                    service_candidates, 10, enable_on_boot=False)
                service_call.assert_called_once_with(
                    rd_instance.ServiceStatuses.RUNNING, 10, False)
                os_cmd['start_service'].assert_called_once_with(
                    service_candidates)
                self.assertFalse(os_cmd['enable_service_on_boot'].called)

        # Test a failing call.
        # The auto-start setting should not get updated if the service call
        # fails.
        with patch.object(
                status, '_wait_for_database_service_status',
                return_value=False) as service_call:
            with patch.multiple(operating_system, start_service=DEFAULT,
                                enable_service_on_boot=DEFAULT) as os_cmd:
                self.assertRaisesRegexp(
                    RuntimeError, "Database failed to start.",
                    status.start_db_service,
                    service_candidates, 10, enable_on_boot=True)
                os_cmd['start_service'].assert_called_once_with(
                    service_candidates)
                self.assertFalse(os_cmd['enable_service_on_boot'].called)

    def test_stop_db_service(self):
        status = BaseDbStatus()
        service_candidates = ['name1', 'name2']

        # Test a successful call with setting auto-start disabled.
        with patch.object(
                status, '_wait_for_database_service_status',
                return_value=True) as service_call:
            with patch.multiple(operating_system, stop_service=DEFAULT,
                                disable_service_on_boot=DEFAULT) as os_cmd:
                status.stop_db_service(
                    service_candidates, 10, disable_on_boot=True)
                service_call.assert_called_once_with(
                    rd_instance.ServiceStatuses.SHUTDOWN, 10, False)
                os_cmd['stop_service'].assert_called_once_with(
                    service_candidates)
                os_cmd['disable_service_on_boot'].assert_called_once_with(
                    service_candidates)

        # Test a successful call without auto-start.
        with patch.object(
                status, '_wait_for_database_service_status',
                return_value=True) as service_call:
            with patch.multiple(operating_system, stop_service=DEFAULT,
                                disable_service_on_boot=DEFAULT) as os_cmd:
                status.stop_db_service(
                    service_candidates, 10, disable_on_boot=False)
                service_call.assert_called_once_with(
                    rd_instance.ServiceStatuses.SHUTDOWN, 10, False)
                os_cmd['stop_service'].assert_called_once_with(
                    service_candidates)
                self.assertFalse(os_cmd['disable_service_on_boot'].called)

        # Test a failing call.
        # The auto-start setting should not get updated if the service call
        # fails.
        with patch.object(
                status, '_wait_for_database_service_status',
                return_value=False) as service_call:
            with patch.multiple(operating_system, stop_service=DEFAULT,
                                disable_service_on_boot=DEFAULT) as os_cmd:
                self.assertRaisesRegexp(
                    RuntimeError, "Database failed to stop.",
                    status.stop_db_service,
                    service_candidates, 10, disable_on_boot=True)
                os_cmd['stop_service'].assert_called_once_with(
                    service_candidates)
                self.assertFalse(os_cmd['disable_service_on_boot'].called)

    def test_restart_db_service(self):
        status = BaseDbStatus()
        service_candidates = ['name1', 'name2']

        # Test the restart flow (stop followed by start).
        # Assert that the auto-start setting does not get changed and the
        # Trove instance status updates are suppressed during restart.
        with patch.multiple(
                status, start_db_service=DEFAULT, stop_db_service=DEFAULT,
                begin_restart=DEFAULT, end_restart=DEFAULT):
            status.restart_db_service(service_candidates, 10)
            status.begin_restart.assert_called_once_with()
            status.stop_db_service.assert_called_once_with(
                service_candidates, 10, disable_on_boot=False, update_db=False)
            status.start_db_service.assert_called_once_with(
                service_candidates, 10, enable_on_boot=False, update_db=False)
            status.end_restart.assert_called_once_with()

        # Test a failing call.
        # Assert the status heartbeat gets re-enabled.
        with patch.multiple(
                status, start_db_service=Mock(
                    side_effect=Exception("Error in database start.")),
                stop_db_service=DEFAULT, begin_restart=DEFAULT,
                end_restart=DEFAULT):
            self.assertRaisesRegexp(
                RuntimeError, "Database restart failed.",
                status.restart_db_service, service_candidates, 10)
            status.begin_restart.assert_called_once_with()
            status.end_restart.assert_called_once_with()


class MySqlAppStatusTest(trove_testtools.TestCase):

    def setUp(self):
        super(MySqlAppStatusTest, self).setUp()
        util.init_db()
        self.orig_utils_execute_with_timeout = \
            dbaas_base.utils.execute_with_timeout
        self.orig_load_mysqld_options = dbaas_base.load_mysqld_options
        self.orig_dbaas_base_os_path_exists = dbaas_base.os.path.exists
        self.orig_dbaas_time_sleep = time.sleep
        self.orig_time_time = time.time
        self.FAKE_ID = str(uuid4())
        InstanceServiceStatus.create(instance_id=self.FAKE_ID,
                                     status=rd_instance.ServiceStatuses.NEW)
        dbaas.CONF.guest_id = self.FAKE_ID

    def tearDown(self):
        dbaas_base.utils.execute_with_timeout = \
            self.orig_utils_execute_with_timeout
        dbaas_base.load_mysqld_options = self.orig_load_mysqld_options
        dbaas_base.os.path.exists = self.orig_dbaas_base_os_path_exists
        time.sleep = self.orig_dbaas_time_sleep
        time.time = self.orig_time_time
        InstanceServiceStatus.find_by(instance_id=self.FAKE_ID).delete()
        dbaas.CONF.guest_id = None
        super(MySqlAppStatusTest, self).tearDown()

    def test_get_actual_db_status(self):

        dbaas_base.utils.execute_with_timeout = Mock(return_value=(None, None))

        self.mySqlAppStatus = MySqlAppStatus.get()
        status = self.mySqlAppStatus._get_actual_db_status()

        self.assertEqual(rd_instance.ServiceStatuses.RUNNING, status)

    @patch.object(utils, 'execute_with_timeout',
                  side_effect=ProcessExecutionError())
    @patch.object(os.path, 'exists', return_value=True)
    @patch('trove.guestagent.datastore.mysql_common.service.LOG')
    def test_get_actual_db_status_error_crashed(self, mock_logging,
                                                mock_exists,
                                                mock_execute):
        dbaas_base.load_mysqld_options = Mock(return_value={})
        self.mySqlAppStatus = MySqlAppStatus.get()
        status = self.mySqlAppStatus._get_actual_db_status()
        self.assertEqual(rd_instance.ServiceStatuses.CRASHED, status)

    @patch('trove.guestagent.datastore.mysql_common.service.LOG')
    def test_get_actual_db_status_error_shutdown(self, *args):

        mocked = Mock(side_effect=ProcessExecutionError())
        dbaas_base.utils.execute_with_timeout = mocked
        dbaas_base.load_mysqld_options = Mock(return_value={})
        dbaas_base.os.path.exists = Mock(return_value=False)

        self.mySqlAppStatus = MySqlAppStatus.get()
        status = self.mySqlAppStatus._get_actual_db_status()

        self.assertEqual(rd_instance.ServiceStatuses.SHUTDOWN, status)

    @patch('trove.guestagent.datastore.mysql_common.service.LOG')
    def test_get_actual_db_status_error_blocked(self, *args):

        dbaas_base.utils.execute_with_timeout = MagicMock(
            side_effect=[ProcessExecutionError(), ("some output", None)])
        dbaas_base.load_mysqld_options = Mock()
        dbaas_base.os.path.exists = Mock(return_value=True)

        self.mySqlAppStatus = MySqlAppStatus.get()
        status = self.mySqlAppStatus._get_actual_db_status()

        self.assertEqual(rd_instance.ServiceStatuses.BLOCKED, status)


class TestRedisApp(BaseAppTest.AppTestCase):

    def setUp(self):
        super(TestRedisApp, self).setUp(str(uuid4()))
        self.orig_os_path_eu = os.path.expanduser
        os.path.expanduser = Mock(return_value='/tmp/.file')

        with patch.object(RedisApp, '_build_admin_client'):
            with patch.object(ImportOverrideStrategy,
                              '_initialize_import_directory'):
                self.redis = RedisApp(state_change_wait_time=0)
                self.redis.status = FakeAppStatus(
                    self.FAKE_ID,
                    rd_instance.ServiceStatuses.NEW)

        self.orig_os_path_isfile = os.path.isfile
        self.orig_utils_execute_with_timeout = utils.execute_with_timeout
        utils.execute_with_timeout = Mock()

    @property
    def app(self):
        return self.redis

    @property
    def appStatus(self):
        return self.redis.status

    @property
    def expected_state_change_timeout(self):
        return self.redis.state_change_wait_time

    @property
    def expected_service_candidates(self):
        return RedisSystem.SERVICE_CANDIDATES

    def tearDown(self):
        os.path.isfile = self.orig_os_path_isfile
        os.path.expanduser = self.orig_os_path_eu
        utils.execute_with_timeout = self.orig_utils_execute_with_timeout
        super(TestRedisApp, self).tearDown()

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
        with patch.object(utils, 'execute_with_timeout',
                          return_value=('0', '')):
            with patch.object(pkg.Package, 'pkg_install', return_value=None):
                with patch.object(RedisApp, 'start_db', return_value=None):
                    self.app._install_redis('redis')
                    pkg.Package.pkg_install.assert_any_call('redis', {}, 1200)
                    RedisApp.start_db.assert_any_call()
                    self.assertTrue(utils.execute_with_timeout.called)

    @patch.object(utils, 'execute_with_timeout', return_value=('0', ''))
    def test_service_cleanup(self, exec_mock):
        rservice.RedisAppStatus(Mock()).cleanup_stalled_db_services()
        exec_mock.assert_called_once_with('pkill', '-9', 'redis-server',
                                          run_as_root=True, root_helper='sudo')


class CassandraDBAppTest(BaseAppTest.AppTestCase):

    @patch.object(ImportOverrideStrategy, '_initialize_import_directory')
    @patch('trove.guestagent.datastore.experimental.cassandra.service.LOG')
    def setUp(self, mock_logging, _):
        super(CassandraDBAppTest, self).setUp(str(uuid4()))
        self.sleep = time.sleep
        self.orig_time_time = time.time
        self.pkg_version = cass_service.packager.pkg_version
        self.pkg = cass_service.packager
        util.init_db()
        self.cassandra = cass_service.CassandraApp()
        self.cassandra.status = FakeAppStatus(self.FAKE_ID,
                                              rd_instance.ServiceStatuses.NEW)
        self.orig_unlink = os.unlink

    @property
    def app(self):
        return self.cassandra

    @property
    def appStatus(self):
        return self.cassandra.status

    @property
    def expected_state_change_timeout(self):
        return self.cassandra.state_change_wait_time

    @property
    def expected_service_candidates(self):
        return self.cassandra.service_candidates

    def tearDown(self):
        time.sleep = self.sleep
        time.time = self.orig_time_time
        cass_service.packager.pkg_version = self.pkg_version
        cass_service.packager = self.pkg
        super(CassandraDBAppTest, self).tearDown()

    def assert_reported_status(self, expected_status):
        service_status = InstanceServiceStatus.find_by(
            instance_id=self.FAKE_ID)
        self.assertEqual(expected_status, service_status.status)

    @patch.object(utils, 'execute_with_timeout')
    def test_service_cleanup(self, exec_mock):
        cass_service.CassandraAppStatus(Mock()).cleanup_stalled_db_services()
        exec_mock.assert_called_once_with(self.cassandra.CASSANDRA_KILL_CMD,
                                          shell=True)

    @patch('trove.guestagent.datastore.experimental.cassandra.service.LOG')
    def test_install(self, _):

        self.cassandra._install_db = Mock()
        self.pkg.pkg_is_installed = Mock(return_value=False)
        self.cassandra.install_if_needed(['cassandra'])
        self.assertTrue(self.cassandra._install_db.called)
        self.assert_reported_status(rd_instance.ServiceStatuses.NEW)

    @patch('trove.guestagent.datastore.experimental.cassandra.service.LOG')
    def test_install_install_error(self, _):

        self.cassandra.start_db = Mock()
        self.cassandra.stop_db = Mock()
        self.pkg.pkg_is_installed = Mock(return_value=False)
        self.cassandra._install_db = Mock(
            side_effect=pkg.PkgPackageStateError("Install error"))

        self.assertRaises(pkg.PkgPackageStateError,
                          self.cassandra.install_if_needed,
                          ['cassandra=1.2.10'])

        self.assert_reported_status(rd_instance.ServiceStatuses.NEW)


class CouchbaseAppTest(BaseAppTest.AppTestCase):

    def fake_couchbase_service_discovery(self, candidates):
        return {
            'cmd_start': 'start',
            'cmd_stop': 'stop',
            'cmd_enable': 'enable',
            'cmd_disable': 'disable'
        }

    def setUp(self):
        super(CouchbaseAppTest, self).setUp(str(uuid4()))
        self.orig_utils_execute_with_timeout = (
            couchservice.utils.execute_with_timeout)
        self.orig_time_sleep = time.sleep
        self.orig_time_time = time.time
        time.sleep = Mock()
        time.time = Mock(side_effect=faketime)
        self.orig_service_discovery = operating_system.service_discovery
        self.orig_get_ip = netutils.get_my_ipv4
        operating_system.service_discovery = (
            self.fake_couchbase_service_discovery)
        netutils.get_my_ipv4 = Mock()
        status = FakeAppStatus(self.FAKE_ID,
                               rd_instance.ServiceStatuses.NEW)
        self.couchbaseApp = couchservice.CouchbaseApp(status)
        dbaas.CONF.guest_id = self.FAKE_ID

    @property
    def app(self):
        return self.couchbaseApp

    @property
    def appStatus(self):
        return self.couchbaseApp.status

    @property
    def expected_state_change_timeout(self):
        return self.couchbaseApp.state_change_wait_time

    @property
    def expected_service_candidates(self):
        return couchservice.system.SERVICE_CANDIDATES

    @patch.object(utils, 'execute_with_timeout')
    def test_service_cleanup(self, exec_mock):
        couchservice.CouchbaseAppStatus().cleanup_stalled_db_services()
        exec_mock.assert_called_once_with(couchservice.system.cmd_kill)

    def tearDown(self):
        couchservice.utils.execute_with_timeout = (
            self.orig_utils_execute_with_timeout)
        netutils.get_my_ipv4 = self.orig_get_ip
        operating_system.service_discovery = self.orig_service_discovery
        time.sleep = self.orig_time_sleep
        time.time = self.orig_time_time
        dbaas.CONF.guest_id = None
        super(CouchbaseAppTest, self).tearDown()

    def test_install_when_couchbase_installed(self):
        couchservice.packager.pkg_is_installed = Mock(return_value=True)
        couchservice.utils.execute_with_timeout = Mock()

        self.couchbaseApp.install_if_needed(["package"])
        self.assertTrue(couchservice.packager.pkg_is_installed.called)
        self.assert_reported_status(rd_instance.ServiceStatuses.NEW)


class CouchDBAppTest(BaseAppTest.AppTestCase):

    def fake_couchdb_service_discovery(self, candidates):
        return {
            'cmd_start': 'start',
            'cmd_stop': 'stop',
            'cmd_enable': 'enable',
            'cmd_disable': 'disable'
        }

    def setUp(self):
        super(CouchDBAppTest, self).setUp(str(uuid4()))
        self.orig_utils_execute_with_timeout = (
            couchdb_service.utils.execute_with_timeout)
        self.orig_time_sleep = time.sleep
        self.orig_time_time = time.time
        time.sleep = Mock()
        time.time = Mock(side_effect=faketime)
        self.orig_service_discovery = operating_system.service_discovery
        self.orig_get_ip = netutils.get_my_ipv4
        operating_system.service_discovery = (
            self.fake_couchdb_service_discovery)
        netutils.get_my_ipv4 = Mock()
        util.init_db()
        status = FakeAppStatus(self.FAKE_ID,
                               rd_instance.ServiceStatuses.NEW)
        self.couchdbApp = couchdb_service.CouchDBApp(status)
        dbaas.CONF.guest_id = self.FAKE_ID

    @property
    def app(self):
        return self.couchdbApp

    @property
    def appStatus(self):
        return self.couchdbApp.status

    @property
    def expected_state_change_timeout(self):
        return self.couchdbApp.state_change_wait_time

    @property
    def expected_service_candidates(self):
        return couchdb_service.system.SERVICE_CANDIDATES

    def tearDown(self):
        couchdb_service.utils.execute_with_timeout = (
            self.orig_utils_execute_with_timeout)
        netutils.get_my_ipv4 = self.orig_get_ip
        operating_system.service_discovery = self.orig_service_discovery
        time.sleep = self.orig_time_sleep
        time.time = self.orig_time_time
        dbaas.CONF.guest_id = None
        super(CouchDBAppTest, self).tearDown()

    def test_install_when_couchdb_installed(self):
        couchdb_service.packager.pkg_is_installed = Mock(return_value=True)
        couchdb_service.utils.execute_with_timeout = Mock()

        self.couchdbApp.install_if_needed(["package"])
        self.assertTrue(couchdb_service.packager.pkg_is_installed.called)
        self.assert_reported_status(rd_instance.ServiceStatuses.NEW)


class MongoDBAppTest(BaseAppTest.AppTestCase):

    def fake_mongodb_service_discovery(self, candidates):
        return {
            'cmd_start': 'start',
            'cmd_stop': 'stop',
            'cmd_enable': 'enable',
            'cmd_disable': 'disable'
        }

    @patch.object(ImportOverrideStrategy, '_initialize_import_directory')
    def setUp(self, _):
        super(MongoDBAppTest, self).setUp(str(uuid4()))
        self.orig_utils_execute_with_timeout = (mongo_service.
                                                utils.execute_with_timeout)
        self.orig_time_sleep = time.sleep
        self.orig_time_time = time.time
        self.orig_packager = mongo_system.PACKAGER
        self.orig_service_discovery = operating_system.service_discovery
        self.orig_os_unlink = os.unlink
        self.orig_os_path_eu = os.path.expanduser
        os.path.expanduser = Mock(return_value='/tmp/.file')

        operating_system.service_discovery = (
            self.fake_mongodb_service_discovery)
        util.init_db()

        self.mongoDbApp = mongo_service.MongoDBApp()
        self.mongoDbApp.status = FakeAppStatus(self.FAKE_ID,
                                               rd_instance.ServiceStatuses.NEW)
        time.sleep = Mock()
        time.time = Mock(side_effect=faketime)
        os.unlink = Mock()

    @property
    def app(self):
        return self.mongoDbApp

    @property
    def appStatus(self):
        return self.mongoDbApp.status

    @property
    def expected_state_change_timeout(self):
        return self.mongoDbApp.state_change_wait_time

    @property
    def expected_service_candidates(self):
        return mongo_system.MONGOD_SERVICE_CANDIDATES

    @patch.object(utils, 'execute_with_timeout')
    def test_service_cleanup(self, exec_mock):
        self.appStatus.cleanup_stalled_db_services()
#     def cleanup_stalled_db_services(self):
#         out, err = utils.execute_with_timeout(system.FIND_PID, shell=True)
#         pid = "".join(out.split(" ")[1:2])
#         utils.execute_with_timeout(system.MONGODB_KILL % pid, shell=True)

    def tearDown(self):
        mongo_service.utils.execute_with_timeout = (
            self.orig_utils_execute_with_timeout)
        time.sleep = self.orig_time_sleep
        time.time = self.orig_time_time
        mongo_system.PACKAGER = self.orig_packager
        operating_system.service_discovery = self.orig_service_discovery
        os.unlink = self.orig_os_unlink
        os.path.expanduser = self.orig_os_path_eu
        super(MongoDBAppTest, self).tearDown()

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


class VerticaAppStatusTest(trove_testtools.TestCase):

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

    @patch('trove.guestagent.datastore.experimental.vertica.service.LOG')
    def test_get_actual_db_status_error_crashed(self, *args):
        self.verticaAppStatus = VerticaAppStatus()
        with patch.object(vertica_system, 'shell_execute',
                          MagicMock(side_effect=ProcessExecutionError('problem'
                                                                      ))):
            status = self.verticaAppStatus._get_actual_db_status()
        self.assertEqual(rd_instance.ServiceStatuses.CRASHED, status)


class VerticaAppTest(trove_testtools.TestCase):

    def setUp(self):
        super(VerticaAppTest, self).setUp()
        self.FAKE_ID = 1000
        self.appStatus = FakeAppStatus(self.FAKE_ID,
                                       rd_instance.ServiceStatuses.NEW)
        self.app = VerticaApp(self.appStatus)
        self.setread = VolumeDevice.set_readahead_size
        self.Popen = subprocess.Popen

        vertica_system_patcher = patch.multiple(
            vertica_system,
            shell_execute=MagicMock(return_value=('', '')),
            exec_vsql_command=MagicMock(return_value=('', '')))
        self.addCleanup(vertica_system_patcher.stop)
        vertica_system_patcher.start()

        VolumeDevice.set_readahead_size = Mock()
        subprocess.Popen = Mock()
        self.test_config = ConfigParser.ConfigParser()
        self.test_config.add_section('credentials')
        self.test_config.set('credentials',
                             'dbadmin_password', 'some_password')

    def tearDown(self):
        self.app = None
        VolumeDevice.set_readahead_size = self.setread
        subprocess.Popen = self.Popen
        super(VerticaAppTest, self).tearDown()

    def test_enable_root_is_root_not_enabled(self):
        app = VerticaApp(MagicMock())
        with patch.object(app, 'read_config', return_value=self.test_config):
            with patch.object(app, 'is_root_enabled', return_value=False):
                with patch.object(vertica_system, 'exec_vsql_command',
                                  MagicMock(side_effect=[['', ''],
                                                         ['', ''],
                                                         ['', '']])):
                    app.enable_root('root_password')
                    create_user_arguments = (
                        vertica_system.exec_vsql_command.call_args_list[0])
                    expected_create_user_cmd = (
                        vertica_system.CREATE_USER % ('root',
                                                      'root_password'))
                    create_user_arguments.assert_called_with(
                        'some_password', expected_create_user_cmd)

                    grant_role_arguments = (
                        vertica_system.exec_vsql_command.call_args_list[1])
                    expected_grant_role_cmd = (
                        vertica_system.GRANT_TO_USER % ('pseudosuperuser',
                                                        'root'))
                    grant_role_arguments.assert_called_with(
                        'some_password', expected_grant_role_cmd)

                    enable_user_arguments = (
                        vertica_system.exec_vsql_command.call_args_list[2])
                    expected_enable_user_cmd = (
                        vertica_system.ENABLE_FOR_USER % ('root',
                                                          'pseudosuperuser'
                                                          ))
                    enable_user_arguments.assert_called_with(
                        'some_password', expected_enable_user_cmd)

    @patch('trove.guestagent.datastore.experimental.vertica.service.LOG')
    def test_enable_root_is_root_not_enabled_failed(self, *args):
        app = VerticaApp(MagicMock())
        with patch.object(app, 'read_config', return_value=self.test_config):
            with patch.object(app, 'is_root_enabled', return_value=False):
                with patch.object(vertica_system, 'exec_vsql_command',
                                  MagicMock(side_effect=[['', 'err']])):
                    self.assertRaises(RuntimeError, app.enable_root,
                                      'root_password')

    @patch('trove.guestagent.datastore.experimental.vertica.service.LOG')
    def test_enable_root_is_root_enabled(self, *args):
        app = VerticaApp(MagicMock())
        with patch.object(app, 'read_config', return_value=self.test_config):
            with patch.object(app, 'is_root_enabled', return_value=True):
                with patch.object(vertica_system, 'exec_vsql_command',
                                  MagicMock(side_effect=[['', '']])):
                    app.enable_root('root_password')
                    alter_user_password_arguments = (
                        vertica_system.exec_vsql_command.call_args_list[0])
                    expected_alter_user_cmd = (
                        vertica_system.ALTER_USER_PASSWORD % ('root',
                                                              'root_password'
                                                              ))
                    alter_user_password_arguments.assert_called_with(
                        'some_password', expected_alter_user_cmd)

    @patch('trove.guestagent.datastore.experimental.vertica.service.LOG')
    def test_enable_root_is_root_enabled_failed(self, *arg):
        app = VerticaApp(MagicMock())
        with patch.object(app, 'read_config', return_value=self.test_config):
            with patch.object(app, 'is_root_enabled', return_value=True):
                with patch.object(vertica_system, 'exec_vsql_command',
                                  MagicMock(side_effect=[
                                      ['', ProcessExecutionError]])):
                    self.assertRaises(RuntimeError, app.enable_root,
                                      'root_password')

    def test_is_root_enable(self):
        app = VerticaApp(MagicMock())
        with patch.object(app, 'read_config', return_value=self.test_config):
            with patch.object(vertica_system, 'shell_execute',
                              MagicMock(side_effect=[['', '']])):
                app.is_root_enabled()
                user_exists_args = (
                    vertica_system.shell_execute.call_args_list[0])
                expected_user_exists_cmd = vertica_system.USER_EXISTS % (
                    'some_password', 'root')
                user_exists_args.assert_called_with(expected_user_exists_cmd,
                                                    'dbadmin')

    @patch('trove.guestagent.datastore.experimental.vertica.service.LOG')
    def test_is_root_enable_failed(self, *args):
        app = VerticaApp(MagicMock())
        with patch.object(app, 'read_config', return_value=self.test_config):
            with patch.object(vertica_system, 'shell_execute',
                              MagicMock(side_effect=[
                                  ['', ProcessExecutionError]])):
                self.assertRaises(RuntimeError, app.is_root_enabled)

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

    @patch('trove.guestagent.datastore.experimental.vertica.service.LOG')
    def test_failure_prepare_for_install_vertica(self, *args):
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

    @patch('trove.guestagent.datastore.experimental.vertica.service.LOG')
    def test_failure_install_vertica(self, *args):
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

    @patch('trove.guestagent.datastore.experimental.vertica.service.LOG')
    def test_failure_create_db(self, *args):
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
        with patch.object(BaseDbStatus, 'prepare_completed') as patch_pc:
            patch_pc.__get__ = Mock(return_value=True)
            with patch.object(VerticaApp, 'stop_db', return_value=None):
                with patch.object(VerticaApp, 'start_db', return_value=None):
                    mock_status.end_restart = MagicMock(
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
                mock_status.end_restart = MagicMock(
                    return_value=None)
                app.start_db()
                agent_start, db_start = subprocess.Popen.call_args_list
                agent_expected_command = [
                    'sudo', 'su', '-', 'root', '-c',
                    (vertica_system.VERTICA_AGENT_SERVICE_COMMAND % 'start')]
                db_expected_cmd = [
                    'sudo', 'su', '-', 'dbadmin', '-c',
                    (vertica_system.START_DB % ('db_srvr', 'some_password'))]
                self.assertTrue(mock_status.end_restart.called)
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
                    mock_status.end_restart = MagicMock(
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

    @patch('trove.guestagent.datastore.experimental.vertica.service.LOG')
    def test_stop_db_failure(self, *args):
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
                    mock_status.end_restart = MagicMock(
                        return_value=None)
                    self.assertRaises(RuntimeError, app.stop_db)

    def test_export_conf_to_members(self):
        self.app._export_conf_to_members(members=['member1', 'member2'])
        self.assertEqual(2, vertica_system.shell_execute.call_count)

    @patch('trove.guestagent.datastore.experimental.vertica.service.LOG')
    def test_fail__export_conf_to_members(self, *args):
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

    @patch('trove.guestagent.datastore.experimental.vertica.service.LOG')
    def test_fail_authorize_public_keys(self, *args):
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

    @patch('trove.guestagent.datastore.experimental.vertica.service.LOG')
    def test_fail_get_public_keys(self, *args):
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

    @patch('trove.guestagent.datastore.experimental.vertica.service.LOG')
    def test_failure__enable_db_on_boot(self, *args):
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

    @patch('trove.guestagent.datastore.experimental.vertica.service.LOG')
    def test_failure__disable_db_on_boot(self, *args):
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

    @patch('trove.guestagent.datastore.experimental.vertica.service.LOG')
    def test_fail_read_config(self, *args):
        with patch.object(ConfigParser.ConfigParser, 'read',
                          side_effect=ConfigParser.Error()):
            self.assertRaises(RuntimeError, self.app.read_config)

    def test_start_db_with_conf_changes(self):
        mock_status = MagicMock()
        type(mock_status)._is_restarting = PropertyMock(return_value=False)
        app = VerticaApp(mock_status)
        with patch.object(app, 'read_config',
                          return_value=self.test_config):
            app.start_db_with_conf_changes('test_config_contents')
            app.status.end_restart.assert_any_call()


class DB2AppTest(trove_testtools.TestCase):

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
        db2service.utils.execute_with_timeout = (
            self.orig_utils_execute_with_timeout)
        InstanceServiceStatus.find_by(instance_id=self.FAKE_ID).delete()
        dbaas.CONF.guest_id = None
        self.db2App = None
        super(DB2AppTest, self).tearDown()

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
        with patch.object(BaseDbStatus, 'prepare_completed') as patch_pc:
            patch_pc.__get__ = Mock(return_value=True)
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


class DB2AdminTest(trove_testtools.TestCase):

    def setUp(self):
        super(DB2AdminTest, self).setUp()
        self.db2Admin = db2service.DB2Admin()
        self.orig_utils_execute_with_timeout = (
            db2service.utils.execute_with_timeout)

    def tearDown(self):
        db2service.utils.execute_with_timeout = (
            self.orig_utils_execute_with_timeout)
        super(DB2AdminTest, self).tearDown()

    @patch('trove.guestagent.datastore.experimental.db2.service.LOG')
    def test_delete_database(self, *args):
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

    @patch('trove.guestagent.datastore.experimental.db2.service.LOG')
    def test_list_databases(self, *args):
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


class PXCAppTest(trove_testtools.TestCase):

    def setUp(self):
        super(PXCAppTest, self).setUp()
        self.orig_utils_execute_with_timeout = \
            dbaas_base.utils.execute_with_timeout
        self.orig_time_sleep = time.sleep
        self.orig_time_time = time.time
        self.orig_unlink = os.unlink
        self.orig_get_auth_password = pxc_service.PXCApp.get_auth_password
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
        time.time = Mock(side_effect=faketime)
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
        self.PXCApp = None
        dbaas_base.utils.execute_with_timeout = \
            self.orig_utils_execute_with_timeout
        time.sleep = self.orig_time_sleep
        time.time = self.orig_time_time
        os.unlink = self.orig_unlink
        pxc_system.service_discovery = self.orig_pxc_system_service_discovery
        pxc_service.PXCApp.get_auth_password = self.orig_get_auth_password
        InstanceServiceStatus.find_by(instance_id=self.FAKE_ID).delete()
        pxc_service.PXCApp.configuration_manager = \
            pxc_service.orig_configuration_manager
        sqlalchemy.create_engine = self.orig_create_engine
        super(PXCAppTest, self).tearDown()

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

    @patch.object(utils, 'execute_with_timeout', return_value=('0', ''))
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


class PostgresAppTest(BaseAppTest.AppTestCase):

    class FakePostgresApp(pg_manager.Manager):
        """Postgresql design is currently different than other datastores.
        It does not have an App class, only the Manager, so we fake one.
        The fake App just passes the calls onto the Postgres manager.
        """

        def restart(self):
            super(PostgresAppTest.FakePostgresApp, self).restart(Mock())

        def start_db(self):
            super(PostgresAppTest.FakePostgresApp, self).start_db(Mock())

        def stop_db(self):
            super(PostgresAppTest.FakePostgresApp, self).stop_db(Mock())

    @patch.object(pg_config.PgSqlConfig, '_find_config_file', return_value='')
    def setUp(self, _):
        super(PostgresAppTest, self).setUp(str(uuid4()))
        self.orig_time_sleep = time.sleep
        self.orig_time_time = time.time
        time.sleep = Mock()
        time.time = Mock(side_effect=faketime)
        status = FakeAppStatus(self.FAKE_ID,
                               rd_instance.ServiceStatuses.NEW)
        self.pg_status_patcher = patch.object(pg_status.PgSqlAppStatus, 'get',
                                              return_value=status)
        self.addCleanup(self.pg_status_patcher.stop)
        self.pg_status_patcher.start()
        self.postgres = PostgresAppTest.FakePostgresApp()

    @property
    def app(self):
        return self.postgres

    @property
    def appStatus(self):
        return self.postgres.status

    @property
    def expected_state_change_timeout(self):
        return CONF.state_change_wait_time

    @property
    def expected_service_candidates(self):
        return self.postgres.SERVICE_CANDIDATES

    def tearDown(self):
        time.sleep = self.orig_time_sleep
        time.time = self.orig_time_time
        super(PostgresAppTest, self).tearDown()
