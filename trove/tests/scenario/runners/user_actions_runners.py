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

import urllib

from trove.tests.scenario.runners.test_runners import TestRunner
from troveclient.compat import exceptions
from troveclient.openstack.common.apiclient.exceptions import ValidationError


class UserActionsRunner(TestRunner):

    # TODO(pmalik): I believe the 202 (Accepted) should be replaced by
    # 200 (OK) as the actions are generally very fast and their results
    # available immediately upon execution of the request. This would
    # likely require replacing GA casts with calls which I believe are
    # more appropriate anyways.

    def run_users_create(self, expected_http_code=202):
        users = self.test_helper.get_valid_user_definitions()
        self.user_defs = self.assert_users_create(
            self.instance_info.id, users, expected_http_code)

    def assert_users_create(self, instance_id, serial_users_def,
                            expected_http_code):
        self.auth_client.users.create(instance_id, serial_users_def)
        self.assert_client_code(expected_http_code)
        return serial_users_def

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
        self.assert_equal(user.name, expected_user_def['name'],
                          "Mismatch of names for user: %s" % user_name)
        self.assert_equal(user.databases, expected_user_def['databases'],
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
            expected_marker = urllib.quote(
                '%s@%s' % (last_user.name, last_user.host))
            self.assert_equal(expected_marker, marker,
                              "Pagination marker should be the last element "
                              "in the page.")
            list_page = self.auth_client.users.list(instance_id, marker=marker)
            self.assert_client_code(expected_http_code)
            self.assert_pagination_match(
                list_page, full_list, limit, len(full_list))

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
            self.instance_info.id, self.user_defs[0],
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

    def run_user_update_with_no_attributes(self):
        # Note: this is caught on the client-side.
        self.assert_user_attribute_update_failure(
            self.instance_info.id, self.user_defs[0],
            {}, ValidationError, None)

    def run_user_update_with_blank_name(
            self, expected_exception=exceptions.BadRequest,
            expected_http_code=400):
        self.assert_user_attribute_update_failure(
            self.instance_info.id, self.user_defs[0], {'name': ''},
            expected_exception, expected_http_code)

    def run_user_update_with_existing_name(
            self, expected_exception=exceptions.BadRequest,
            expected_http_code=400):
        self.assert_user_attribute_update_failure(
            self.instance_info.id, self.user_defs[0],
            {'name': self.user_defs[0]['name']},
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
        updated_def = self.user_defs[0]
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

        self.assert_raises(exceptions.NotFound, 404,
                           self.auth_client.users.get,
                           instance_id, user_name, user_host)

        for user in self.auth_client.users.list(instance_id):
            if user.name == user_name:
                self.fail("User still listed after delete: %s" % user_name)

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
