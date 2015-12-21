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

from trove.tests.scenario.runners.test_runners import TestRunner
from troveclient.compat import exceptions


class RootActionsRunner(TestRunner):

    def __init__(self):
        self.current_root_creds = None
        super(RootActionsRunner, self).__init__()

    def run_check_root_never_enabled(self, expected_http_code=200):
        self.assert_root_disabled(self.instance_info.id, expected_http_code)

    def assert_root_disabled(self, instance_id, expected_http_code):
        self._assert_root_state(instance_id, False, expected_http_code,
                                "The root has already been enabled on the "
                                "instance.")

    def _assert_root_state(self, instance_id, expected_state,
                           expected_http_code, message):
        # The call returns a nameless user object with 'rootEnabled' attribute.
        response = self.auth_client.root.is_root_enabled(instance_id)
        self.assert_instance_action(instance_id, None, expected_http_code)
        actual_state = getattr(response, 'rootEnabled', None)
        self.assert_equal(expected_state, actual_state, message)

    def run_disable_root_before_enabled(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        self.assert_root_disable_failure(
            self.instance_info.id, expected_exception, expected_http_code)

    def assert_root_disable_failure(self, instance_id, expected_exception,
                                    expected_http_code):
        self.assert_raises(expected_exception, expected_http_code,
                           self.auth_client.root.delete, instance_id)

    def run_enable_root_no_password(self, expected_http_code=200):
        self.current_root_creds = self.assert_root_create(
            self.instance_info.id, None, expected_http_code)

    def assert_root_create(self, instance_id, root_password,
                           expected_http_code):
        if root_password:
            root_creds = self.auth_client.root.create_instance_root(
                instance_id, root_password)
        else:
            root_creds = self.auth_client.root.create(instance_id)

        self.assert_instance_action(instance_id, None, expected_http_code)
        return root_creds

    def run_check_root_enabled(self, expected_http_code=200):
        self.assert_root_enabled(self.instance_info.id, expected_http_code)

    def assert_root_enabled(self, instance_id, expected_http_code):
        self._assert_root_state(instance_id, True, expected_http_code,
                                "The root has not been enabled on the "
                                "instance yet.")

    def run_enable_root_with_password(self, expected_http_code=200):
        password = self.test_helper.get_valid_root_password()
        self.current_root_creds = self.assert_root_create(
            self.instance_info.id, password, expected_http_code)

    def run_check_root_still_enabled(self, expected_http_code=200):
        self.assert_root_enabled(self.instance_info.id, expected_http_code)

    def run_disable_root(self, expected_http_code=200):
        self.assert_root_disable(self.instance_info.id, expected_http_code)

    def assert_root_disable(self, instance_id, expected_http_code):
        self.auth_client.root.delete(instance_id)
        self.assert_instance_action(instance_id, None, expected_http_code)

    def run_check_root_still_enabled_after_disable(
            self, expected_http_code=200):
        self.assert_root_enabled(self.instance_info.id, expected_http_code)

    def run_delete_root(self, expected_exception=exceptions.BadRequest,
                        expected_http_code=400):
        self.assert_root_delete_failure(
            self.instance_info.id, expected_exception, expected_http_code)

    def assert_root_delete_failure(self, instance_id, expected_exception,
                                   expected_http_code):
        root_user_name = self.current_root_creds[0]
        self.assert_raises(expected_exception, expected_http_code,
                           self.auth_client.users.delete,
                           instance_id, root_user_name)

    def run_check_root_enabled_after_restore(self, restored_instance_id,
                                             expected_http_code=200):
        if restored_instance_id:
            self.assert_root_enabled(restored_instance_id, expected_http_code)
        else:
            raise SkipTest("No instance with enabled root restored.")


class MysqlRootActionsRunner(RootActionsRunner):

    def run_enable_root_with_password(self):
        raise SkipTest("Operation is currently not supported.")


class CouchbaseRootActionsRunner(RootActionsRunner):

    def run_disable_root_before_enabled(self):
        raise SkipTest("Operation is currently not supported.")

    def run_enable_root_with_password(self):
        raise SkipTest("Operation is currently not supported.")

    def run_disable_root(self):
        raise SkipTest("Operation is currently not supported.")
