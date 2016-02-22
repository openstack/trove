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

from oslo_config.cfg import NoSuchOptError
from proboscis import asserts
import swiftclient
from troveclient.compat import exceptions

from trove.common import cfg
from trove.common import exception
from trove.common import utils
from trove.common.utils import poll_until, build_polling_task
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
        instance_info.dbaas_datastore = CONFIG.dbaas_datastore
        instance_info.dbaas_datastore_version = CONFIG.dbaas_datastore_version
        if self.VOLUME_SUPPORT:
            instance_info.volume = {'size': CONFIG.get('trove_volume_size', 1)}
        else:
            instance_info.volume = None

        self.auth_client = create_dbaas_client(self.instance_info.user)
        self._unauth_client = None
        self._admin_client = None
        self._swift_client = None
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

    @property
    def unauth_client(self):
        if not self._unauth_client:
            self._unauth_client = self._create_unauthorized_client()
        return self._unauth_client

    def _create_unauthorized_client(self):
        """Create a client from a different 'unauthorized' user
        to facilitate negative testing.
        """
        requirements = Requirements(is_admin=False)
        other_user = CONFIG.users.find_user(
            requirements, black_list=[self.instance_info.user.auth_user])
        return create_dbaas_client(other_user)

    @property
    def admin_client(self):
        if not self._admin_client:
            self._admin_client = self._create_admin_client()
        return self._admin_client

    def _create_admin_client(self):
        """Create a client from an admin user."""
        requirements = Requirements(is_admin=True, services=["swift"])
        admin_user = CONFIG.users.find_user(requirements)
        return create_dbaas_client(admin_user)

    @property
    def swift_client(self):
        if not self._swift_client:
            self._swift_client = self._create_swift_client()
        return self._swift_client

    def _create_swift_client(self):
        """Create a swift client from the admin user details."""
        requirements = Requirements(is_admin=True, services=["swift"])
        user = CONFIG.users.find_user(requirements)
        os_options = {'region_name': os.getenv("OS_REGION_NAME")}
        return swiftclient.client.Connection(
            authurl=CONFIG.nova_client['auth_url'],
            user=user.auth_user,
            key=user.auth_key,
            tenant_name=user.tenant,
            auth_version='2.0',
            os_options=os_options)

    def get_client_tenant(self, client):
        tenant_name = client.real_client.client.tenant
        service_url = client.real_client.client.service_url
        su_parts = service_url.split('/')
        tenant_id = su_parts[-1]
        return tenant_name, tenant_id

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
            datastore = datastore or self.instance_info.dbaas_datastore
            return CONF.get(datastore).get(name)
        except NoSuchOptError:
            return CONF.get(name)

    @property
    def is_using_existing_instance(self):
        return self.has_env_flag(self.USE_INSTANCE_ID_FLAG)

    @staticmethod
    def has_env_flag(flag_name):
        """Return whether a given flag was set."""
        return os.environ.get(flag_name, None) is not None

    def get_existing_instance(self):
        if self.is_using_existing_instance:
            instance_id = os.environ.get(self.USE_INSTANCE_ID_FLAG)
            return self.get_instance(instance_id)

        return None

    @property
    def has_do_not_delete_instance(self):
        return self.has_env_flag(self.DO_NOT_DELETE_INSTANCE_FLAG)

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
                                fast_fail_status=['ERROR', 'FAILED'],
                                require_all_states=False):
        """Keep polling for the expected instance states until the instance
        acquires either the last or fast-fail state.

        If the instance state does not match the state expected at the time of
        polling (and 'require_all_states' is not set) the code assumes the
        instance had already acquired before and moves to the next expected
        state.
        """

        found = False
        for status in expected_states:
            if require_all_states or found or self._has_status(
                    instance_id, status, fast_fail_status=fast_fail_status):
                found = True
                start_time = timer.time()
                try:
                    poll_until(lambda: self._has_status(
                        instance_id, status,
                        fast_fail_status=fast_fail_status),
                        sleep_time=self.def_sleep_time,
                        time_out=self.def_timeout)
                    self.report.log("Instance has gone '%s' in %s." %
                                    (status, self._time_since(start_time)))
                except exception.PollTimeOut:
                    self.report.log(
                        "Status of instance '%s' did not change to '%s' "
                        "after %s."
                        % (instance_id, status, self._time_since(start_time)))
                    return False
            else:
                self.report.log(
                    "Instance state was not '%s', moving to the next expected "
                    "state." % status)

        return found

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
        fast_fail_status = fast_fail_status or []
        instance = self.get_instance(instance_id)
        self.report.log("Polling instance '%s' for state '%s', was '%s'."
                        % (instance_id, status, instance.status))
        if instance.status in fast_fail_status:
            raise RuntimeError("Instance '%s' acquired a fast-fail status: %s"
                               % (instance_id, instance.status))
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

    def copy_dict(self, d, ignored_keys=None):
        return {k: v for k, v in d.items()
                if not ignored_keys or k not in ignored_keys}

    def create_test_helper_on_instance(self, instance_id):
        """Here we add a helper user/database, if any, to a given instance
        via the Trove API.
        These are for internal use by the test framework and should
        not be changed by individual test-cases.
        """
        database_def, user_def = self.build_helper_defs()
        if database_def:
            self.report.log(
                "Creating a helper database '%s' on instance: %s"
                % (database_def['name'], instance_id))
            self.auth_client.databases.create(instance_id, [database_def])

        if user_def:
            self.report.log(
                "Creating a helper user '%s:%s' on instance: %s"
                % (user_def['name'], user_def['password'], instance_id))
            self.auth_client.users.create(instance_id, [user_def])

    def build_helper_defs(self):
        """Build helper database and user JSON definitions if credentials
        are defined by the helper.
        """
        database_def = None
        user_def = None
        credentials = self.test_helper.get_helper_credentials()
        if credentials:
            database = credentials.get('database')
            if database:
                database_def = {'name': database}

            username = credentials.get('name')
            if username:
                password = credentials.get('password', '')
                user_def = {'name': username, 'password': password,
                            'databases': [{'name': database}]}

        return database_def, user_def
