# Copyright 2013 OpenStack Foundation
# Copyright 2013 Rackspace Hosting
# Copyright 2013 Hewlett-Packard Development Company, L.P.
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
#

from proboscis import after_class
from proboscis import asserts
from proboscis.asserts import Check
from proboscis import before_class
from proboscis import test
from troveclient.compat import exceptions

from trove.tests.config import CONFIG
from trove.tests.util import create_client
from trove.tests.util import create_dbaas_client
from trove.tests.util import get_standby_instance_flavor
from trove.tests.util.users import Requirements


class QuotasBase(object):

    def setUp(self):
        self.user1 = CONFIG.users.find_user(Requirements(is_admin=False))
        self.user2 = CONFIG.users.find_user(Requirements(is_admin=False))
        asserts.assert_not_equal(self.user1.tenant, self.user2.tenant,
                                 "Not enough users to run QuotasTest."
                                 + " Needs >=2.")
        self.client1 = create_dbaas_client(self.user1)
        self.client2 = create_dbaas_client(self.user2)
        self.mgmt_client = create_client(is_admin=True)
        ''' Orig quotas from config
            "trove_max_instances_per_user": 55,
            "trove_max_volumes_per_user": 100,    '''
        self.original_quotas1 = self.mgmt_client.quota.show(self.user1.tenant)
        self.original_quotas2 = self.mgmt_client.quota.show(self.user2.tenant)

    def tearDown(self):
        self.mgmt_client.quota.update(self.user1.tenant,
                                      self.original_quotas1)
        self.mgmt_client.quota.update(self.user2.tenant,
                                      self.original_quotas2)


@test(groups=["dbaas.api.mgmt.quotas"])
class DefaultQuotasTest(QuotasBase):

    @before_class
    def setUp(self):
        super(DefaultQuotasTest, self).setUp()

    @after_class
    def tearDown(self):
        super(DefaultQuotasTest, self).tearDown()

    @test
    def check_quotas_are_set_to_defaults(self):
        quotas = self.mgmt_client.quota.show(self.user1.tenant)
        with Check() as check:
            check.equal(CONFIG.trove_max_instances_per_user,
                        quotas["instances"])
            check.equal(CONFIG.trove_max_volumes_per_user,
                        quotas["volumes"])
        asserts.assert_equal(len(quotas), 2)


@test(groups=["dbaas.api.mgmt.quotas"])
class ChangeInstancesQuota(QuotasBase):

    @before_class
    def setUp(self):
        super(ChangeInstancesQuota, self).setUp()
        self.mgmt_client.quota.update(self.user1.tenant, {"instances": 0})
        asserts.assert_equal(200, self.mgmt_client.last_http_code)

    @after_class
    def tearDown(self):
        super(ChangeInstancesQuota, self).tearDown()

    @test
    def check_user2_is_not_affected_on_instances_quota_change(self):
        user2_current_quota = self.mgmt_client.quota.show(self.user2.tenant)
        asserts.assert_equal(self.original_quotas2, user2_current_quota,
                             "Changing one user's quota affected another"
                             + "user's quota."
                             + " Original: %s. After Quota Change: %s" %
                             (self.original_quotas2, user2_current_quota))

    @test
    def verify_correct_update(self):
        quotas = self.mgmt_client.quota.show(self.user1.tenant)
        with Check() as check:
            check.equal(0, quotas["instances"])
            check.equal(CONFIG.trove_max_volumes_per_user,
                        quotas["volumes"])
        asserts.assert_equal(len(quotas), 2)

    @test
    def create_too_many_instances(self):
        flavor, flavor_href = get_standby_instance_flavor(self.client1)
        asserts.assert_raises(exceptions.OverLimit,
                              self.client1.instances.create,
                              "too_many_instances",
                              flavor_href, {'size': 1})
        asserts.assert_equal(413, self.client1.last_http_code)


@test(groups=["dbaas.api.mgmt.quotas"])
class ChangeVolumesQuota(QuotasBase):

    @before_class
    def setUp(self):
        super(ChangeVolumesQuota, self).setUp()
        self.mgmt_client.quota.update(self.user1.tenant, {"volumes": 0})
        asserts.assert_equal(200, self.mgmt_client.last_http_code)

    @after_class
    def tearDown(self):
        super(ChangeVolumesQuota, self).tearDown()

    @test
    def check_volumes_overlimit(self):
        flavor, flavor_href = get_standby_instance_flavor(self.client1)
        asserts.assert_raises(exceptions.OverLimit,
                              self.client1.instances.create,
                              "too_large_volume",
                              flavor_href,
                              {'size': CONFIG.trove_max_accepted_volume_size
                               + 1})
        asserts.assert_equal(413, self.client1.last_http_code)

    @test
    def check_user2_is_not_affected_on_volumes_quota_change(self):
        user2_current_quota = self.mgmt_client.quota.show(self.user2.tenant)
        asserts.assert_equal(self.original_quotas2, user2_current_quota,
                             "Changing one user's quota affected another"
                             + "user's quota."
                             + " Original: %s. After Quota Change: %s" %
                             (self.original_quotas2, user2_current_quota))

    @test
    def verify_correct_update(self):
        quotas = self.mgmt_client.quota.show(self.user1.tenant)
        with Check() as check:
            check.equal(CONFIG.trove_max_instances_per_user,
                        quotas["instances"])
            check.equal(0, quotas["volumes"])
        asserts.assert_equal(len(quotas), 2)

    @test
    def create_too_large_volume(self):
        flavor, flavor_href = get_standby_instance_flavor(self.client1)
        asserts.assert_raises(exceptions.OverLimit,
                              self.client1.instances.create,
                              "too_large_volume",
                              flavor_href,
                              {'size': CONFIG.trove_max_accepted_volume_size
                               + 1})
        asserts.assert_equal(413, self.client1.last_http_code)

    # create an instance when I set the limit back to
    # multiple updates to the quota and it should do what you expect
