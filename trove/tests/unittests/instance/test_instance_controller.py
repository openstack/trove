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
import copy
from unittest import mock
from unittest.mock import MagicMock
from unittest.mock import Mock
import uuid

import jsonschema
from testtools.matchers import Equals
from testtools.matchers import Is
from testtools.testcase import skip

from trove.common import apischema
from trove.common import exception
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

    def test_validate_create_valid_nics(self):
        body = copy.copy(self.instance)
        body['instance']['nics'] = [
            {
                'network_id': str(uuid.uuid4()),
                'subnet_id': str(uuid.uuid4()),
                'ip_address': '192.168.1.11'
            }
        ]

        schema = self.controller.get_schema('create', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertTrue(validator.is_valid(body))

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

    def test_validate_resize_volume_string_start_with_zero(self):
        body = {"resize": {"volume": {"size": "0040"}}}
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
                        Equals("'-44.0' does not match '^0*[1-9]+[0-9]*$'"))
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
                        Equals("'x' does not match '^0*[1-9]+[0-9]*$'"))
        self.assertThat(errors[0].path.pop(), Equals('size'))

    def test_validate_resize_volume_zero_number(self):
        body = {"resize": {"volume": {"size": 0}}}
        schema = self.controller.get_schema('action', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertFalse(validator.is_valid(body))
        errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        self.assertThat(errors[0].context[0].message,
                        Equals("0 is less than the minimum of 1"))
        self.assertThat(errors[0].path.pop(), Equals('size'))

    def test_validate_resize_volume_string_zero_number(self):
        body = {"resize": {"volume": {"size": '0'}}}
        schema = self.controller.get_schema('action', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertFalse(validator.is_valid(body))
        errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        self.assertThat(errors[0].context[1].message,
                        Equals("'0' does not match '^0*[1-9]+[0-9]*$'"))
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
                           ["'' should be non-empty",
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
        self.verify_errors(errors, ["'' should be non-empty"], ["flavorRef"])

    def _setup_modify_instance_mocks(self):
        instance = Mock()
        instance.detach_replica = Mock()
        instance.attach_configuration = Mock()
        instance.detach_configuration = Mock()
        instance.update_db = Mock()
        instance.update_access = Mock()
        return instance

    def test_modify_instance_with_empty_args(self):
        instance = self._setup_modify_instance_mocks()
        args = {}

        self.controller._modify_instance(self.context, self.req,
                                         instance, **args)

        self.assertEqual(0, instance.detach_replica.call_count)
        self.assertEqual(0, instance.detach_configuration.call_count)
        self.assertEqual(0, instance.attach_configuration.call_count)
        self.assertEqual(0, instance.update_db.call_count)

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

        self.assertEqual(1, instance.attach_configuration.call_count)

    def test_modify_instance_with_None_configuration_id_arg(self):
        instance = self._setup_modify_instance_mocks()
        args = {}
        args['configuration_id'] = None

        self.controller._modify_instance(self.context, self.req,
                                         instance, **args)

        self.assertEqual(1, instance.detach_configuration.call_count)

    def test_update_api_invalid_field(self):
        body = {
            'instance': {
                'invalid': 'invalid'
            }
        }
        schema = self.controller.get_schema('update', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertFalse(validator.is_valid(body))

    @mock.patch('trove.instance.models.Instance.load')
    def test_update_name(self, load_mock):
        body = {
            'instance': {
                'name': 'new_name'
            }
        }
        ins_mock = MagicMock()
        load_mock.return_value = ins_mock

        self.controller.update(MagicMock(), 'fake_id', body, 'fake_tenant_id')

        ins_mock.update_db.assert_called_once_with(name='new_name')

    def test_update_multiple_operations(self):
        body = {
            'instance': {
                'name': 'new_name',
                'replica_of': None,
                'configuration': 'fake_config_id'
            }
        }

        self.assertRaises(
            exception.BadRequest,
            self.controller.update,
            MagicMock(), 'fake_id', body, 'fake_tenant_id'
        )

    @mock.patch('trove.instance.models.Instance.load')
    def test_update_name_and_access(self, load_mock):
        body = {
            'instance': {
                'name': 'new_name',
                'access': {
                    'is_public': True,
                    'allowed_cidrs': []
                }
            }
        }
        ins_mock = MagicMock()
        load_mock.return_value = ins_mock

        self.controller.update(MagicMock(), 'fake_id', body, 'fake_tenant_id')

        ins_mock.update_db.assert_called_once_with(name='new_name')
        ins_mock.update_access.assert_called_once_with(
            body['instance']['access'])

    @mock.patch('trove.instance.models.Instance.load')
    def test_update_does_not_touch_conf_on_name_or_access(self, load_mock):
        body = {
            'instance': {
                'name': 'new_name',
                'access': {'is_public': True, 'allowed_cidrs': []},
            }
        }

        ins = MagicMock()
        ins.slaves = []
        load_mock.return_value = ins

        self.controller.update(MagicMock(), 'fake_id', body, 'tenant')

        ins.update_db.assert_called_once_with(name='new_name')
        ins.update_access.assert_called_once_with(body['instance']['access'])
        ins.attach_configuration.assert_not_called()
        ins.detach_configuration.assert_not_called()

    @mock.patch('trove.instance.models.Instance.load')
    def test_update_detach_configuration(self, load_mock):
        body = {
            'instance': {
                'configuration': None
            }
        }

        ins = MagicMock()
        ins.slaves = []
        cfg = MagicMock()
        cfg.id = 'old_cfg'
        ins.configuration = cfg

        load_mock.return_value = ins

        self.controller.update(MagicMock(), 'fake_id', body, 'tenant')

        ins.detach_configuration.assert_called_once()
        ins.attach_configuration.assert_not_called()

    @mock.patch('trove.instance.models.Instance.load')
    def test_update_detach_configuration_with_empty_instance(self, load_mock):
        body = {
            'instance': {}
        }

        ins = MagicMock()
        ins.slaves = []
        cfg = MagicMock()
        cfg.id = 'old_cfg'
        ins.configuration = cfg

        load_mock.return_value = ins

        self.controller.update(MagicMock(), 'fake_id', body, 'tenant')

        ins.detach_configuration.assert_called_once()
        ins.attach_configuration.assert_not_called()

    @mock.patch('trove.instance.models.Instance.load')
    @mock.patch(
        'trove.instance.service.InstanceController._configuration_parse')
    def test_update_attach_configuration(self, parse_mock, load_mock):
        body = {
            'instance': {
                'configuration': 'fake_config_id'
            }
        }

        parse_mock.return_value = 'fake_config_id'

        ins = MagicMock()
        ins.slaves = []
        ins.configuration = None
        load_mock.return_value = ins

        self.controller.update(MagicMock(), 'fake_id', body, 'tenant')

        ins.attach_configuration.assert_called_once_with('fake_config_id')
        ins.detach_configuration.assert_not_called()

    @mock.patch('trove.instance.service.clients.create_guest_client')
    @mock.patch('trove.instance.models.Instance.load')
    def test_ssl_show_calls_guest_agent(self, load_mock, guest_client_mock):
        ins_mock = MagicMock()
        ins_mock.tenant_id = 'tenant123'
        ins_mock.db_info.ssl_mode = 'basic'
        load_mock.return_value = ins_mock

        guest_mock = MagicMock()
        guest_client_mock.return_value = guest_mock
        guest_mock.ssl_show.return_value = {
            'status': 'on'}

        req = MagicMock()
        req.environ = {'trove.context': self.context}

        result = self.controller.ssl_show(req, 'fake_tenant', 'fake_id')

        load_mock.assert_called_once_with(self.context, 'fake_id')
        guest_client_mock.assert_called_once_with(self.context, 'fake_id')
        guest_mock.ssl_show.assert_called_once_with()
        self.assertEqual({'ssl': {'status': 'on', 'mode': 'basic'}},
                         result.data('application/json'))

    @mock.patch('trove.common.ssl.TroveSSL.register_consumer')
    @mock.patch('trove.common.ssl.TroveSSL.get_p12_bundle')
    @mock.patch('trove.instance.service.clients.create_guest_client')
    @mock.patch('trove.instance.models.Instance.load')
    def test_ssl_action_calls_guest_agent_enable(
            self, load_mock, guest_client_mock, get_bundle_mock,
            register_consumer_mock):
        ins_mock = MagicMock()
        ins_mock.tenant_id = 'tenant123'
        ins_mock.db_info = MagicMock()
        ins_mock.db_info.ssl_ref = None
        ins_mock.db_info.ssl_mode = None
        ins_mock.slave_of_id = None
        ins_mock.slaves = []
        load_mock.return_value = ins_mock

        guest_mock = MagicMock()
        guest_client_mock.return_value = guest_mock
        guest_mock.ssl_action.return_value = {'status': 'disabled'}

        get_bundle_mock.return_value = {
            'private_key': 'key',
            'certificate': 'cert',
            'ca': 'ca'
        }

        req = MagicMock()
        req.environ = {'trove.context': self.context}

        body = {'ssl': {
            'enable': True,
            'container_ref': 'container_ref'}}
        result = self.controller.ssl_action(req, body,
                                            'fake_tenant', 'fake_id')

        load_mock.assert_called_once_with(self.context, 'fake_id')
        guest_client_mock.assert_called_once_with(self.context, 'fake_id')
        get_bundle_mock.assert_called_once_with('container_ref', None)

        guest_mock.ssl_action.assert_called_once_with(
            'basic',
            get_bundle_mock.return_value,
            True,
            None
        )
        register_consumer_mock.assert_called_once()
        self.assertEqual({'ssl': {'status': 'disabled'}},
                         result.data('application/json'))

    @mock.patch.object(InstanceController, 'authorize_instance_action')
    @mock.patch('trove.instance.service.clients.create_guest_client')
    @mock.patch('trove.instance.models.Instance.load')
    def test_ssl_action_enable_and_disable_raises(
            self, load_mock, guest_client_mock, authorize_mock):
        instance = MagicMock()
        instance.tenant_id = 'tenant123'
        load_mock.return_value = instance

        req = MagicMock()
        req.environ = {'trove.context': self.context}

        body = {'ssl': {'enable': True, 'disable': True}}

        self.assertRaises(
            exception.BadRequest,
            self.controller.ssl_action,
            req, body, 'fake_tenant', 'fake_id'
        )

        load_mock.assert_called_once_with(self.context, 'fake_id')
        guest_client_mock.assert_called_once_with(self.context, 'fake_id')
        authorize_mock.assert_called_once_with(
            self.context, 'update', instance)

    @mock.patch('trove.instance.service.clients.create_guest_client')
    @mock.patch('trove.instance.models.Instance.load')
    def test_ssl_action_against_replica_raises(
            self, load_mock, guest_client_mock):
        ins_mock = MagicMock()
        ins_mock.tenant_id = 'tenant123'
        ins_mock.db_info = MagicMock()
        ins_mock.db_info.ssl_ref = None
        ins_mock.db_info.ssl_mode = None
        ins_mock.slave_of_id = 'tenant234'
        load_mock.return_value = ins_mock

        req = MagicMock()
        req.environ = {'trove.context': self.context}

        body = {'ssl': {
            'enable': True,
            'container_ref': 'container_ref'}}

        self.assertRaises(
            exception.BadRequest,
            self.controller.ssl_action,
            req, body, 'fake_tenant', 'fake_id'
        )

    @mock.patch('trove.instance.service.clients.create_guest_client')
    @mock.patch('trove.instance.models.Instance.load')
    def test_ssl_show_include_certificate_flag(
            self, load_mock, guest_client_mock):
        ins_mock = MagicMock()
        ins_mock.tenant_id = 'tenant123'
        ins_mock.db_info.ssl_mode = 'basic'
        load_mock.return_value = ins_mock

        req = MagicMock()
        req.environ = {'trove.context': self.context}

        test_cases = [
            {
                'name': 'parameter is not set',
                'query': {},
                'expect_payload': False,
            },
            {
                'name': 'include_certificate=1',
                'query': {'include_certificate': '1'},
                'expect_payload': True,
            },
            {
                'name': 'include_certificate=false',
                'query': {'include_certificate': 'false'},
                'expect_payload': False,
            },
            {
                'name': 'include_certificate=true',
                'query': {'include_certificate': 'true'},
                'expect_payload': True,
            },
        ]

        for case in test_cases:
            guest_mock = MagicMock()
            guest_client_mock.return_value = guest_mock

            guest_mock.ssl_show.return_value = {
                'status': 'on',
                'certificate': {
                    'name': 'server-cert',
                    'payload': 'secret-cert-data'
                }
            }

            req.GET = case['query']

            result = self.controller.ssl_show(
                req, 'fake_tenant', 'fake_id')

            expected_certificate = {
                'name': 'server-cert'
            }

            if case['expect_payload']:
                expected_certificate['payload'] = 'secret-cert-data'

            self.assertEqual(
                {'ssl': {
                    'status': 'on',
                    'mode': 'basic',
                    'certificate': expected_certificate
                }},
                result.data('application/json'),
                case['name']
            )

    @mock.patch('trove.common.ssl.TroveSSL.remove_consumer')
    @mock.patch('trove.common.ssl.TroveSSL.register_consumer')
    @mock.patch('trove.common.ssl.TroveSSL.get_p12_bundle')
    @mock.patch('trove.instance.service.clients.create_guest_client')
    @mock.patch('trove.instance.models.Instance.load')
    def test_ssl_action_rolls_back_metadata_on_guest_failure(
            self,
            load_mock,
            guest_client_mock,
            get_bundle_mock,
            register_consumer_mock,
            remove_consumer_mock):

        instance = MagicMock()
        instance.id = 'instance-id'
        instance.slave_of_id = None
        instance.slaves = []
        instance.db_info.ssl_mode = None
        instance.db_info.ssl_ref = None
        load_mock.return_value = instance

        guest = MagicMock()
        guest.ssl_action.side_effect = RuntimeError('guest failure')
        guest_client_mock.return_value = guest

        get_bundle_mock.return_value = 'fake-container'
        register_consumer_mock.return_value = None
        remove_consumer_mock.return_value = None

        req = MagicMock()
        req.environ = {'trove.context': self.context}

        body = {
            'ssl': {
                'enable': True,
                'mode': 'basic',
                'container_ref': 'container-ref'
            }
        }

        # The controller should re-raise the RuntimeError after rollback
        self.assertRaises(
            RuntimeError,
            self.controller.ssl_action,
            req,
            body,
            'tenant-id',
            'instance-id'
        )

        # Verify register_consumer was called before the failure
        register_consumer_mock.assert_called_once_with(
            'container-ref',
            'instance',
            'instance-id'
        )

        # Verify rollback logic: remove_consumer should be called on failure
        remove_consumer_mock.assert_called_once_with(
            'container-ref',
            'instance',
            'instance-id'
        )

        # Verify metadata rollback:
        # The wrapper should have reset these to None after the guest failure
        self.assertIsNone(instance.db_info.ssl_mode)
        self.assertIsNone(instance.db_info.ssl_ref)

        # Verify saves were executed (one for the initial update, one for
        # rollback)
        self.assertGreaterEqual(instance.db_info.save.call_count, 2)

    @mock.patch('trove.common.ssl.TroveSSL.register_consumer')
    @mock.patch('trove.common.ssl.TroveSSL.get_p12_bundle')
    @mock.patch('trove.instance.service.clients.create_guest_client')
    @mock.patch('trove.instance.models.Instance.load')
    def test_ssl_action_success_applies_metadata_and_calls_guest(
            self,
            load_mock,
            guest_client_mock,
            get_bundle_mock,
            register_consumer_mock):

        instance = MagicMock()
        instance.id = 'instance-id'
        instance.slave_of_id = None
        instance.slaves = []

        # Initial DB state (No SSL yet)
        instance.db_info.ssl_mode = None
        instance.db_info.ssl_ref = None

        load_mock.return_value = instance

        guest = MagicMock()
        guest.ssl_action.return_value = {'status': 'enabled'}
        guest_client_mock.return_value = guest

        get_bundle_mock.return_value = 'fake-container'
        # register_consumer returns None by default, simulating success

        # --- 4. Execute Test ---
        req = MagicMock()
        req.environ = {'trove.context': self.context}

        body = {
            'ssl': {
                'enable': True,
                'mode': 'basic',
                'container_ref': 'container-ref'
            }
        }

        result = self.controller.ssl_action(
            req, body, 'tenant-id', 'instance-id'
        )

        # Verify the Guest Agent was called with data from our get_bundle mock
        guest.ssl_action.assert_called_once_with(
            'basic',
            'fake-container',
            True,
            None
        )

        # Verify the wrapper updated the Database state correctly
        self.assertEqual('basic', instance.db_info.ssl_mode)
        self.assertEqual('container-ref', instance.db_info.ssl_ref)

        # Verify Barbican interaction was triggered by the real wrapper
        register_consumer_mock.assert_called_once_with(
            'container-ref',
            'instance',
            'instance-id'
        )

        # Ensure the changes were actually persisted to the DB
        instance.db_info.save.assert_called()

        # Check response structure
        self.assertEqual(
            {'ssl': {'status': 'enabled'}},
            result.data('application/json')
        )

    @mock.patch('trove.instance.service.ssl.run_ssl_state_transaction')
    @mock.patch('trove.common.ssl.TroveSSL.get_p12_bundle')
    @mock.patch('trove.instance.service.clients.create_guest_client')
    @mock.patch('trove.instance.models.Instance.load')
    def test_ssl_action_passes_guest_actions_to_transaction(
            self, load_mock, guest_client_mock, get_bundle_mock,
            transaction_mock):
        instance = MagicMock()
        instance.id = 'instance-id'
        instance.slave_of_id = None
        instance.slaves = [MagicMock(id='replica-id')]

        replica = MagicMock()
        replica.id = 'replica-id'
        load_mock.side_effect = [instance, replica]

        primary_guest = MagicMock()
        replica_guest = MagicMock()
        guest_client_mock.side_effect = [primary_guest, replica_guest]
        primary_guest.ssl_action.return_value = {'status': 'enabled'}
        get_bundle_mock.return_value = 'certificate-bundle'

        guest_calls = MagicMock()
        guest_calls.attach_mock(primary_guest, 'primary')
        guest_calls.attach_mock(replica_guest, 'replica')

        def run_transaction(ssl_client, instances, mode, container_ref,
                            enable, disable, execute, rollback):
            self.assertEqual([instance, replica], instances)
            self.assertEqual('enforced', mode)
            self.assertEqual('container-ref', container_ref)
            self.assertTrue(enable)
            self.assertIsNone(disable)

            result = execute()
            rollback()
            return result

        transaction_mock.side_effect = run_transaction

        req = MagicMock()
        req.environ = {'trove.context': self.context}
        body = {
            'ssl': {
                'enable': True,
                'mode': 'enforced',
                'container_ref': 'container-ref'
            }
        }

        result = self.controller.ssl_action(
            req, body, 'tenant-id', 'instance-id')

        transaction_mock.assert_called_once()
        self.assertEqual(
            [
                mock.call.primary.ssl_action(
                    'enforced', 'certificate-bundle', True, None),
                mock.call.replica.ssl_action(
                    'enforced', 'certificate-bundle', True, None),
                mock.call.replica.ssl_rollback(),
                mock.call.primary.ssl_rollback(),
            ],
            guest_calls.mock_calls
        )
        self.assertEqual(
            {'ssl': {'status': 'enabled'}},
            result.data('application/json')
        )
