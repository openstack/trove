# Copyright 2015 Tesora Inc.
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

from swiftclient.client import ClientException
import tempfile

from troveclient.compat import exceptions

from trove.common import cfg
from trove.guestagent.common import operating_system
from trove.guestagent import guest_log
from trove.tests.config import CONFIG
from trove.tests.scenario.helpers.test_helper import DataType
from trove.tests.scenario.runners.test_runners import TestRunner


CONF = cfg.CONF


class GuestLogRunner(TestRunner):

    def __init__(self):
        super(GuestLogRunner, self).__init__()

        self.container = CONF.guest_log_container_name
        self.prefix_pattern = '%(instance_id)s/%(datastore)s-%(log)s/'
        self._last_log_published = {}
        self._last_log_contents = {}

    def _get_last_log_published(self, log_name):
        return self._last_log_published.get(log_name, None)

    def _set_last_log_published(self, log_name, published):
        self._last_log_published[log_name] = published

    def _get_last_log_contents(self, log_name):
        return self._last_log_contents.get(log_name, [])

    def _set_last_log_contents(self, log_name, published):
        self._last_log_contents[log_name] = published

    def _get_exposed_user_log_names(self):
        """Returns the full list of exposed user logs."""
        return self.test_helper.get_exposed_user_log_names()

    def _get_exposed_user_log_name(self):
        """Return the first exposed user log name."""
        return self.test_helper.get_exposed_user_log_names()[0]

    def _get_unexposed_sys_log_name(self):
        """Return the first unexposed sys log name."""
        return self.test_helper.get_unexposed_sys_log_names()[0]

    def run_test_log_list(self):
        self.assert_log_list(self.auth_client,
                             self.test_helper.get_exposed_log_list())

    def assert_log_list(self, client, expected_list):
        log_list = list(client.instances.log_list(self.instance_info.id))
        log_names = list(ll.name for ll in log_list)
        self.assert_list_elements_equal(expected_list, log_names)

    def run_test_admin_log_list(self):
        self.assert_log_list(self.admin_client,
                             self.test_helper.get_full_log_list())

    def run_test_log_show(self):
        log_pending = self._set_zero_or_none()
        self.assert_log_show(self.auth_client,
                             self._get_exposed_user_log_name(),
                             expected_published=0,
                             expected_pending=log_pending)

    def _set_zero_or_none(self):
        """This attempts to handle the case where an existing instance
        is used.  Values that would normally be '0' are not, and must
        be ignored.
        """
        value = 0
        if self.is_using_existing_instance:
            value = None
        return value

    def assert_log_show(self, client, log_name,
                        expected_http_code=200,
                        expected_type=guest_log.LogType.USER.name,
                        expected_status=guest_log.LogStatus.Disabled.name,
                        expected_published=None, expected_pending=None):
        self.report.log("Executing log_show for log '%s'" % log_name)
        log_details = client.instances.log_show(
            self.instance_info.id, log_name)
        self.assert_client_code(expected_http_code, client=client)
        self.assert_log_details(
            log_details, log_name,
            expected_type=expected_type,
            expected_status=expected_status,
            expected_published=expected_published,
            expected_pending=expected_pending)

    def assert_log_details(self, log_details, expected_log_name,
                           expected_type=guest_log.LogType.USER.name,
                           expected_status=guest_log.LogStatus.Disabled.name,
                           expected_published=None, expected_pending=None):
        """Check that the action generates the proper response data.
        For log_published and log_pending, setting the value to 'None'
        will skip that check (useful when using an existing instance,
        as there may be pending things in user logs right from the get-go)
        and setting it to a value other than '0' will verify that the actual
        value is '>=value' (since it's impossible to know what the actual
        value will be at any given time). '0' will still match exclusively.
        """
        self.report.log("Validating log details for log '%s'" %
                        expected_log_name)
        self._set_last_log_published(expected_log_name, log_details.published)
        self.assert_equal(expected_log_name, log_details.name,
                          "Wrong log name for '%s' log" % expected_log_name)
        self.assert_equal(expected_type, log_details.type,
                          "Wrong log type for '%s' log" % expected_log_name)
        current_status = log_details.status.replace(' ', '_')
        self.assert_equal(expected_status, current_status,
                          "Wrong log status for '%s' log" % expected_log_name)
        if expected_published is None:
            pass
        elif expected_published == 0:
            self.assert_equal(0, log_details.published,
                              "Wrong log published for '%s' log" %
                              expected_log_name)
        else:
            self.assert_true(log_details.published >= expected_published,
                             "Missing log published for '%s' log: "
                             "expected %d, got %d" %
                             (expected_log_name, expected_published,
                              log_details.published))
        if expected_pending is None:
            pass
        elif expected_pending == 0:
            self.assert_equal(0, log_details.pending,
                              "Wrong log pending for '%s' log" %
                              expected_log_name)
        else:
            self.assert_true(log_details.pending >= expected_pending,
                             "Missing log pending for '%s' log: "
                             "expected %d, got %d" %
                             (expected_log_name, expected_pending,
                              log_details.pending))
        container = self.container
        prefix = self.prefix_pattern % {
            'instance_id': self.instance_info.id,
            'datastore': CONFIG.dbaas_datastore,
            'log': expected_log_name}
        metafile = prefix.rstrip('/') + '_metafile'
        if expected_published == 0:
            self.assert_storage_gone(container, prefix, metafile)
            container = 'None'
            prefix = 'None'
        else:
            self.assert_storage_exists(container, prefix, metafile)
        self.assert_equal(container, log_details.container,
                          "Wrong log container for '%s' log" %
                          expected_log_name)
        self.assert_equal(prefix, log_details.prefix,
                          "Wrong log prefix for '%s' log" % expected_log_name)
        self.assert_equal(metafile, log_details.metafile,
                          "Wrong log metafile for '%s' log" %
                          expected_log_name)

    def assert_log_enable(self, client, log_name,
                          expected_http_code=200,
                          expected_type=guest_log.LogType.USER.name,
                          expected_status=guest_log.LogStatus.Disabled.name,
                          expected_published=None, expected_pending=None):
        self.report.log("Executing log_enable for log '%s'" % log_name)
        log_details = client.instances.log_enable(
            self.instance_info.id, log_name)
        self.assert_client_code(expected_http_code, client=client)
        self.assert_log_details(
            log_details, log_name,
            expected_type=expected_type,
            expected_status=expected_status,
            expected_published=expected_published,
            expected_pending=expected_pending)

    def assert_log_disable(self, client, log_name, discard=None,
                           expected_http_code=200,
                           expected_type=guest_log.LogType.USER.name,
                           expected_status=guest_log.LogStatus.Disabled.name,
                           expected_published=None, expected_pending=None):
        self.report.log("Executing log_disable for log '%s' (discard: %s)" %
                        (log_name, discard))
        log_details = client.instances.log_disable(
            self.instance_info.id, log_name, discard=discard)
        self.assert_client_code(expected_http_code, client=client)
        self.assert_log_details(
            log_details, log_name,
            expected_type=expected_type,
            expected_status=expected_status,
            expected_published=expected_published,
            expected_pending=expected_pending)

    def assert_log_publish(self, client, log_name, disable=None, discard=None,
                           expected_http_code=200,
                           expected_type=guest_log.LogType.USER.name,
                           expected_status=guest_log.LogStatus.Disabled.name,
                           expected_published=None, expected_pending=None):
        self.report.log("Executing log_publish for log '%s' (disable: %s  "
                        "discard: %s)" %
                        (log_name, disable, discard))
        log_details = client.instances.log_publish(
            self.instance_info.id, log_name, disable=disable, discard=discard)
        self.assert_client_code(expected_http_code, client=client)
        self.assert_log_details(
            log_details, log_name,
            expected_type=expected_type,
            expected_status=expected_status,
            expected_published=expected_published,
            expected_pending=expected_pending)

    def assert_log_discard(self, client, log_name,
                           expected_http_code=200,
                           expected_type=guest_log.LogType.USER.name,
                           expected_status=guest_log.LogStatus.Disabled.name,
                           expected_published=None, expected_pending=None):
        self.report.log("Executing log_discard for log '%s'" % log_name)
        log_details = client.instances.log_discard(
            self.instance_info.id, log_name)
        self.assert_client_code(expected_http_code, client=client)
        self.assert_log_details(
            log_details, log_name,
            expected_type=expected_type,
            expected_status=expected_status,
            expected_published=expected_published,
            expected_pending=expected_pending)

    def assert_storage_gone(self, container, prefix, metafile):
        try:
            headers, container_files = self.swift_client.get_container(
                container, prefix=prefix)
            self.assert_equal(0, len(container_files),
                              "Found files in %s/%s: %s" %
                              (container, prefix, container_files))
        except ClientException as ex:
            if ex.http_status == 404:
                self.report.log("Container '%s' does not exist" %
                                container)
                pass
            else:
                raise
        try:
            self.swift_client.get_object(container, metafile)
            self.fail("Found metafile after discard: %s" % metafile)
        except ClientException as ex:
            if ex.http_status == 404:
                self.report.log("Metafile '%s' gone as expected" %
                                metafile)
                pass
            else:
                raise

    def assert_storage_exists(self, container, prefix, metafile):
        try:
            headers, container_files = self.swift_client.get_container(
                container, prefix=prefix)
            self.assert_true(len(container_files) > 0,
                             "No files found in %s/%s" %
                             (container, prefix))
        except ClientException as ex:
            if ex.http_status == 404:
                self.fail("Container '%s' does not exist" % container)
            else:
                raise
        try:
            self.swift_client.get_object(container, metafile)
        except ClientException as ex:
            if ex.http_status == 404:
                self.fail("Missing metafile: %s" % metafile)
            else:
                raise

    def run_test_log_enable_sys(self,
                                expected_exception=exceptions.BadRequest,
                                expected_http_code=400):
        self.assert_log_enable_fails(
            self.admin_client,
            expected_exception, expected_http_code,
            self._get_unexposed_sys_log_name())

    def assert_log_enable_fails(self, client,
                                expected_exception, expected_http_code,
                                log_name):
        self.assert_raises(expected_exception, None,
                           client.instances.log_enable,
                           self.instance_info.id, log_name)
        # we may not be using the main client, so check explicitly here
        self.assert_client_code(expected_http_code, client=client)

    def run_test_log_disable_sys(self,
                                 expected_exception=exceptions.BadRequest,
                                 expected_http_code=400):
        self.assert_log_disable_fails(
            self.admin_client,
            expected_exception, expected_http_code,
            self._get_unexposed_sys_log_name())

    def assert_log_disable_fails(self, client,
                                 expected_exception, expected_http_code,
                                 log_name, discard=None):
        self.assert_raises(expected_exception, None,
                           client.instances.log_disable,
                           self.instance_info.id, log_name,
                           discard=discard)
        # we may not be using the main client, so check explicitly here
        self.assert_client_code(expected_http_code, client=client)

    def run_test_log_show_unauth_user(self,
                                      expected_exception=exceptions.NotFound,
                                      expected_http_code=404):
        self.assert_log_show_fails(
            self.unauth_client,
            expected_exception, expected_http_code,
            self._get_exposed_user_log_name())

    def assert_log_show_fails(self, client,
                              expected_exception, expected_http_code,
                              log_name):
        self.assert_raises(expected_exception, None,
                           client.instances.log_show,
                           self.instance_info.id, log_name)
        # we may not be using the main client, so check explicitly here
        self.assert_client_code(expected_http_code, client=client)

    def run_test_log_list_unauth_user(self,
                                      expected_exception=exceptions.NotFound,
                                      expected_http_code=404):
        self.assert_raises(expected_exception, None,
                           self.unauth_client.instances.log_list,
                           self.instance_info.id)
        # we're not using the main client, so check explicitly here
        self.assert_client_code(expected_http_code, client=self.unauth_client)

    def run_test_log_generator_unauth_user(self):
        self.assert_log_generator_unauth_user(
            self.unauth_client, self._get_exposed_user_log_name())

    def assert_log_generator_unauth_user(self, client, log_name, publish=None):
        try:
            client.instances.log_generator(
                self.instance_info.id, log_name, publish=publish)
            raise("Client allowed unauthorized access to log_generator")
        except Exception:
            pass

    def run_test_log_generator_publish_unauth_user(self):
        self.assert_log_generator_unauth_user(
            self.unauth_client, self._get_exposed_user_log_name(),
            publish=True)

    def run_test_log_show_unexposed_user(
            self, expected_exception=exceptions.BadRequest,
            expected_http_code=400):
        self.assert_log_show_fails(
            self.auth_client,
            expected_exception, expected_http_code,
            self._get_unexposed_sys_log_name())

    def run_test_log_enable_unexposed_user(
            self, expected_exception=exceptions.BadRequest,
            expected_http_code=400):
        self.assert_log_enable_fails(
            self.auth_client,
            expected_exception, expected_http_code,
            self._get_unexposed_sys_log_name())

    def run_test_log_disable_unexposed_user(
            self, expected_exception=exceptions.BadRequest,
            expected_http_code=400):
        self.assert_log_disable_fails(
            self.auth_client,
            expected_exception, expected_http_code,
            self._get_unexposed_sys_log_name())

    def run_test_log_publish_unexposed_user(
            self, expected_exception=exceptions.BadRequest,
            expected_http_code=400):
        self.assert_log_publish_fails(
            self.auth_client,
            expected_exception, expected_http_code,
            self._get_unexposed_sys_log_name())

    def assert_log_publish_fails(self, client,
                                 expected_exception, expected_http_code,
                                 log_name,
                                 disable=None, discard=None):
        self.assert_raises(expected_exception, None,
                           client.instances.log_publish,
                           self.instance_info.id, log_name,
                           disable=disable, discard=discard)
        # we may not be using the main client, so check explicitly here
        self.assert_client_code(expected_http_code, client=client)

    def run_test_log_discard_unexposed_user(
            self, expected_exception=exceptions.BadRequest,
            expected_http_code=400):
        self.assert_log_discard_fails(
            self.auth_client,
            expected_exception, expected_http_code,
            self._get_unexposed_sys_log_name())

    def assert_log_discard_fails(self, client,
                                 expected_exception, expected_http_code,
                                 log_name):
        self.assert_raises(expected_exception, None,
                           client.instances.log_discard,
                           self.instance_info.id, log_name)
        # we may not be using the main client, so check explicitly here
        self.assert_client_code(expected_http_code, client=client)

    def run_test_log_enable_user(self):
        expected_status = guest_log.LogStatus.Ready.name
        expected_pending = 1
        if self.test_helper.log_enable_requires_restart():
            expected_status = guest_log.LogStatus.Restart_Required.name
            # if using an existing instance, there may already be something
            expected_pending = self._set_zero_or_none()

        for log_name in self._get_exposed_user_log_names():
            self.assert_log_enable(
                self.auth_client,
                log_name,
                expected_status=expected_status,
                expected_published=0, expected_pending=expected_pending)

    def run_test_log_enable_flip_user(self):
        # for restart required datastores, test that flipping them
        # back to disabled returns the status to 'Disabled'
        # from 'Restart_Required'
        if self.test_helper.log_enable_requires_restart():
            # if using an existing instance, there may already be something
            expected_pending = self._set_zero_or_none()

            for log_name in self._get_exposed_user_log_names():
                self.assert_log_disable(
                    self.auth_client,
                    log_name,
                    expected_status=guest_log.LogStatus.Disabled.name,
                    expected_published=0, expected_pending=expected_pending)
                self.assert_log_enable(
                    self.auth_client,
                    log_name,
                    expected_status=guest_log.LogStatus.Restart_Required.name,
                    expected_published=0, expected_pending=expected_pending)

    def run_test_restart_datastore(self, expected_http_code=202):
        if self.test_helper.log_enable_requires_restart():
            instance_id = self.instance_info.id
            # we need to wait until the heartbeat flips the instance
            # back into 'ACTIVE' before we issue the restart command
            expected_states = ['RESTART_REQUIRED', 'ACTIVE']
            self.assert_instance_action(instance_id, expected_states, None)
            self.auth_client.instances.restart(instance_id)
            self.assert_client_code(expected_http_code,
                                    client=self.auth_client)

    def run_test_wait_for_restart(self, expected_states=['REBOOT', 'ACTIVE']):
        if self.test_helper.log_enable_requires_restart():
            self.assert_instance_action(self.instance_info.id,
                                        expected_states, None)

    def run_test_log_publish_user(self):
        for log_name in self._get_exposed_user_log_names():
            self.assert_log_publish(
                self.auth_client,
                log_name,
                expected_status=guest_log.LogStatus.Published.name,
                expected_published=1, expected_pending=0)

    def run_test_add_data(self):
        self.test_helper.add_data(DataType.micro, self.get_instance_host())

    def run_test_verify_data(self):
        self.test_helper.verify_data(DataType.micro, self.get_instance_host())

    def run_test_log_publish_again_user(self):
        for log_name in self._get_exposed_user_log_names():
            self.assert_log_publish(
                self.admin_client,
                log_name,
                expected_status=guest_log.LogStatus.Published.name,
                expected_published=self._get_last_log_published(log_name),
                expected_pending=0)

    def run_test_log_generator_user(self):
        for log_name in self._get_exposed_user_log_names():
            self.assert_log_generator(
                self.auth_client,
                log_name,
                lines=2, expected_lines=2)

    def assert_log_generator(self, client, log_name, publish=False,
                             lines=4, expected_lines=None,
                             swift_client=None):
        self.report.log("Executing log_generator for log '%s' (publish: %s)" %
                        (log_name, publish))
        log_gen = client.instances.log_generator(
            self.instance_info.id, log_name,
            publish=publish, lines=lines, swift=swift_client)
        log_contents = "".join([chunk for chunk in log_gen()])
        self.report.log("Returned %d lines for log '%s': %s" % (
            len(log_contents.splitlines()), log_name, log_contents))
        self._set_last_log_contents(log_name, log_contents)
        if expected_lines:
            self.assert_equal(expected_lines,
                              len(log_contents.splitlines()),
                              "Wrong line count for '%s' log" % log_name)
        else:
            self.assert_true(len(log_contents.splitlines()) <= lines,
                             "More than %d lines found for '%s' log" %
                             (lines, log_name))

    def run_test_log_generator_publish_user(self):
        for log_name in self._get_exposed_user_log_names():
            self.assert_log_generator(
                self.auth_client,
                log_name, publish=True,
                lines=3, expected_lines=3)

    def run_test_log_generator_swift_client_user(self):
        swift_client = self.swift_client
        for log_name in self._get_exposed_user_log_names():
            self.assert_log_generator(
                self.auth_client,
                log_name, publish=True,
                lines=3, expected_lines=3,
                swift_client=swift_client)

    def run_test_add_data_again(self):
        # Add some more data so we have at least 3 log data files
        self.test_helper.add_data(DataType.micro2, self.get_instance_host())

    def run_test_verify_data_again(self):
        self.test_helper.verify_data(DataType.micro2, self.get_instance_host())

    def run_test_log_generator_user_by_row(self):
        log_name = self._get_exposed_user_log_name()
        self.assert_log_publish(
            self.auth_client,
            log_name,
            expected_status=guest_log.LogStatus.Published.name,
            expected_published=self._get_last_log_published(log_name),
            expected_pending=0)
        # Now get the full contents of the log
        self.assert_log_generator(self.auth_client, log_name, lines=100000)
        log_lines = len(self._get_last_log_contents(log_name).splitlines())
        # cap at 100, so the test can't run away if something goes wrong
        log_lines = min(log_lines, 100)
        # Make sure we get the right number of log lines back each time
        for lines in range(1, log_lines):
            self.assert_log_generator(
                self.auth_client,
                log_name, lines=lines, expected_lines=lines)

    def run_test_log_save_user(self):
        for log_name in self._get_exposed_user_log_names():
            self.assert_test_log_save(self.auth_client, log_name)

    def run_test_log_save_publish_user(self):
        for log_name in self._get_exposed_user_log_names():
            self.assert_test_log_save(self.auth_client, log_name, publish=True)

    def assert_test_log_save(self, client, log_name, publish=False):
        # generate the file
        self.report.log("Executing log_save for log '%s' (publish: %s)" %
                        (log_name, publish))
        with tempfile.NamedTemporaryFile() as temp_file:
            client.instances.log_save(self.instance_info.id,
                                      log_name=log_name, publish=publish,
                                      filename=temp_file.name)
            file_contents = operating_system.read_file(temp_file.name)
            # now grab the contents ourselves
            self.assert_log_generator(client, log_name, lines=100000)
            # and compare them
            self.assert_equal(self._get_last_log_contents(log_name),
                              file_contents)

    def run_test_log_discard_user(self):
        for log_name in self._get_exposed_user_log_names():
            self.assert_log_discard(
                self.auth_client,
                log_name,
                expected_status=guest_log.LogStatus.Ready.name,
                expected_published=0, expected_pending=1)

    def run_test_log_disable_user(self):
        expected_status = guest_log.LogStatus.Disabled.name
        if self.test_helper.log_enable_requires_restart():
            expected_status = guest_log.LogStatus.Restart_Required.name
        for log_name in self._get_exposed_user_log_names():
            self.assert_log_disable(
                self.auth_client,
                log_name,
                expected_status=expected_status,
                expected_published=0, expected_pending=1)

    def run_test_log_show_sys(self):
        self.assert_log_show(
            self.admin_client,
            self._get_unexposed_sys_log_name(),
            expected_type=guest_log.LogType.SYS.name,
            expected_status=guest_log.LogStatus.Ready.name,
            expected_published=0, expected_pending=1)

    def run_test_log_publish_sys(self):
        log_name = self._get_unexposed_sys_log_name()
        self.assert_log_publish(
            self.admin_client,
            log_name,
            expected_type=guest_log.LogType.SYS.name,
            expected_status=guest_log.LogStatus.Partial.name,
            expected_published=1, expected_pending=1)

    def run_test_log_publish_again_sys(self):
        log_name = self._get_unexposed_sys_log_name()
        self.assert_log_publish(
            self.admin_client,
            log_name,
            expected_type=guest_log.LogType.SYS.name,
            expected_status=guest_log.LogStatus.Partial.name,
            expected_published=self._get_last_log_published(log_name) + 1,
            expected_pending=1)

    def run_test_log_generator_sys(self):
        self.assert_log_generator(
            self.admin_client,
            self._get_unexposed_sys_log_name(),
            lines=4, expected_lines=4)

    def run_test_log_generator_publish_sys(self):
        self.assert_log_generator(
            self.admin_client,
            self._get_unexposed_sys_log_name(), publish=True,
            lines=4, expected_lines=4)

    def run_test_log_generator_swift_client_sys(self):
        self.assert_log_generator(
            self.admin_client,
            self._get_unexposed_sys_log_name(), publish=True,
            lines=4, expected_lines=4,
            swift_client=self.swift_client)

    def run_test_log_save_sys(self):
        self.assert_test_log_save(
            self.admin_client,
            self._get_unexposed_sys_log_name())

    def run_test_log_save_publish_sys(self):
        self.assert_test_log_save(
            self.admin_client,
            self._get_unexposed_sys_log_name(),
            publish=True)

    def run_test_log_discard_sys(self):
        self.assert_log_discard(
            self.admin_client,
            self._get_unexposed_sys_log_name(),
            expected_type=guest_log.LogType.SYS.name,
            expected_status=guest_log.LogStatus.Ready.name,
            expected_published=0, expected_pending=1)


class CassandraGuestLogRunner(GuestLogRunner):

    def run_test_log_show(self):
        self.assert_log_show(self.auth_client,
                             self._get_exposed_user_log_name(),
                             expected_published=0,
                             expected_pending=None)
