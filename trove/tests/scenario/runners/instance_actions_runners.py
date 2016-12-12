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

from proboscis import SkipTest

from trove.tests.config import CONFIG
from trove.tests.scenario.helpers.test_helper import DataType
from trove.tests.scenario.runners.test_runners import TestRunner


class InstanceActionsRunner(TestRunner):

    def __init__(self):
        super(InstanceActionsRunner, self).__init__()

        self.resize_flavor_id = self._get_resize_flavor().id

    def _get_resize_flavor(self):
        if self.EPHEMERAL_SUPPORT:
            flavor_name = CONFIG.values.get(
                'instance_bigger_eph_flavor_name', 'eph.rd-smaller')
        else:
            flavor_name = CONFIG.values.get(
                'instance_bigger_flavor_name', 'm1.rd-smaller')

        return self.get_flavor(flavor_name)

    def run_add_test_data(self):
        host = self.get_instance_host(self.instance_info.id)
        self.test_helper.add_data(DataType.small, host)

    def run_verify_test_data(self):
        host = self.get_instance_host(self.instance_info.id)
        self.test_helper.verify_data(DataType.small, host)

    def run_remove_test_data(self):
        host = self.get_instance_host(self.instance_info.id)
        self.test_helper.remove_data(DataType.small, host)

    def run_instance_restart(
            self, expected_states=['REBOOT', 'ACTIVE'],
            expected_http_code=202):
        self.assert_instance_restart(self.instance_info.id, expected_states,
                                     expected_http_code)

    def assert_instance_restart(self, instance_id, expected_states,
                                expected_http_code):
        self.report.log("Testing restart on instance: %s" % instance_id)

        client = self.auth_client
        client.instances.restart(instance_id)
        self.assert_client_code(client, expected_http_code)
        self.assert_instance_action(instance_id, expected_states)

    def run_instance_resize_volume(
            self, resize_amount=1,
            expected_states=['RESIZE', 'ACTIVE'],
            expected_http_code=202):
        if self.VOLUME_SUPPORT:
            self.assert_instance_resize_volume(
                self.instance_info.id, resize_amount, expected_states,
                expected_http_code)
        else:
            raise SkipTest("Volume support is disabled.")

    def assert_instance_resize_volume(self, instance_id, resize_amount,
                                      expected_states, expected_http_code):
        self.report.log("Testing volume resize by '%d' on instance: %s"
                        % (resize_amount, instance_id))

        instance = self.get_instance(instance_id)
        old_volume_size = int(instance.volume['size'])
        new_volume_size = old_volume_size + resize_amount

        client = self.auth_client
        client.instances.resize_volume(instance_id, new_volume_size)
        self.assert_client_code(client, expected_http_code)
        self.assert_instance_action(instance_id, expected_states)

        instance = self.get_instance(instance_id)
        self.assert_equal(new_volume_size, instance.volume['size'],
                          'Unexpected new volume size')

    def run_instance_resize_flavor(self, expected_http_code=202):
        self.assert_instance_resize_flavor(
            self.instance_info.id, self.resize_flavor_id, expected_http_code)

    def assert_instance_resize_flavor(self, instance_id, resize_flavor_id,
                                      expected_http_code):
        self.report.log("Testing resize to '%s' on instance: %s" %
                        (resize_flavor_id, instance_id))
        client = self.auth_client
        client.instances.resize_instance(instance_id, resize_flavor_id)
        self.assert_client_code(client, expected_http_code)

    def run_wait_for_instance_resize_flavor(
            self, expected_states=['RESIZE', 'ACTIVE']):
        self.report.log("Waiting for resize to '%s' on instance: %s" %
                        (self.resize_flavor_id, self.instance_info.id))
        self._assert_instance_states(self.instance_info.id, expected_states)
        instance = self.get_instance(self.instance_info.id)
        self.assert_equal(self.resize_flavor_id, instance.flavor['id'],
                          'Unexpected resize flavor_id')
