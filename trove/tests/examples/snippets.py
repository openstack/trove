#    Copyright 2014 Rackspace
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

import functools
import json
import time

from oslo_log import log as logging
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_true
from proboscis.asserts import Check
from proboscis import before_class
from proboscis import SkipTest
from proboscis import test
from proboscis import TestProgram
import six
from troveclient.compat import client as trove_client
from troveclient.compat import Dbaas
from troveclient.compat import TroveHTTPClient

from trove.tests.config import CONFIG
from trove.tests.examples.client import JsonClient
from trove.tests.examples.client import SnippetWriter

trove_client._logger.setLevel(logging.CRITICAL)

FAKE_INFO = {'m': 30, 's': 0, 'uuid': 'abcdef00-aaaa-aaaa-aaaa-bbbbbbbbbbbb'}
EXAMPLE_BACKUP_ID = "a9832168-7541-4536-b8d9-a8a9b79cf1b4"
EXAMPLE_BACKUP_INCREMENTAL_ID = "2e351a71-dd28-4bcb-a7d6-d36a5b487173"
EXAMPLE_CONFIG_ID = "43a6ea86-e959-4735-9e46-a6a5d4a2d80f"
EXAMPLE_INSTANCE_ID = "44b277eb-39be-4921-be31-3d61b43651d7"
EXAMPLE_INSTANCE_ID_2 = "d5a9db64-7ef7-41c5-8e1e-4013166874bc"
EXAMPLE_CONFIG_SERVER_ID = "271898715"


def get_now():
    from datetime import datetime
    return datetime(2014, 10, 30, hour=12, minute=FAKE_INFO['m'],
                    second=FAKE_INFO['s'])


def get_uuid():
    return FAKE_INFO['uuid']


def set_fake_stuff(uuid=None, minute=None, unique_id=None):
    if uuid:
        FAKE_INFO['uuid'] = uuid
    if minute:
        FAKE_INFO['minute'] = minute
    if unique_id:
        from trove.common.template import SingleInstanceConfigTemplate

        def fake_calc_id(self):
            return unique_id

        SingleInstanceConfigTemplate._calculate_unique_id = fake_calc_id


def monkey_patch_uuid_and_date():
    import uuid
    uuid.uuid4 = get_uuid
    from trove.common import utils
    utils.utcnow = get_now
    utils.generate_uuid = get_uuid


@test
def load_config_file():
    global conf
    if CONFIG.get("examples", None) is None:
        fail("Missing 'examples' config in test config.")
    conf = CONFIG.examples
    global normal_user
    normal_user = CONFIG.users.find_user_by_name(conf['normal_user_name'])
    global admin_user
    admin_user = CONFIG.users.find_user_by_name(conf['admin_user_name'])


def create_client_args(user):

    auth_strategy = None

    kwargs = {
        'service_type': 'trove',
        'insecure': CONFIG.values['trove_client_insecure'],
    }

    def set_optional(kwargs_name, test_conf_name):
        value = CONFIG.values.get(test_conf_name, None)
        if value is not None:
            kwargs[kwargs_name] = value

    service_url = CONFIG.get('override_trove_api_url', None)
    if user.requirements.is_admin:
        service_url = CONFIG.get('override_admin_trove_api_url',
                                 service_url)
    if service_url:
        kwargs['service_url'] = service_url

    auth_strategy = None
    if user.requirements.is_admin:
        auth_strategy = CONFIG.get('admin_auth_strategy',
                                   CONFIG.auth_strategy)
    else:
        auth_strategy = CONFIG.auth_strategy
    set_optional('region_name', 'trove_client_region_name')
    if CONFIG.values.get('override_trove_api_url_append_tenant',
                         False):
        kwargs['service_url'] += "/" + user.tenant

    if auth_strategy == 'fake':
        from troveclient.compat import auth

        class FakeAuth(auth.Authenticator):

            def authenticate(self):
                class FakeCatalog(object):
                    def __init__(self, auth):
                        self.auth = auth

                    def get_public_url(self):
                        return "%s/%s" % (CONFIG.dbaas_url,
                                          self.auth.tenant)

                    def get_token(self):
                        return self.auth.tenant

                return FakeCatalog(self)

        auth_strategy = FakeAuth

    if auth_strategy:
        kwargs['auth_strategy'] = auth_strategy

    if not user.requirements.is_admin:
        auth_url = CONFIG.trove_auth_url
    else:
        auth_url = CONFIG.values.get('trove_admin_auth_url',
                                     CONFIG.trove_auth_url)

    if CONFIG.values.get('trove_client_cls'):
        cls_name = CONFIG.trove_client_cls
        kwargs['client_cls'] = import_class(cls_name)

    kwargs['tenant'] = user.tenant
    kwargs['auth_url'] = auth_url
    return (user.auth_user, user.auth_key), kwargs


def create_client(cls, user):
    args, kwargs = create_client_args(user)
    kwargs['client_cls'] = cls
    client = Dbaas(*args, **kwargs)
    return client


def make_client(user):
    args, kwargs = create_client_args(user)
    kwargs['client_cls'] = JsonClient
    client = Dbaas(*args, **kwargs)
    client.client.name = "auth"
    client.authenticate()
    return client


def write_snippet(get_replace_list, client, name, url, method, status, reason,
                  func, *func_args):
        """
        'name' is the name of the file, while 'url,' 'method,' 'status,'
        and 'reason' are expected values that are asserted against.
        If func_args is present, it is a list of lists, each one of which
        is passed as the *args to the two invocations of "func".
        """
        func_args = func_args or []
        snippet_writer = SnippetWriter(conf, get_replace_list)
        results = []
        client.client.snippet_writer = snippet_writer
        client.client.name = name
        args = func_args
        result = func(client, *args)

        # Now write the snippet (if this happens earlier we can't replace
        # data such as the instance ID).
        client.client.write_snippet()
        with Check() as check:
            check.equal(client.client.old_info['url'], url)
            check.equal(client.client.old_info['method'], method)
            check.equal(client.client.old_info['response_headers'].status,
                        status)
            check.equal(client.client.old_info['response_headers'].reason,
                        reason)
        results.append(result)
        # To prevent this from writing a snippet somewhere else...
        client.client.name = "junk"

        return results


JSON_INDEX = 0


class Example(object):

    @classmethod
    def get_replace_list(cls):
        return []

    def snippet(self, *args, **kwargs):
        return write_snippet(self.get_replace_list, self.client,
                             *args, **kwargs)


@test(depends_on=[load_config_file], enabled=False)
class Versions(Example):

    @before_class
    def setup(self):
        self.client = make_client(normal_user)

    @test
    def get_versions(self):
        self.snippet(
            "versions",
            "", "GET", 200, "OK",
            lambda client: client.versions.index(conf['version_url']))

    @test
    def get_version(self):
        def version_call(client):
            return client.versions.index(conf['version_url'] + "/v1.0/")

        self.snippet("versions", "/v1.0", "GET", 200, "OK", get_version)


@test(depends_on=[load_config_file])
class Flavors(Example):

    @before_class
    def setup(self):
        self.client = make_client(normal_user)

    @test
    def get_flavors(self):
        self.snippet(
            "flavors",
            "/flavors", "GET", 200, "OK",
            lambda client: client.flavors.list())

    @test
    def get_flavor_by_id(self):
        self.snippet(
            "flavors_by_id",
            "/flavors/1", "GET", 200, "OK",
            lambda client: client.flavors.get(1))


@test(depends_on=[load_config_file])
def clean_slate():
    client = create_client(TroveHTTPClient, admin_user)
    client.client.name = "list"
    instances = client.instances.list()
    assert_equal(0, len(instances), "Instance count must be zero.")


@test(depends_on=[clean_slate])
class CreateInstance(Example):

    @before_class
    def setup(self):
        self.client = make_client(normal_user)

    @test
    def post_create_instance(self):
        set_fake_stuff(uuid=EXAMPLE_INSTANCE_ID)

        def create_instance(client, name):
            instance = client.instances.create(
                name, 1,
                volume={'size': 2},
                databases=[
                    {
                        "name": "sampledb",
                        "character_set": "utf8",
                        "collate": "utf8_general_ci"
                    },
                    {
                        "name": "nextround"
                    }
                ],
                users=[
                    {
                        "databases": [{"name": "sampledb"}],
                        "name": "demouser",
                        "password": "demopassword"
                    }
                ])
            assert_equal(instance.status, "BUILD")
            return instance
        self.instances = self.snippet(
            "create_instance",
            "/instances", "POST", 200, "OK",
            create_instance,
            "json_rack_instance")

    def an_instance_is_not_active(self):
        for instance in self.instances:
            instance = self.client.instances.get(instance.id)
            if instance.status != "ACTIVE":
                assert_equal(instance.status, "BUILD")
                return True
        return False

    @test(depends_on=[post_create_instance])
    def wait_for_instances(self):
        while self.an_instance_is_not_active():
            time.sleep(1)
        global json_instance
        json_instance = self.instances[0]


@test(depends_on=[CreateInstance], groups=['uses_instances'])
class Databases(Example):

    @before_class
    def setup(self):
        self.client = make_client(normal_user)

    @test
    def post_create_databases(self):
        self.snippet(
            "create_databases",
            "/instances/%s/databases" % json_instance.id,
            "POST", 202, "Accepted",
            lambda client: client.databases.create(
                json_instance.id,
                databases=[
                    {
                        "name": "testingdb",
                        "character_set": "utf8",
                        "collate": "utf8_general_ci"
                    }, {
                        "name": "anotherdb"
                    }, {
                        "name": "oneMoreDB"
                    }]))

    @test(depends_on=[post_create_databases])
    def get_list_databases(self):
        self.snippet(
            "list_databases",
            "/instances/%s/databases" % json_instance.id,
            "GET", 200, "OK",
            lambda client: client.databases.list(json_instance.id))

    @test(depends_on=[post_create_databases])
    def get_list_databases_limit_two(self):
        results = self.snippet(
            "list_databases_pagination",
            "/instances/%s/databases?limit=1" % json_instance.id,
            "GET", 200, "OK",
            lambda client: client.databases.list(json_instance.id, limit=1))
        assert_equal(1, len(results[JSON_INDEX]))
        assert_equal("anotherdb", results[JSON_INDEX].next)

    @test(depends_on=[post_create_databases],
          runs_after=[get_list_databases, get_list_databases_limit_two])
    def delete_databases(self):
        self.snippet(
            "delete_databases",
            "/instances/%s/databases/testingdb" % json_instance.id,
            "DELETE", 202, "Accepted",
            lambda client:
            client.databases.delete(json_instance.id, 'testingdb'))


@test(depends_on=[CreateInstance], groups=['uses_instances'])
class Users(Example):

    @before_class
    def setup(self):
        self.client = make_client(normal_user)

    @test
    def post_create_users(self):
        self.snippet(
            "create_users",
            "/instances/%s/users" % json_instance.id,
            "POST", 202, "Accepted",
            lambda client: client.users.create(
                json_instance.id,
                [{
                    "name": "dbuser1",
                    "password": "password",
                    "databases": [
                        {
                            "name": "databaseA"
                        }
                    ]
                }, {
                    "name": "dbuser2",
                    "password": "password",
                    "databases": [
                        {
                            "name": "databaseB"
                        },
                        {
                            "name": "databaseC"
                        }
                    ]
                }, {
                    "name": "dbuser3",
                    "password": "password",
                    "databases": [
                        {
                            "name": "databaseD"
                        }
                    ]
                }]))

    @test(depends_on=[post_create_users])
    def get_list_users(self):
        self.snippet(
            "list_users",
            "/instances/%s/users" % json_instance.id,
            "GET", 200, "OK",
            lambda client: client.users.list(json_instance.id))

    @test(depends_on=[post_create_users])
    def get_list_users_limit_two(self):
        self.snippet(
            "list_users_pagination",
            "/instances/%s/users?limit=2" % json_instance.id,
            "GET", 200, "OK",
            lambda client: client.users.list(json_instance.id, limit=2))

    @test(depends_on=[post_create_users],
          runs_after=[get_list_users, get_list_users_limit_two])
    def delete_users(self):
        user_name = "demouser"
        self.snippet(
            "delete_users",
            "/instances/%s/users/%s" % (json_instance.id, user_name),
            "DELETE", 202, "Accepted",
            lambda client: client.users.delete(json_instance.id,
                                               username=user_name))

    @test(depends_on=[post_create_users])
    def modify_user_attributes(self):
        old_user_name = "dbuser1"
        self.snippet(
            "change_user_attributes",
            "/instances/%s/users/%s" % (json_instance.id, old_user_name),
            "PUT", 202, "Accepted",
            lambda client: client.users.update_attributes(
                json_instance.id,
                username=old_user_name,
                newuserattr={
                    "name": "new_username",
                    "password": "new_password"
                }
            )
        )


@test(depends_on=[CreateInstance], groups=['uses_instances'])
class Root(Example):

    @before_class
    def setup(self):
        self.client = make_client(normal_user)

    @test
    def post_enable_root_access(self):
        self.snippet(
            "enable_root_user",
            "/instances/%s/root" % json_instance.id,
            "POST", 200, "OK",
            lambda client: client.root.create(json_instance.id))

    @test(depends_on=[post_enable_root_access])
    def get_check_root_access(self):
        results = self.snippet(
            "check_root_user",
            "/instances/%s/root" % json_instance.id,
            "GET", 200, "OK",
            lambda client: client.root.is_root_enabled(json_instance.id))
        assert_equal(results[JSON_INDEX].rootEnabled, True)

    @test(depends_on=[get_check_root_access])
    def delete_disable_root_access(self):
        self.snippet(
            "disable_root_user",
            "/instances/%s/root" % json_instance.id,
            "DELETE", 200, "OK",
            lambda client: client.root.delete(json_instance.id))

        # restore root for subsequent tests
        self.post_enable_root_access()


class ActiveMixin(Example):
    """Adds a method to wait for instance status to become ACTIVE."""

    def _wait_for_active(self, *acceptable_states):
        global json_instance
        json_instance = self.client.instances.get(json_instance.id)
        print('instance.status=%s' % json_instance.status)
        while json_instance.status != "ACTIVE":
            assert_true(
                json_instance.status in acceptable_states,
                "Instance status == %s; expected it to be one of: %s"
                % (json_instance.status, acceptable_states))
            time.sleep(0.1)
            json_instance = self.client.instances.get(json_instance.id)

    def _wait_for_restore_active(self, *acceptable_states):
        for instance in (self.json_restore, ):
            instance = self.client.instances.get(instance.id)
            print('instance.status=%s' % instance.status)
            while instance.status != "ACTIVE":
                assert_true(
                    instance.status in acceptable_states,
                    "Instance status == %s; expected it to be one of: %s"
                    % (instance.status, acceptable_states))
                time.sleep(0.1)
                instance = self.client.instances.get(instance.id)


STATE = {
    "CONFIGURATION": None,
    "DATASTORE_ID": None,
    "DATASTORE_VERSION_ID": None,
}


@test(depends_on=[CreateInstance], groups=['uses_instances'])
class Datastores(Example):

    @before_class
    def setup(self):
        self.client = make_client(normal_user)

    @test
    def get_datastores_list(self):
        self.datastores = self.snippet(
            "datastores_list",
            "/datastores",
            "GET", 200, "OK",
            lambda client: client.datastores.list())
        for result in self.datastores:
            assert_equal(1, len(result))

    @test(depends_on=[get_datastores_list])
    def get_datastore_by_id(self):
        ds, = self.datastores
        mysql_ds = [x for x in ds if x.name == 'mysql']
        if not mysql_ds:
            fail('no mysql datastore found in list')
        ds_id = STATE["DATASTORE_ID"] = mysql_ds[JSON_INDEX].id
        self.datastore = self.snippet(
            "datastore_by_id",
            "/datastores/%s" % ds_id,
            "GET", 200, "OK",
            lambda client: client.datastores.get(ds_id))

    @test(depends_on=[get_datastore_by_id])
    def get_datastore_versions_list(self):
        ds_id = STATE["DATASTORE_ID"]
        self.datastore_versions = self.snippet(
            "datastore_versions_list",
            "/datastores/%s/versions" % ds_id,
            "GET", 200, "OK",
            lambda client: client.datastore_versions.list(ds_id))

    @test(depends_on=[get_datastore_versions_list])
    def get_datastore_version_by_id(self):
        ds_id = STATE["DATASTORE_ID"]
        ds_v_id = STATE["DATASTORE_VERSION_ID"] = (
            self.datastore_versions[JSON_INDEX][0].id
        )
        self.datastore_version = self.snippet(
            "datastore_version_by_id",
            "/datastores/%s/versions/%s" % (ds_id, ds_v_id),
            "GET", 200, "OK",
            lambda client: client.datastore_versions.get(ds_id, ds_v_id))


@test(depends_on=[Datastores], groups=['uses_instances'])
class Configurations(ActiveMixin):

    @before_class
    def setup(self):
        self.client = make_client(normal_user)

    @test
    def get_configuration_parameters_for_datastore_version(self):
        ds_id = STATE["DATASTORE_ID"]
        ds_v_id = STATE["DATASTORE_VERSION_ID"]
        self.snippet(
            "configuration_parameters_for_datastore_version",
            "/datastores/%s/versions/%s/parameters" % (ds_id, ds_v_id),
            "GET", 200, "OK",
            lambda client: client.configuration_parameters.parameters(
                ds_id, ds_v_id
            )
        )

    @test
    def get_configuration_parameters_without_datastore_version(self):
        ds_v_id = STATE["DATASTORE_VERSION_ID"]
        self.params = self.snippet(
            "configuration_parameters_without_datastore_version",
            "/datastores/versions/%s/parameters" % (ds_v_id),
            "GET", 200, "OK",
            lambda client: (
                client.configuration_parameters.parameters_by_version(ds_v_id)
            )
        )
        assert_true(self.params)

    @test(depends_on=[get_configuration_parameters_without_datastore_version])
    def get_configuration_parameter_for_datastore_version(self):
        ds_id = STATE["DATASTORE_ID"]
        ds_v_id = STATE["DATASTORE_VERSION_ID"]
        param = self.params[JSON_INDEX][0].name
        self.snippet(
            "configuration_parameter_for_datastore_version",
            "/datastores/%s/versions/%s/parameters/%s"
            % (ds_id, ds_v_id, param),
            "GET", 200, "OK",
            lambda client: client.configuration_parameters.get_parameter(
                ds_id, ds_v_id, param))

    @test(depends_on=[get_configuration_parameters_without_datastore_version])
    def get_configuration_parameter_without_datastore_version(self):
        ds_v_id = STATE["DATASTORE_VERSION_ID"]
        param = self.params[JSON_INDEX][0].name

        def get_param(client):
            return client.configuration_parameters.get_parameter_by_version(
                ds_v_id,
                param
            )

        self.params = self.snippet(
            "configuration_parameter_without_datastore_version",
            "/datastores/versions/%s/parameters/%s" % (ds_v_id, param),
            "GET", 200, "OK",
            get_param
        )

    @test(depends_on=[get_configuration_parameter_without_datastore_version])
    def create_configuration(self):
        set_fake_stuff(uuid=EXAMPLE_CONFIG_ID)
        ds_id = STATE["DATASTORE_ID"]
        ds_v_id = STATE["DATASTORE_VERSION_ID"]
        values = {
            "connect_timeout": 120,
            "collation_server": "latin1_swedish_ci"
        }

        def create(client):
            config = client.configurations.create(
                'example-configuration-name', json.dumps(values),
                'example description', ds_id, ds_v_id)
            return config

        self.configurations = self.snippet(
            "configuration_create",
            "/configurations",
            "POST", 200, "OK",
            create)
        STATE["CONFIGURATION"] = self.configurations[JSON_INDEX]

    @test(depends_on=[create_configuration])
    def get_configuration(self):
        config = STATE["CONFIGURATION"]
        self.config = self.snippet(
            "configuration_details",
            "/configurations/%s" % config.id,
            "GET", 200, "OK",
            lambda client: client.configurations.get(config.id))

    @test(depends_on=[create_configuration])
    def list_configurations(self):
        self.configs = self.snippet(
            "configuration_list",
            "/configurations",
            "GET", 200, "OK",
            lambda client: client.configurations.list())

    @test(depends_on=[list_configurations, get_configuration])
    def edit_configuration(self):
        config = STATE["CONFIGURATION"]
        values = {
            'connect_timeout': 300
        }
        self.snippet(
            "configuration_edit_parameters",
            "/configurations/%s" % config.id,
            "PATCH", 200, "OK",
            lambda client: client.configurations.edit(
                config.id, json.dumps(values)))

    @test(depends_on=[edit_configuration])
    def update_configuration(self):
        config = STATE["CONFIGURATION"]
        values = {
            'connect_timeout': 150,
            'collation_server': 'utf8_unicode_ci'
        }
        self.snippet(
            "configuration_update_parameters",
            "/configurations/%s" % config.id,
            "PUT", 202, "Accepted",
            lambda client: client.configurations.update(
                config.id, json.dumps(values),
                'example-updated-name', 'example updated description'))

    @test(depends_on=[update_configuration])
    def attach_configuration_to_instance(self):
        config = STATE["CONFIGURATION"]
        self.snippet(
            "configuration_attach_to_instance",
            "/instances/%s" % json_instance.id,
            "PUT", 202, "Accepted",
            lambda client: client.instances.modify(
                json_instance.id,
                config.id
            )
        )

    @test(depends_on=[attach_configuration_to_instance])
    def list_configurations_instances(self):
        config = STATE["CONFIGURATION"]
        self.config_instances = self.snippet(
            "configuration_list_instances",
            "/configurations/%s/instances" % config.id,
            "GET", 200, "OK",
            lambda client: client.configurations.instances(config.id))

    @test(depends_on=[list_configurations_instances])
    def detach_configuration_from_instance(self):
        self.snippet(
            "configuration_detach_from_instance",
            "/instances/%s" % json_instance.id,
            "PUT", 202, "Accepted",
            lambda client: client.instances.modify(
                json_instance.id, ""))

    @test(depends_on=[detach_configuration_from_instance])
    def instance_restart_after_configration_change(self):
        self.client.instances.restart(json_instance.id)
        self._wait_for_active("REBOOT")


@test(depends_on=[CreateInstance], groups=['uses_instances'])
class InstanceList(Example):

    @before_class
    def setup(self):
        self.client = make_client(normal_user)

    @test
    def get_list_instance_index(self):
        results = self.snippet(
            "instances_index",
            "/instances", "GET", 200, "OK",
            lambda client: client.instances.list())
        for result in results:
            assert_equal(1, len(result))

    @test
    def get_instance_details(self):
        results = self.snippet(
            "instance_status_detail",
            "/instances/%s" % json_instance.id,
            "GET", 200, "OK",
            lambda client: client.instances.get(json_instance.id))
        assert_equal(results[JSON_INDEX].id, json_instance.id)

    @test
    def get_default_instance_configuration(self):
        set_fake_stuff(unique_id=EXAMPLE_CONFIG_SERVER_ID)
        self.snippet(
            "get_default_instance_configuration",
            "/instances/%s/configuration" % json_instance.id,
            "GET", 200, "OK",
            lambda client: client.instances.configuration(json_instance.id))

    @test
    def get_list_instance_index_limit_two(self):
        third_instance = self.client.instances.create(
            "The Third Instance", 1, volume={'size': 2})
        third_instance = self.client.instances.get(third_instance.id)
        while third_instance.status != "ACTIVE":
            time.sleep(0.1)
            third_instance = self.client.instances.get(third_instance.id)

        results = self.snippet(
            "instances_index_pagination",
            "/instances?limit=2", "GET", 200, "OK",
            lambda client: client.instances.list(limit=2))
        for result in results:
            assert_equal(2, len(result))

        self.client.instances.delete(third_instance.id)


@test(depends_on=[CreateInstance], groups=['uses_instances'])
class Backups(ActiveMixin):

    @before_class
    def setup(self):
        self.client = make_client(normal_user)

    @test
    def create_backup(self):
        set_fake_stuff(uuid=EXAMPLE_BACKUP_ID)
        results = self.snippet(
            "backup_create", "/backups", "POST", 202, "Accepted",
            lambda client: client.backups.create(
                name='snapshot',
                instance=json_instance.id,
                description="My Backup"
            )
        )
        self._wait_for_active("BACKUP")
        assert_equal(len(results), 1)
        self.json_backup = results[JSON_INDEX]

    @test(depends_on=[create_backup])
    def create_incremental_backup(self):
        set_fake_stuff(uuid=EXAMPLE_BACKUP_INCREMENTAL_ID)
        results = self.snippet(
            "backup_create_incremental", "/backups", "POST", 202, "Accepted",
            lambda client: client.backups.create(
                name='Incremental Snapshot',
                instance=json_instance.id,
                parent_id=EXAMPLE_BACKUP_ID,
                description="My Incremental Backup"
            )
        )

        self._wait_for_active("BACKUP")
        assert_equal(len(results), 1)
        self.json_backup2 = results[JSON_INDEX]

    @test(depends_on=[create_incremental_backup])
    def get_backup(self):
        results = self.snippet(
            "backup_get",
            "/backups/%s" % self.json_backup.id,
            "GET", 200, "OK",
            lambda client: client.backups.get(self.json_backup.id))
        assert_equal(len(results), 1)

    @test(depends_on=[create_incremental_backup])
    def get_backups_for_instance(self):
        results = self.snippet(
            "backups_by_instance",
            "/instances/%s/backups" % json_instance.id,
            "GET", 200, "OK",
            lambda client: client.instances.backups(json_instance.id))
        assert_equal(len(results), 1)

    @test(depends_on=[create_incremental_backup])
    def list_backups(self):
        results = self.snippet(
            "backup_list",
            "/backups", "GET", 200, "OK",
            lambda client: client.backups.list())
        assert_equal(len(results), 1)

    @test(depends_on=[create_backup])
    def restore(self):
        set_fake_stuff(uuid=EXAMPLE_INSTANCE_ID_2)

        def create_instance(client, name, backup):
            instance = client.instances.create(
                name, 1,
                volume={'size': 2},
                restorePoint={'backupRef': backup})
            assert_equal(instance.status, "BUILD")
            return instance
        results = self.snippet(
            "backup_restore",
            "/instances", "POST", 200, "OK",
            lambda client: create_instance(
                client, "backup_instance", self.json_backup.id))
        assert_equal(len(results), 1)
        self.json_restore = results[JSON_INDEX]
        self._wait_for_restore_active("BUILD")
        self.json_restore = self.client.instances.get(self.json_restore.id)
        assert_equal(self.json_restore.status, "ACTIVE")

    @test(depends_on=[restore])
    def delete_restores(self):
        self.snippet(
            "restore_delete",
            "/instances/%s" % self.json_restore.id,
            "DELETE", 202, "Accepted",
            lambda client: client.instances.delete(self.json_restore.id))
        self.json_restore = self.client.instances.get(self.json_restore.id)
        assert_equal(self.json_restore.status, "SHUTDOWN")

    @test(depends_on=[create_backup],
          runs_after=[get_backup, list_backups, restore,
                      get_backups_for_instance])
    def delete_backup(self):
        results = self.snippet(
            "backup_delete",
            "/backups/%s" % self.json_backup.id,
            "DELETE", 202, "Accepted",
            lambda client: client.backups.delete(self.json_backup.id))
        assert_equal(len(results), 1)


@test(depends_on=[CreateInstance], groups=['uses_instances'])
class Actions(ActiveMixin):

    @before_class
    def setup(self):
        self.client = make_client(normal_user)

    @test
    def instance_restart(self):
        self.snippet(
            "instance_restart",
            "/instances/%s/action" % json_instance.id,
            "POST", 202, "Accepted",
            lambda client: client.instances.restart(json_instance.id))
        self._wait_for_active("REBOOT")

    @test
    def instance_resize_volume(self):
        self.snippet(
            "instance_resize_volume",
            "/instances/%s/action" % json_instance.id,
            "POST", 202, "Accepted",
            lambda client: client.instances.resize_volume(json_instance.id, 4))
        self._wait_for_active("RESIZE")
        assert_equal(json_instance.volume['size'], 4)

    @test
    def instance_resize_flavor(self):
        self.snippet(
            "instance_resize_flavor",
            ("/instances/%s/action" % json_instance.id),
            "POST", 202, "Accepted",
            lambda client: client.instances.resize_instance(
                json_instance.id, 3))
        self._wait_for_active("RESIZE")
        # TODO(imsplitbit): remove coercion when troveclient fixes are in
        assert_equal(int(json_instance.flavor['id']), 3)


@test(depends_on=[CreateInstance], groups=['uses_instances', "MgmtHosts"])
class MgmtHosts(Example):

    @before_class
    def setup(self):
        self.client = make_client(admin_user)

    @test
    def mgmt_list_hosts(self):
        results = self.snippet(
            "mgmt_list_hosts",
            "/mgmt/hosts", "GET", 200, "OK",
            lambda client: client.mgmt.hosts.index())

        with Check() as check:
            for hosts in results:
                check.equal(2, len(hosts))
                check.true("fake_host_1" == hosts[0].name
                           or "fake_host_1" == hosts[1].name)
                check.true("fake_host_2" == hosts[0].name
                           or "fake_host_2" == hosts[1].name)
                check.true(1 == results[0][1].instanceCount
                           or 1 == results[0][0].instanceCount)

    @test
    def mgmt_get_host_detail(self):
        results = self.snippet(
            "mgmt_get_host_detail",
            "/mgmt/hosts/fake_host_1", "GET", 200, "OK",
            lambda client: client.mgmt.hosts.get("fake_host_1"))
        with Check() as check:
            for host in results:
                check.equal(results[0].name, "fake_host_1")
                # XML entries won't come back as these types. :(
                check.true(isinstance(results[0].percentUsed, int)),
                check.true(isinstance(results[0].totalRAM, int)),
                check.true(isinstance(results[0].usedRAM, int)),
        with Check() as check:
            for host in results:
                check.equal(1, len(host.instances))
                for instance in host.instances:
                    check.equal(instance['status'], 'ACTIVE')
                    check.true(isinstance(instance['name'], six.string_types))
                    check.true(isinstance(instance['id'], six.string_types))
                    check.true(isinstance(instance['server_id'],
                               six.string_types))
                    check.true(isinstance(instance['tenant_id'],
                               six.string_types))

    @test
    def mgmt_host_update_all(self):
        raise SkipTest("This isn't working... :(")
        self.snippet(
            "mgmt_host_update",
            "/mgmt/hosts/fake_host_1/instances/action",
            "POST", 202, "Accepted",
            lambda client: client.mgmt.hosts.update_all("fake_host_1"))


@test(depends_on=[CreateInstance], groups=['uses_instances'])
class MgmtStorage(Example):

    @before_class
    def setup(self):
        self.client = make_client(admin_user)

    @test
    def mgmt_get_storage(self):
        results = self.snippet(
            "mgmt_get_storage",
            "/mgmt/storage", "GET", 200, "OK",
            lambda client: client.mgmt.storage.index())
        for index, devices in enumerate(results):
            with Check() as check:
                check.equal(1, len(devices))
                device = devices[0]
                check.equal(int(device.capacity['available']), 90)
                check.equal(int(device.capacity['total']), 100)
                check.equal(device.name, "fake_storage")
                check.equal(int(device.provision['available']), 40)
                check.equal(int(device.provision['percent']), 10)
                check.equal(int(device.provision['total']), 50)
                check.equal(device.type, "test_type")
                check.equal(int(device.used), 10)
                if index == JSON_INDEX:
                    check.true(isinstance(device.capacity['available'], int))
                    check.true(isinstance(device.capacity['total'], int))
                    check.true(isinstance(device.provision['available'], int))
                    check.true(isinstance(device.provision['percent'], int))
                    check.true(isinstance(device.provision['total'], int))
                    check.true(isinstance(device.used, int))


@test(depends_on=[CreateInstance], groups=['uses_instances'])
class MgmtAccount(Example):

    @before_class
    def setup(self):
        self.client = make_client(admin_user)

    @test
    def mgmt_get_account_details(self):
        results = self.snippet(
            "mgmt_get_account_details",
            "/mgmt/accounts/%s" % conf['normal_user_tenant'],
            "GET", 200, "OK",
            lambda client: client.mgmt.accounts.show(
                conf['normal_user_tenant'], ))
        with Check() as check:
            for account_info in results:
                check.equal(conf['normal_user_tenant'], account_info.id)

    @test
    def mgmt_get_account_list(self):
        results = self.snippet(
            "mgmt_list_accounts",
            "/mgmt/accounts", "GET", 200, "OK",
            lambda client: client.mgmt.accounts.index())
        matches = {conf['normal_user_tenant']: 2,
                   conf['admin_user_tenant']: 0}
        for index, result in enumerate(results):
            for account in result.accounts:
                if account['id'] not in matches:
                    fail("Did not expect this account ID: %s" % account['id'])
                expected_count = matches[account['id']]
                if index == JSON_INDEX:
                    assert_equal(2, expected_count)
                else:
                    assert_equal(2, expected_count)


def for_both(func):
    @functools.wraps(func)
    def both(self):
        for result in self.results:
            func(self, result)
    return both


@test(depends_on=[CreateInstance], groups=['uses_instances'])
class MgmtInstance(Example):

    @before_class
    def mgmt_get_instance_details(self):
        self.client = make_client(admin_user)
        self.results = self.snippet(
            "mgmt_get_instance_details",
            ("/mgmt/instances/%s" % json_instance.id),
            "GET", 200, "OK",
            lambda client: client.mgmt.instances.show(json_instance.id))

    @test
    @for_both
    def created(self, result):
        assert_true(isinstance(result.created, six.string_types))

    @test
    def deleted(self):
        assert_equal(self.results[JSON_INDEX].deleted, False)

    @test
    @for_both
    def flavor(self, result):
        # TODO(imsplitbit): remove the coercion when python-troveclient fixes
        # land in the public.
        assert_true(
            int(result.flavor['id']) == 1 or int(result.flavor['id']) == 3)
        assert_equal(len(result.flavor['links']), 2)

    @test
    @for_both
    def guest_status(self, result):
        assert_equal(result.guest_status['state_description'], 'running')

    @test(enabled=False)
    @for_both
    def host(self, result):
        assert_equal(result.host, 'fake_host_1')

    @test
    def id(self):
        assert_equal(self.results[JSON_INDEX].id, json_instance.id)

    @test
    @for_both
    def links(self, result):
        assert_true(isinstance(result.links, list))
        for link in result.links:
            assert_true(isinstance(link, dict))
            assert_true(isinstance(link['href'], six.string_types))
            assert_true(isinstance(link['rel'], six.string_types))

    @test
    def local_id(self):
        assert_true(isinstance(self.results[JSON_INDEX].server['local_id'],
                    int))

    @test
    @for_both
    def name(self, result):
        assert_true(isinstance(result.name, six.string_types))

    @test
    @for_both
    def server_id(self, result):
        assert_true(isinstance(result.server['id'], six.string_types))

    @test
    @for_both
    def status(self, result):
        assert_equal("ACTIVE", result.status)

    @test
    @for_both
    def task_description(self, result):
        assert_equal(result.task_description, "No tasks for the instance.")

    @test
    @for_both
    def tenant_id(self, result):
        assert_equal(result.tenant_id, conf['normal_user_tenant'])

    @test
    @for_both
    def updated(self, result):
        assert_true(isinstance(result.updated, six.string_types))

    @test
    @for_both
    def volume(self, result):
        assert_true(isinstance(result.volume, dict))
        assert_true('id' in result.volume)
        assert_true('size' in result.volume)


@test(depends_on=[CreateInstance], groups=['uses_instances'])
class MgmtInstanceIndex(Example):

    @before_class
    def setup(self):
        self.client = make_client(admin_user)

    @test
    def mgmt_instance_index(self, deleted=False):
        self.snippet(
            "mgmt_instance_index",
            "/mgmt/instances?deleted=false", "GET", 200, "OK",
            lambda client: client.mgmt.instances.index(deleted=False))


@test(depends_on=[CreateInstance], groups=['uses_instances'])
class MgmtInstanceDiagnostics(Example):

    @before_class
    def setup(self):
        self.client = make_client(admin_user)

    @test
    def mgmt_get_instance_diagnostics(self):
        self.snippet(
            "mgmt_instance_diagnostics",
            ("/mgmt/instances/%s/diagnostics" % json_instance.id),
            "GET", 200, "OK",
            lambda client: client.diagnostics.get(json_instance.id))


@test(depends_on=[CreateInstance])
class MgmtInstanceRoot(Example):

    @before_class
    def setup(self):
        self.client = make_client(admin_user)

    @test
    def mgmt_get_root_details(self):
        self.snippet(
            "mgmt_get_root_details",
            ("/mgmt/instances/%s/root" % json_instance.id),
            "GET", 200, "OK",
            lambda client: client.mgmt.instances.root_enabled_history(
                json_instance.id)
        )


@test(depends_on=[CreateInstance], enabled=False)
class MgmtInstanceHWInfo(Example):

    @before_class
    def setup(self):
        self.client = make_client(admin_user)

    @test
    def mgmt_get_hw_info(self):
        self.snippet(
            "mgmt_get_hw_info",
            ("/mgmt/instances/%s/hwinfo" % json_instance.id),
            "GET", 200, "OK",
            lambda client, id: client.hw_info.get(id),
            ([json_instance.id], ))


@test(depends_on=[CreateInstance], groups=['uses_instances'])
class MgmtInstanceReboot(Example):

    @before_class
    def setup(self):
        self.client = make_client(admin_user)

    @test
    def mgmt_instance_reboot(self):
        self.snippet(
            "instance_reboot",
            ("/mgmt/instances/%s/action" % json_instance.id),
            "POST", 202, "Accepted",
            lambda client: client.mgmt.instances.reboot(json_instance.id))


@test(depends_on=[CreateInstance],
      groups=['uses_instances'], enabled=False)
class MgmtInstanceGuestUpdate(Example):

    @before_class
    def setup(self):
        self.client = make_client(admin_user)

    @test
    def mgmt_instance_guest_update(self):
        self.snippet(
            "guest_update",
            ("/mgmt/instances/%s/action" % json_instance.id),
            "POST", 202, "Accepted",
            lambda client: client.mgmt.instances.update(json_instance.id))


@test(depends_on=[CreateInstance], runs_after_groups=['uses_instances'])
class ZzzDeleteInstance(Example):

    @before_class
    def setup(self):
        self.client = make_client(normal_user)

    @test
    def zzz_delete_instance(self):
        global json_instance
        self.snippet(
            "delete_instance",
            "/instances/%s" % json_instance.id,
            "DELETE", 202, "Accepted",
            lambda client: client.instances.delete(json_instance.id))
        json_instance = self.client.instances.get(json_instance.id)
        assert_equal(json_instance.status, "SHUTDOWN")

    @test(depends_on=[zzz_delete_instance])
    def delete_configuration(self):
        config = STATE["CONFIGURATION"]
        self.configs = self.snippet(
            "configuration_delete",
            ("/configurations/%s" % config.id),
            "DELETE", 202, "Accepted",
            lambda client: client.configurations.delete(config.id))


if __name__ == "__main__":
    CONFIG.load_from_file("etc/tests/localhost.test.conf")
    TestProgram().run_and_exit()
