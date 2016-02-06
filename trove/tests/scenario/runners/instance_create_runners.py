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

import json

from proboscis import SkipTest

from trove.tests.api.instances import CheckInstance, InstanceTestInfo
from trove.tests.config import CONFIG
from trove.tests.scenario.helpers.test_helper import DataType
from trove.tests.scenario.runners.test_runners import TestRunner


class InstanceCreateRunner(TestRunner):

    def __init__(self):
        super(InstanceCreateRunner, self).__init__()
        self.init_inst_id = None
        self.init_inst_dbs = None
        self.init_inst_users = None
        self.init_inst_host = None
        self.init_inst_data = None
        self.init_config_group_id = None

    def run_empty_instance_create(
            self, expected_states=['BUILD', 'ACTIVE'], expected_http_code=200):
        name = self.instance_info.name
        flavor = self._get_instance_flavor()
        trove_volume_size = CONFIG.get('trove_volume_size', 1)

        info = self.assert_instance_create(
            name, flavor, trove_volume_size, [], [], None, None,
            CONFIG.dbaas_datastore, CONFIG.dbaas_datastore_version,
            expected_states, expected_http_code, create_helper_user=True)

        # Update the shared instance info.
        self.instance_info.databases = info.databases
        self.instance_info.users = info.users
        self.instance_info.dbaas_datastore = info.dbaas_datastore
        self.instance_info.dbaas_datastore_version = (info.
                                                      dbaas_datastore_version)
        self.instance_info.dbaas_flavor_href = info.dbaas_flavor_href
        self.instance_info.volume = info.volume
        self.instance_info.id = info.id

    def run_initial_configuration_create(self, expected_http_code=200):
        dynamic_config = self.test_helper.get_dynamic_group()
        non_dynamic_config = self.test_helper.get_non_dynamic_group()
        values = dynamic_config or non_dynamic_config
        if values:
            json_def = json.dumps(values)
            result = self.auth_client.configurations.create(
                'initial_configuration_for_instance_create',
                json_def,
                "Configuration group used by instance create tests.",
                datastore=self.instance_info.dbaas_datastore,
                datastore_version=self.instance_info.dbaas_datastore_version)
            self.assert_client_code(expected_http_code)

            self.init_config_group_id = result.id
        else:
            raise SkipTest("No groups defined.")

    def run_initialized_instance_create(
            self, with_dbs=True, with_users=True, configuration_id=None,
            expected_states=['BUILD', 'ACTIVE'], expected_http_code=200,
            create_helper_user=True):
        if self.is_using_existing_instance:
            # The user requested to run the tests using an existing instance.
            # We therefore skip any scenarios that involve creating new
            # test instances.
            raise SkipTest("Using an existing instance.")

        name = self.instance_info.name + '_init'
        flavor = self._get_instance_flavor()
        trove_volume_size = CONFIG.get('trove_volume_size', 1)
        self.init_inst_dbs = (self.test_helper.get_valid_database_definitions()
                              if with_dbs else [])
        self.init_inst_users = (self.test_helper.get_valid_user_definitions()
                                if with_users else [])
        if configuration_id:
            self.init_config_group_id = configuration_id

        if (self.init_inst_dbs or self.init_inst_users or
                self.init_config_group_id):
            info = self.assert_instance_create(
                name, flavor, trove_volume_size,
                self.init_inst_dbs, self.init_inst_users,
                self.init_config_group_id, None,
                CONFIG.dbaas_datastore, CONFIG.dbaas_datastore_version,
                expected_states, expected_http_code,
                create_helper_user=create_helper_user)

            self.init_inst_id = info.id
        else:
            # There is no need to run this test as it's effectively the same as
            # the empty instance test.
            raise SkipTest("No testable initial properties provided.")

    def _get_instance_flavor(self):
        if self.EPHEMERAL_SUPPORT:
            flavor_name = CONFIG.values.get('instance_eph_flavor_name',
                                            'eph.rd-tiny')
        else:
            flavor_name = CONFIG.values.get('instance_flavor_name', 'm1.tiny')

        return self.get_flavor(flavor_name)

    def _get_flavor_href(self, flavor):
        return self.auth_client.find_flavor_self_href(flavor)

    def assert_instance_create(
        self, name, flavor, trove_volume_size,
        database_definitions, user_definitions,
            configuration_id, root_password, datastore, datastore_version,
            expected_states, expected_http_code, create_helper_user=False):
        """This assert method executes a 'create' call and verifies the server
        response. It neither waits for the instance to become available
        nor it performs any other validations itself.
        It has been designed this way to increase test granularity
        (other tests may run while the instance is building) and also to allow
        its reuse in other runners .
        """

        databases = database_definitions
        users = [{'name': item['name'], 'password': item['password']}
                 for item in user_definitions]

        # Here we add helper user/database if any.
        if create_helper_user:
            helper_db_def, helper_user_def = self.build_helper_defs()
            if helper_db_def:
                self.report.log(
                    "Appending a helper database '%s' to the instance "
                    "definition." % helper_db_def['name'])
                databases.append(helper_db_def)
            if helper_user_def:
                self.report.log(
                    "Appending a helper user '%s:%s' to the instance "
                    "definition."
                    % (helper_user_def['name'], helper_user_def['password']))
                users.append(helper_user_def)

        instance_info = InstanceTestInfo()
        instance_info.name = name
        instance_info.databases = databases
        instance_info.users = users
        instance_info.dbaas_datastore = CONFIG.dbaas_datastore
        instance_info.dbaas_datastore_version = CONFIG.dbaas_datastore_version
        instance_info.dbaas_flavor_href = self._get_flavor_href(flavor)
        if self.VOLUME_SUPPORT:
            instance_info.volume = {'size': trove_volume_size}
        else:
            instance_info.volume = None

        shared_network = CONFIG.get('shared_network', None)
        if shared_network:
            instance_info.nics = [{'net-id': shared_network}]

        self.report.log("Testing create instance: %s"
                        % {'name': name,
                           'flavor': flavor.id,
                           'volume': trove_volume_size,
                           'nics': instance_info.nics,
                           'databases': databases,
                           'users': users,
                           'configuration': configuration_id,
                           'root password': root_password,
                           'datastore': datastore,
                           'datastore version': datastore_version})

        instance = self.get_existing_instance()
        if instance:
            self.report.log("Using an existing instance: %s" % instance.id)
            self.assert_equal(expected_states[-1], instance.status,
                              "Given instance is in a bad state.")
        else:
            self.report.log("Creating a new instance.")
            instance = self.auth_client.instances.create(
                instance_info.name,
                instance_info.dbaas_flavor_href,
                instance_info.volume,
                instance_info.databases,
                instance_info.users,
                nics=instance_info.nics,
                configuration=configuration_id,
                availability_zone="nova",
                datastore=instance_info.dbaas_datastore,
                datastore_version=instance_info.dbaas_datastore_version)
            self.assert_instance_action(
                instance.id, expected_states[0:1], expected_http_code)

        instance_info.id = instance.id

        with CheckInstance(instance._info) as check:
            check.flavor()
            check.datastore()
            check.links(instance._info['links'])
            if self.VOLUME_SUPPORT:
                check.volume()
                self.assert_equal(trove_volume_size,
                                  instance._info['volume']['size'],
                                  "Unexpected Trove volume size")

            self.assert_equal(instance_info.name, instance._info['name'],
                              "Unexpected instance name")
            self.assert_equal(flavor.id,
                              int(instance._info['flavor']['id']),
                              "Unexpected instance flavor")
            self.assert_equal(instance_info.dbaas_datastore,
                              instance._info['datastore']['type'],
                              "Unexpected instance datastore version")
            self.assert_equal(instance_info.dbaas_datastore_version,
                              instance._info['datastore']['version'],
                              "Unexpected instance datastore version")
            self.assert_configuration_group(instance_info.id, configuration_id)

        return instance_info

    def wait_for_created_instances(self, expected_states=['BUILD', 'ACTIVE']):
        instances = [self.instance_info.id]
        if self.init_inst_id:
            instances.append(self.init_inst_id)
        self.assert_all_instance_states(instances, expected_states)

    def run_add_initialized_instance_data(self):
        self.init_inst_data = DataType.small
        self.init_inst_host = self.get_instance_host(self.instance_info.id)
        self.test_helper.add_data(self.init_inst_data, self.init_inst_host)

    def run_validate_initialized_instance(self):
        if self.init_inst_id:
            self.assert_instance_properties(
                self.init_inst_id, self.init_inst_dbs, self.init_inst_users,
                self.init_config_group_id, self.init_inst_data)

    def assert_instance_properties(
            self, instance_id, expected_dbs_definitions,
            expected_user_definitions, expected_config_group_id,
            expected_data_type):
        if expected_dbs_definitions:
            self.assert_database_list(instance_id, expected_dbs_definitions)
        else:
            self.report.log("No databases to validate for instance: %s"
                            % instance_id)
        if expected_user_definitions:
            self.assert_user_list(instance_id, expected_user_definitions)
        else:
            self.report.log("No users to validate for instance: %s"
                            % instance_id)
        self.assert_configuration_group(instance_id, expected_config_group_id)

        if self.init_inst_host:
            self.test_helper.verify_data(
                expected_data_type, self.init_inst_host)
        else:
            self.report.log("No data to validate for instance: %s"
                            % instance_id)

    def assert_configuration_group(self, instance_id, expected_group_id):
        instance = self.get_instance(instance_id)
        if expected_group_id:
            self.assert_equal(expected_group_id, instance.configuration['id'],
                              "Wrong configuration group attached")
        else:
            self.assert_false(hasattr(instance, 'configuration'),
                              "No configuration group expected")

    def assert_database_list(self, instance_id, expected_databases):
        expected_names = self._get_names(expected_databases)
        full_list = self.auth_client.databases.list(instance_id)
        self.assert_is_none(full_list.next,
                            "Unexpected pagination in the database list.")
        listed_names = [database.name for database in full_list]
        self.assert_is_sublist(expected_names, listed_names,
                               "Mismatch in instance databases.")

    def _get_names(self, definitions):
        return [item['name'] for item in definitions]

    def assert_user_list(self, instance_id, expected_users):
        expected_names = self._get_names(expected_users)
        full_list = self.auth_client.users.list(instance_id)
        self.assert_is_none(full_list.next,
                            "Unexpected pagination in the user list.")
        listed_names = [user.name for user in full_list]
        self.assert_is_sublist(expected_names, listed_names,
                               "Mismatch in instance users.")

        # Verify that user definitions include only created databases.
        all_databases = self._get_names(
            self.test_helper.get_valid_database_definitions())
        for user in expected_users:
            self.assert_is_sublist(
                self._get_names(user['databases']), all_databases,
                "Definition of user '%s' specifies databases not included in "
                "the list of initial databases." % user['name'])

    def run_initialized_instance_delete(self, expected_states=['SHUTDOWN'],
                                        expected_http_code=202):
        if self.init_inst_id:
            self.auth_client.instances.delete(self.init_inst_id)
            self.assert_client_code(expected_http_code)
            self.assert_all_gone(self.init_inst_id, expected_states[-1])
        else:
            raise SkipTest("Cleanup is not required.")

    def run_initial_configuration_delete(self, expected_http_code=202):
        if self.init_config_group_id:
            self.auth_client.configurations.delete(self.init_config_group_id)
            self.assert_client_code(expected_http_code)
        else:
            raise SkipTest("Cleanup is not required.")
