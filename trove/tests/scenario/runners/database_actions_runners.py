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

from trove.tests.scenario.runners.test_runners import TestRunner
from troveclient.compat import exceptions


class DatabaseActionsRunner(TestRunner):

    # TODO(pmalik): I believe the 202 (Accepted) should be replaced by
    # 200 (OK) as the actions are generally very fast and their results
    # available immediately upon execution of the request. This would
    # likely require replacing GA casts with calls which I believe are
    # more appropriate anyways.

    def run_databases_create(self, expected_http_code=202):
        databases = self.test_helper.get_valid_database_definitions()
        self.db_defs = self.assert_databases_create(
            self.instance_info.id, databases, expected_http_code)

    def assert_databases_create(self, instance_id, serial_databases_def,
                                expected_http_code):
        self.auth_client.databases.create(instance_id, serial_databases_def)
        self.assert_client_code(expected_http_code)
        return serial_databases_def

    def run_databases_list(self, expected_http_code=200):
        self.assert_databases_list(
            self.instance_info.id, self.db_defs, expected_http_code)

    def assert_databases_list(self, instance_id, expected_database_defs,
                              expected_http_code, limit=2):
        full_list = self.auth_client.databases.list(instance_id)
        self.assert_client_code(expected_http_code)
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
        self.assert_client_code(expected_http_code)

        self.assert_true(len(list_page) <= limit)
        if len(full_list) > limit:
            self.assert_is_not_none(list_page.next, "List page is missing.")
        else:
            self.assert_is_none(list_page.next, "An extra page in the list.")
        marker = list_page.next

        self.assert_pagination_match(list_page, full_list, 0, limit)
        if marker:
            self.assert_equal(list_page[-1], marker.name,
                              "Pagination marker should be the last element "
                              "in the page.")
            list_page = self.auth_client.databases.list(
                instance_id, marker=marker)
            self.assert_client_code(expected_http_code)
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
            self.instance_info.id, self.db_defs[0],
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
        self.assert_client_code(expected_http_code)

        for database in self.auth_client.databases.list(instance_id):
            if database.name == database_name:
                self.fail(
                    "Database still listed after delete: %s" %
                    database_name)

    def run_nonexisting_database_delete(self, expected_http_code=202):
        # Deleting a non-existing database is expected to succeed as if the
        # database was deleted.
        self.assert_database_delete(
            self.instance_info.id, 'justashadow', expected_http_code)

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
