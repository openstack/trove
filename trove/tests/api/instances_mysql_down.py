# Copyright 2012 OpenStack Foundation
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
"""
Extra tests to create an instance, shut down MySQL, and delete it.
"""

from proboscis.decorators import time_out
from proboscis import before_class
from proboscis import test
from proboscis import asserts
import time

from datetime import datetime
from troveclient.compat import exceptions
from trove.tests.util import create_client
from trove.common.utils import poll_until
from trove.tests.util import test_config
from trove.tests.api.instances import VOLUME_SUPPORT
from trove.tests.api.instances import EPHEMERAL_SUPPORT


@test(groups=["dbaas.api.instances.down"])
class TestBase(object):
    """Base class for instance-down tests."""

    @before_class
    def set_up(self):
        self.client = create_client(is_admin=False)
        self.mgmt_client = create_client(is_admin=True)

        if EPHEMERAL_SUPPORT:
            flavor_name = test_config.values.get('instance_eph_flavor_name',
                                                 'eph.rd-tiny')
            flavor2_name = test_config.values.get(
                'instance_bigger_eph_flavor_name', 'eph.rd-smaller')
        else:
            flavor_name = test_config.values.get('instance_flavor_name',
                                                 'm1.tiny')
            flavor2_name = test_config.values.get(
                'instance_bigger_flavor_name', 'm1.small')
        flavors = self.client.find_flavors_by_name(flavor_name)
        self.flavor_id = flavors[0].id
        self.name = "TEST_" + str(datetime.now())
        # Get the resize to flavor.
        flavors2 = self.client.find_flavors_by_name(flavor2_name)
        self.new_flavor_id = flavors2[0].id
        asserts.assert_not_equal(self.flavor_id, self.new_flavor_id)

    def _wait_for_active(self):
        poll_until(lambda: self.client.instances.get(self.id),
                   lambda instance: instance.status == "ACTIVE",
                   time_out=(60 * 8))

    @test
    def create_instance(self):
        volume = None
        if VOLUME_SUPPORT:
            volume = {'size': 1}
        initial = self.client.instances.create(self.name, self.flavor_id,
                                               volume, [], [])
        self.id = initial.id
        self._wait_for_active()

    def _shutdown_instance(self):
        self.client.instances.get(self.id)
        self.mgmt_client.management.stop(self.id)

    @test(depends_on=[create_instance])
    def put_into_shutdown_state(self):
        self._shutdown_instance()

    @test(depends_on=[put_into_shutdown_state])
    @time_out(60 * 5)
    def resize_instance_in_shutdown_state(self):
        self.client.instances.resize_instance(self.id, self.new_flavor_id)
        self._wait_for_active()

    @test(depends_on=[create_instance],
          runs_after=[resize_instance_in_shutdown_state])
    def put_into_shutdown_state_2(self):
        self._shutdown_instance()

    @test(depends_on=[put_into_shutdown_state_2],
          enabled=VOLUME_SUPPORT)
    @time_out(60 * 5)
    def resize_volume_in_shutdown_state(self):
        self.client.instances.resize_volume(self.id, 2)
        poll_until(lambda: self.client.instances.get(self.id),
                   lambda instance: instance.volume['size'] == 2,
                   time_out=(60 * 8))

    @test(depends_on=[create_instance],
          runs_after=[resize_volume_in_shutdown_state])
    def put_into_shutdown_state_3(self):
        self._shutdown_instance()

    @test(depends_on=[create_instance],
          runs_after=[put_into_shutdown_state_3])
    @time_out(2 * 60)
    def delete_instances(self):
        instance = self.client.instances.get(self.id)
        instance.delete()
        while True:
            try:
                instance = self.client.instances.get(self.id)
                asserts.assert_equal("SHUTDOWN", instance.status)
            except exceptions.NotFound:
                break
            time.sleep(0.25)
