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

from trove.tests.scenario.runners.test_runners import CheckInstance
from trove.tests.scenario.runners.test_runners import TestRunner


class InstanceErrorCreateRunner(TestRunner):

    def __init__(self):
        super(InstanceErrorCreateRunner, self).__init__(sleep_time=1)
        self.error_inst_id = None
        self.error2_inst_id = None

    def run_create_error_instance(self, expected_http_code=200):
        if self.is_using_existing_instance:
            raise SkipTest("Using an existing instance.")

        name = self.instance_info.name + '_error'
        flavor = self.get_instance_flavor(fault_num=1)

        client = self.auth_client
        inst = client.instances.create(
            name,
            self.get_flavor_href(flavor),
            self.instance_info.volume,
            nics=self.instance_info.nics,
            datastore=self.instance_info.dbaas_datastore,
            datastore_version=self.instance_info.dbaas_datastore_version)
        self.assert_client_code(client, expected_http_code)
        self.error_inst_id = inst.id

    def run_create_error2_instance(self, expected_http_code=200):
        if self.is_using_existing_instance:
            raise SkipTest("Using an existing instance.")

        name = self.instance_info.name + '_error2'
        flavor = self.get_instance_flavor(fault_num=2)

        client = self.auth_client
        inst = client.instances.create(
            name,
            self.get_flavor_href(flavor),
            self.instance_info.volume,
            nics=self.instance_info.nics,
            datastore=self.instance_info.dbaas_datastore,
            datastore_version=self.instance_info.dbaas_datastore_version)
        self.assert_client_code(client, expected_http_code)
        self.error2_inst_id = inst.id

    def run_wait_for_error_instances(self, expected_states=['ERROR']):
        error_ids = []
        if self.error_inst_id:
            error_ids.append(self.error_inst_id)
        if self.error2_inst_id:
            error_ids.append(self.error2_inst_id)

        if error_ids:
            self.assert_all_instance_states(
                error_ids, expected_states, fast_fail_status=[])

    def run_validate_error_instance(self):
        if not self.error_inst_id:
            raise SkipTest("No error instance created.")

        instance = self.get_instance(
            self.error_inst_id, self.auth_client)
        with CheckInstance(instance._info) as check:
            check.fault()

        err_msg = "disk is too small for requested image"
        self.assert_true(err_msg in instance.fault['message'],
                         "Message '%s' does not contain '%s'" %
                         (instance.fault['message'], err_msg))

    def run_validate_error2_instance(self):
        if not self.error2_inst_id:
            raise SkipTest("No error2 instance created.")

        instance = self.get_instance(
            self.error2_inst_id, client=self.admin_client)
        with CheckInstance(instance._info) as check:
            check.fault(is_admin=True)

        err_msg = "Quota exceeded for ram"
        self.assert_true(err_msg in instance.fault['message'],
                         "Message '%s' does not contain '%s'" %
                         (instance.fault['message'], err_msg))

    def run_delete_error_instances(self, expected_http_code=202):
        client = self.auth_client
        if self.error_inst_id:
            client.instances.delete(self.error_inst_id)
            self.assert_client_code(client, expected_http_code)
        if self.error2_inst_id:
            client.instances.delete(self.error2_inst_id)
            self.assert_client_code(client, expected_http_code)

    def run_wait_for_error_delete(self, expected_states=['SHUTDOWN']):
        delete_ids = []
        if self.error_inst_id:
            delete_ids.append(self.error_inst_id)
        if self.error2_inst_id:
            delete_ids.append(self.error2_inst_id)
        if delete_ids:
            self.assert_all_gone(delete_ids, expected_states[-1])
        else:
            raise SkipTest("Cleanup is not required.")
