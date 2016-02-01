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

from datetime import datetime
import json
from proboscis import SkipTest

from trove.common.utils import generate_uuid
from trove.tests.config import CONFIG
from trove.tests.scenario.runners.test_runners import TestRunner
from trove.tests.util.check import CollectionCheck
from trove.tests.util.check import TypeCheck
from trove.tests.util import create_dbaas_client
from trove.tests.util.users import Requirements
from troveclient.compat import exceptions


class ConfigurationRunner(TestRunner):

    def __init__(self):
        super(ConfigurationRunner, self).__init__(sleep_time=10)
        self.dynamic_group_name = 'dynamic_test_group'
        self.dynamic_group_id = None
        self.dynamic_inst_count = 0
        self.non_dynamic_group_name = 'non_dynamic_test_group'
        self.non_dynamic_group_id = None
        self.non_dynamic_inst_count = 0
        self.initial_group_count = 0
        self.additional_group_count = 0
        self.other_client = None
        self.config_id_for_inst = None
        self.config_inst_id = None

    def run_create_bad_group(self,
                             expected_exception=exceptions.UnprocessableEntity,
                             expected_http_code=422):
        bad_group = {'unknown_datastore_key': 'bad_value'}
        self.assert_action_on_conf_group_failure(
            bad_group, expected_exception, expected_http_code)

    def assert_action_on_conf_group_failure(
            self, group_values, expected_exception, expected_http_code):
        json_def = json.dumps(group_values)
        self.assert_raises(
            expected_exception, expected_http_code,
            self.auth_client.configurations.create,
            'conf_group',
            json_def,
            'Group with Bad or Invalid entries',
            datastore=self.instance_info.dbaas_datastore,
            datastore_version=self.instance_info.dbaas_datastore_version)

    def run_create_invalid_groups(
            self, expected_exception=exceptions.UnprocessableEntity,
            expected_http_code=422):
        invalid_groups = self.test_helper.get_invalid_groups()
        if invalid_groups:
            for invalid_group in invalid_groups:
                self.assert_action_on_conf_group_failure(
                    invalid_group,
                    expected_exception, expected_http_code)
        elif invalid_groups is None:
            raise SkipTest("No invalid configuration values defined in %s." %
                           self.test_helper.get_class_name())
        else:
            raise SkipTest("Datastore has no invalid configuration values.")

    def run_delete_non_existent_group(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        self.assert_group_delete_failure(
            None, expected_exception, expected_http_code)

    def run_delete_bad_group_id(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        self.assert_group_delete_failure(
            generate_uuid(), expected_exception, expected_http_code)

    def run_attach_non_existent_group(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        self.assert_instance_modify_failure(
            self.instance_info.id, generate_uuid(),
            expected_exception, expected_http_code)

    def run_attach_non_existent_group_to_non_existent_inst(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        self.assert_instance_modify_failure(
            generate_uuid(), generate_uuid(),
            expected_exception, expected_http_code)

    def run_detach_group_with_none_attached(self,
                                            expected_states=['ACTIVE'],
                                            expected_http_code=202):
        self.assert_instance_modify(
            self.instance_info.id, None,
            expected_states, expected_http_code)
        # run again, just to make sure
        self.assert_instance_modify(
            self.instance_info.id, None,
            expected_states, expected_http_code)

    def run_create_dynamic_group(self, expected_http_code=200):
        self.initial_group_count = len(self.auth_client.configurations.list())
        values = self.test_helper.get_dynamic_group()
        if values:
            self.dynamic_group_id = self.assert_create_group(
                self.dynamic_group_name,
                'a fully dynamic group should not require restart',
                values, expected_http_code)
            self.additional_group_count += 1
        elif values is None:
            raise SkipTest("No dynamic group defined in %s." %
                           self.test_helper.get_class_name())
        else:
            raise SkipTest("Datastore has no dynamic configuration values.")

    def assert_create_group(self, name, description, values,
                            expected_http_code):
        json_def = json.dumps(values)
        result = self.auth_client.configurations.create(
            name,
            json_def,
            description,
            datastore=self.instance_info.dbaas_datastore,
            datastore_version=self.instance_info.dbaas_datastore_version)
        self.assert_client_code(expected_http_code)

        with TypeCheck('Configuration', result) as configuration:
            configuration.has_field('name', basestring)
            configuration.has_field('description', basestring)
            configuration.has_field('values', dict)
            configuration.has_field('datastore_name', basestring)
            configuration.has_field('datastore_version_id', unicode)
            configuration.has_field('datastore_version_name', basestring)

            self.assert_equal(name, result.name)
            self.assert_equal(description, result.description)
            self.assert_equal(values, result.values)

        return result.id

    def run_create_non_dynamic_group(self, expected_http_code=200):
        values = self.test_helper.get_non_dynamic_group()
        if values:
            self.non_dynamic_group_id = self.assert_create_group(
                self.non_dynamic_group_name,
                'a group containing non-dynamic properties should always '
                'require restart',
                values, expected_http_code)
            self.additional_group_count += 1
        elif values is None:
            raise SkipTest("No non-dynamic group defined in %s." %
                           self.test_helper.get_class_name())
        else:
            raise SkipTest("Datastore has no non-dynamic configuration "
                           "values.")

    def run_attach_dynamic_group_to_non_existent_inst(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        if self.dynamic_group_id:
            self.assert_instance_modify_failure(
                generate_uuid(), self.dynamic_group_id,
                expected_exception, expected_http_code)

    def run_attach_non_dynamic_group_to_non_existent_inst(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        if self.non_dynamic_group_id:
            self.assert_instance_modify_failure(
                generate_uuid(), self.non_dynamic_group_id,
                expected_exception, expected_http_code)

    def run_list_configuration_groups(self):
        configuration_list = self.auth_client.configurations.list()
        self.assert_configuration_list(
            configuration_list,
            self.initial_group_count + self.additional_group_count)

    def assert_configuration_list(self, configuration_list, expected_count):
        self.assert_equal(expected_count, len(configuration_list),
                          'Unexpected number of configurations found')
        if expected_count:
            configuration_names = [conf.name for conf in configuration_list]
            if self.dynamic_group_id:
                self.assert_true(
                    self.dynamic_group_name in configuration_names)
            if self.non_dynamic_group_id:
                self.assert_true(
                    self.non_dynamic_group_name in configuration_names)

    def run_dynamic_configuration_show(self):
        if self.dynamic_group_id:
            self.assert_configuration_show(self.dynamic_group_id,
                                           self.dynamic_group_name)
        else:
            raise SkipTest("No dynamic group created.")

    def assert_configuration_show(self, config_id, config_name):
        result = self.auth_client.configurations.get(config_id)
        self.assert_equal(config_id, result.id, "Unexpected config id")
        self.assert_equal(config_name, result.name, "Unexpected config name")

        # check the result field types
        with TypeCheck("configuration", result) as check:
            check.has_field("id", basestring)
            check.has_field("name", basestring)
            check.has_field("description", basestring)
            check.has_field("values", dict)
            check.has_field("created", basestring)
            check.has_field("updated", basestring)
            check.has_field("instance_count", int)

        # check for valid timestamps
        self.assert_true(self._is_valid_timestamp(result.created),
                         'Created timestamp %s is invalid' % result.created)
        self.assert_true(self._is_valid_timestamp(result.updated),
                         'Updated timestamp %s is invalid' % result.updated)

        with CollectionCheck("configuration_values", result.values) as check:
            # check each item has the correct type according to the rules
            for (item_key, item_val) in result.values.iteritems():
                print("item_key: %s" % item_key)
                print("item_val: %s" % item_val)
                param = (
                    self.auth_client.configuration_parameters.get_parameter(
                        self.instance_info.dbaas_datastore,
                        self.instance_info.dbaas_datastore_version,
                        item_key))
                if param.type == 'integer':
                    check.has_element(item_key, int)
                if param.type == 'string':
                    check.has_element(item_key, basestring)
                if param.type == 'boolean':
                    check.has_element(item_key, bool)

    def _is_valid_timestamp(self, time_string):
        try:
            datetime.strptime(time_string, "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return False
        return True

    def run_non_dynamic_configuration_show(self):
        if self.non_dynamic_group_id:
            self.assert_configuration_show(self.non_dynamic_group_id,
                                           self.non_dynamic_group_name)
        else:
            raise SkipTest("No non-dynamic group created.")

    def run_dynamic_conf_get_unauthorized_user(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        self.assert_conf_get_unauthorized_user(self.dynamic_group_id,
                                               expected_exception,
                                               expected_http_code)

    def assert_conf_get_unauthorized_user(
            self, config_id, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        self._create_other_client()
        self.assert_raises(
            expected_exception, None,
            self.other_client.configurations.get, config_id)
        # we're using a different client, so we'll check the return code
        # on it explicitly, instead of depending on 'assert_raises'
        self.assert_client_code(expected_http_code, client=self.other_client)

    def _create_other_client(self):
        if not self.other_client:
            requirements = Requirements(is_admin=False)
            other_user = CONFIG.users.find_user(
                requirements, black_list=[self.instance_info.user.auth_user])
            self.other_client = create_dbaas_client(other_user)

    def run_non_dynamic_conf_get_unauthorized_user(
            self, expected_exception=exceptions.NotFound,
            expected_http_code=404):
        self.assert_conf_get_unauthorized_user(self.dynamic_group_id,
                                               expected_exception,
                                               expected_http_code)

    def run_list_dynamic_inst_conf_groups_before(self):
        if self.dynamic_group_id:
            self.dynamic_inst_count = len(
                self.auth_client.configurations.instances(
                    self.dynamic_group_id))

    def assert_conf_instance_list(self, group_id, expected_count):
        conf_instance_list = self.auth_client.configurations.instances(
            group_id)
        self.assert_equal(expected_count, len(conf_instance_list),
                          'Unexpected number of configurations found')
        if expected_count:
            conf_instance_ids = [inst.id for inst in conf_instance_list]
            self.assert_true(
                self.instance_info.id in conf_instance_ids)

    def run_attach_dynamic_group(
            self, expected_states=['ACTIVE'], expected_http_code=202):
        if self.dynamic_group_id:
            self.assert_instance_modify(
                self.instance_info.id, self.dynamic_group_id,
                expected_states, expected_http_code)

    def run_list_dynamic_inst_conf_groups_after(self):
        if self.dynamic_group_id:
            self.assert_conf_instance_list(self.dynamic_group_id,
                                           self.dynamic_inst_count + 1)

    def run_attach_dynamic_group_again(
            self, expected_exception=exceptions.BadRequest,
            expected_http_code=400):
        # The exception here should probably be UnprocessableEntity or
        # something else other than BadRequest as the request really is
        # valid.
        if self.dynamic_group_id:
            self.assert_instance_modify_failure(
                self.instance_info.id, self.dynamic_group_id,
                expected_exception, expected_http_code)

    def run_delete_attached_dynamic_group(
            self, expected_exception=exceptions.BadRequest,
            expected_http_code=400):
        # The exception here should probably be UnprocessableEntity or
        # something else other than BadRequest as the request really is
        # valid.
        if self.dynamic_group_id:
            self.assert_group_delete_failure(
                self.dynamic_group_id, expected_exception, expected_http_code)

    def run_update_dynamic_group(
            self, expected_states=['ACTIVE'], expected_http_code=202):
        if self.dynamic_group_id:
            values = json.dumps(self.test_helper.get_dynamic_group())
            self.assert_update_group(
                self.instance_info.id, self.dynamic_group_id, values,
                expected_states, expected_http_code)

    def assert_update_group(
            self, instance_id, group_id, values,
            expected_states, expected_http_code, restart_inst=False):
        self.auth_client.configurations.update(group_id, values)
        self.assert_instance_action(
            instance_id, expected_states, expected_http_code)
        if restart_inst:
            self._restart_instance(instance_id)

    def run_detach_dynamic_group(
            self, expected_states=['ACTIVE'], expected_http_code=202):
        if self.dynamic_group_id:
            self.assert_instance_modify(
                self.instance_info.id, None,
                expected_states, expected_http_code)

    def run_list_non_dynamic_inst_conf_groups_before(self):
        if self.non_dynamic_group_id:
            self.non_dynamic_inst_count = len(
                self.auth_client.configurations.instances(
                    self.non_dynamic_group_id))

    def run_attach_non_dynamic_group(
            self, expected_states=['RESTART_REQUIRED'],
            expected_http_code=202):
        if self.non_dynamic_group_id:
            self.assert_instance_modify(
                self.instance_info.id, self.non_dynamic_group_id,
                expected_states, expected_http_code, restart_inst=True)

    def run_list_non_dynamic_inst_conf_groups_after(self):
        if self.non_dynamic_group_id:
            self.assert_conf_instance_list(self.non_dynamic_group_id,
                                           self.non_dynamic_inst_count + 1)

    def run_attach_non_dynamic_group_again(
            self, expected_exception=exceptions.BadRequest,
            expected_http_code=400):
        if self.non_dynamic_group_id:
            self.assert_instance_modify_failure(
                self.instance_info.id, self.non_dynamic_group_id,
                expected_exception, expected_http_code)

    def run_delete_attached_non_dynamic_group(
            self, expected_exception=exceptions.BadRequest,
            expected_http_code=400):
        if self.non_dynamic_group_id:
            self.assert_group_delete_failure(
                self.non_dynamic_group_id, expected_exception,
                expected_http_code)

    def run_update_non_dynamic_group(
            self, expected_states=['RESTART_REQUIRED'],
            expected_http_code=202):
        if self.non_dynamic_group_id:
            values = json.dumps(self.test_helper.get_non_dynamic_group())
            self.assert_update_group(
                self.instance_info.id, self.non_dynamic_group_id, values,
                expected_states, expected_http_code, restart_inst=True)

    def run_detach_non_dynamic_group(
            self, expected_states=['RESTART_REQUIRED'],
            expected_http_code=202):
        if self.non_dynamic_group_id:
            self.assert_instance_modify(
                self.instance_info.id, None, expected_states,
                expected_http_code, restart_inst=True)

    def assert_instance_modify(
            self, instance_id, group_id, expected_states, expected_http_code,
            restart_inst=False):
        self.auth_client.instances.modify(instance_id, configuration=group_id)
        self.assert_instance_action(
            instance_id, expected_states, expected_http_code)

        # Verify the group has been attached.
        instance = self.get_instance(instance_id)
        if group_id:
            group = self.auth_client.configurations.get(group_id)
            self.assert_equal(
                group.id, instance.configuration['id'],
                "Attached group does not have the expected ID")
            self.assert_equal(
                group.name, instance.configuration['name'],
                "Attached group does not have the expected name")
        else:
            self.assert_false(
                hasattr(instance, 'configuration'),
                "The configuration group was not detached from the instance.")

        if restart_inst:
            self._restart_instance(instance_id)

    def assert_instance_modify_failure(
            self, instance_id, group_id, expected_exception,
            expected_http_code):
        self.assert_raises(
            expected_exception, expected_http_code,
            self.auth_client.instances.modify,
            instance_id, configuration=group_id)

    def run_delete_dynamic_group(self, expected_http_code=202):
        if self.dynamic_group_id:
            self.assert_group_delete(self.dynamic_group_id,
                                     expected_http_code)

    def assert_group_delete(self, group_id, expected_http_code):
        self.auth_client.configurations.delete(group_id)
        self.assert_client_code(expected_http_code)

    def run_delete_non_dynamic_group(self, expected_http_code=202):
        if self.non_dynamic_group_id:
            self.assert_group_delete(self.non_dynamic_group_id,
                                     expected_http_code)

    def assert_group_delete_failure(self, group_id, expected_exception,
                                    expected_http_code):
        self.assert_raises(
            expected_exception, expected_http_code,
            self.auth_client.configurations.delete, group_id)

    def _restart_instance(
            self, instance_id, expected_states=['REBOOT', 'ACTIVE'],
            expected_http_code=202):
        self.auth_client.instances.restart(instance_id)
        self.assert_instance_action(instance_id, expected_states,
                                    expected_http_code)

    def run_create_instance_with_conf(self):
        self.config_id_for_inst = (
            self.dynamic_group_id or self.non_dynamic_group_id)
        if self.config_id_for_inst:
            self.config_inst_id = self.assert_create_instance_with_conf(
                self.config_id_for_inst)
        else:
            raise SkipTest("No groups (dynamic or non-dynamic) defined in %s."
                           % self.test_helper.get_class_name())

    def assert_create_instance_with_conf(self, config_id):
        # test that a new instance will apply the configuration on create
        result = self.auth_client.instances.create(
            "TEST_" + str(datetime.now()) + "_config",
            self.instance_info.dbaas_flavor_href,
            self.instance_info.volume,
            [], [], availability_zone="nova",
            configuration=config_id)
        self.assert_client_code(200)
        self.assert_equal("BUILD", result.status, 'Unexpected inst status')
        return result.id

    def run_wait_for_conf_instance(
            # we can't specify all the states here, as it may go active
            # before this test runs
            self, final_state=['ACTIVE'],
            expected_http_code=200):
        if self.config_inst_id:
            self.assert_instance_action(self.config_inst_id, final_state,
                                        expected_http_code)
            inst = self.auth_client.instances.get(self.config_inst_id)
            self.assert_equal(self.config_id_for_inst,
                              inst.configuration['id'])
        else:
            raise SkipTest("No instance created with a configuration group.")

    def run_delete_conf_instance(
            self, expected_states=['SHUTDOWN'],
            expected_http_code=202):
        if self.config_inst_id:
            self.assert_delete_conf_instance(
                self.config_inst_id, expected_states, expected_http_code)
        else:
            raise SkipTest("No instance created with a configuration group.")

    def assert_delete_conf_instance(
            self, instance_id, expected_state, expected_http_code):
        self.auth_client.instances.delete(instance_id)
        self.assert_client_code(expected_http_code)
        self.assert_all_gone(instance_id, expected_state)
