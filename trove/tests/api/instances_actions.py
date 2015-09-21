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

import time

from proboscis import after_class
from proboscis import asserts
from proboscis import before_class
from proboscis.decorators import time_out
from proboscis import SkipTest
from proboscis import test
from sqlalchemy import exc as sqlalchemy_exc
from sqlalchemy.sql.expression import text
from troveclient.compat.exceptions import BadRequest
from troveclient.compat.exceptions import HTTPNotImplemented

from trove.common.utils import poll_until
from trove import tests
from trove.tests.api.instances import assert_unprocessable
from trove.tests.api.instances import EPHEMERAL_SUPPORT
from trove.tests.api.instances import GROUP as INSTANCE_GROUP
from trove.tests.api.instances import GROUP_START
from trove.tests.api.instances import instance_info
from trove.tests.api.instances import VOLUME_SUPPORT
from trove.tests.config import CONFIG
import trove.tests.util as testsutil
from trove.tests.util.check import Checker
from trove.tests.util.check import TypeCheck
from trove.tests.util import LocalSqlClient
from trove.tests.util.server_connection import create_server_connection

GROUP = "dbaas.api.instances.actions"
GROUP_REBOOT = "dbaas.api.instances.actions.reboot"
GROUP_RESTART = "dbaas.api.instances.actions.restart"
GROUP_RESIZE = "dbaas.api.instances.actions.resize.instance"
GROUP_STOP_MYSQL = "dbaas.api.instances.actions.stop"
MYSQL_USERNAME = "test_user"
MYSQL_PASSWORD = "abcde"
# stored in test conf
SERVICE_ID = '123'
FAKE_MODE = CONFIG.fake_mode
# If true, then we will actually log into the database.
USE_IP = not FAKE_MODE
# If true, then we will actually search for the process
USE_LOCAL_OVZ = CONFIG.use_local_ovz


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
        try:
            with self.client:
                self.client.execute(text("""SELECT "Hello.";"""))
            return True
        except (sqlalchemy_exc.OperationalError,
                sqlalchemy_exc.DisconnectionError,
                sqlalchemy_exc.TimeoutError):
            return False
        except Exception as ex:
            print("EX WAS:")
            print(type(ex))
            print(ex)
            raise ex


TIME_OUT_TIME = 15 * 60
USER_WAS_DELETED = False


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
        """Make sure MySQL is accessible before restarting."""
        with Checker() as check:
            if USE_IP:
                self.connection.connect()
                check.true(self.connection.is_connected(),
                           "Able to connect to MySQL.")
                self.proc_id = self.find_mysql_proc_on_instance()
                check.true(self.proc_id is not None,
                           "MySQL process can not be found.")
            instance = self.instance
            check.false(instance is None)
            check.equal(instance.status, "ACTIVE")

    def find_mysql_proc_on_instance(self):
        server = create_server_connection(self.instance_id)
        cmd = "ps acux | grep mysqld " \
              "| grep -v mysqld_safe | awk '{print $2}'"
        stdout, stderr = server.execute(cmd)
        try:
            return int(stdout)
        except ValueError:
            return None

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


@test(depends_on_groups=[GROUP_START])
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

    def wait_for_broken_connection(self):
        """Wait until our connection breaks."""
        if not USE_IP:
            return
        if not hasattr(self, "connection"):
            return
        poll_until(self.connection.is_connected,
                   lambda connected: not connected,
                   time_out=TIME_OUT_TIME)

    def wait_for_successful_restart(self):
        """Wait until status becomes running."""
        def is_finished_rebooting():
            instance = self.instance
            if instance.status == "REBOOT":
                return False
            asserts.assert_equal("ACTIVE", instance.status)
            return True

        poll_until(is_finished_rebooting, time_out=TIME_OUT_TIME)

    def assert_mysql_proc_is_different(self):
        if not USE_IP:
            return
        new_proc_id = self.find_mysql_proc_on_instance()
        asserts.assert_not_equal(new_proc_id, self.proc_id,
                                 "MySQL process ID should be different!")

    def successful_restart(self):
        """Restart MySQL via the REST API successfully."""
        self.fix_mysql()
        self.call_reboot()
        self.wait_for_broken_connection()
        self.wait_for_successful_restart()
        self.assert_mysql_proc_is_different()

    def mess_up_mysql(self):
        """Ruin MySQL's ability to restart."""
        server = create_server_connection(self.instance_id)
        cmd = "sudo cp /dev/null /var/lib/mysql/data/ib_logfile%d"
        instance_info.dbaas_admin.management.stop(self.instance_id)
        for index in range(2):
            server.execute(cmd % index)

    def fix_mysql(self):
        """Fix MySQL's ability to restart."""
        if not FAKE_MODE:
            server = create_server_connection(self.instance_id)
            cmd = "sudo rm /var/lib/mysql/data/ib_logfile%d"
            # We want to stop mysql so that upstart does not keep trying to
            # respawn it and block the guest agent from accessing the logs.
            instance_info.dbaas_admin.management.stop(self.instance_id)
            for index in range(2):
                server.execute(cmd % index)

    def wait_for_failure_status(self):
        """Wait until status becomes running."""
        def is_finished_rebooting():
            instance = self.instance
            if instance.status == "REBOOT" or instance.status == "ACTIVE":
                return False
            # The reason we check for BLOCKED as well as SHUTDOWN is because
            # Upstart might try to bring mysql back up after the borked
            # connection and the guest status can be either
            asserts.assert_true(instance.status in ("SHUTDOWN", "BLOCKED"))
            return True

        poll_until(is_finished_rebooting, time_out=TIME_OUT_TIME)

    def unsuccessful_restart(self):
        """Restart MySQL via the REST when it should fail, assert it does."""
        assert not FAKE_MODE
        self.mess_up_mysql()
        self.call_reboot()
        self.wait_for_broken_connection()
        self.wait_for_failure_status()

    def restart_normally(self):
        """Fix iblogs and reboot normally."""
        self.fix_mysql()
        self.test_successful_restart()


@test(groups=[tests.INSTANCES, INSTANCE_GROUP, GROUP, GROUP_RESTART],
      depends_on_groups=[GROUP_START], depends_on=[create_user])
class RestartTests(RebootTestBase):
    """Tests restarting MySQL."""

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

    @test(depends_on=[test_ensure_mysql_is_running], enabled=not FAKE_MODE)
    def test_unsuccessful_restart(self):
        """Restart MySQL via the REST when it should fail, assert it does."""
        if FAKE_MODE:
            raise SkipTest("Cannot run this in fake mode.")
        self.unsuccessful_restart()

    @test(depends_on=[test_set_up],
          runs_after=[test_ensure_mysql_is_running, test_unsuccessful_restart])
    def test_successful_restart(self):
        """Restart MySQL via the REST API successfully."""
        self.successful_restart()


@test(groups=[tests.INSTANCES, INSTANCE_GROUP, GROUP, GROUP_STOP_MYSQL],
      depends_on_groups=[GROUP_START], depends_on=[create_user])
class StopTests(RebootTestBase):
    """Tests which involve stopping MySQL."""

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
        """Stops MySQL."""
        instance_info.dbaas_admin.management.stop(self.instance_id)
        self.wait_for_broken_connection()
        self.wait_for_failure_status()

    @test(depends_on=[test_stop_mysql])
    def test_instance_get_shows_volume_info_while_mysql_is_down(self):
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

    @test(depends_on=[test_set_up],
          runs_after=[test_instance_get_shows_volume_info_while_mysql_is_down])
    def test_successful_restart_when_in_shutdown_state(self):
        """Restart MySQL via the REST API successfully when MySQL is down."""
        self.successful_restart()


@test(groups=[tests.INSTANCES, INSTANCE_GROUP, GROUP, GROUP_REBOOT],
      depends_on_groups=[GROUP_START], depends_on=[RestartTests, create_user])
class RebootTests(RebootTestBase):
    """Tests restarting instance."""

    def call_reboot(self):
        instance_info.dbaas_admin.management.reboot(self.instance_id)

    @before_class
    def test_set_up(self):
        self.set_up()
        asserts.assert_true(hasattr(self, 'dbaas'))
        asserts.assert_true(self.dbaas is not None)

    @test
    def test_ensure_mysql_is_running(self):
        """Make sure MySQL is accessible before restarting."""
        self.ensure_mysql_is_running()

    @test(depends_on=[test_ensure_mysql_is_running])
    def test_unsuccessful_restart(self):
        """Restart MySQL via the REST when it should fail, assert it does."""
        if FAKE_MODE:
            raise SkipTest("Cannot run this in fake mode.")
        self.unsuccessful_restart()

    @after_class(depends_on=[test_set_up])
    def test_successful_restart(self):
        """Restart MySQL via the REST API successfully."""
        if FAKE_MODE:
            raise SkipTest("Cannot run this in fake mode.")
        self.successful_restart()


@test(groups=[tests.INSTANCES, INSTANCE_GROUP, GROUP,
              GROUP_RESIZE],
      depends_on_groups=[GROUP_START], depends_on=[create_user],
      runs_after=[RebootTests])
class ResizeInstanceTest(ActionTestBase):

    """
    Integration Test cases for resize instance
    """
    @property
    def flavor_id(self):
        return instance_info.dbaas_flavor_href

    def get_flavor_href(self, flavor_id=2):
        res = instance_info.dbaas.find_flavor_and_self_href(flavor_id)
        dbaas_flavor, dbaas_flavor_href = res
        return dbaas_flavor_href

    def wait_for_resize(self):
        def is_finished_resizing():
            instance = self.instance
            if instance.status == "RESIZE":
                return False
            asserts.assert_equal("ACTIVE", instance.status)
            return True
        poll_until(is_finished_resizing, time_out=TIME_OUT_TIME)

    @before_class
    def setup(self):
        self.set_up()
        if USE_IP:
            self.connection.connect()
            asserts.assert_true(self.connection.is_connected(),
                                "Should be able to connect before resize.")
        self.user_was_deleted = False

    @test
    def test_instance_resize_same_size_should_fail(self):
        asserts.assert_raises(BadRequest, self.dbaas.instances.resize_instance,
                              self.instance_id, self.flavor_id)

    @test(enabled=VOLUME_SUPPORT)
    def test_instance_resize_to_ephemeral_in_volume_support_should_fail(self):
        flavor_name = CONFIG.values.get('instance_bigger_eph_flavor_name',
                                        'eph.rd-smaller')
        flavors = self.dbaas.find_flavors_by_name(flavor_name)

        def is_active():
            return self.instance.status == 'ACTIVE'
        poll_until(is_active, time_out=TIME_OUT_TIME)
        asserts.assert_equal(self.instance.status, 'ACTIVE')

        self.get_flavor_href(
            flavor_id=self.expected_old_flavor_id)
        asserts.assert_raises(HTTPNotImplemented,
                              self.dbaas.instances.resize_instance,
                              self.instance_id, flavors[0].id)

    @test(enabled=EPHEMERAL_SUPPORT)
    def test_instance_resize_to_non_ephemeral_flavor_should_fail(self):
        flavor_name = CONFIG.values.get('instance_bigger_flavor_name',
                                        'm1-small')
        flavors = self.dbaas.find_flavors_by_name(flavor_name)
        asserts.assert_raises(BadRequest, self.dbaas.instances.resize_instance,
                              self.instance_id, flavors[0].id)

    def obtain_flavor_ids(self):
        old_id = self.instance.flavor['id']
        self.expected_old_flavor_id = old_id
        res = instance_info.dbaas.find_flavor_and_self_href(old_id)
        self.expected_dbaas_flavor, _dontcare_ = res
        if EPHEMERAL_SUPPORT:
            flavor_name = CONFIG.values.get('instance_bigger_eph_flavor_name',
                                            'eph.rd-smaller')
        else:
            flavor_name = CONFIG.values.get('instance_bigger_flavor_name',
                                            'm1.small')
        flavors = self.dbaas.find_flavors_by_name(flavor_name)
        asserts.assert_equal(len(flavors), 1,
                             "Number of flavors with name '%s' "
                             "found was '%d'." % (flavor_name,
                                                  len(flavors)))
        flavor = flavors[0]
        self.old_dbaas_flavor = instance_info.dbaas_flavor
        instance_info.dbaas_flavor = flavor
        asserts.assert_true(flavor is not None,
                            "Flavor '%s' not found!" % flavor_name)
        flavor_href = self.dbaas.find_flavor_self_href(flavor)
        asserts.assert_true(flavor_href is not None,
                            "Flavor href '%s' not found!" % flavor_name)
        self.expected_new_flavor_id = flavor.id

    @test(depends_on=[test_instance_resize_same_size_should_fail])
    def test_status_changed_to_resize(self):
        self.log_current_users()
        self.obtain_flavor_ids()
        self.dbaas.instances.resize_instance(
            self.instance_id,
            self.get_flavor_href(flavor_id=self.expected_new_flavor_id))
        asserts.assert_equal(202, self.dbaas.last_http_code)

        # (WARNING) IF THE RESIZE IS WAY TOO FAST THIS WILL FAIL
        assert_unprocessable(
            self.dbaas.instances.resize_instance,
            self.instance_id,
            self.get_flavor_href(flavor_id=self.expected_new_flavor_id))

    @test(depends_on=[test_status_changed_to_resize])
    @time_out(TIME_OUT_TIME)
    def test_instance_returns_to_active_after_resize(self):
        self.wait_for_resize()

    @test(depends_on=[test_instance_returns_to_active_after_resize,
                      test_status_changed_to_resize],
          groups=["dbaas.usage"])
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
            self.connection.connect()
            if not self.connection.is_connected():
                # Ok, this is def. a failure, but before we toss up an error
                # lets recreate to see how far we can get.
                CONFIG.get_report().log(
                    "Having to recreate the test_user! Resizing killed it!")
                self.log_current_users()
                self.create_user()
                asserts.fail(
                    "Somehow, the resize made the test user disappear.")

    @test(depends_on=[test_instance_returns_to_active_after_resize],
          runs_after=[resize_should_not_delete_users])
    def test_make_sure_mysql_is_running_after_resize(self):
        self.ensure_mysql_is_running()

    @test(depends_on=[test_instance_returns_to_active_after_resize],
          runs_after=[test_make_sure_mysql_is_running_after_resize])
    def test_instance_has_new_flavor_after_resize(self):
        actual = self.get_flavor_href(self.instance.flavor['id'])
        expected = self.get_flavor_href(flavor_id=self.expected_new_flavor_id)
        asserts.assert_equal(actual, expected)

    @test(depends_on=[test_instance_has_new_flavor_after_resize])
    @time_out(TIME_OUT_TIME)
    def test_resize_down(self):
        expected_dbaas_flavor = self.expected_dbaas_flavor

        def is_active():
            return self.instance.status == 'ACTIVE'
        poll_until(is_active, time_out=TIME_OUT_TIME)
        asserts.assert_equal(self.instance.status, 'ACTIVE')

        old_flavor_href = self.get_flavor_href(
            flavor_id=self.expected_old_flavor_id)

        self.dbaas.instances.resize_instance(self.instance_id, old_flavor_href)
        asserts.assert_equal(202, self.dbaas.last_http_code)
        self.old_dbaas_flavor = instance_info.dbaas_flavor
        instance_info.dbaas_flavor = expected_dbaas_flavor
        self.wait_for_resize()
        asserts.assert_equal(str(self.instance.flavor['id']),
                             str(self.expected_old_flavor_id))

    @test(depends_on=[test_resize_down],
          groups=["dbaas.usage"])
    def test_resize_instance_down_usage_event_sent(self):
        expected = self._build_expected_msg()
        expected['old_instance_size'] = self.old_dbaas_flavor.ram
        instance_info.consumer.check_message(instance_info.id,
                                             'trove.instance.modify_flavor',
                                             **expected)


@test(groups=[tests.INSTANCES, INSTANCE_GROUP, GROUP,
              GROUP + ".resize.instance"],
      depends_on_groups=[GROUP_START], depends_on=[create_user],
      runs_after=[RebootTests, ResizeInstanceTest])
def resize_should_not_delete_users():
    if USER_WAS_DELETED:
        asserts.fail("Somehow, the resize made the test user disappear.")


@test(runs_after=[ResizeInstanceTest], depends_on=[create_user],
      groups=[GROUP, tests.INSTANCES, INSTANCE_GROUP, GROUP_RESIZE],
      enabled=VOLUME_SUPPORT)
class ResizeInstanceVolume(ActionTestBase):
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
        instance_info.dbaas.instances.resize_volume(instance_info.id,
                                                    self.new_volume_size)

    @test(depends_on=[test_volume_resize])
    @time_out(300)
    def test_volume_resize_success(self):

        def check_resize_status():
            instance = instance_info.dbaas.instances.get(instance_info.id)
            if instance.status == "ACTIVE":
                return True
            elif instance.status == "RESIZE":
                return False
            else:
                asserts.fail("Status should not be %s" % instance.status)

        poll_until(check_resize_status, sleep_time=2, time_out=300)
        instance = instance_info.dbaas.instances.get(instance_info.id)
        asserts.assert_equal(instance.volume['size'], self.new_volume_size)

    @test(depends_on=[test_volume_resize_success])
    def test_volume_filesystem_resize_success(self):
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

    @test(depends_on=[test_volume_resize_success], groups=["dbaas.usage"])
    def test_resize_volume_usage_event_sent(self):
        expected = self._build_expected_msg()
        expected['volume_size'] = self.new_volume_size
        expected['old_volume_size'] = self.old_volume_size
        instance_info.consumer.check_message(instance_info.id,
                                             'trove.instance.modify_volume',
                                             **expected)

    @test
    @time_out(300)
    def test_volume_resize_success_databases(self):
        databases = instance_info.dbaas.databases.list(instance_info.id)
        db_list = []
        for database in databases:
            db_list.append(database.name)
        for name in self.expected_dbs:
            if name not in db_list:
                asserts.fail(
                    "Database %s was not found after the volume resize. "
                    "Returned list: %s" % (name, databases))


# This tests the ability of the guest to upgrade itself.
# It is necessarily tricky because we need to be able to upload a new copy of
# the guest into an apt-repo in the middle of the test.
# "guest-update-test" is where the knowledge of how to do this is set in the
# test conf. If it is not specified this test never runs.
UPDATE_GUEST_CONF = CONFIG.values.get("guest-update-test", None)


@test(groups=[tests.INSTANCES, INSTANCE_GROUP, GROUP, GROUP + ".update_guest"],
      depends_on=[create_user],
      depends_on_groups=[GROUP_START])
class UpdateGuest(object):

    def get_version(self):
        info = instance_info.dbaas_admin.diagnostics.get(instance_info.id)
        return info.version

    @before_class(enabled=UPDATE_GUEST_CONF is not None)
    def check_version_is_old(self):
        """Make sure we have the old version before proceeding."""
        self.old_version = self.get_version()
        self.next_version = UPDATE_GUEST_CONF["next-version"]
        asserts.assert_not_equal(self.old_version, self.next_version)

    @test(enabled=UPDATE_GUEST_CONF is not None)
    def upload_update_to_repo(self):
        cmds = UPDATE_GUEST_CONF["install-repo-cmd"]
        testsutil.execute(*cmds, run_as_root=True, root_helper="sudo")

    @test(enabled=UPDATE_GUEST_CONF is not None,
          depends_on=[upload_update_to_repo])
    def update_and_wait_to_finish(self):
        instance_info.dbaas_admin.management.update(instance_info.id)

        def finished():
            current_version = self.get_version()
            if current_version == self.next_version:
                return True
            # The only valid thing for it to be aside from next_version is
            # old version.
            asserts.assert_equal(current_version, self.old_version)
        poll_until(finished, sleep_time=1, time_out=3 * 60)

    @test(enabled=UPDATE_GUEST_CONF is not None,
          depends_on=[upload_update_to_repo])
    @time_out(30)
    def update_again(self):
        """Test the wait time of a pointless update."""
        instance_info.dbaas_admin.management.update(instance_info.id)
        # Make sure this isn't taking too long.
        instance_info.dbaas_admin.diagnostics.get(instance_info.id)
