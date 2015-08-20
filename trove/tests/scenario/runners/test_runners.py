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

import os
import time as timer

from proboscis import asserts
from troveclient.compat import exceptions

from oslo_config.cfg import NoSuchOptError
from trove.common import cfg
from trove.common import utils
from trove.common.utils import poll_until, build_polling_task
from trove.common import exception
from trove.tests.api.instances import instance_info
from trove.tests.config import CONFIG
from trove.tests.util import create_dbaas_client
from trove.tests.util.users import Requirements

CONF = cfg.CONF


class TestRunner(object):
    """
    Base class for all 'Runner' classes.

    The Runner classes are those that actually do the work.  The 'Group'
    classes are set up with decorators that control how the tests flow,
    and are used to organized the tests - however they are typically set up
    to just call a corresponding method in a Runner class.

    A Runner class can be overridden if a particular set of tests
    needs to have DataStore specific coding.  The corresponding Group
    class will try to first load a DataStore specific class, and then fall
    back to the generic one if need be.  For example,
    the NegativeClusterActionsGroup class specifies a runner_base_name of
    NegativeClusterActionsRunner.  If the manager of the default
    datastore is mongodb, then the MongodbNegativeClusterActionsRunner is
    used instead.  The prefix is created by capitalizing the name of the
    manager - overriding classes *must* follow this naming convention
    to be automatically used.  The main assumption made here is that
    if a manager is used for different datastore versions, then the
    overriding runner should also be valid for the same datastore versions.
    """

    USE_INSTANCE_ID_FLAG = 'TESTS_USE_INSTANCE_ID'
    DO_NOT_DELETE_INSTANCE_FLAG = 'TESTS_DO_NOT_DELETE_INSTANCE'

    VOLUME_SUPPORT = CONFIG.get('trove_volume_support', True)
    EPHEMERAL_SUPPORT = not VOLUME_SUPPORT and CONFIG.get('device_path', None)
    ROOT_PARTITION = not (VOLUME_SUPPORT or CONFIG.get('device_path', None))

    report = CONFIG.get_report()

    def __init__(self, sleep_time=10, timeout=1200):
        self.def_sleep_time = sleep_time
        self.def_timeout = timeout
        self.instance_info = instance_info
        self.auth_client = create_dbaas_client(self.instance_info.user)
        self.unauth_client = None
        self._test_helper = None

    @classmethod
    def fail(cls, message):
        asserts.fail(message)

    @classmethod
    def assert_is_sublist(cls, sub_list, full_list, message=None):
        return cls.assert_true(set(sub_list).issubset(full_list), message)

    @classmethod
    def assert_unique(cls, iterable, message=None):
        """Assert that a given iterable contains only unique elements.
        """
        cls.assert_equal(len(iterable), len(set(iterable)), message)

    @classmethod
    def assert_true(cls, condition, message=None):
        asserts.assert_true(condition, message=message)

    @classmethod
    def assert_false(cls, condition, message=None):
        asserts.assert_false(condition, message=message)

    @classmethod
    def assert_is_none(cls, value, message=None):
        asserts.assert_is_none(value, message=message)

    @classmethod
    def assert_is_not_none(cls, value, message=None):
        asserts.assert_is_not_none(value, message=message)

    @classmethod
    def assert_list_elements_equal(cls, expected, actual, message=None):
        """Assert that two lists contain same elements
        (with same multiplicities) ignoring the element order.
        """
        return cls.assert_equal(sorted(expected), sorted(actual), message)

    @classmethod
    def assert_equal(cls, expected, actual, message=None):
        if not message:
            message = 'Unexpected value'
        try:
            message += ": '%s' (expected '%s')." % (actual, expected)
        except TypeError:
            pass

        asserts.assert_equal(expected, actual, message=message)

    @classmethod
    def assert_not_equal(cls, expected, actual, message=None):
        if not message:
            message = 'Expected different value than'
        try:
            message += ": '%s'." % expected
        except TypeError:
            pass

        asserts.assert_not_equal(expected, actual, message=message)

    @property
    def test_helper(self):
        return self._test_helper

    @test_helper.setter
    def test_helper(self, test_helper):
        self._test_helper = test_helper

    def get_unauth_client(self):
        if not self.unauth_client:
            self.unauth_client = self._create_unauthorized_client()
        return self.unauth_client

    def _create_unauthorized_client(self, force=False):
        """Create a client from a different 'unauthorized' user
        to facilitate negative testing.
        """
        requirements = Requirements(is_admin=False)
        other_user = CONFIG.users.find_user(
            requirements, black_list=[self.instance_info.user.auth_user])
        return create_dbaas_client(other_user)

    def assert_raises(self, expected_exception, expected_http_code,
                      client_cmd, *cmd_args, **cmd_kwargs):
        asserts.assert_raises(expected_exception, client_cmd,
                              *cmd_args, **cmd_kwargs)

        self.assert_client_code(expected_http_code)

    def get_datastore_config_property(self, name, datastore=None):
        """Get a Trove configuration property for a given datastore.
        Use the current instance's datastore if None.
        """
        try:
            return CONF.get(
                datastore or self.instance_info.dbaas_datastore).get(name)
        except NoSuchOptError:
            return CONF.get(name)

    @property
    def is_using_existing_instance(self):
        return os.environ.get(self.USE_INSTANCE_ID_FLAG, None) is not None

    def get_existing_instance(self):
        if self.is_using_existing_instance:
            instance_id = os.environ.get(self.USE_INSTANCE_ID_FLAG)
            return self._get_instance_info(instance_id)

        return None

    @property
    def has_do_not_delete_instance(self):
        return os.environ.get(
            self.DO_NOT_DELETE_INSTANCE_FLAG, None) is not None

    def assert_instance_action(
            self, instance_ids, expected_states, expected_http_code):
        self.assert_client_code(expected_http_code)
        if expected_states:
            self.assert_all_instance_states(
                instance_ids if utils.is_collection(instance_ids)
                else [instance_ids], expected_states)

    def assert_client_code(self, expected_http_code, client=None):
        if expected_http_code is not None:
            client = client or self.auth_client
            self.assert_equal(expected_http_code, client.last_http_code,
                              "Unexpected client status code")

    def assert_all_instance_states(self, instance_ids, expected_states):
        tasks = [build_polling_task(
            lambda: self._assert_instance_states(instance_id, expected_states),
            sleep_time=self.def_sleep_time, time_out=self.def_timeout)
            for instance_id in instance_ids]
        poll_until(lambda: all(poll_task.ready() for poll_task in tasks),
                   sleep_time=self.def_sleep_time, time_out=self.def_timeout)

        for task in tasks:
            if task.has_result():
                self.assert_true(
                    task.poll_result(),
                    "Some instances failed to acquire all expected states.")
            elif task.has_exception():
                self.fail(str(task.poll_exception()))

    def _assert_instance_states(self, instance_id, expected_states,
                                fast_fail_status='ERROR'):
        for status in expected_states:
            start_time = timer.time()
            try:
                poll_until(lambda: self._has_status(
                    instance_id, status, fast_fail_status=fast_fail_status),
                    sleep_time=self.def_sleep_time,
                    time_out=self.def_timeout)
                self.report.log("Instance has gone '%s' in %s." %
                                (status, self._time_since(start_time)))
            except exception.PollTimeOut:
                self.report.log(
                    "Status of instance '%s' did not change to '%s' after %s."
                    % (instance_id, status, self._time_since(start_time)))
                return False

        return True

    def _time_since(self, start_time):
        return '%.1fs' % (timer.time() - start_time)

    def assert_all_gone(self, instance_ids, expected_last_status):
        self._wait_all_deleted(instance_ids
                               if utils.is_collection(instance_ids)
                               else [instance_ids], expected_last_status)

    def assert_pagination_match(
            self, list_page, full_list, start_idx, end_idx):
        self.assert_equal(full_list[start_idx:end_idx], list(list_page),
                          "List page does not match the expected full "
                          "list section.")

    def _wait_all_deleted(self, instance_ids, expected_last_status):
        tasks = [build_polling_task(
            lambda: self._wait_for_delete(instance_id, expected_last_status),
            sleep_time=self.def_sleep_time, time_out=self.def_timeout)
            for instance_id in instance_ids]
        poll_until(lambda: all(poll_task.ready() for poll_task in tasks),
                   sleep_time=self.def_sleep_time, time_out=self.def_timeout)

        for task in tasks:
            if task.has_result():
                self.assert_true(
                    task.poll_result(),
                    "Some instances were not removed.")
            elif task.has_exception():
                self.fail(str(task.poll_exception()))

    def _wait_for_delete(self, instance_id, expected_last_status):
        start_time = timer.time()
        try:
            self._poll_while(instance_id, expected_last_status,
                             sleep_time=self.def_sleep_time,
                             time_out=self.def_timeout)
        except exceptions.NotFound:
            self.assert_client_code(404)
            self.report.log("Instance was removed in %s." %
                            self._time_since(start_time))
            return True
        except exception.PollTimeOut:
            self.report.log(
                "Instance '%s' still existed after %s."
                % (instance_id, self._time_since(start_time)))

        return False

    def _poll_while(self, instance_id, expected_status,
                    sleep_time=1, time_out=None):
        poll_until(lambda: not self._has_status(instance_id, expected_status),
                   sleep_time=sleep_time, time_out=time_out)

    def _has_status(self, instance_id, status, fast_fail_status=None):
        instance = self.get_instance(instance_id)
        self.report.log("Waiting for instance '%s' to become '%s': %s"
                        % (instance_id, status, instance.status))
        if fast_fail_status and instance.status == fast_fail_status:
            raise RuntimeError("Instance '%s' acquired a fast-fail status: %s"
                               % (instance_id, status))
        return instance.status == status

    def get_instance(self, instance_id):
        return self.auth_client.instances.get(instance_id)

    def get_instance_host(self, instance_id=None):
        instance_id = instance_id or self.instance_info.id
        instance = self.get_instance(instance_id)
        host = str(instance._info['ip'][0])
        self.report.log("Found host %s for instance %s." % (host, instance_id))
        return host

    def build_flavor(self, flavor_id=2, volume_size=1):
        return {"flavorRef": flavor_id, "volume": {"size": volume_size}}

    def get_flavor(self, flavor_name):
        flavors = self.auth_client.find_flavors_by_name(flavor_name)
        self.assert_equal(
            1, len(flavors),
            "Unexpected number of flavors with name '%s' found." % flavor_name)
        flavor = flavors[0]
        self.assert_is_not_none(flavor, "Flavor '%s' not found." % flavor_name)

        return flavor
