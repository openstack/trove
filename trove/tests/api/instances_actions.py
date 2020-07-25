# Copyright 2011 OpenStack Foundation
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
import time

from proboscis import after_class
from proboscis import asserts
from proboscis import before_class
from proboscis.decorators import time_out
from proboscis import SkipTest
from proboscis import test
from troveclient.compat.exceptions import BadRequest
from troveclient.compat.exceptions import HTTPNotImplemented

from trove.common import cfg
from trove.common.utils import poll_until
from trove import tests
from trove.tests.api.instances import assert_unprocessable
from trove.tests.api.instances import EPHEMERAL_SUPPORT
from trove.tests.api.instances import instance_info
from trove.tests.api.instances import VOLUME_SUPPORT
from trove.tests.config import CONFIG
import trove.tests.util as testsutil
from trove.tests.util.check import TypeCheck
from trove.tests.util import LocalSqlClient
from trove.tests.util.server_connection import create_server_connection

MYSQL_USERNAME = "test_user"
MYSQL_PASSWORD = "abcde"
FAKE_MODE = CONFIG.fake_mode
# If true, then we will actually log into the database.
USE_IP = not FAKE_MODE


class MySqlConnection(object):

    def __init__(self, host):
        self.host = host

    def connect(self):
        """Connect to MySQL database."""
        print("Connecting to MySQL, mysql --host %s -u %s -p%s"
              % (self.host, MYSQL_USERNAME, MYSQL_PASSWORD))
        sql_engine = LocalSqlClient.init_engine(MYSQL_USERNAME, MYSQL_PASSWORD,
                                                self.host)
        self.client = LocalSqlClient(sql_engine, use_flush=False)

    def is_connected(self):
        cmd = "SELECT 1;"
        try:
            with self.client:
                self.client.execute(cmd)
            return True
        except Exception as e:
            print(
                "Failed to execute command: %s, error: %s" % (cmd, str(e))
            )
            return False

    def execute(self, cmd):
        try:
            with self.client:
                self.client.execute(cmd)
            return True
        except Exception as e:
            print(
                "Failed to execute command: %s, error: %s" % (cmd, str(e))
            )
            return False


# Use default value from trove.common.cfg, and it could be overridden by
# a environment variable when the tests run.
def get_resize_timeout():
    value_from_env = os.environ.get("TROVE_RESIZE_TIME_OUT", None)
    if value_from_env:
        return int(value_from_env)

    return cfg.CONF.resize_time_out


TIME_OUT_TIME = get_resize_timeout()


class ActionTestBase(object):
    """Has some helpful functions for testing actions.

    The test user must be created for some of these functions to work.

    """

    def set_up(self):
        """If you're using this as a base class, call this method first."""
        self.dbaas = instance_info.dbaas
        if USE_IP:
            address = instance_info.get_address()
            self.connection = MySqlConnection(address)

    @property
    def instance(self):
        return self.dbaas.instances.get(self.instance_id)

    @property
    def instance_address(self):
        return instance_info.get_address()

    @property
    def instance_mgmt_address(self):
        return instance_info.get_address(mgmt=True)

    @property
    def instance_id(self):
        return instance_info.id

    def create_user(self):
        """Create a MySQL user we can use for this test."""

        users = [{"name": MYSQL_USERNAME, "password": MYSQL_PASSWORD,
                  "databases": [{"name": MYSQL_USERNAME}]}]
        self.dbaas.users.create(instance_info.id, users)

        def has_user():
            users = self.dbaas.users.list(instance_info.id)
            return any([user.name == MYSQL_USERNAME for user in users])

        poll_until(has_user, time_out=30)
        if not FAKE_MODE:
            time.sleep(5)

    def ensure_mysql_is_running(self):
        if USE_IP:
            self.connection.connect()
            asserts.assert_true(self.connection.is_connected(),
                                "Unable to connect to MySQL.")

            self.proc_id = self.find_mysql_proc_on_instance()
            asserts.assert_is_not_none(self.proc_id,
                                       "MySQL process can not be found.")

        asserts.assert_is_not_none(self.instance)
        asserts.assert_true(self.instance.status in CONFIG.running_status)

    def find_mysql_proc_on_instance(self):
        server = create_server_connection(
            self.instance_id,
            ip_address=self.instance_mgmt_address
        )
        container_exist_cmd = 'sudo docker ps -q'
        pid_cmd = "sudo docker inspect database -f '{{.State.Pid}}'"

        try:
            server.execute(container_exist_cmd)
        except Exception as err:
            asserts.fail("Failed to execute command: %s, error: %s" %
                         (container_exist_cmd, str(err)))

        try:
            stdout = server.execute(pid_cmd)
            return int(stdout)
        except ValueError:
            return None
        except Exception as err:
            asserts.fail("Failed to execute command: %s, error: %s" %
                         (pid_cmd, str(err)))

    def log_current_users(self):
        users = self.dbaas.users.list(self.instance_id)
        CONFIG.get_report().log("Current user count = %d" % len(users))
        for user in users:
            CONFIG.get_report().log("\t" + str(user))

    def _build_expected_msg(self):
        expected = {
            'instance_size': instance_info.dbaas_flavor.ram,
            'tenant_id': instance_info.user.tenant_id,
            'instance_id': instance_info.id,
            'instance_name': instance_info.name,
            'created_at': testsutil.iso_time(
                instance_info.initial_result.created),
            'launched_at': testsutil.iso_time(self.instance.updated),
            'modify_at': testsutil.iso_time(self.instance.updated)
        }
        return expected


@test(depends_on_groups=[tests.DBAAS_API_INSTANCES])
def create_user():
    """Create a test user so that subsequent tests can log in."""
    helper = ActionTestBase()
    helper.set_up()
    if USE_IP:
        try:
            helper.create_user()
        except BadRequest:
            pass  # Ignore this if the user already exists.
        helper.connection.connect()
        asserts.assert_true(helper.connection.is_connected(),
                            "Test user must be able to connect to MySQL.")


class RebootTestBase(ActionTestBase):
    """Tests restarting MySQL."""

    def call_reboot(self):
        raise NotImplementedError()

    def wait_for_successful_restart(self):
        """Wait until status becomes running.

        Reboot is an async operation, make sure the instance is rebooting
        before active.
        """
        def _is_rebooting():
            instance = self.instance
            if instance.status == "REBOOT":
                return True
            return False

        poll_until(_is_rebooting, time_out=TIME_OUT_TIME)

        def is_finished_rebooting():
            instance = self.instance
            asserts.assert_not_equal(instance.status, "ERROR")
            if instance.status in CONFIG.running_status:
                return True
            return False

        poll_until(is_finished_rebooting, time_out=TIME_OUT_TIME)

    def assert_mysql_proc_is_different(self):
        if not USE_IP:
            return
        new_proc_id = self.find_mysql_proc_on_instance()
        asserts.assert_not_equal(new_proc_id, self.proc_id,
                                 "MySQL process ID should be different!")

    def successful_restart(self):
        """Restart MySQL via the REST API successfully."""
        self.call_reboot()
        self.wait_for_successful_restart()
        self.assert_mysql_proc_is_different()

    def wait_for_failure_status(self):
        """Wait until status becomes running."""
        def is_finished_rebooting():
            instance = self.instance
            if instance.status in ['REBOOT', 'ACTIVE', 'HEALTHY']:
                return False
            # The reason we check for BLOCKED as well as SHUTDOWN is because
            # Upstart might try to bring mysql back up after the borked
            # connection and the guest status can be either
            asserts.assert_true(instance.status in ("SHUTDOWN", "BLOCKED"))
            return True

        poll_until(is_finished_rebooting, time_out=TIME_OUT_TIME)

    def wait_for_status(self, status, timeout=60, sleep_time=5):
        def is_status():
            instance = self.instance
            if instance.status in status:
                return True
            return False

        poll_until(is_status, time_out=timeout, sleep_time=sleep_time)


@test(groups=[tests.DBAAS_API_INSTANCE_ACTIONS],
      depends_on_groups=[tests.DBAAS_API_DATABASES],
      depends_on=[create_user])
class RestartTests(RebootTestBase):
    """Test restarting MySQL."""

    def call_reboot(self):
        self.instance.restart()
        asserts.assert_equal(202, self.dbaas.last_http_code)

    @before_class
    def test_set_up(self):
        self.set_up()

    @test
    def test_ensure_mysql_is_running(self):
        """Make sure MySQL is accessible before restarting."""
        self.ensure_mysql_is_running()

    @test(depends_on=[test_ensure_mysql_is_running])
    def test_successful_restart(self):
        """Restart MySQL via the REST API successfully."""
        self.successful_restart()


@test(groups=[tests.DBAAS_API_INSTANCE_ACTIONS],
      depends_on_classes=[RestartTests])
class StopTests(RebootTestBase):
    """Test stopping MySQL."""

    def call_reboot(self):
        self.instance.restart()

    @before_class
    def test_set_up(self):
        self.set_up()

    @test
    def test_ensure_mysql_is_running(self):
        """Make sure MySQL is accessible before restarting."""
        self.ensure_mysql_is_running()

    @test(depends_on=[test_ensure_mysql_is_running])
    def test_stop_mysql(self):
        """Stops MySQL by admin."""
        instance_info.dbaas_admin.management.stop(self.instance_id)

        # The instance status will only be updated by guest agent.
        self.wait_for_status(['SHUTDOWN'], timeout=90, sleep_time=10)

    @test(depends_on=[test_stop_mysql])
    def test_volume_info_while_mysql_is_down(self):
        """
        Confirms the get call behaves appropriately while an instance is
        down.
        """
        if not VOLUME_SUPPORT:
            raise SkipTest("Not testing volumes.")
        instance = self.dbaas.instances.get(self.instance_id)
        with TypeCheck("instance", instance) as check:
            check.has_field("volume", dict)
            check.true('size' in instance.volume)
            check.true('used' in instance.volume)
            check.true(isinstance(instance.volume.get('size', None), int))
            check.true(isinstance(instance.volume.get('used', None), float))

    @test(depends_on=[test_volume_info_while_mysql_is_down])
    def test_successful_restart_from_shutdown(self):
        """Restart MySQL via the REST API successfully when MySQL is down."""
        self.successful_restart()


@test(groups=[tests.DBAAS_API_INSTANCE_ACTIONS],
      depends_on_classes=[StopTests])
class RebootTests(RebootTestBase):
    """Test restarting instance."""

    def call_reboot(self):
        instance_info.dbaas_admin.management.reboot(self.instance_id)

    @before_class
    def test_set_up(self):
        self.set_up()
        asserts.assert_true(hasattr(self, 'dbaas'))
        asserts.assert_true(self.dbaas is not None)

    @test
    def test_ensure_mysql_is_running(self):
        """Make sure MySQL is accessible before rebooting."""
        self.ensure_mysql_is_running()

    @after_class(depends_on=[test_ensure_mysql_is_running])
    def test_successful_reboot(self):
        """MySQL process is different after rebooting."""
        if FAKE_MODE:
            raise SkipTest("Cannot run this in fake mode.")
        self.successful_restart()


@test(groups=[tests.DBAAS_API_INSTANCE_ACTIONS],
      depends_on_classes=[RebootTests])
class ResizeInstanceTest(ActionTestBase):
    """Test resizing instance."""
    @property
    def flavor_id(self):
        return instance_info.dbaas_flavor_href

    def wait_for_resize(self):
        def is_finished_resizing():
            instance = self.instance
            if instance.status == "RESIZE":
                return False
            asserts.assert_true(instance.status in CONFIG.running_status)
            return True

        poll_until(is_finished_resizing, time_out=TIME_OUT_TIME)

    @before_class
    def setup(self):
        self.set_up()
        if USE_IP:
            self.connection.connect()
            asserts.assert_true(self.connection.is_connected(),
                                "Should be able to connect before resize.")

    @test
    def test_instance_resize_same_size_should_fail(self):
        asserts.assert_raises(BadRequest, self.dbaas.instances.resize_instance,
                              self.instance_id, self.flavor_id)

    @test(enabled=VOLUME_SUPPORT)
    def test_instance_resize_to_ephemeral_in_volume_support_should_fail(self):
        flavor_name = CONFIG.values.get('instance_bigger_eph_flavor_name',
                                        'eph.rd-smaller')
        flavor_id = None
        for item in instance_info.flavors:
            if item.name == flavor_name:
                flavor_id = item.id

        asserts.assert_is_not_none(flavor_id)

        def is_active():
            return self.instance.status in CONFIG.running_status

        poll_until(is_active, time_out=TIME_OUT_TIME)
        asserts.assert_true(self.instance.status in CONFIG.running_status)

        asserts.assert_raises(HTTPNotImplemented,
                              self.dbaas.instances.resize_instance,
                              self.instance_id, flavor_id)

    @test(enabled=EPHEMERAL_SUPPORT)
    def test_instance_resize_to_non_ephemeral_flavor_should_fail(self):
        flavor_name = CONFIG.values.get('instance_bigger_flavor_name',
                                        'm1-small')
        flavor_id = None
        for item in instance_info.flavors:
            if item.name == flavor_name:
                flavor_id = item.id

        asserts.assert_is_not_none(flavor_id)
        asserts.assert_raises(BadRequest, self.dbaas.instances.resize_instance,
                              self.instance_id, flavor_id)

    def obtain_flavor_ids(self):
        old_id = self.instance.flavor['id']
        self.expected_old_flavor_id = old_id
        if EPHEMERAL_SUPPORT:
            flavor_name = CONFIG.values.get('instance_bigger_eph_flavor_name',
                                            'eph.rd-smaller')
        else:
            flavor_name = CONFIG.values.get('instance_bigger_flavor_name',
                                            'm1.small')

        new_flavor = None
        for item in instance_info.flavors:
            if item.name == flavor_name:
                new_flavor = item
                break

        asserts.assert_is_not_none(new_flavor)

        self.old_dbaas_flavor = instance_info.dbaas_flavor
        instance_info.dbaas_flavor = new_flavor
        self.expected_new_flavor_id = new_flavor.id

    @test(depends_on=[test_instance_resize_same_size_should_fail])
    def test_status_changed_to_resize(self):
        """test_status_changed_to_resize"""
        self.log_current_users()
        self.obtain_flavor_ids()
        self.dbaas.instances.resize_instance(
            self.instance_id,
            self.expected_new_flavor_id)
        asserts.assert_equal(202, self.dbaas.last_http_code)

        # (WARNING) IF THE RESIZE IS WAY TOO FAST THIS WILL FAIL
        assert_unprocessable(
            self.dbaas.instances.resize_instance,
            self.instance_id,
            self.expected_new_flavor_id)

    @test(depends_on=[test_status_changed_to_resize])
    @time_out(TIME_OUT_TIME)
    def test_instance_returns_to_active_after_resize(self):
        """test_instance_returns_to_active_after_resize"""
        self.wait_for_resize()

    @test(depends_on=[test_instance_returns_to_active_after_resize,
                      test_status_changed_to_resize])
    def test_resize_instance_usage_event_sent(self):
        expected = self._build_expected_msg()
        expected['old_instance_size'] = self.old_dbaas_flavor.ram
        instance_info.consumer.check_message(instance_info.id,
                                             'trove.instance.modify_flavor',
                                             **expected)

    @test(depends_on=[test_instance_returns_to_active_after_resize],
          runs_after=[test_resize_instance_usage_event_sent])
    def resize_should_not_delete_users(self):
        """Resize should not delete users."""
        # Resize has an incredibly weird bug where users are deleted after
        # a resize. The code below is an attempt to catch this while proceeding
        # with the rest of the test (note the use of runs_after).
        if USE_IP:
            users = self.dbaas.users.list(self.instance_id)
            usernames = [user.name for user in users]
            if MYSQL_USERNAME not in usernames:
                self.create_user()
                asserts.fail("Resize made the test user disappear.")

    @test(depends_on=[test_instance_returns_to_active_after_resize],
          runs_after=[resize_should_not_delete_users])
    def test_make_sure_mysql_is_running_after_resize(self):
        self.ensure_mysql_is_running()

    @test(depends_on=[test_make_sure_mysql_is_running_after_resize])
    def test_instance_has_new_flavor_after_resize(self):
        actual = self.instance.flavor['id']
        asserts.assert_equal(actual, self.expected_new_flavor_id)


@test(depends_on_classes=[ResizeInstanceTest],
      groups=[tests.DBAAS_API_INSTANCE_ACTIONS],
      enabled=VOLUME_SUPPORT)
class ResizeInstanceVolumeTest(ActionTestBase):
    """Resize the volume of the instance."""
    @before_class
    def setUp(self):
        self.set_up()
        self.old_volume_size = int(instance_info.volume['size'])
        self.new_volume_size = self.old_volume_size + 1
        self.old_volume_fs_size = instance_info.get_volume_filesystem_size()

        # Create some databases to check they still exist after the resize
        self.expected_dbs = ['salmon', 'halibut']
        databases = []
        for name in self.expected_dbs:
            databases.append({"name": name})
        instance_info.dbaas.databases.create(instance_info.id, databases)

    @test
    @time_out(60)
    def test_volume_resize(self):
        """test_volume_resize"""
        instance_info.dbaas.instances.resize_volume(instance_info.id,
                                                    self.new_volume_size)

    @test(depends_on=[test_volume_resize])
    def test_volume_resize_success(self):
        """test_volume_resize_success"""

        def check_resize_status():
            instance = instance_info.dbaas.instances.get(instance_info.id)
            if instance.status in CONFIG.running_status:
                return True
            elif instance.status in ["RESIZE", "SHUTDOWN"]:
                return False
            else:
                asserts.fail("Status should not be %s" % instance.status)

        poll_until(check_resize_status, sleep_time=5, time_out=300,
                   initial_delay=5)
        instance = instance_info.dbaas.instances.get(instance_info.id)
        asserts.assert_equal(instance.volume['size'], self.new_volume_size)

    @test(depends_on=[test_volume_resize_success])
    def test_volume_filesystem_resize_success(self):
        """test_volume_filesystem_resize_success"""
        # The get_volume_filesystem_size is a mgmt call through the guestagent
        # and the volume resize occurs through the fake nova-volume.
        # Currently the guestagent fakes don't have access to the nova fakes so
        # it doesn't know that a volume resize happened and to what size so
        # we can't fake the filesystem size.
        if FAKE_MODE:
            raise SkipTest("Cannot run this in fake mode.")
        new_volume_fs_size = instance_info.get_volume_filesystem_size()
        asserts.assert_true(self.old_volume_fs_size < new_volume_fs_size)
        # The total filesystem size is not going to be exactly the same size of
        # cinder volume but it should round to it. (e.g. round(1.9) == 2)
        asserts.assert_equal(round(new_volume_fs_size), self.new_volume_size)

    @test(depends_on=[test_volume_resize_success])
    def test_resize_volume_usage_event_sent(self):
        """test_resize_volume_usage_event_sent"""
        expected = self._build_expected_msg()
        expected['volume_size'] = self.new_volume_size
        expected['old_volume_size'] = self.old_volume_size
        instance_info.consumer.check_message(instance_info.id,
                                             'trove.instance.modify_volume',
                                             **expected)

    @test(depends_on=[test_volume_resize_success])
    def test_volume_resize_success_databases(self):
        """test_volume_resize_success_databases"""
        databases = instance_info.dbaas.databases.list(instance_info.id)
        db_list = []
        for database in databases:
            db_list.append(database.name)
        for name in self.expected_dbs:
            if name not in db_list:
                asserts.fail(
                    "Database %s was not found after the volume resize. "
                    "Returned list: %s" % (name, databases))
