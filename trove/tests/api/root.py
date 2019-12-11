#    Copyright 2011 OpenStack Foundation
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

from nose.plugins.skip import SkipTest
import proboscis
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_not_equal
from proboscis.asserts import assert_raises
from proboscis.asserts import assert_true
from proboscis import test
from troveclient.compat import exceptions

from trove.common import utils
from trove import tests
from trove.tests.api import instances
from trove.tests.config import CONFIG
from trove.tests import util
from trove.tests.util import test_config
from trove.tests.util import users as users_util

GROUP = "dbaas.api.root"


@test(groups=[tests.DBAAS_API, GROUP, tests.INSTANCES])
class TestRoot(object):
    """
    Test the root operations
    """

    root_enabled_timestamp = 'Never'
    system_users = ['root', 'debian_sys_maint']

    @proboscis.before_class
    def setUp(self):
        self.info = instances.InstanceTestInfo()

        reqs = users_util.Requirements(is_admin=True)
        self.info.admin_user = CONFIG.users.find_user(reqs)
        self.info.dbaas_admin = self.dbaas_admin = util.create_dbaas_client(
            self.info.admin_user
        )
        reqs = users_util.Requirements(is_admin=False)
        self.info.user = CONFIG.users.find_user(reqs)
        self.info.dbaas = self.dbaas = util.create_dbaas_client(self.info.user)

        self.info.name = "TEST_%s" % self.__class__.__name__

        flavor, flavor_href = self.info.find_default_flavor()
        self.info.dbaas_flavor = flavor
        self.info.dbaas_flavor_href = flavor_href

        databases = []
        databases.append({"name": "firstdb", "character_set": "latin2",
                          "collate": "latin2_general_ci"})
        databases.append({"name": "db2"})
        self.info.databases = databases

        users = []
        users.append({"name": "lite", "password": "litepass",
                      "databases": [{"name": "firstdb"}]})
        self.info.users = users

        self.info.dbaas_datastore = CONFIG.dbaas_datastore
        self.info.dbaas_datastore_version = CONFIG.dbaas_datastore_version
        self.info.volume = {'size': CONFIG.get('trove_volume_size', 2)}

        self.info.initial_result = self.dbaas.instances.create(
            self.info.name,
            self.info.dbaas_flavor_href,
            self.info.volume,
            databases,
            users,
            nics=self.info.nics,
            availability_zone="nova",
            datastore=self.info.dbaas_datastore,
            datastore_version=self.info.dbaas_datastore_version
        )

        assert_equal(200, self.dbaas.last_http_code)

        self.id = self.info.initial_result.id

        def result_is_active():
            instance = self.dbaas.instances.get(self.id)
            if instance.status in CONFIG.running_status:
                return True
            else:
                # If its not ACTIVE, anything but BUILD must be
                # an error.
                assert_equal("BUILD", instance.status)
                return False

        utils.poll_until(result_is_active)

    @proboscis.after_class
    def tearDown(self):
        self.dbaas.instances.delete(self.id)

        def _is_delete():
            try:
                self.dbaas.instances.get(self.id)
            except exceptions.NotFound:
                return True

        utils.poll_until(_is_delete)

    def _verify_root_timestamp(self, id):
        reh = self.dbaas_admin.management.root_enabled_history(id)
        timestamp = reh.enabled
        assert_equal(self.root_enabled_timestamp, timestamp)
        assert_equal(id, reh.id)

    def _root(self):
        self.dbaas.root.create(self.id)
        assert_equal(200, self.dbaas.last_http_code)
        reh = self.dbaas_admin.management.root_enabled_history
        self.root_enabled_timestamp = reh(self.id).enabled

    @test
    def test_root_initially_disabled(self):
        """Test that root is disabled."""
        enabled = self.dbaas.root.is_root_enabled(self.id)
        assert_equal(200, self.dbaas.last_http_code)

        is_enabled = enabled
        if hasattr(enabled, 'rootEnabled'):
            is_enabled = enabled.rootEnabled
        assert_false(is_enabled, "Root SHOULD NOT be enabled.")

    @test
    def test_create_user_os_admin_failure(self):
        users = [{"name": "os_admin", "password": "12345"}]
        assert_raises(exceptions.BadRequest, self.dbaas.users.create,
                      self.id, users)

    @test
    def test_delete_user_os_admin_failure(self):
        assert_raises(exceptions.BadRequest, self.dbaas.users.delete,
                      self.id, "os_admin")

    @test(depends_on=[test_root_initially_disabled],
          enabled=not test_config.values['root_removed_from_instance_api'])
    def test_root_initially_disabled_details(self):
        """Use instance details to test that root is disabled."""
        instance = self.dbaas.instances.get(self.id)
        assert_true(hasattr(instance, 'rootEnabled'),
                    "Instance has no rootEnabled property.")
        assert_false(instance.rootEnabled, "Root SHOULD NOT be enabled.")
        assert_equal(self.root_enabled_timestamp, 'Never')

    @test(depends_on=[test_root_initially_disabled_details])
    def test_root_disabled_in_mgmt_api(self):
        """Verifies in the management api that the timestamp exists."""
        self._verify_root_timestamp(self.id)

    @test(depends_on=[test_root_initially_disabled_details])
    def test_root_disable_when_root_not_enabled(self):
        reh = self.dbaas_admin.management.root_enabled_history
        self.root_enabled_timestamp = reh(self.id).enabled
        assert_raises(exceptions.NotFound, self.dbaas.root.delete,
                      self.id)
        self._verify_root_timestamp(self.id)

    @test(depends_on=[test_root_disable_when_root_not_enabled])
    def test_enable_root(self):
        self._root()

    @test(depends_on=[test_enable_root])
    def test_enabled_timestamp(self):
        assert_not_equal(self.root_enabled_timestamp, 'Never')

    @test(depends_on=[test_enable_root])
    def test_root_not_in_users_list(self):
        """
        Tests that despite having enabled root, user root doesn't appear
        in the users list for the instance.
        """
        users = self.dbaas.users.list(self.id)
        usernames = [user.name for user in users]
        assert_true('root' not in usernames)

    @test(depends_on=[test_enable_root])
    def test_root_now_enabled(self):
        """Test that root is now enabled."""
        enabled = self.dbaas.root.is_root_enabled(self.id)
        assert_equal(200, self.dbaas.last_http_code)
        assert_true(enabled, "Root SHOULD be enabled.")

    @test(depends_on=[test_root_now_enabled],
          enabled=not test_config.values['root_removed_from_instance_api'])
    def test_root_now_enabled_details(self):
        """Use instance details to test that root is now enabled."""
        instance = self.dbaas.instances.get(self.id)
        assert_true(hasattr(instance, 'rootEnabled'),
                    "Instance has no rootEnabled property.")
        assert_true(instance.rootEnabled, "Root SHOULD be enabled.")
        assert_not_equal(self.root_enabled_timestamp, 'Never')
        self._verify_root_timestamp(self.id)

    @test(depends_on=[test_root_now_enabled_details])
    def test_reset_root(self):
        if test_config.values['root_timestamp_disabled']:
            raise SkipTest("Enabled timestamp not enabled yet")
        old_ts = self.root_enabled_timestamp
        self._root()
        assert_not_equal(self.root_enabled_timestamp, 'Never')
        assert_equal(self.root_enabled_timestamp, old_ts)

    @test(depends_on=[test_reset_root])
    def test_root_still_enabled(self):
        """Test that after root was reset it's still enabled."""
        enabled = self.dbaas.root.is_root_enabled(self.id)
        assert_equal(200, self.dbaas.last_http_code)
        assert_true(enabled, "Root SHOULD still be enabled.")

    @test(depends_on=[test_root_still_enabled],
          enabled=not test_config.values['root_removed_from_instance_api'])
    def test_root_still_enabled_details(self):
        """Use instance details to test that after root was reset,
            it's still enabled.
        """
        instance = self.dbaas.instances.get(self.id)
        assert_true(hasattr(instance, 'rootEnabled'),
                    "Instance has no rootEnabled property.")
        assert_true(instance.rootEnabled, "Root SHOULD still be enabled.")
        assert_not_equal(self.root_enabled_timestamp, 'Never')
        self._verify_root_timestamp(self.id)

    @test(depends_on=[test_enable_root])
    def test_root_cannot_be_deleted(self):
        """Even if root was enabled, the user root cannot be deleted."""
        assert_raises(exceptions.BadRequest, self.dbaas.users.delete,
                      self.id, "root")

    @test(depends_on=[test_root_still_enabled_details])
    def test_root_disable(self):
        reh = self.dbaas_admin.management.root_enabled_history
        self.root_enabled_timestamp = reh(self.id).enabled
        self.dbaas.root.delete(self.id)
        assert_equal(204, self.dbaas.last_http_code)
        self._verify_root_timestamp(self.id)
