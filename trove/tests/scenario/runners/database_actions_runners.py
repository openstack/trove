# Copyright 2015 Tesora Inc.
# All Rights Reserved.
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

from proboscis import SkipTest

from trove.common import exception
from trove.common.utils import poll_until
from trove.tests.scenario import runners
from trove.tests.scenario.runners.test_runners import SkipKnownBug
from trove.tests.scenario.runners.test_runners import TestRunner
from troveclient.compat import exceptions


class DatabaseActionsRunner(TestRunner):

    def __init__(self):
        super(DatabaseActionsRunner, self).__init__()
        self.db_defs = []

    @property
    def first_db_def(self):
        if self.db_defs:
            return self.db_defs[0]
        raise SkipTest("No valid database definitions provided.")

    @property
    def non_existing_db_def(self):
        db_def = self.test_helper.get_non_existing_database_definition()
        if db_def:
            return db_def
        raise SkipTest("No valid database definitions provided.")

    def run_databases_create(self, expected_http_code=202):
        databases = self.test_helper.get_valid_database_definitions()
        if databases:
            self.db_defs = self.assert_databases_create(
                self.instance_info.id, databases, expected_http_code)
        else:
            raise SkipTest("No valid database definitions provided.")

    def assert_databases_create(self, instance_id, serial_databases_def,
                                expected_http_code):
        self.auth_client.databases.create(instance_id, serial_databases_def)
        self.assert_client_code(expected_http_code, client=self.auth_client)
        self.wait_for_database_create(instance_id, serial_databases_def)
        return serial_databases_def

    def run_databases_list(self, expected_http_code=200):
        self.assert_databases_list(
            self.instance_info.id, self.db_defs, expected_http_code)

    def assert_databases_list(self, instance_id, expected_database_defs,
                              expected_http_code, limit=2):
        full_list = self.auth_client.databases.list(instance_id)
        self.assert_client_code(expected_http_code, client=self.auth_client)
        listed_databases = {database.name: database for database in full_list}
        self.assert_is_none(full_list.next,
                            "Unexpected pagination in the list.")

        for database_def in expected_database_defs:
            database_name = database_def['name']
            self.assert_true(
                database_name in listed_databases,
                "Database not included in the 'database-list' output: %s" %
                database_name)

        # Check that the system (ignored) databases are not included in the
        # output.
        system_databases = self.get_system_databases()
        self.assert_false(
            any(name in listed_databases for name in system_databases),
            "System databases should not be included in the 'database-list' "
            "output.")

        # Test list pagination.
        list_page = self.auth_client.databases.list(instance_id, limit=limit)
        self.assert_client_code(expected_http_code, client=self.auth_client)

        self.assert_true(len(list_page) <= limit)
        if len(full_list) > limit:
            self.assert_is_not_none(list_page.next, "List page is missing.")
        else:
            self.assert_is_none(list_page.next, "An extra page in the list.")
        marker = list_page.next

        self.assert_pagination_match(list_page, full_list, 0, limit)
        if marker:
            last_database = list_page[-1]
            expected_marker = last_database.name
            self.assert_equal(expected_marker, marker,
                              "Pagination marker should be the last element "
                              "in the page.")
            list_page = self.auth_client.databases.list(
                instance_id, marker=marker)
            self.assert_client_code(expected_http_code,
                                    client=self.auth_client)
            self.assert_pagination_match(
                list_page, full_list, limit, len(full_list))

    def run_database_create_with_no_attributes(
            self, expected_exception=exceptions.BadRequest,
            expected_http_code=400):
        self.assert_databases_create_failure(
            self.instance_info.id, {}, expected_exception, expected_http_code)

    def run_database_create_with_blank_name(
            self, expected_exception=exceptions.BadRequest,
            expected_http_code=400):
        self.assert_databases_create_failure(
            self.instance_info.id, {'name': ''},
            expected_exception, expected_http_code)

    def run_existing_database_create(
            self, expected_exception=exceptions.BadRequest,
            expected_http_code=400):
        self.assert_databases_create_failure(
            self.instance_info.id, self.first_db_def,
            expected_exception, expected_http_code)

    def assert_databases_create_failure(
            self, instance_id, serial_databases_def,
            expected_exception, expected_http_code):
        self.assert_raises(
            expected_exception,
            expected_http_code,
            self.auth_client.databases.create,
            instance_id,
            serial_databases_def)

    def run_system_database_create(
            self, expected_exception=exceptions.BadRequest,
            expected_http_code=400):
        # TODO(pmalik): Actions on system users and databases should probably
        # return Forbidden 403 instead. The current error messages are
        # confusing (talking about a malformed request).
        system_databases = self.get_system_databases()
        database_defs = [{'name': name} for name in system_databases]
        if system_databases:
            self.assert_databases_create_failure(
                self.instance_info.id, database_defs,
                expected_exception, expected_http_code)

    def run_database_delete(self, expected_http_code=202):
        for database_def in self.db_defs:
            self.assert_database_delete(
                self.instance_info.id, database_def['name'],
                expected_http_code)

    def assert_database_delete(
            self,
            instance_id,
            database_name,
            expected_http_code):
        self.auth_client.databases.delete(instance_id, database_name)
        self.assert_client_code(expected_http_code, client=self.auth_client)
        self._wait_for_database_delete(instance_id, database_name)

    def _wait_for_database_delete(self, instance_id, deleted_database_name):
        self.report.log("Waiting for deleted database to disappear from the "
                        "listing: %s" % deleted_database_name)

        def _db_is_gone():
            all_dbs = self.get_db_names(instance_id)
            return deleted_database_name not in all_dbs

        try:
            poll_until(_db_is_gone, time_out=self.GUEST_CAST_WAIT_TIMEOUT_SEC)
            self.report.log("Database is now gone from the instance.")
        except exception.PollTimeOut:
            self.fail("Database still listed after the poll timeout: %ds" %
                      self.GUEST_CAST_WAIT_TIMEOUT_SEC)

    def run_nonexisting_database_delete(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        self.assert_database_delete_failure(
            self.instance_info.id, self.non_existing_db_def['name'],
            expected_exception, expected_http_code)

    def run_system_database_delete(
            self, expected_exception=exceptions.BadRequest,
            expected_http_code=400):
        # TODO(pmalik): Actions on system users and databases should probably
        # return Forbidden 403 instead. The current error messages are
        # confusing (talking about a malformed request).
        system_databases = self.get_system_databases()
        if system_databases:
            for name in system_databases:
                self.assert_database_delete_failure(
                    self.instance_info.id, name,
                    expected_exception, expected_http_code)

    def assert_database_delete_failure(
            self, instance_id, database_name,
            expected_exception, expected_http_code):
        self.assert_raises(expected_exception, expected_http_code,
                           self.auth_client.databases.delete,
                           instance_id, database_name)

    def get_system_databases(self):
        return self.get_datastore_config_property('ignore_dbs')


class PostgresqlDatabaseActionsRunner(DatabaseActionsRunner):

    def run_system_database_create(self):
        raise SkipKnownBug(runners.BUG_WRONG_API_VALIDATION)

    def run_system_database_delete(self):
        raise SkipKnownBug(runners.BUG_WRONG_API_VALIDATION)
