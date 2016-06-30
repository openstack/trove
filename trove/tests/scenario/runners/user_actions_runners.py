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

from six.moves.urllib import parse as urllib_parse

from proboscis import SkipTest

from trove.common import exception
from trove.common.utils import poll_until
from trove.tests.scenario.runners.test_runners import TestRunner
from troveclient.compat import exceptions


class UserActionsRunner(TestRunner):

    # TODO(pmalik): I believe the 202 (Accepted) should be replaced by
    # 200 (OK) as the actions are generally very fast and their results
    # available immediately upon execution of the request. This would
    # likely require replacing GA casts with calls which I believe are
    # more appropriate anyways.

    def __init__(self):
        super(UserActionsRunner, self).__init__()
        self.user_defs = []

    @property
    def first_user_def(self):
        if self.user_defs:
            return self.user_defs[0]
        raise SkipTest("No valid user definitions provided.")

    def run_users_create(self, expected_http_code=202):
        users = self.test_helper.get_valid_user_definitions()
        if users:
            self.user_defs = self.assert_users_create(
                self.instance_info.id, users, expected_http_code)
        else:
            raise SkipTest("No valid user definitions provided.")

    def assert_users_create(self, instance_id, serial_users_def,
                            expected_http_code):
        self.auth_client.users.create(instance_id, serial_users_def)
        self.assert_client_code(expected_http_code)
        self._wait_for_user_create(instance_id, serial_users_def)
        return serial_users_def

    def _wait_for_user_create(self, instance_id, expected_user_defs):
        expected_user_names = {user_def['name']
                               for user_def in expected_user_defs}
        self.report.log("Waiting for all created users to appear in the "
                        "listing: %s" % expected_user_names)

        def _all_exist():
            all_users = self._get_user_names(instance_id)
            return all(usr in all_users for usr in expected_user_names)

        try:
            poll_until(_all_exist, time_out=self.GUEST_CAST_WAIT_TIMEOUT_SEC)
            self.report.log("All users now exist on the instance.")
        except exception.PollTimeOut:
            self.fail("Some users were not created within the poll "
                      "timeout: %ds" % self.GUEST_CAST_WAIT_TIMEOUT_SEC)

    def _get_user_names(self, instance_id):
        full_list = self.auth_client.users.list(instance_id)
        return {user.name: user for user in full_list}

    def run_user_show(self, expected_http_code=200):
        for user_def in self.user_defs:
            self.assert_user_show(
                self.instance_info.id, user_def, expected_http_code)

    def assert_user_show(self, instance_id, expected_user_def,
                         expected_http_code):
        user_name = expected_user_def['name']
        user_host = expected_user_def.get('host')

        queried_user = self.auth_client.users.get(
            instance_id, user_name, user_host)
        self.assert_client_code(expected_http_code)
        self._assert_user_matches(queried_user, expected_user_def)

    def _assert_user_matches(self, user, expected_user_def):
        user_name = expected_user_def['name']
        self.assert_equal(expected_user_def['name'], user.name,
                          "Mismatch of names for user: %s" % user_name)
        self.assert_list_elements_equal(
            expected_user_def['databases'], user.databases,
            "Mismatch of databases for user: %s" % user_name)

    def run_users_list(self, expected_http_code=200):
        self.assert_users_list(
            self.instance_info.id, self.user_defs, expected_http_code)

    def assert_users_list(self, instance_id, expected_user_defs,
                          expected_http_code, limit=2):
        full_list = self.auth_client.users.list(instance_id)
        self.assert_client_code(expected_http_code)
        listed_users = {user.name: user for user in full_list}
        self.assert_is_none(full_list.next,
                            "Unexpected pagination in the list.")

        for user_def in expected_user_defs:
            user_name = user_def['name']
            self.assert_true(
                user_name in listed_users,
                "User not included in the 'user-list' output: %s" %
                user_name)
            self._assert_user_matches(listed_users[user_name], user_def)

        # Check that the system (ignored) users are not included in the output.
        system_users = self.get_system_users()
        self.assert_false(
            any(name in listed_users for name in system_users),
            "System users should not be included in the 'user-list' output.")

        # Test list pagination.
        list_page = self.auth_client.users.list(instance_id, limit=limit)
        self.assert_client_code(expected_http_code)

        self.assert_true(len(list_page) <= limit)
        if len(full_list) > limit:
            self.assert_is_not_none(list_page.next, "List page is missing.")
        else:
            self.assert_is_none(list_page.next, "An extra page in the list.")
        marker = list_page.next

        self.assert_pagination_match(list_page, full_list, 0, limit)
        if marker:
            last_user = list_page[-1]
            expected_marker = self.as_pagination_marker(last_user)
            self.assert_equal(expected_marker, marker,
                              "Pagination marker should be the last element "
                              "in the page.")
            list_page = self.auth_client.users.list(instance_id, marker=marker)
            self.assert_client_code(expected_http_code)
            self.assert_pagination_match(
                list_page, full_list, limit, len(full_list))

    def as_pagination_marker(self, user):
        return urllib_parse.quote(user.name)

    def run_user_access_show(self, expected_http_code=200):
        for user_def in self.user_defs:
            self.assert_user_access_show(
                self.instance_info.id, user_def, expected_http_code)

    def assert_user_access_show(self, instance_id, user_def,
                                expected_http_code):
        user_name, user_host = self._get_user_name_host_pair(user_def)
        user_dbs = self.auth_client.users.list_access(instance_id, user_name,
                                                      hostname=user_host)
        self.assert_client_code(expected_http_code)

        expected_dbs = {db_def['name'] for db_def in user_def['databases']}
        listed_dbs = [db.name for db in user_dbs]

        self.assert_equal(len(expected_dbs), len(listed_dbs),
                          "Unexpected number of databases on the user access "
                          "list.")

        for database in expected_dbs:
            self.assert_true(
                database in listed_dbs,
                "Database not found in the user access list: %s" % database)

    def run_user_access_revoke(self, expected_http_code=202):
        self._apply_on_all_databases(
            self.instance_info.id, self.assert_user_access_revoke,
            expected_http_code)

    def _apply_on_all_databases(self, instance_id, action, expected_http_code):
        if any(user_def['databases'] for user_def in self.user_defs):
            for user_def in self.user_defs:
                user_name, user_host = self._get_user_name_host_pair(user_def)
                db_defs = user_def['databases']
                for db_def in db_defs:
                    db_name = db_def['name']
                    action(instance_id, user_name, user_host,
                           db_name, expected_http_code)
        else:
            raise SkipTest("No user databases defined.")

    def assert_user_access_revoke(self, instance_id, user_name, user_host,
                                  database, expected_http_code):
        self.auth_client.users.revoke(
            instance_id, user_name, database, hostname=user_host)
        self.assert_client_code(expected_http_code)
        user_dbs = self.auth_client.users.list_access(
            instance_id, user_name, hostname=user_host)
        self.assert_false(any(db.name == database for db in user_dbs),
                          "Database should no longer be included in the user "
                          "access list after revoke: %s" % database)

    def run_user_access_grant(self, expected_http_code=202):
        self._apply_on_all_databases(
            self.instance_info.id, self.assert_user_access_grant,
            expected_http_code)

    def assert_user_access_grant(self, instance_id, user_name, user_host,
                                 database, expected_http_code):
        self.auth_client.users.grant(
            instance_id, user_name, [database], hostname=user_host)
        self.assert_client_code(expected_http_code)
        user_dbs = self.auth_client.users.list_access(
            instance_id, user_name, hostname=user_host)
        self.assert_true(any(db.name == database for db in user_dbs),
                         "Database should be included in the user "
                         "access list after granting access: %s" % database)

    def run_user_create_with_no_attributes(
            self, expected_exception=exceptions.BadRequest,
            expected_http_code=400):
        self.assert_users_create_failure(
            self.instance_info.id, {}, expected_exception, expected_http_code)

    def run_user_create_with_blank_name(
            self, expected_exception=exceptions.BadRequest,
            expected_http_code=400):
        usr_def = self.test_helper.get_non_existing_user_definition()
        # Test with missing user name attribute.
        no_name_usr_def = self.copy_dict(usr_def, ignored_keys=['name'])
        self.assert_users_create_failure(
            self.instance_info.id, no_name_usr_def,
            expected_exception, expected_http_code)

        # Test with empty user name attribute.
        blank_name_usr_def = self.copy_dict(usr_def)
        blank_name_usr_def.update({'name': ''})
        self.assert_users_create_failure(
            self.instance_info.id, blank_name_usr_def,
            expected_exception, expected_http_code)

    def run_user_create_with_blank_password(
            self, expected_exception=exceptions.BadRequest,
            expected_http_code=400):
        usr_def = self.test_helper.get_non_existing_user_definition()
        # Test with missing password attribute.
        no_pass_usr_def = self.copy_dict(usr_def, ignored_keys=['password'])
        self.assert_users_create_failure(
            self.instance_info.id, no_pass_usr_def,
            expected_exception, expected_http_code)

        # Test with missing databases attribute.
        no_db_usr_def = self.copy_dict(usr_def, ignored_keys=['databases'])
        self.assert_users_create_failure(
            self.instance_info.id, no_db_usr_def,
            expected_exception, expected_http_code)

    def run_existing_user_create(
            self, expected_exception=exceptions.BadRequest,
            expected_http_code=400):
        self.assert_users_create_failure(
            self.instance_info.id, self.first_user_def,
            expected_exception, expected_http_code)

    def run_system_user_create(
            self, expected_exception=exceptions.BadRequest,
            expected_http_code=400):
        # TODO(pmalik): Actions on system users and databases should probably
        # return Forbidden 403 instead. The current error messages are
        # confusing (talking about a malformed request).
        system_users = self.get_system_users()
        if system_users:
            user_defs = [{'name': name, 'password': 'password1',
                          'databases': []} for name in system_users]
            self.assert_users_create_failure(
                self.instance_info.id, user_defs,
                expected_exception, expected_http_code)

    def assert_users_create_failure(
            self, instance_id, serial_users_def,
            expected_exception, expected_http_code):
        self.assert_raises(
            expected_exception, expected_http_code,
            self.auth_client.users.create, instance_id, serial_users_def)

    def run_user_update_with_blank_name(
            self, expected_exception=exceptions.BadRequest,
            expected_http_code=400):
        self.assert_user_attribute_update_failure(
            self.instance_info.id, self.first_user_def, {'name': ''},
            expected_exception, expected_http_code)

    def run_user_update_with_existing_name(
            self, expected_exception=exceptions.BadRequest,
            expected_http_code=400):
        self.assert_user_attribute_update_failure(
            self.instance_info.id, self.first_user_def,
            {'name': self.first_user_def['name']},
            expected_exception, expected_http_code)

    def assert_user_attribute_update_failure(
            self, instance_id, user_def, update_attribites,
            expected_exception, expected_http_code):
        user_name, user_host = self._get_user_name_host_pair(user_def)

        self.assert_raises(
            expected_exception, expected_http_code,
            self.auth_client.users.update_attributes, instance_id,
            user_name, update_attribites, user_host)

    def _get_user_name_host_pair(self, user_def):
        return user_def['name'], user_def.get('host')

    def run_system_user_attribute_update(
            self, expected_exception=exceptions.BadRequest,
            expected_http_code=400):
        # TODO(pmalik): Actions on system users and databases should probably
        # return Forbidden 403 instead. The current error messages are
        # confusing (talking about a malformed request).
        system_users = self.get_system_users()
        if system_users:
            for name in system_users:
                user_def = {'name': name, 'password': 'password2'}
                self.assert_user_attribute_update_failure(
                    self.instance_info.id, user_def, user_def,
                    expected_exception, expected_http_code)

    def run_user_attribute_update(self, expected_http_code=202):
        updated_def = self.first_user_def
        # Update the name by appending a random string to it.
        updated_name = ''.join([updated_def['name'], 'upd'])
        update_attribites = {'name': updated_name,
                             'password': 'password2'}
        self.assert_user_attribute_update(
            self.instance_info.id, updated_def,
            update_attribites, expected_http_code)

    def assert_user_attribute_update(self, instance_id, user_def,
                                     update_attribites, expected_http_code):
        user_name, user_host = self._get_user_name_host_pair(user_def)

        self.auth_client.users.update_attributes(
            instance_id, user_name, update_attribites, user_host)
        self.assert_client_code(expected_http_code)

        # Update the stored definitions with the new value.
        expected_def = None
        for user_def in self.user_defs:
            if user_def['name'] == user_name:
                user_def.update(update_attribites)
                expected_def = user_def

        self._wait_for_user_create(instance_id, self.user_defs)

        # Verify using 'user-show' and 'user-list'.
        self.assert_user_show(instance_id, expected_def, 200)
        self.assert_users_list(instance_id, self.user_defs, 200)

    def run_user_delete(self, expected_http_code=202):
        for user_def in self.user_defs:
            self.assert_user_delete(
                self.instance_info.id, user_def, expected_http_code)

    def assert_user_delete(self, instance_id, user_def, expected_http_code):
        user_name, user_host = self._get_user_name_host_pair(user_def)

        self.auth_client.users.delete(instance_id, user_name, user_host)
        self.assert_client_code(expected_http_code)
        self._wait_for_user_delete(instance_id, user_name)

    def _wait_for_user_delete(self, instance_id, deleted_user_name):
        self.report.log("Waiting for deleted user to disappear from the "
                        "listing: %s" % deleted_user_name)

        def _db_is_gone():
            all_users = self._get_user_names(instance_id)
            return deleted_user_name not in all_users

        try:
            poll_until(_db_is_gone, time_out=self.GUEST_CAST_WAIT_TIMEOUT_SEC)
            self.report.log("User is now gone from the instance.")
        except exception.PollTimeOut:
            self.fail("User still listed after the poll timeout: %ds" %
                      self.GUEST_CAST_WAIT_TIMEOUT_SEC)

    def run_nonexisting_user_show(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        usr_def = self.test_helper.get_non_existing_user_definition()
        self.assert_user_show_failure(
            self.instance_info.id, {'name': usr_def['name']},
            expected_exception, expected_http_code)

    def assert_user_show_failure(self, instance_id, user_def,
                                 expected_exception, expected_http_code):
        user_name, user_host = self._get_user_name_host_pair(user_def)

        self.assert_raises(
            expected_exception, expected_http_code,
            self.auth_client.users.get, instance_id, user_name, user_host)

    def run_system_user_show(
            self, expected_exception=exceptions.BadRequest,
            expected_http_code=400):
        # TODO(pmalik): Actions on system users and databases should probably
        # return Forbidden 403 instead. The current error messages are
        # confusing (talking about a malformed request).
        system_users = self.get_system_users()
        if system_users:
            for name in system_users:
                self.assert_user_show_failure(
                    self.instance_info.id, {'name': name},
                    expected_exception, expected_http_code)

    def run_nonexisting_user_update(self, expected_http_code=404):
        # Test valid update on a non-existing user.
        usr_def = self.test_helper.get_non_existing_user_definition()
        update_def = {'name': usr_def['name']}
        self.assert_user_attribute_update_failure(
            self.instance_info.id, update_def, update_def,
            exceptions.NotFound, expected_http_code)

    def run_nonexisting_user_delete(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        usr_def = self.test_helper.get_non_existing_user_definition()
        self.assert_user_delete_failure(
            self.instance_info.id, {'name': usr_def['name']},
            expected_exception, expected_http_code)

    def assert_user_delete_failure(
            self, instance_id, user_def,
            expected_exception, expected_http_code):
        user_name, user_host = self._get_user_name_host_pair(user_def)

        self.assert_raises(expected_exception, expected_http_code,
                           self.auth_client.users.delete,
                           instance_id, user_name, user_host)

    def run_system_user_delete(
            self, expected_exception=exceptions.BadRequest,
            expected_http_code=400):
        # TODO(pmalik): Actions on system users and databases should probably
        # return Forbidden 403 instead. The current error messages are
        # confusing (talking about a malformed request).
        system_users = self.get_system_users()
        if system_users:
            for name in system_users:
                self.assert_user_delete_failure(
                    self.instance_info.id, {'name': name},
                    expected_exception, expected_http_code)

    def get_system_users(self):
        return self.get_datastore_config_property('ignore_users')


class MysqlUserActionsRunner(UserActionsRunner):

    def as_pagination_marker(self, user):
        return urllib_parse.quote('%s@%s' % (user.name, user.host))


class MariadbUserActionsRunner(MysqlUserActionsRunner):

    def __init__(self):
        super(MariadbUserActionsRunner, self).__init__()


class PerconaUserActionsRunner(MysqlUserActionsRunner):

    def __init__(self):
        super(PerconaUserActionsRunner, self).__init__()
