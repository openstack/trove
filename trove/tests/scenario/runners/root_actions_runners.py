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

from trove.common import utils
from trove.tests.scenario import runners
from trove.tests.scenario.runners.test_runners import SkipKnownBug
from trove.tests.scenario.runners.test_runners import TestRunner
from troveclient.compat import exceptions


class RootActionsRunner(TestRunner):

    def __init__(self):
        self.current_root_creds = None
        self.restored_root_creds = None
        self.restored_root_creds2 = None
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
        root_credentials = self.test_helper.get_helper_credentials_root()
        self.current_root_creds = self.assert_root_create(
            self.instance_info.id, None, root_credentials['name'],
            expected_http_code)
        self.restored_root_creds = list(self.current_root_creds)

    def assert_root_create(self, instance_id, root_password,
                           expected_root_name, expected_http_code):
        if root_password is not None:
            root_creds = self.auth_client.root.create_instance_root(
                instance_id, root_password)
            self.assert_equal(root_password, root_creds[1])
        else:
            root_creds = self.auth_client.root.create(instance_id)

        if expected_root_name is not None:
            self.assert_equal(expected_root_name, root_creds[0])

        self.assert_instance_action(instance_id, None, expected_http_code)
        self.assert_can_connect(instance_id, root_creds)

        return root_creds

    def assert_can_connect(self, instance_id, test_connect_creds):
        self._assert_connect(instance_id, True, test_connect_creds)

    def _assert_connect(
            self, instance_id, expected_response, test_connect_creds):
        host = self.get_instance_host(instance_id=instance_id)
        self.report.log("Pinging instance %s with credentials: %s"
                        % (instance_id, test_connect_creds))

        ping_response = self.test_helper.ping(
            host,
            username=test_connect_creds[0],
            password=test_connect_creds[1]
        )
        self.assert_equal(expected_response, ping_response)

    def run_check_root_enabled(self, expected_http_code=200):
        self.assert_root_enabled(self.instance_info.id, expected_http_code)

    def assert_root_enabled(self, instance_id, expected_http_code):
        self._assert_root_state(instance_id, True, expected_http_code,
                                "The root has not been enabled on the "
                                "instance yet.")

    def run_enable_root_with_password(self, expected_http_code=200):
        root_credentials = self.test_helper.get_helper_credentials_root()
        password = root_credentials['password']
        if password is not None:
            self.current_root_creds = self.assert_root_create(
                self.instance_info.id,
                password, root_credentials['name'],
                expected_http_code)
        else:
            raise SkipTest("No valid root password defined in %s."
                           % self.test_helper.get_class_name())

    def run_disable_root(self, expected_http_code=200):
        self.restored_root_creds2 = list(self.current_root_creds)
        self.assert_root_disable(self.instance_info.id, expected_http_code)

    def assert_root_disable(self, instance_id, expected_http_code):
        self.auth_client.root.delete(instance_id)
        self.assert_instance_action(instance_id, None, expected_http_code)
        self.assert_cannot_connect(self.instance_info.id,
                                   self.current_root_creds)

    def assert_cannot_connect(self, instance_id, test_connect_creds):
        self._assert_connect(instance_id, False, test_connect_creds)

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

    def run_check_root_enabled_after_restore(
            self, restored_instance_id, restored_creds,
            expected_http_code=200):
        self.assert_root_enabled_after_restore(
            restored_instance_id, restored_creds, True, expected_http_code)

    def run_check_root_enabled_after_restore2(
            self, restored_instance_id, restored_creds,
            expected_http_code=200):
        self.assert_root_enabled_after_restore(
            restored_instance_id, restored_creds, False, expected_http_code)

    def assert_root_enabled_after_restore(
            self, restored_instance_id, restored_creds,
            expected_connect_response, expected_http_code):
        if restored_instance_id:
            self.assert_root_enabled(restored_instance_id, expected_http_code)
            self._assert_connect(restored_instance_id,
                                 expected_connect_response, restored_creds)
        else:
            raise SkipTest("No restored instance.")

    def check_root_disable_supported(self):
        """Throw SkipTest if root-disable is not supported."""
        pass


class PerconaRootActionsRunner(RootActionsRunner):

    def check_root_disable_supported(self):
        raise SkipTest("Operation is currently not supported.")


class MariadbRootActionsRunner(RootActionsRunner):

    def check_root_disable_supported(self):
        raise SkipTest("Operation is currently not supported.")


class PxcRootActionsRunner(RootActionsRunner):

    def check_root_disable_supported(self):
        raise SkipTest("Operation is currently not supported.")


class PostgresqlRootActionsRunner(RootActionsRunner):

    def check_root_disable_supported(self):
        raise SkipTest("Operation is currently not supported.")

    def run_enable_root_with_password(self):
        raise SkipTest("Operation is currently not supported.")

    def run_delete_root(self):
        raise SkipKnownBug(runners.BUG_WRONG_API_VALIDATION)


class CouchbaseRootActionsRunner(RootActionsRunner):

    def _assert_connect(
            self, instance_id, expected_response, test_connect_creds):
        host = self.get_instance_host(instance_id=instance_id)
        self.report.log("Pinging instance %s with credentials: %s"
                        % (instance_id, test_connect_creds))
        mgmt_port = 8091
        mgmt_creds = '%s:%s' % (test_connect_creds[0], test_connect_creds[1])
        rest_endpoint = ('http://%s:%d/pools/nodes'
                         % (host, mgmt_port))
        out, err = utils.execute_with_timeout(
            'curl', '-u', mgmt_creds, rest_endpoint)
        self.assert_equal(expected_response, out and len(out) > 0)

    def check_root_disable_supported(self):
        raise SkipTest("Operation is currently not supported.")

    def run_enable_root_with_password(self):
        raise SkipTest("Operation is currently not supported.")

    def run_delete_root(self):
        raise SkipKnownBug(runners.BUG_WRONG_API_VALIDATION)
