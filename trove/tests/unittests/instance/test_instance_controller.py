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
from mock import Mock
from testtools.matchers import Is, Equals
from testtools.testcase import skip

from trove.common import apischema
from trove.instance.service import InstanceController
from trove.tests.unittests import trove_testtools


class TestInstanceController(trove_testtools.TestCase):
    def setUp(self):
        super(TestInstanceController, self).setUp()
        self.controller = InstanceController()
        self.locality = 'affinity'
        self.instance = {
            "instance": {
                "volume": {"size": "1"},
                "users": [
                    {"name": "user1",
                     "password": "litepass",
                     "databases": [{"name": "firstdb"}]}
                ],
                "flavorRef": "https://localhost:8779/v1.0/2500/1",
                "name": "TEST-XYS2d2fe2kl;zx;jkl2l;sjdcma239(E)@(D",
                "databases": [
                    {
                        "name": "firstdb",
                        "collate": "latin2_general_ci",
                        "character_set": "latin2"
                    },
                    {
                        "name": "db2"
                    }
                ],
                "locality": self.locality
            }
        }
        self.context = trove_testtools.TroveTestContext(self)
        self.req = Mock(remote_addr='ip:port', host='myhost')

    def verify_errors(self, errors, msg=None, properties=None, path=None):
        msg = msg or []
        properties = properties or []
        self.assertThat(len(errors), Is(len(msg)))
        i = 0
        while i < len(msg):
            self.assertIn(errors[i].message, msg)
            if path:
                self.assertThat(path, Equals(properties[i]))
            else:
                self.assertThat(errors[i].path.pop(), Equals(properties[i]))
            i += 1

    def test_get_schema_create(self):
        schema = self.controller.get_schema('create', {'instance': {}})
        self.assertIsNotNone(schema)
        self.assertIn('instance', schema['properties'])

    def test_get_schema_action_restart(self):
        schema = self.controller.get_schema('action', {'restart': {}})
        self.assertIsNotNone(schema)
        self.assertIn('restart', schema['properties'])

    def test_get_schema_action_resize_volume(self):
        schema = self.controller.get_schema(
            'action', {'resize': {'volume': {}}})
        self.assertIsNotNone(schema)
        self.assertIn('resize', schema['properties'])
        self.assertIn(
            'volume', schema['properties']['resize']['properties'])

    def test_get_schema_action_resize_flavorRef(self):
        schema = self.controller.get_schema(
            'action', {'resize': {'flavorRef': {}}})
        self.assertIsNotNone(schema)
        self.assertIn('resize', schema['properties'])
        self.assertIn(
            'flavorRef', schema['properties']['resize']['properties'])

    def test_get_schema_action_other(self):
        schema = self.controller.get_schema(
            'action', {'supersized': {'flavorRef': {}}})
        self.assertIsNotNone(schema)
        self.assertThat(len(schema.keys()), Is(0))

    def test_validate_create_complete(self):
        body = self.instance
        schema = self.controller.get_schema('create', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertTrue(validator.is_valid(body))

    def test_validate_create_complete_with_restore(self):
        body = self.instance
        body['instance']['restorePoint'] = {
            "backupRef": "d761edd8-0771-46ff-9743-688b9e297a3b"
        }
        schema = self.controller.get_schema('create', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertTrue(validator.is_valid(body))

    def test_validate_create_complete_with_restore_error(self):
        body = self.instance
        backup_id_ref = "invalid-backup-id-ref"
        body['instance']['restorePoint'] = {
            "backupRef": backup_id_ref
        }
        schema = self.controller.get_schema('create', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertFalse(validator.is_valid(body))
        errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        self.assertThat(len(errors), Is(1))
        self.assertThat(errors[0].message,
                        Equals("'%s' does not match '%s'" %
                               (backup_id_ref, apischema.uuid['pattern'])))

    def test_validate_create_blankname(self):
        body = self.instance
        body['instance']['name'] = "     "
        schema = self.controller.get_schema('create', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertFalse(validator.is_valid(body))
        errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        self.assertThat(len(errors), Is(1))
        self.assertThat(errors[0].message,
                        Equals("'     ' does not match '^.*[0-9a-zA-Z]+.*$'"))

    def test_validate_create_invalid_name(self):
        body = self.instance
        body['instance']['name'] = "$#$%^^"
        schema = self.controller.get_schema('create', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertFalse(validator.is_valid(body))
        errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        self.assertEqual(1, len(errors))
        self.assertIn("'$#$%^^' does not match '^.*[0-9a-zA-Z]+.*$'",
                      errors[0].message)

    def test_validate_create_invalid_locality(self):
        body = self.instance
        body['instance']['locality'] = "$%^"
        schema = self.controller.get_schema('create', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertFalse(validator.is_valid(body))
        errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        error_messages = [error.message for error in errors]
        error_paths = [error.path.pop() for error in errors]
        self.assertEqual(1, len(errors))
        self.assertIn("'$%^' does not match '^.*[0-9a-zA-Z]+.*$'",
                      error_messages)
        self.assertIn("locality", error_paths)

    def test_validate_restart(self):
        body = {"restart": {}}
        schema = self.controller.get_schema('action', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertTrue(validator.is_valid(body))

    def test_validate_invalid_action(self):
        # TODO(juice) perhaps we should validate the schema not recognized
        body = {"restarted": {}}
        schema = self.controller.get_schema('action', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertTrue(validator.is_valid(body))

    def test_validate_resize_volume(self):
        body = {"resize": {"volume": {"size": 4}}}
        schema = self.controller.get_schema('action', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertTrue(validator.is_valid(body))

    def test_validate_resize_volume_string(self):
        body = {"resize": {"volume": {"size": "4"}}}
        schema = self.controller.get_schema('action', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertTrue(validator.is_valid(body))

    def test_validate_resize_volume_string_invalid_number(self):
        body = {"resize": {"volume": {"size": '-44.0'}}}
        schema = self.controller.get_schema('action', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertFalse(validator.is_valid(body))
        errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        self.assertThat(errors[0].context[1].message,
                        Equals("'-44.0' does not match '^[0-9]+$'"))
        self.assertThat(errors[0].path.pop(), Equals('size'))

    def test_validate_resize_volume_invalid_characters(self):
        body = {"resize": {"volume": {"size": 'x'}}}
        schema = self.controller.get_schema('action', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertFalse(validator.is_valid(body))
        errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        self.assertThat(errors[0].context[0].message,
                        Equals("'x' is not of type 'integer'"))
        self.assertThat(errors[0].context[1].message,
                        Equals("'x' does not match '^[0-9]+$'"))
        self.assertThat(errors[0].path.pop(), Equals('size'))

    def test_validate_resize_instance(self):
        body = {"resize": {"flavorRef": "https://endpoint/v1.0/123/flavors/2"}}
        schema = self.controller.get_schema('action', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertTrue(validator.is_valid(body))

    def test_validate_resize_instance_int(self):
        body = {"resize": {"flavorRef": 2}}
        schema = self.controller.get_schema('action', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertTrue(validator.is_valid(body))

    def test_validate_resize_instance_string(self):
        body = {"resize": {"flavorRef": 'foo'}}
        schema = self.controller.get_schema('action', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertTrue(validator.is_valid(body))

    def test_validate_resize_instance_empty_url(self):
        body = {"resize": {"flavorRef": ""}}
        schema = self.controller.get_schema('action', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertFalse(validator.is_valid(body))
        errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        self.verify_errors(errors[0].context,
                           ["'' is too short",
                            "'' does not match '^.*[0-9a-zA-Z]+.*$'",
                            "'' is not of type 'integer'"],
                           ["flavorRef", "flavorRef", "flavorRef",
                            "flavorRef"],
                           errors[0].path.pop())

    @skip("This URI validator allows just about anything you give it")
    def test_validate_resize_instance_invalid_url(self):
        body = {"resize": {"flavorRef": "xyz-re1f2-daze329d-f23901"}}
        schema = self.controller.get_schema('action', body)
        self.assertIsNotNone(schema)
        validator = jsonschema.Draft4Validator(schema)
        self.assertFalse(validator.is_valid(body))
        errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        self.verify_errors(errors, ["'' is too short"], ["flavorRef"])

    def _setup_modify_instance_mocks(self):
        instance = Mock()
        instance.detach_replica = Mock()
        instance.assign_configuration = Mock()
        instance.unassign_configuration = Mock()
        instance.update_db = Mock()
        return instance

    def test_modify_instance_with_empty_args(self):
        instance = self._setup_modify_instance_mocks()
        args = {}

        self.controller._modify_instance(self.context, self.req,
                                         instance, **args)

        self.assertEqual(0, instance.detach_replica.call_count)
        self.assertEqual(0, instance.unassign_configuration.call_count)
        self.assertEqual(0, instance.assign_configuration.call_count)
        self.assertEqual(0, instance.update_db.call_count)

    def test_modify_instance_with_nonempty_args_calls_update_db(self):
        instance = self._setup_modify_instance_mocks()
        args = {}
        args['any'] = 'anything'

        self.controller._modify_instance(self.context, self.req,
                                         instance, **args)

        instance.update_db.assert_called_once_with(**args)

    def test_modify_instance_with_False_detach_replica_arg(self):
        instance = self._setup_modify_instance_mocks()
        args = {}
        args['detach_replica'] = False

        self.controller._modify_instance(self.context, self.req,
                                         instance, **args)

        self.assertEqual(0, instance.detach_replica.call_count)

    def test_modify_instance_with_True_detach_replica_arg(self):
        instance = self._setup_modify_instance_mocks()
        args = {}
        args['detach_replica'] = True

        self.controller._modify_instance(self.context, self.req,
                                         instance, **args)

        self.assertEqual(1, instance.detach_replica.call_count)

    def test_modify_instance_with_configuration_id_arg(self):
        instance = self._setup_modify_instance_mocks()
        args = {}
        args['configuration_id'] = 'some_id'

        self.controller._modify_instance(self.context, self.req,
                                         instance, **args)

        self.assertEqual(1, instance.assign_configuration.call_count)

    def test_modify_instance_with_None_configuration_id_arg(self):
        instance = self._setup_modify_instance_mocks()
        args = {}
        args['configuration_id'] = None

        self.controller._modify_instance(self.context, self.req,
                                         instance, **args)

        self.assertEqual(1, instance.unassign_configuration.call_count)

    def test_modify_instance_with_all_args(self):
        instance = self._setup_modify_instance_mocks()
        args = {}
        args['detach_replica'] = True
        args['configuration_id'] = 'some_id'

        self.controller._modify_instance(self.context, self.req,
                                         instance, **args)

        self.assertEqual(1, instance.detach_replica.call_count)
        self.assertEqual(1, instance.assign_configuration.call_count)
        instance.update_db.assert_called_once_with(**args)
