# Copyright 2013 Hewlett-Packard Development Company, L.P.
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
#
import jsonschema

from testtools import TestCase
from testtools.matchers import Is, Equals
from trove.extensions.mysql.service import UserController
from trove.extensions.mysql.service import UserAccessController
from trove.extensions.mysql.service import SchemaController


class TestUserController(TestCase):
    def setUp(self):
        super(TestUserController, self).setUp()
        self.controller = UserController()

    def test_get_create_schema(self):
        body = {'users': [{'name': 'test', 'password': 'test'}]}
        schema = self.controller.get_schema('create', body)
        self.assertTrue('users' in schema['properties'])

    def test_get_update_user_pw(self):
        body = {'users': [{'name': 'test', 'password': 'test'}]}
        schema = self.controller.get_schema('update_all', body)
        self.assertTrue('users' in schema['properties'])

    def test_get_update_user_db(self):
        body = {'databases': [{'name': 'test'}, {'name': 'test'}]}
        schema = self.controller.get_schema('update_all', body)
        self.assertTrue('databases' in schema['properties'])

    def test_validate_create_empty(self):
        body = {"users": []}
        schema = self.controller.get_schema('create', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertTrue(validator.is_valid(body))
        #TODO(zed): Restore after API version increment
        #errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        #self.assertThat(len(errors), Is(1))
        #self.assertThat(errors[0].message, Equals("[] is too short"))
        #self.assertThat(errors[0].path.pop(), Equals("users"))

    def test_validate_create_short_password(self):
        body = {"users": [{"name": "joe", "password": ""}]}
        schema = self.controller.get_schema('create', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertFalse(validator.is_valid(body))
        errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        self.assertThat(len(errors), Is(2))
        self.assertThat(errors[0].message, Equals("'' is too short"))
        self.assertThat(errors[1].message,
                        Equals("'' does not match '^.*[0-9a-zA-Z]+.*$'"))
        self.assertThat(errors[0].path.pop(), Equals("password"))

    def test_validate_create_no_password(self):
        body = {"users": [{"name": "joe"}]}
        schema = self.controller.get_schema('create', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertFalse(validator.is_valid(body))
        errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        self.assertThat(len(errors), Is(1))
        self.assertThat(errors[0].message,
                        Equals("'password' is a required property"))

    def test_validate_create_short_name(self):
        body = {"users": [{"name": ""}]}
        schema = self.controller.get_schema('create', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertFalse(validator.is_valid(body))
        errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        self.assertThat(len(errors), Is(3))
        self.assertThat(errors[0].message,
                        Equals("'password' is a required property"))
        self.assertThat(errors[1].message, Equals("'' is too short"))
        self.assertThat(errors[2].message,
                        Equals("'' does not match '^.*[0-9a-zA-Z]+.*$'"))
        self.assertThat(errors[1].path.pop(), Equals("name"))

    def test_validate_create_complete_db_empty(self):
        body = {"users": [{"databases": [], "name": "joe", "password": "123"}]}
        schema = self.controller.get_schema('create', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertTrue(validator.is_valid(body))
        errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        self.assertThat(len(errors), Is(0))

    def test_validate_create_complete_db_no_name(self):
        body = {"users": [{"databases": [{}], "name": "joe",
                           "password": "123"}]}
        schema = self.controller.get_schema('create', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertFalse(validator.is_valid(body))
        errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        self.assertThat(len(errors), Is(1))
        self.assertThat(errors[0].message,
                        Equals("'name' is a required property"))

    def test_validate_create_bogus_attr(self):
        body = {"users": [{"databases": [{"name": "x"}], "name": "joe",
                           "bogosity": 100,
                           "password": "123"}]}
        schema = self.controller.get_schema('create', body)
        validator = jsonschema.Draft4Validator(schema)
        #TODO(zed): After API increment, this will NOT be valid.
        self.assertTrue(validator.is_valid(body))

    def test_validate_create_complete_db(self):
        body = {"users": [{"databases": [{"name": "x"}], "name": "joe",
                           "password": "123"}]}
        schema = self.controller.get_schema('create', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertTrue(validator.is_valid(body))

    def test_validate_update_empty(self):
        body = {"users": []}
        schema = self.controller.get_schema('update_all', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertTrue(validator.is_valid(body))
        #TODO(zed): Restore after API version increment
        #errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        #self.assertThat(len(errors), Is(1))
        #self.assertThat(errors[0].message, Equals("[] is too short"))
        #self.assertThat(errors[0].path.pop(), Equals("users"))

    def test_validate_update_short_password(self):
        body = {"users": [{"name": "joe", "password": ""}]}
        schema = self.controller.get_schema('update_all', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertFalse(validator.is_valid(body))
        errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        self.assertThat(len(errors), Is(2))
        self.assertThat(errors[0].message, Equals("'' is too short"))
        self.assertThat(errors[1].message,
                        Equals("'' does not match '^.*[0-9a-zA-Z]+.*$'"))
        self.assertThat(errors[0].path.pop(), Equals("password"))

    def test_validate_update_user_complete(self):
        body = {"users": [{"name": "joe", "password": "",
                           "databases": [{"name": "testdb"}]}]}
        schema = self.controller.get_schema('update_all', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertFalse(validator.is_valid(body))
        errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        self.assertThat(len(errors), Is(2))
        self.assertThat(errors[0].message, Equals("'' is too short"))
        self.assertThat(errors[1].message, Equals(
            "'' does not match '^.*[0-9a-zA-Z]+.*$'"))
        self.assertThat(errors[0].path.pop(), Equals("password"))

    def test_validate_update_user_with_db_short_password(self):
        body = {"users": [{"name": "joe", "password": "",
                           "databases": [{"name": "testdb"}]}]}
        schema = self.controller.get_schema('update_all', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertFalse(validator.is_valid(body))
        errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        self.assertThat(len(errors), Is(2))
        self.assertThat(errors[0].message, Equals("'' is too short"))
        self.assertThat(errors[0].path.pop(), Equals("password"))

    def test_validate_update_no_password(self):
        body = {"users": [{"name": "joe"}]}
        schema = self.controller.get_schema('update_all', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertFalse(validator.is_valid(body))
        errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        self.assertThat(len(errors), Is(1))
        self.assertThat(errors[0].message,
                        Equals("'password' is a required property"))

    def test_validate_update_database_complete(self):
        body = {"databases": [{"name": "test1"}, {"name": "test2"}]}
        schema = self.controller.get_schema('update_all', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertTrue(validator.is_valid(body))

    def test_validate_update_database_empty(self):
        body = {"databases": []}
        schema = self.controller.get_schema('update_all', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertTrue(validator.is_valid(body))
        #TODO(zed): Restore after API version increment
        #errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        #self.assertThat(len(errors), Is(1))
        #self.assertThat(errors[0].message, Equals('[] is too short'))

    def test_validate_update_short_name(self):
        body = {"users": [{"name": ""}]}
        schema = self.controller.get_schema('update_all', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertFalse(validator.is_valid(body))
        errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        self.assertThat(len(errors), Is(3))
        self.assertThat(errors[0].message,
                        Equals("'password' is a required property"))
        self.assertThat(errors[1].message, Equals("'' is too short"))
        self.assertThat(errors[2].message,
                        Equals("'' does not match '^.*[0-9a-zA-Z]+.*$'"))
        self.assertThat(errors[1].path.pop(), Equals("name"))

    def test_get_update_user_attributes(self):
        body = {'user': {'name': 'test'}}
        schema = self.controller.get_schema('update', body)
        self.assertTrue('user' in schema['properties'])

    def test_validate_update_user_attributes(self):
        body = {'user': {'name': 'test', 'password': 'test', 'host': '%'}}
        schema = self.controller.get_schema('update', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertTrue(validator.is_valid(body))

    def test_validate_update_user_attributes_empty(self):
        body = {"user": {}}
        schema = self.controller.get_schema('update', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertFalse(validator.is_valid(body))

    def test_validate_host_in_user_attributes(self):
        body_empty_host = {'user': {
            'name': 'test',
            'password': 'test',
            'host': '%'
        }}
        body_with_host = {'user': {
            'name': 'test',
            'password': 'test',
            'host': '1.1.1.1'
        }}
        body_none_host = {'user': {
            'name': 'test',
            'password': 'test',
            'host': ""
        }}

        schema_empty_host = self.controller.get_schema('update',
                                                       body_empty_host)
        schema_with_host = self.controller.get_schema('update',
                                                      body_with_host)
        schema_none_host = self.controller.get_schema('update', body_none_host)

        validator_empty_host = jsonschema.Draft4Validator(schema_empty_host)
        validator_with_host = jsonschema.Draft4Validator(schema_with_host)
        validator_none_host = jsonschema.Draft4Validator(schema_none_host)

        self.assertTrue(validator_empty_host.is_valid(body_empty_host))
        self.assertTrue(validator_with_host.is_valid(body_with_host))
        self.assertFalse(validator_none_host.is_valid(body_none_host))


class TestUserAccessController(TestCase):
    def test_validate_update_db(self):
        body = {"databases": []}
        schema = (UserAccessController()).get_schema('update_all', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertTrue(validator.is_valid(body))
        #TODO(zed): Restore after API version increment
        #errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        #self.assertThat(len(errors), Is(1))
        #self.assertThat(errors[0].message, Equals("[] is too short"))
        #self.assertThat(errors[0].path.pop(), Equals("databases"))


class TestSchemaController(TestCase):
    def setUp(self):
        super(TestSchemaController, self).setUp()
        self.controller = SchemaController()
        self.body = {
            "databases": [
                {
                    "name": "first_db",
                    "collate": "latin2_general_ci",
                    "character_set": "latin2"
                },
                {
                    "name": "second_db"
                }
            ]
        }

    def test_validate_mixed(self):
        schema = self.controller.get_schema('create', self.body)
        self.assertIsNotNone(schema)
        validator = jsonschema.Draft4Validator(schema)
        self.assertTrue(validator.is_valid(self.body))

    def test_validate_mixed_with_no_name(self):
        body = self.body.copy()
        body['databases'].append({"collate": "some_collation"})
        schema = self.controller.get_schema('create', body)
        self.assertIsNotNone(schema)
        validator = jsonschema.Draft4Validator(schema)
        self.assertFalse(validator.is_valid(body))

    def test_validate_empty(self):
        body = {"databases": []}
        schema = self.controller.get_schema('create', body)
        self.assertIsNotNone(schema)
        self.assertTrue('databases' in body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertTrue(validator.is_valid(body))
