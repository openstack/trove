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

import proboscis

from trove.tests.scenario.runners.test_runners import TestRunner


class InstanceDeleteRunner(TestRunner):

    def __init__(self):
        super(InstanceDeleteRunner, self).__init__()

    def run_instance_delete(self, expected_http_code=202):
        if self.has_do_not_delete_instance:
            self.report.log("TESTS_DO_NOT_DELETE_INSTANCE=True was "
                            "specified, skipping delete...")
            raise proboscis.SkipTest("TESTS_DO_NOT_DELETE_INSTANCE "
                                     "was specified.")

        self.assert_instance_delete(self.instance_info.id, expected_http_code)

    def assert_instance_delete(self, instance_id, expected_http_code):
        self.report.log("Testing delete on instance: %s" % instance_id)

        self.auth_client.instances.delete(instance_id)
        self.assert_client_code(expected_http_code, client=self.auth_client)

    def run_instance_delete_wait(self, expected_states=['SHUTDOWN']):
        if self.has_do_not_delete_instance:
            self.report.log("TESTS_DO_NOT_DELETE_INSTANCE=True was "
                            "specified, skipping delete wait...")
            raise proboscis.SkipTest("TESTS_DO_NOT_DELETE_INSTANCE "
                                     "was specified.")
        self.assert_all_gone(self.instance_info.id, expected_states[-1])
        self.assert_server_group_gone(self.instance_info.srv_grp_id)
