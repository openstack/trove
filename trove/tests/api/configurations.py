#    Copyright 2014 Rackspace Hosting
#    All Rights Reserved.
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


import json
from time import sleep
from datetime import datetime
from proboscis import after_class
from proboscis import before_class
from proboscis import SkipTest
from proboscis import test
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_raises
from proboscis.asserts import assert_true
from proboscis.asserts import assert_not_equal
from proboscis.decorators import time_out
from trove.common.utils import poll_until
from trove.tests.api.backups import RestoreUsingBackup
from trove.tests.api.instances import assert_unprocessable
from trove.tests.api.instances import InstanceTestInfo
from trove.tests.api.instances import instance_info
from trove.tests.api.instances import TIMEOUT_INSTANCE_CREATE
from trove.tests.api.instances import TIMEOUT_INSTANCE_DELETE
from trove.tests.api.instances import WaitForGuestInstallationToFinish
from trove.tests.config import CONFIG
from trove.tests.util import create_dbaas_client
from trove.tests.util.check import AttrCheck
from trove.tests.util.check import CollectionCheck
from trove.tests.util.check import TypeCheck
from trove.tests.util.mysql import create_mysql_connection
from trove.tests.util.users import Requirements
from troveclient.compat import exceptions


GROUP = "dbaas.api.configurations"
GROUP_CONFIG_DEFINE = "dbaas.api.configurations.define"
CONFIG_NAME = "test_configuration"
CONFIG_DESC = "configuration description"

configuration_default = None
configuration_info = None
configuration_href = None
configuration_instance = InstanceTestInfo()
configuration_instance_id = None
sql_variables = [
    'key_buffer_size',
    'connect_timeout',
    'join_buffer_size',
]


def _is_valid_timestamp(time_string):
    try:
        datetime.strptime(time_string, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return False
    return True


# helper methods to validate configuration is applied to instance
def _execute_query(host, user_name, password, query):
    print(host, user_name, password, query)
    with create_mysql_connection(host, user_name, password) as db:
        result = db.execute(query)
        return result
    assert_true(False, "something went wrong in the sql connection")


def _get_address(instance_id):
    result = instance_info.dbaas_admin.mgmt.instances.show(instance_id)
    return result.ip[0]


def _test_configuration_is_applied_to_instance(instance, configuration_id):
    if CONFIG.fake_mode:
        raise SkipTest("configuration from sql does not work in fake mode")
    instance_test = instance_info.dbaas.instances.get(instance.id)
    assert_equal(configuration_id, instance_test.configuration['id'])
    if configuration_id:
        testconfig_info = instance_info.dbaas.configurations.get(
            configuration_id)
    else:
        testconfig_info = instance_info.dbaas.instance.configuration(
            instance.id)
        testconfig_info['configuration']
    conf_instances = instance_info.dbaas.configurations.instances(
        configuration_id)
    config_instance_ids = [inst.id for inst in conf_instances]
    assert_true(instance_test.id in config_instance_ids)
    cfg_names = testconfig_info.values.keys()

    host = _get_address(instance.id)
    for user in instance.users:
        username = user['name']
        password = user['password']
        concat_variables = "','".join(cfg_names)
        query = ("show variables where Variable_name "
                 "in ('%s');" % concat_variables)
        actual_values = _execute_query(host, username, password, query)
    print("actual_values %s" % actual_values)
    print("testconfig_info.values %s" % testconfig_info.values)
    assert_true(len(actual_values) == len(cfg_names))

    # check the configs exist
    attrcheck = AttrCheck()
    allowed_attrs = [actual_key for actual_key, actual_value in actual_values]
    attrcheck.contains_allowed_attrs(
        testconfig_info.values, allowed_attrs,
        msg="Configurations parameters")

    def _get_parameter_type(name):
        instance_info.dbaas.configuration_parameters.get_parameter(
            instance_info.dbaas_datastore,
            instance_info.dbaas_datastore_version,
            name)
        resp, body = instance_info.dbaas.client.last_response
        print(resp)
        print(body)
        return json.loads(body)['type']

    # check the config values are correct
    for key, value in actual_values:
        key_type = _get_parameter_type(key)
        # mysql returns 'ON' and 'OFF' for True and False respectively
        if value == 'ON':
            converted_key_value = (str(key), 1)
        elif value == 'OFF':
            converted_key_value = (str(key), 0)
        else:
            if key_type == 'integer':
                value = int(value)
            converted_key_value = (str(key), value)
        print("converted_key_value: %s" % str(converted_key_value))
        assert_true(converted_key_value in testconfig_info.values.items())


class ConfigurationsTestBase(object):

    @staticmethod
    def expected_instance_datastore_configs(instance_id):
        """Given an instance retrieve the expected test configurations for
        instance's datastore.
        """
        instance = instance_info.dbaas.instances.get(instance_id)
        datastore_type = instance.datastore['type']
        datastore_test_configs = CONFIG.get(datastore_type, {})
        return datastore_test_configs.get("configurations", {})

    @staticmethod
    def expected_default_datastore_configs():
        """Returns the expected test configurations for the default datastore
        defined in the Test Config as dbaas_datastore.
        """
        default_datatstore = CONFIG.get('dbaas_datastore', None)
        datastore_test_configs = CONFIG.get(default_datatstore, {})
        return datastore_test_configs.get("configurations", {})


@test(depends_on_classes=[WaitForGuestInstallationToFinish],
      runs_after=[RestoreUsingBackup],
      groups=[GROUP, GROUP_CONFIG_DEFINE])
class CreateConfigurations(ConfigurationsTestBase):

    @test
    def test_expected_configurations_parameters(self):
        """Test get expected configurations parameters."""
        allowed_attrs = ["configuration-parameters"]
        instance_info.dbaas.configuration_parameters.parameters(
            instance_info.dbaas_datastore,
            instance_info.dbaas_datastore_version)
        resp, body = instance_info.dbaas.client.last_response
        attrcheck = AttrCheck()
        config_parameters_dict = json.loads(body)
        attrcheck.contains_allowed_attrs(
            config_parameters_dict, allowed_attrs,
            msg="Configurations parameters")
        # sanity check that a few options are in the list
        config_params_list = config_parameters_dict['configuration-parameters']
        config_param_keys = []
        for param in config_params_list:
            config_param_keys.append(param['name'])
        expected_configs = self.expected_default_datastore_configs()
        expected_config_params = expected_configs.get('parameters_list')
        # check for duplicate configuration parameters
        msg = "check for duplicate configuration parameters"
        assert_equal(len(config_param_keys), len(set(config_param_keys)), msg)
        for expected_config_item in expected_config_params:
            assert_true(expected_config_item in config_param_keys)

    @test
    def test_expected_get_configuration_parameter(self):
        # tests get on a single parameter to verify it has expected attributes
        param_name = 'key_buffer_size'
        allowed_config_params = ['name', 'restart_required',
                                 'max', 'min', 'type',
                                 'deleted', 'deleted_at',
                                 'datastore_version_id']
        param = instance_info.dbaas.configuration_parameters.get_parameter(
            instance_info.dbaas_datastore,
            instance_info.dbaas_datastore_version,
            param_name)
        resp, body = instance_info.dbaas.client.last_response
        print("params: %s" % param)
        print("resp: %s" % resp)
        print("body: %s" % body)
        attrcheck = AttrCheck()
        config_parameter_dict = json.loads(body)
        print("config_parameter_dict: %s" % config_parameter_dict)
        attrcheck.contains_allowed_attrs(
            config_parameter_dict,
            allowed_config_params,
            msg="Get Configuration parameter")
        assert_equal(param_name, config_parameter_dict['name'])
        with TypeCheck('ConfigurationParameter', param) as parameter:
            parameter.has_field('name', basestring)
            parameter.has_field('restart_required', bool)
            parameter.has_field('max', int)
            parameter.has_field('min', int)
            parameter.has_field('type', basestring)
            parameter.has_field('datastore_version_id', unicode)

    @test
    def test_configurations_create_invalid_values(self):
        """Test create configurations with invalid values."""
        values = '{"this_is_invalid": 123}'
        try:
            instance_info.dbaas.configurations.create(
                CONFIG_NAME,
                values,
                CONFIG_DESC)
        except exceptions.UnprocessableEntity:
            resp, body = instance_info.dbaas.client.last_response
            assert_equal(resp.status, 422)

    @test
    def test_configurations_create_invalid_value_type(self):
        """Test create configuration with invalild value type."""
        values = '{"key_buffer_size": "this is a string not int"}'
        assert_unprocessable(instance_info.dbaas.configurations.create,
                             CONFIG_NAME, values, CONFIG_DESC)

    @test
    def test_configurations_create_value_out_of_bounds(self):
        """Test create configuration with value out of bounds."""
        expected_configs = self.expected_default_datastore_configs()
        values = json.dumps(expected_configs.get('out_of_bounds_over'))
        assert_unprocessable(instance_info.dbaas.configurations.create,
                             CONFIG_NAME, values, CONFIG_DESC)
        values = json.dumps(expected_configs.get('out_of_bounds_under'))
        assert_unprocessable(instance_info.dbaas.configurations.create,
                             CONFIG_NAME, values, CONFIG_DESC)

    @test
    def test_valid_configurations_create(self):
        # create a configuration with valid parameters
        expected_configs = self.expected_default_datastore_configs()
        values = json.dumps(expected_configs.get('valid_values'))
        expected_values = json.loads(values)
        result = instance_info.dbaas.configurations.create(
            CONFIG_NAME,
            values,
            CONFIG_DESC,
            datastore=instance_info.dbaas_datastore,
            datastore_version=instance_info.dbaas_datastore_version)
        resp, body = instance_info.dbaas.client.last_response
        assert_equal(resp.status, 200)
        with TypeCheck('Configuration', result) as configuration:
            configuration.has_field('name', basestring)
            configuration.has_field('description', basestring)
            configuration.has_field('values', dict)
            configuration.has_field('datastore_name', basestring)
            configuration.has_field('datastore_version_id', unicode)
            configuration.has_field('datastore_version_name', basestring)
        global configuration_info
        configuration_info = result
        assert_equal(configuration_info.name, CONFIG_NAME)
        assert_equal(configuration_info.description, CONFIG_DESC)
        assert_equal(configuration_info.values, expected_values)

    @test(runs_after=[test_valid_configurations_create])
    def test_appending_to_existing_configuration(self):
        # test being able to update and insert new parameter name and values
        # to an existing configuration
        expected_configs = self.expected_default_datastore_configs()
        values = json.dumps(expected_configs.get('appending_values'))
        # ensure updated timestamp is different than created
        if not CONFIG.fake_mode:
            sleep(1)
        instance_info.dbaas.configurations.edit(configuration_info.id,
                                                values)
        resp, body = instance_info.dbaas.client.last_response
        assert_equal(resp.status, 200)


@test(runs_after=[CreateConfigurations],
      groups=[GROUP, GROUP_CONFIG_DEFINE])
class AfterConfigurationsCreation(ConfigurationsTestBase):

    @test
    def test_assign_configuration_to_invalid_instance(self):
        # test assigning to an instance that does not exist
        invalid_id = "invalid-inst-id"
        try:
            instance_info.dbaas.instances.modify(invalid_id,
                                                 configuration_info.id)
        except exceptions.NotFound:
            resp, body = instance_info.dbaas.client.last_response
            assert_equal(resp.status, 404)

    @test
    def test_assign_configuration_to_valid_instance(self):
        # test assigning a configuration to an instance
        print("instance_info.id: %s" % instance_info.id)
        print("configuration_info: %s" % configuration_info)
        print("configuration_info.id: %s" % configuration_info.id)
        config_id = configuration_info.id
        instance_info.dbaas.instances.modify(instance_info.id,
                                             configuration=config_id)
        resp, body = instance_info.dbaas.client.last_response
        assert_equal(resp.status, 202)

    @test
    def test_assign_name_to_instance_using_patch(self):
        # test assigning a name to an instance
        new_name = 'new_name_1'
        report = CONFIG.get_report()
        report.log("instance_info.id: %s" % instance_info.id)
        report.log("instance name:%s" % instance_info.name)
        report.log("instance new name:%s" % new_name)
        instance_info.dbaas.instances.edit(instance_info.id, name=new_name)
        assert_equal(202, instance_info.dbaas.last_http_code)
        check = instance_info.dbaas.instances.get(instance_info.id)
        assert_equal(200, instance_info.dbaas.last_http_code)
        assert_equal(check.name, new_name)
        # Restore instance name
        instance_info.dbaas.instances.edit(instance_info.id,
                                           name=instance_info.name)
        assert_equal(202, instance_info.dbaas.last_http_code)

    @test
    def test_assign_configuration_to_invalid_instance_using_patch(self):
        # test assign config group to an invalid instance
        invalid_id = "invalid-inst-id"
        assert_raises(exceptions.NotFound,
                      instance_info.dbaas.instances.edit,
                      invalid_id, configuration=configuration_info.id)

    @test(depends_on=[test_assign_configuration_to_valid_instance])
    def test_assign_configuration_to_instance_with_config(self):
        # test assigning a configuration to an instance that
        # already has an assigned configuration
        config_id = configuration_info.id
        assert_raises(exceptions.BadRequest,
                      instance_info.dbaas.instances.modify, instance_info.id,
                      configuration=config_id)

    @test(depends_on=[test_assign_configuration_to_valid_instance])
    @time_out(30)
    def test_get_configuration_details_from_instance_validation(self):
        # validate that the configuration was applied correctly to the instance
        print("instance_info.id: %s" % instance_info.id)
        inst = instance_info.dbaas.instances.get(instance_info.id)
        configuration_id = inst.configuration['id']
        print("configuration_info: %s" % configuration_id)
        assert_not_equal(None, inst.configuration['id'])
        _test_configuration_is_applied_to_instance(instance_info,
                                                   configuration_id)

    def test_configurations_get(self):
        # test that the instance shows up on the assigned configuration
        result = instance_info.dbaas.configurations.get(configuration_info.id)
        assert_equal(configuration_info.id, result.id)
        assert_equal(configuration_info.name, result.name)
        assert_equal(configuration_info.description, result.description)

        # check the result field types
        with TypeCheck("configuration", result) as check:
            check.has_field("id", basestring)
            check.has_field("name", basestring)
            check.has_field("description", basestring)
            check.has_field("values", dict)
            check.has_field("created", basestring)
            check.has_field("updated", basestring)
            check.has_field("instance_count", int)

        print(result.values)

        # check for valid timestamps
        assert_true(_is_valid_timestamp(result.created))
        assert_true(_is_valid_timestamp(result.updated))

        # check that created and updated timestamps differ, since
        # test_appending_to_existing_configuration should have changed the
        # updated timestamp
        if not CONFIG.fake_mode:
            assert_not_equal(result.created, result.updated)

        assert_equal(result.instance_count, 1)

        with CollectionCheck("configuration_values", result.values) as check:
            # check each item has the correct type according to the rules
            for (item_key, item_val) in result.values.iteritems():
                print("item_key: %s" % item_key)
                print("item_val: %s" % item_val)
                dbaas = instance_info.dbaas
                param = dbaas.configuration_parameters.get_parameter(
                    instance_info.dbaas_datastore,
                    instance_info.dbaas_datastore_version,
                    item_key)
                if param.type == 'integer':
                    check.has_element(item_key, int)
                if param.type == 'string':
                    check.has_element(item_key, basestring)
                if param.type == 'boolean':
                    check.has_element(item_key, bool)

        # Test to make sure that another user is not able to GET this config
        reqs = Requirements(is_admin=False)
        test_auth_user = instance_info.user.auth_user
        other_user = CONFIG.users.find_user(reqs, black_list=[test_auth_user])
        other_user_tenant_id = other_user.tenant_id
        client_tenant_id = instance_info.user.tenant_id
        if other_user_tenant_id == client_tenant_id:
            other_user = CONFIG.users.find_user(reqs,
                                                black_list=[
                                                instance_info.user.auth_user,
                                                other_user])
        print(other_user)
        print(other_user.__dict__)
        other_client = create_dbaas_client(other_user)
        assert_raises(exceptions.NotFound, other_client.configurations.get,
                      configuration_info.id)


@test(runs_after=[AfterConfigurationsCreation],
      groups=[GROUP, GROUP_CONFIG_DEFINE])
class ListConfigurations(ConfigurationsTestBase):

    @test
    def test_configurations_list(self):
        # test listing configurations show up
        result = instance_info.dbaas.configurations.list()
        for conf in result:
            with TypeCheck("Configuration", conf) as check:
                check.has_field('id', basestring)
                check.has_field('name', basestring)
                check.has_field('description', basestring)
                check.has_field('datastore_version_id', basestring)
                check.has_field('datastore_version_name', basestring)
                check.has_field('datastore_name', basestring)

        exists = [config for config in result if
                  config.id == configuration_info.id]
        assert_equal(1, len(exists))
        configuration = exists[0]
        assert_equal(configuration.id, configuration_info.id)
        assert_equal(configuration.name, configuration_info.name)
        assert_equal(configuration.description, configuration_info.description)

    @test
    def test_configurations_list_for_instance(self):
        # test getting an instance shows the configuration assigned shows up
        instance = instance_info.dbaas.instances.get(instance_info.id)
        assert_equal(instance.configuration['id'], configuration_info.id)
        assert_equal(instance.configuration['name'], configuration_info.name)
        # expecting two things in links, href and bookmark
        assert_equal(2, len(instance.configuration['links']))
        link = instance.configuration['links'][0]
        global configuration_href
        configuration_href = link['href']

    @test
    def test_get_default_configuration_on_instance(self):
        # test the api call to get the default template of an instance exists
        result = instance_info.dbaas.instances.configuration(instance_info.id)
        global configuration_default
        configuration_default = result
        assert_not_equal(None, result.configuration)

    @test
    def test_changing_configuration_with_nondynamic_parameter(self):
        # test that changing a non-dynamic parameter is applied to instance
        # and show that the instance requires a restart
        expected_configs = self.expected_default_datastore_configs()
        values = json.dumps(expected_configs.get('nondynamic_parameter'))
        instance_info.dbaas.configurations.update(configuration_info.id,
                                                  values)
        resp, body = instance_info.dbaas.client.last_response
        assert_equal(resp.status, 202)

        instance_info.dbaas.configurations.get(configuration_info.id)
        resp, body = instance_info.dbaas.client.last_response
        assert_equal(resp.status, 200)

    @test(depends_on=[test_changing_configuration_with_nondynamic_parameter])
    @time_out(20)
    def test_waiting_for_instance_in_restart_required(self):
        def result_is_not_active():
            instance = instance_info.dbaas.instances.get(
                instance_info.id)
            if instance.status == "ACTIVE":
                return False
            else:
                return True
        poll_until(result_is_not_active)

        instance = instance_info.dbaas.instances.get(instance_info.id)
        resp, body = instance_info.dbaas.client.last_response
        assert_equal(resp.status, 200)
        print(instance.status)
        assert_equal('RESTART_REQUIRED', instance.status)

    @test(depends_on=[test_waiting_for_instance_in_restart_required])
    def test_restart_service_should_return_active(self):
        # test that after restarting the instance it becomes active
        instance_info.dbaas.instances.restart(instance_info.id)
        resp, body = instance_info.dbaas.client.last_response
        assert_equal(resp.status, 202)

        def result_is_active():
            instance = instance_info.dbaas.instances.get(
                instance_info.id)
            if instance.status == "ACTIVE":
                return True
            else:
                assert_equal("REBOOT", instance.status)
                return False
        poll_until(result_is_active)

    @test(depends_on=[test_restart_service_should_return_active])
    @time_out(30)
    def test_get_configuration_details_from_instance_validation(self):
        # validate that the configuraiton was applied correctly to the instance
        inst = instance_info.dbaas.instances.get(instance_info.id)
        configuration_id = inst.configuration['id']
        assert_not_equal(None, inst.configuration['id'])
        _test_configuration_is_applied_to_instance(instance_info,
                                                   configuration_id)

    @test(depends_on=[test_configurations_list])
    def test_compare_list_and_details_timestamps(self):
        # compare config timestamps between list and details calls
        result = instance_info.dbaas.configurations.list()
        list_config = [config for config in result if
                       config.id == configuration_info.id]
        assert_equal(1, len(list_config))
        details_config = instance_info.dbaas.configurations.get(
            configuration_info.id)
        assert_equal(list_config[0].created, details_config.created)
        assert_equal(list_config[0].updated, details_config.updated)


@test(runs_after=[ListConfigurations],
      groups=[GROUP, GROUP_CONFIG_DEFINE])
class StartInstanceWithConfiguration(ConfigurationsTestBase):

    @test
    def test_start_instance_with_configuration(self):
        # test that a new instance will apply the configuration on create
        global configuration_instance
        databases = []
        databases.append({"name": "firstdbconfig", "character_set": "latin2",
                          "collate": "latin2_general_ci"})
        databases.append({"name": "db2"})
        configuration_instance.databases = databases
        users = []
        users.append({"name": "liteconf", "password": "liteconfpass",
                      "databases": [{"name": "firstdbconfig"}]})
        configuration_instance.users = users
        configuration_instance.name = "TEST_" + str(datetime.now()) + "_config"
        flavor_href = instance_info.dbaas_flavor_href
        configuration_instance.dbaas_flavor_href = flavor_href
        configuration_instance.volume = instance_info.volume

        result = instance_info.dbaas.instances.create(
            configuration_instance.name,
            configuration_instance.dbaas_flavor_href,
            configuration_instance.volume,
            configuration_instance.databases,
            configuration_instance.users,
            availability_zone="nova",
            configuration=configuration_href)
        assert_equal(200, instance_info.dbaas.last_http_code)
        assert_equal("BUILD", result.status)
        configuration_instance.id = result.id


@test(depends_on_classes=[StartInstanceWithConfiguration],
      runs_after_groups=['dbaas.api.backups'],
      groups=[GROUP])
class WaitForConfigurationInstanceToFinish(ConfigurationsTestBase):

    @test
    @time_out(TIMEOUT_INSTANCE_CREATE)
    def test_instance_with_configuration_active(self):
        # wait for the instance to become active

        def result_is_active():
            instance = instance_info.dbaas.instances.get(
                configuration_instance.id)
            if instance.status == "ACTIVE":
                return True
            else:
                assert_equal("BUILD", instance.status)
                return False

        poll_until(result_is_active)

    @test(depends_on=[test_instance_with_configuration_active])
    @time_out(30)
    def test_get_configuration_details_from_instance_validation(self):
        # validate that the configuraiton was applied correctly to the instance
        inst = instance_info.dbaas.instances.get(configuration_instance.id)
        configuration_id = inst.configuration['id']
        assert_not_equal(None, inst.configuration['id'])
        _test_configuration_is_applied_to_instance(configuration_instance,
                                                   configuration_id)


@test(runs_after=[WaitForConfigurationInstanceToFinish], groups=[GROUP])
class DeleteConfigurations(ConfigurationsTestBase):

    @before_class
    def setUp(self):
        # need to store the parameter details that will be deleted
        config_param_name = sql_variables[1]
        instance_info.dbaas.configuration_parameters.get_parameter(
            instance_info.dbaas_datastore,
            instance_info.dbaas_datastore_version,
            config_param_name)
        resp, body = instance_info.dbaas.client.last_response
        print(resp)
        print(body)
        self.config_parameter_dict = json.loads(body)

    @after_class(always_run=True)
    def tearDown(self):
        # need to "undelete" the parameter that was deleted from the mgmt call
        ds = instance_info.dbaas_datastore
        ds_v = instance_info.dbaas_datastore_version
        version = instance_info.dbaas.datastore_versions.get(
            ds, ds_v)
        client = instance_info.dbaas_admin.mgmt_configs
        print(self.config_parameter_dict)
        client.create(version.id,
                      self.config_parameter_dict['name'],
                      self.config_parameter_dict['restart_required'],
                      self.config_parameter_dict['type'],
                      self.config_parameter_dict['max'],
                      self.config_parameter_dict['min'])

    @test
    def test_delete_invalid_configuration_not_found(self):
        # test deleting a configuration that does not exist throws exception
        invalid_configuration_id = "invalid-config-id"
        assert_raises(exceptions.NotFound,
                      instance_info.dbaas.configurations.delete,
                      invalid_configuration_id)

    @test(depends_on=[test_delete_invalid_configuration_not_found])
    def test_delete_configuration_parameter_with_mgmt_api(self):
        # testing a param that is assigned to an instance can be deleted
        # and doesn't affect an unassign later. So we delete a parameter
        # that is used by a test (connect_timeout)
        ds = instance_info.dbaas_datastore
        ds_v = instance_info.dbaas_datastore_version
        version = instance_info.dbaas.datastore_versions.get(
            ds, ds_v)
        client = instance_info.dbaas_admin.mgmt_configs
        config_param_name = self.config_parameter_dict['name']
        client.delete(version.id, config_param_name)
        assert_raises(
            exceptions.NotFound,
            instance_info.dbaas.configuration_parameters.get_parameter,
            ds,
            ds_v,
            config_param_name)

    @test(depends_on=[test_delete_configuration_parameter_with_mgmt_api])
    def test_unable_delete_instance_configurations(self):
        # test deleting a configuration that is assigned to
        # an instance is not allowed.
        assert_raises(exceptions.BadRequest,
                      instance_info.dbaas.configurations.delete,
                      configuration_info.id)

    @test(depends_on=[test_unable_delete_instance_configurations])
    @time_out(30)
    def test_unassign_configuration_from_instances(self):
        # test to unassign configuration from instance
        instance_info.dbaas.instances.modify(configuration_instance.id,
                                             configuration="")
        resp, body = instance_info.dbaas.client.last_response
        assert_equal(resp.status, 202)
        instance_info.dbaas.instances.get(configuration_instance.id)
        #test that config group is not removed
        instance_info.dbaas.instances.modify(instance_info.id,
                                             configuration=None)
        resp, body = instance_info.dbaas.client.last_response
        assert_equal(resp.status, 202)
        instance_info.dbaas.instances.get(instance_info.id)

        def result_has_no_configuration():
            instance = instance_info.dbaas.instances.get(inst_info.id)
            if hasattr(instance, 'configuration'):
                return False
            else:
                return True
        inst_info = instance_info
        poll_until(result_has_no_configuration)
        inst_info = configuration_instance
        poll_until(result_has_no_configuration)
        instance = instance_info.dbaas.instances.get(instance_info.id)
        assert_equal('RESTART_REQUIRED', instance.status)

    @test(depends_on=[test_unassign_configuration_from_instances])
    def test_assign_in_wrong_state(self):
        # test assigning a config to an instance in RESTART state
        assert_raises(exceptions.BadRequest,
                      instance_info.dbaas.instances.modify,
                      configuration_instance.id,
                      configuration=configuration_info.id)

    @test(depends_on=[test_assign_in_wrong_state])
    def test_no_instances_on_configuration(self):
        # test there is no configuration on the instance after unassigning
        result = instance_info.dbaas.configurations.get(configuration_info.id)
        assert_equal(configuration_info.id, result.id)
        assert_equal(configuration_info.name, result.name)
        assert_equal(configuration_info.description, result.description)
        assert_equal(result.instance_count, 0)
        print(configuration_instance.id)
        print(instance_info.id)

    @test(depends_on=[test_unassign_configuration_from_instances])
    @time_out(120)
    def test_restart_service_after_unassign_return_active(self):
        def result_is_not_active():
            instance = instance_info.dbaas.instances.get(
                instance_info.id)
            if instance.status == "ACTIVE":
                return False
            else:
                return True
        poll_until(result_is_not_active)

        config = instance_info.dbaas.configurations.list()
        print(config)
        instance = instance_info.dbaas.instances.get(instance_info.id)
        print(instance.__dict__)
        resp, body = instance_info.dbaas.client.last_response
        assert_equal(resp.status, 200)
        print(instance.status)
        assert_equal('RESTART_REQUIRED', instance.status)

    @test(depends_on=[test_restart_service_after_unassign_return_active])
    @time_out(120)
    def test_restart_service_should_return_active(self):
        # test that after restarting the instance it becomes active
        instance_info.dbaas.instances.restart(instance_info.id)
        resp, body = instance_info.dbaas.client.last_response
        assert_equal(resp.status, 202)

        def result_is_active():
            instance = instance_info.dbaas.instances.get(
                instance_info.id)
            if instance.status == "ACTIVE":
                return True
            else:
                assert_equal("REBOOT", instance.status)
                return False
        poll_until(result_is_active)

    @test(depends_on=[test_restart_service_should_return_active])
    def test_assign_config_and_name_to_instance_using_patch(self):
        # test assigning a configuration and name to an instance
        new_name = 'new_name'
        report = CONFIG.get_report()
        report.log("instance_info.id: %s" % instance_info.id)
        report.log("configuration_info: %s" % configuration_info)
        report.log("configuration_info.id: %s" % configuration_info.id)
        report.log("instance name:%s" % instance_info.name)
        report.log("instance new name:%s" % new_name)
        saved_name = instance_info.name
        config_id = configuration_info.id
        instance_info.dbaas.instances.edit(instance_info.id,
                                           configuration=config_id,
                                           name=new_name)
        assert_equal(202, instance_info.dbaas.last_http_code)
        check = instance_info.dbaas.instances.get(instance_info.id)
        assert_equal(200, instance_info.dbaas.last_http_code)
        assert_equal(check.name, new_name)

        # restore instance name
        instance_info.dbaas.instances.edit(instance_info.id,
                                           name=saved_name)
        assert_equal(202, instance_info.dbaas.last_http_code)

        instance = instance_info.dbaas.instances.get(instance_info.id)
        assert_equal('RESTART_REQUIRED', instance.status)
        # restart to be sure configuration is applied
        instance_info.dbaas.instances.restart(instance_info.id)
        assert_equal(202, instance_info.dbaas.last_http_code)
        sleep(2)

        def result_is_active():
            instance = instance_info.dbaas.instances.get(
                instance_info.id)
            if instance.status == "ACTIVE":
                return True
            else:
                assert_equal("REBOOT", instance.status)
                return False
        poll_until(result_is_active)
        # test assigning a configuration to an instance that
        # already has an assigned configuration with patch
        config_id = configuration_info.id
        assert_raises(exceptions.BadRequest,
                      instance_info.dbaas.instances.edit,
                      instance_info.id, configuration=config_id)

    @test(runs_after=[test_assign_config_and_name_to_instance_using_patch])
    def test_unassign_configuration_after_patch(self):
        # remove the configuration from the instance
        instance_info.dbaas.instances.edit(instance_info.id,
                                           remove_configuration=True)
        assert_equal(202, instance_info.dbaas.last_http_code)
        instance = instance_info.dbaas.instances.get(instance_info.id)
        assert_equal('RESTART_REQUIRED', instance.status)
        # restart to be sure configuration has been unassigned
        instance_info.dbaas.instances.restart(instance_info.id)
        assert_equal(202, instance_info.dbaas.last_http_code)
        sleep(2)

        def result_is_active():
            instance = instance_info.dbaas.instances.get(
                instance_info.id)
            if instance.status == "ACTIVE":
                return True
            else:
                assert_equal("REBOOT", instance.status)
                return False
        poll_until(result_is_active)
        result = instance_info.dbaas.configurations.get(configuration_info.id)
        assert_equal(result.instance_count, 0)

    @test
    def test_unassign_configuration_from_invalid_instance_using_patch(self):
        # test unassign config group from an invalid instance
        invalid_id = "invalid-inst-id"
        try:
            instance_info.dbaas.instances.edit(invalid_id,
                                               remove_configuration=True)
        except exceptions.NotFound:
            resp, body = instance_info.dbaas.client.last_response
            assert_equal(resp.status, 404)

    @test(runs_after=[test_unassign_configuration_after_patch])
    def test_delete_unassigned_configuration(self):
        # test that we can delete the configuration after no instances are
        # assigned to it any longer
        instance_info.dbaas.configurations.delete(configuration_info.id)
        resp, body = instance_info.dbaas.client.last_response
        assert_equal(resp.status, 202)

    @test(depends_on=[test_delete_unassigned_configuration])
    @time_out(TIMEOUT_INSTANCE_DELETE)
    def test_delete_configuration_instance(self):
        # test that we can delete the instance even though there is a
        # configuration applied to the instance
        instance_info.dbaas.instances.delete(configuration_instance.id)
        assert_equal(202, instance_info.dbaas.last_http_code)

        def instance_is_gone():
            try:
                instance_info.dbaas.instances.get(configuration_instance.id)
                return False
            except exceptions.NotFound:
                return True

        poll_until(instance_is_gone)
        assert_raises(exceptions.NotFound, instance_info.dbaas.instances.get,
                      configuration_instance.id)
