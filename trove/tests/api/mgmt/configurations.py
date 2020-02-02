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

from proboscis import asserts
from proboscis import before_class
from proboscis import test
from troveclient.compat import exceptions

from trove import tests
from trove.tests.util import create_dbaas_client
from trove.tests.util import test_config
from trove.tests.util.users import Requirements

GROUP = "dbaas.api.mgmt.configurations"


@test(groups=[GROUP, tests.DBAAS_API, tests.PRE_INSTANCES])
class ConfigGroupsSetupBeforeInstanceCreation(object):

    @before_class
    def setUp(self):
        self.user = test_config.users.find_user(Requirements(is_admin=True))
        self.admin_client = create_dbaas_client(self.user)
        self.datastore_version_id = self.admin_client.datastore_versions.get(
            "mysql", "5.5").id

    @test
    def test_valid_config_create_type(self):
        name = "testconfig-create"
        restart_required = 1
        data_type = "string"
        max_size = None
        min_size = None
        client = self.admin_client.mgmt_configs
        param_list = client.parameters_by_version(
            self.datastore_version_id)
        asserts.assert_true(name not in [p.name for p in param_list])
        client.create(
            self.datastore_version_id,
            name,
            restart_required,
            data_type,
            max_size,
            min_size)
        param_list = client.parameters_by_version(
            self.datastore_version_id)
        asserts.assert_true(name in [p.name for p in param_list])
        param = client.get_parameter_by_version(
            self.datastore_version_id, name)
        asserts.assert_equal(name, param.name)
        asserts.assert_equal(restart_required, param.restart_required)
        asserts.assert_equal(data_type, param.type)

        # test the modify
        restart_required = 0
        data_type = "integer"
        max_size = "10"
        min_size = "1"
        client.modify(
            self.datastore_version_id,
            name,
            restart_required,
            data_type,
            max_size,
            min_size)
        param = client.get_parameter_by_version(
            self.datastore_version_id, name)
        asserts.assert_equal(name, param.name)
        asserts.assert_equal(restart_required, param.restart_required)
        asserts.assert_equal(data_type, param.type)
        asserts.assert_equal(max_size, param.max)
        asserts.assert_equal(min_size, param.min)
        client.delete(self.datastore_version_id, name)

        # test show deleted params work
        param_list = client.list_all_parameter_by_version(
            self.datastore_version_id)
        asserts.assert_true(name in [p.name for p in param_list])
        param = client.get_any_parameter_by_version(
            self.datastore_version_id, name)
        asserts.assert_equal(name, param.name)
        asserts.assert_equal(restart_required, param.restart_required)
        asserts.assert_equal(data_type, param.type)
        asserts.assert_equal(int(max_size), int(param.max))
        asserts.assert_equal(int(min_size), int(param.min))
        asserts.assert_equal(True, param.deleted)
        asserts.assert_true(param.deleted_at)

    def test_create_config_type_twice_fails(self):
        name = "test-delete-config-types"
        restart_required = 1
        data_type = "string"
        max_size = None
        min_size = None
        client = self.admin_client.mgmt_configs
        client.create(
            self.datastore_version_id,
            name,
            restart_required,
            data_type,
            max_size,
            min_size)
        asserts.assert_raises(exceptions.BadRequest,
                              client.create,
                              self.datastore_version_id,
                              name,
                              restart_required,
                              data_type,
                              max_size,
                              min_size)
        client.delete(self.datastore_version_id, name)
        config_list = client.parameters_by_version(self.datastore_version_id)
        asserts.assert_true(name not in [conf.name for conf in config_list])
        # testing that recreate of a deleted parameter works.
        client.create(
            self.datastore_version_id,
            name,
            restart_required,
            data_type,
            max_size,
            min_size)
        config_list = client.parameters_by_version(self.datastore_version_id)
        asserts.assert_false(name not in [conf.name for conf in config_list])

    @test
    def test_delete_config_type(self):
        name = "test-delete-config-types"
        restart_required = 1
        data_type = "string"
        max_size = None
        min_size = None
        client = self.admin_client.mgmt_configs
        client.create(
            self.datastore_version_id,
            name,
            restart_required,
            data_type,
            max_size,
            min_size)
        client.delete(self.datastore_version_id, name)
        config_list = client.parameters_by_version(self.datastore_version_id)
        asserts.assert_true(name not in [conf.name for conf in config_list])

    @test
    def test_delete_config_type_fail(self):
        asserts.assert_raises(
            exceptions.BadRequest,
            self.admin_client.mgmt_configs.delete,
            self.datastore_version_id,
            "test-delete-config-types")

    @test
    def test_invalid_config_create_type(self):
        name = "testconfig_invalid_type"
        restart_required = 1
        data_type = "other"
        max_size = None
        min_size = None
        asserts.assert_raises(
            exceptions.BadRequest,
            self.admin_client.mgmt_configs.create,
            self.datastore_version_id,
            name,
            restart_required,
            data_type,
            max_size,
            min_size)

    @test
    def test_invalid_config_create_restart_required(self):
        name = "testconfig_invalid_restart_required"
        restart_required = 5
        data_type = "string"
        max_size = None
        min_size = None
        asserts.assert_raises(
            exceptions.BadRequest,
            self.admin_client.mgmt_configs.create,
            self.datastore_version_id,
            name,
            restart_required,
            data_type,
            max_size,
            min_size)

    @test
    def test_config_parameter_was_deleted_then_recreate_updates_it(self):
        name = "test-delete-and-recreate-param"
        restart_required = 1
        data_type = "string"
        max_size = None
        min_size = None
        client = self.admin_client.mgmt_configs
        client.create(
            self.datastore_version_id,
            name,
            restart_required,
            data_type,
            max_size,
            min_size)
        client.delete(self.datastore_version_id, name)
        client.create(
            self.datastore_version_id,
            name,
            0,
            data_type,
            max_size,
            min_size)
        param_list = client.list_all_parameter_by_version(
            self.datastore_version_id)
        asserts.assert_true(name in [p.name for p in param_list])
        param = client.get_any_parameter_by_version(
            self.datastore_version_id, name)
        asserts.assert_equal(False, param.deleted)
