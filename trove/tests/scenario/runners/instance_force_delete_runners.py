# Copyright 2016 Tesora Inc.
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

from trove.tests.scenario.runners.test_runners import TestRunner


class InstanceForceDeleteRunner(TestRunner):

    def __init__(self):
        super(InstanceForceDeleteRunner, self).__init__(sleep_time=1)

        self.build_inst_id = None

    def run_create_build_instance(self, expected_states=['NEW', 'BUILD'],
                                  expected_http_code=200):
        if self.is_using_existing_instance:
            raise SkipTest("Using an existing instance.")

        name = self.instance_info.name + '_build'
        flavor = self.get_instance_flavor()

        inst = self.auth_client.instances.create(
            name,
            self.get_flavor_href(flavor),
            self.instance_info.volume,
            nics=self.instance_info.nics,
            datastore=self.instance_info.dbaas_datastore,
            datastore_version=self.instance_info.dbaas_datastore_version)
        self.assert_instance_action([inst.id], expected_states,
                                    expected_http_code)
        self.build_inst_id = inst.id

    def run_delete_build_instance(self, expected_http_code=202):
        if self.build_inst_id:
            self.auth_client.instances.force_delete(self.build_inst_id)
            self.assert_client_code(expected_http_code)

    def run_wait_for_force_delete(self):
        if self.build_inst_id:
            self.assert_all_gone([self.build_inst_id], ['SHUTDOWN'])
