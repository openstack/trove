# Copyright 2012 OpenStack LLC.
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


GROUP = "dbaas.api.instances.status"

from proboscis import before_class
from proboscis import test
from proboscis.asserts import assert_equal

from trove.tests.config import CONFIG
from trove.tests.util import create_dbaas_client
from trove.tests.util.users import Requirements
from trove.common.utils import poll_until


@test(groups=[GROUP])
class InstanceStatusTests(object):

    @before_class
    def set_up(self):
        reqs = Requirements(is_admin=False)
        self.user = CONFIG.users.find_user(reqs)
        self.dbaas = create_dbaas_client(self.user)

    @test
    def test_create_failure_on_volume_prov_failure(self):
        # Fake nova will fail a volume of size 9.
        response = self.dbaas.instances.create('volume_fail', 1,
            {'size': 9}, [])
        poll_until(lambda: self.dbaas.instances.get(response.id),
                   lambda instance: instance.status == 'ERROR',
                   time_out=10)
        instance = self.dbaas.instances.get(response.id)
        print "Status: %s" % instance.status
        assert_equal(instance.status, "ERROR",
            "Instance did not drop to error after volume prov failure.")

    @test
    def test_create_failure_on_server_failure(self):
        # Fake nova will fail a server ending with 'SERVER_ERROR'."
        response = self.dbaas.instances.create('test_SERVER_ERROR', 1,
            {'size': 1}, [])
        poll_until(lambda: self.dbaas.instances.get(response.id),
                   lambda instance: instance.status == 'ERROR',
                   time_out=10)
        instance = self.dbaas.instances.get(response.id)
        print "Status: %s" % instance.status
        assert_equal(instance.status, "ERROR",
            "Instance did not drop to error after server prov failure.")

    ###TODO(ed-): We don't at present have a way to test DNS in FAKE_MODE.
    @test(enabled=False)
    def test_create_failure_on_dns_failure(self):
        #TODO(ed-): Throw DNS-specific monkeywrench into works
        response = self.dbaas.instances.create('test_DNS_ERROR', 1,
            {'size': 1}, [])
        poll_until(lambda: self.dbaas.instances.get(response.id),
                   lambda instance: instance.status == 'ERROR',
                   time_out=10)
        instance = self.dbaas.instances.get(response.id)
        print "Status: %s" % instance.status
        assert_equal(instance.status, "ERROR",
            "Instance did not drop to error after DNS prov failure.")
