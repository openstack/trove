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
from oslo_service import loopingcall

from trove.tests.scenario.helpers.test_helper import DataType
from trove.tests.scenario.runners.test_runners import TestRunner


class InstanceUpgradeRunner(TestRunner):

    def __init__(self):
        super(InstanceUpgradeRunner, self).__init__()

    def run_add_test_data(self):
        host = self.get_instance_host(self.instance_info.id)
        self.test_helper.add_data(DataType.small, host)

    def run_verify_test_data(self):
        host = self.get_instance_host(self.instance_info.id)
        self.test_helper.verify_data(DataType.small, host)

    def run_remove_test_data(self):
        host = self.get_instance_host(self.instance_info.id)
        self.test_helper.remove_data(DataType.small, host)

    def run_instance_upgrade(self, expected_states=['UPGRADE', 'ACTIVE'],
                             expected_http_code=202):
        instance_id = self.instance_info.id
        self.report.log("Testing upgrade on instance: %s" % instance_id)

        target_version = self.instance_info.dbaas_datastore_version
        client = self.auth_client
        client.instances.upgrade(instance_id, target_version)
        self.assert_client_code(client, expected_http_code)
        self.assert_instance_action(instance_id, expected_states)

        def _wait_for_user_list():
            try:
                all_users = self.get_user_names(client, instance_id)
                self.report.log("Users in the db instance %s: %s" %
                                (instance_id, all_users))
            except Exception as e:
                self.report.log(
                    "Failed to list users in db instance %s(will continue), "
                    "error: %s" % (instance_id, str(e))
                )
            else:
                raise loopingcall.LoopingCallDone()

        timer = loopingcall.FixedIntervalWithTimeoutLoopingCall(
            _wait_for_user_list)
        try:
            timer.start(interval=3, timeout=120).wait()
        except loopingcall.LoopingCallTimeOut:
            self.fail("Timed out: Cannot list users in the db instance %s"
                      % instance_id)
