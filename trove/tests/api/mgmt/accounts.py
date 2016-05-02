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
from proboscis import after_class
from proboscis import asserts
from proboscis import before_class
from proboscis.decorators import time_out
from proboscis import test
import six
from troveclient.compat import exceptions

from trove.common.utils import poll_until
from trove import tests
from trove.tests.api.instances import instance_info
from trove.tests.config import CONFIG
from trove.tests.util import create_dbaas_client
from trove.tests.util import test_config
from trove.tests.util.users import Requirements


GROUP = "dbaas.api.mgmt.accounts"


@test(groups=[tests.DBAAS_API, GROUP, tests.PRE_INSTANCES],
      depends_on_groups=["services.initialize"])
class AccountsBeforeInstanceCreation(object):

    @before_class
    def setUp(self):
        self.user = test_config.users.find_user(Requirements(is_admin=True))
        self.client = create_dbaas_client(self.user)

    @test
    def test_invalid_account_fails(self):
        account_info = self.client.accounts.show("badaccount")
        asserts.assert_not_equal(self.user.tenant_id, account_info.id)


@test(groups=[tests.INSTANCES, GROUP], depends_on_groups=["dbaas.listing"])
class AccountsAfterInstanceCreation(object):

    @before_class
    def setUp(self):
        self.user = test_config.users.find_user(Requirements(is_admin=True))
        self.client = create_dbaas_client(self.user)

    @test
    def test_account_details_available(self):
        if CONFIG.fake_mode:
            raise SkipTest("Skipping this as auth is faked anyway.")
        account_info = self.client.accounts.show(instance_info.user.tenant_id)
        # Now check the results.
        expected = instance_info.user.tenant_id
        if expected is None:
            expected = "None"
        print("account_id.id = '%s'" % account_info.id)
        print("expected = '%s'" % expected)
        asserts.assert_equal(expected, account_info.id)
        # Instances: there should at least be one instance
        asserts.assert_true(len(account_info.instance_ids) > 0)
        # The instance id should be one of the instances for the account
        asserts.assert_true(instance_info.id in account_info.instance_ids)

    @test
    def test_list_accounts(self):
        if CONFIG.fake_mode:
            raise SkipTest("Skipping this as auth is faked anyway.")
        accounts_info = self.client.accounts.index()
        asserts.assert_equal(1, len(accounts_info.accounts))
        account = accounts_info.accounts[0]
        asserts.assert_true(account['num_instances'] > 0)
        asserts.assert_equal(instance_info.user.tenant_id, account['id'])


@test(groups=[tests.POST_INSTANCES, GROUP],
      depends_on_groups=["dbaas.guest.shutdown"])
class AccountsAfterInstanceDeletion(object):

    @before_class
    def setUp(self):
        self.user = test_config.users.find_user(Requirements(is_admin=True))
        self.client = create_dbaas_client(self.user)

    @test
    def test_instance_id_removed_from_account(self):
        account_info = self.client.accounts.show(instance_info.user.tenant_id)
        asserts.assert_true(instance_info.id not in account_info.instance_ids)


@test(groups=["fake.dbaas.api.mgmt.allaccounts"],
      depends_on_groups=["services.initialize"])
class AllAccounts(object):
    max = 5

    def _delete_instances_for_users(self):
        for user in self.users:
            user_client = create_dbaas_client(user)
            while True:
                deleted_count = 0
                user_instances = user_client.instances.list()
                for instance in user_instances:
                    try:
                        instance.delete()
                    except exceptions.NotFound:
                        deleted_count += 1
                    except Exception:
                        print("Failed to delete instance")
                if deleted_count == len(user_instances):
                    break

    def _create_instances_for_users(self):
        for user in self.users:
            user_client = create_dbaas_client(user)
            for index in range(self.max):
                name = "instance-%s-%03d" % (user.auth_user, index)
                user_client.instances.create(name, 1, {'size': 1}, [], [])

    @before_class
    def setUp(self):
        admin_req = Requirements(is_admin=True)
        self.admin_user = test_config.users.find_user(admin_req)
        self.admin_client = create_dbaas_client(self.admin_user)
        user_req = Requirements(is_admin=False)
        self.users = test_config.users.find_all_users_who_satisfy(user_req)
        self.user_tenant_ids = [user.tenant_id for user in self.users]
        self._create_instances_for_users()

    @test
    def test_list_accounts_with_multiple_users(self):
        accounts_info = self.admin_client.accounts.index()
        for account in accounts_info.accounts:
            asserts.assert_true(account['id'] in self.user_tenant_ids)
            asserts.assert_equal(self.max, account['num_instances'])

    @after_class(always_run=True)
    @time_out(60)
    def tear_down(self):
        self._delete_instances_for_users()


@test(groups=["fake.%s.broken" % GROUP],
      depends_on_groups=["services.initialize"],
      runs_after_groups=["dbaas.guest.shutdown"])
class AccountWithBrokenInstance(object):

    @before_class
    def setUpACCR(self):
        from trove.taskmanager.models import CONF
        self.old_dns_support = CONF.trove_dns_support
        CONF.trove_dns_support = False

        self.user = test_config.users.find_user(Requirements(is_admin=True))
        self.client = create_dbaas_client(self.user)
        self.name = 'test_SERVER_ERROR'
        # Create an instance with a broken compute instance.
        volume = None
        if CONFIG.trove_volume_support:
            volume = {'size': 1}
        self.response = self.client.instances.create(
            self.name,
            instance_info.dbaas_flavor_href,
            volume,
            [])
        poll_until(lambda: self.client.instances.get(self.response.id),
                   lambda instance: instance.status == 'ERROR',
                   time_out=10)
        self.instance = self.client.instances.get(self.response.id)
        print("Status: %s" % self.instance.status)
        msg = "Instance did not drop to error after server prov failure."
        asserts.assert_equal(self.instance.status, "ERROR", msg)

    @test
    def no_compute_instance_no_problem(self):
        """Get account by ID shows even instances lacking computes."""
        if test_config.auth_strategy == "fake":
            raise SkipTest("Skipping this as auth is faked anyway.")
        account_info = self.client.accounts.show(self.user.tenant_id)
        # All we care about is that accounts.show doesn't 500 on us
        # for having a broken instance in the roster.
        asserts.assert_equal(len(account_info.instances), 1)
        instance = account_info.instances[0]
        asserts.assert_true(isinstance(instance['id'], six.string_types))
        asserts.assert_equal(len(instance['id']), 36)
        asserts.assert_equal(instance['name'], self.name)
        asserts.assert_equal(instance['status'], "ERROR")
        assert_is_none(instance['host'])

    @after_class
    def tear_down(self):
        self.client.instances.delete(self.response.id)

    @after_class
    def restore_dns(self):
        from trove.taskmanager.models import CONF
        CONF.trove_dns_support = self.old_dns_support
