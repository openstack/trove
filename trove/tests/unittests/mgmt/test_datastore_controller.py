# Copyright [2015] Hewlett-Packard Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import jsonschema

from mock import Mock, patch, MagicMock, PropertyMock
from testtools.matchers import Is, Equals

from trove.common import clients
from trove.common import exception
from trove.datastore import models as datastore_models
from trove.extensions.mgmt.datastores.service import DatastoreVersionController
from trove.tests.unittests import trove_testtools


class TestDatastoreVersionController(trove_testtools.TestCase):
    def setUp(self):
        super(TestDatastoreVersionController, self).setUp()
        self.controller = DatastoreVersionController()

        self.version = {
            "version": {
                "datastore_name": "test_dsx",
                "name": "test_vr1",
                "datastore_manager": "mysql",
                "image": "154b350d-4d86-4214-9067-9c54b230c0da",
                "packages": ["mysql-server-5.7"],
                "active": True,
                "default": False
            }
        }

        self.tenant_id = Mock()
        context = trove_testtools.TroveTestContext(self)
        self.req = Mock()
        self.req.environ = Mock()
        self.req.environ.__getitem__ = Mock(return_value=context)

    def test_get_schema_create(self):
        schema = self.controller.get_schema('create', self.version)
        self.assertIsNotNone(schema)
        self.assertIn('version', schema['properties'])

    def test_validate_create(self):
        body = self.version
        schema = self.controller.get_schema('create', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertTrue(validator.is_valid(body))

    def test_validate_create_blankname(self):
        body = self.version
        body['version']['name'] = "     "
        schema = self.controller.get_schema('create', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertFalse(validator.is_valid(body))
        errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        self.assertThat(len(errors), Is(1))
        self.assertThat(errors[0].message,
                        Equals("'     ' does not match '^.*[0-9a-zA-Z]+.*$'"))

    def test_validate_create_blank_datastore(self):
        body = self.version
        body['version']['datastore_name'] = ""
        schema = self.controller.get_schema('create', body)
        validator = jsonschema.Draft4Validator(schema)
        self.assertFalse(validator.is_valid(body))
        errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        error_messages = [error.message for error in errors]
        self.assertThat(len(errors), Is(2))
        self.assertIn("'' is too short", error_messages)
        self.assertIn("'' does not match '^.*[0-9a-zA-Z]+.*$'", error_messages)

    @patch.object(clients, 'create_glance_client')
    @patch.object(datastore_models.Datastore, 'load')
    @patch.object(datastore_models.DatastoreVersion, 'load',
                  side_effect=exception.DatastoreVersionNotFound)
    @patch.object(datastore_models, 'update_datastore_version')
    def test_create_datastore_versions(self, mock_ds_version_create,
                                       mock_ds_version_load,
                                       mock_ds_load, mock_glance_client):
        body = self.version
        mock_ds_load.return_value.name = 'test_dsx'

        self.controller.create(self.req, body, self.tenant_id)
        mock_ds_version_create.assert_called_with(
            'test_dsx', 'test_vr1', 'mysql',
            '154b350d-4d86-4214-9067-9c54b230c0da',
            'mysql-server-5.7', True)

    @patch.object(datastore_models.DatastoreVersion, 'load_by_uuid')
    def test_show_ds_version(self, mock_ds_version_load):
        id = Mock()

        self.controller.show(self.req, self.tenant_id, id)
        mock_ds_version_load.assert_called_with(id)

    @patch('trove.configuration.models.DBConfiguration.find_all')
    @patch('trove.backup.models.DBBackup.find_all')
    @patch('trove.instance.models.DBInstance.find_all')
    @patch.object(datastore_models.Datastore, 'load')
    @patch.object(datastore_models.DatastoreVersion, 'load_by_uuid')
    def test_delete_ds_version(self, mock_ds_version_load, mock_ds_load,
                               mock_instance_find, mock_backup_find,
                               mock_config_find):
        ds_version_id = Mock()
        ds_version = Mock()
        mock_ds_version_load.return_value = ds_version
        self.controller.delete(self.req, self.tenant_id, ds_version_id)
        ds_version.delete.assert_called_with()

    @patch('trove.instance.models.DBInstance.find_all')
    def test_delete_ds_version_instance_in_use(self, mock_instance_find):
        mock_instance_find.return_value.all.return_value = [Mock()]

        self.assertRaises(
            exception.DatastoreVersionsInUse,
            self.controller.delete,
            self.req, self.tenant_id, 'fake_version_id'
        )

    @patch('trove.backup.models.DBBackup.find_all')
    @patch('trove.instance.models.DBInstance.find_all')
    def test_delete_ds_version_backup_in_use(self, mock_instance_find,
                                             mock_backup_find):
        mock_backup_find.return_value.all.return_value = [Mock()]

        self.assertRaises(
            exception.DatastoreVersionsInUse,
            self.controller.delete,
            self.req, self.tenant_id, 'fake_version_id'
        )

    @patch('trove.configuration.models.DBConfiguration.find_all')
    @patch('trove.backup.models.DBBackup.find_all')
    @patch('trove.instance.models.DBInstance.find_all')
    def test_delete_ds_version_config_in_use(self, mock_instance_find,
                                             mock_backup_find,
                                             mock_config_find):
        mock_config_find.return_value.all.return_value = [Mock()]

        self.assertRaises(
            exception.DatastoreVersionsInUse,
            self.controller.delete,
            self.req, self.tenant_id, 'fake_version_id'
        )

    @patch.object(datastore_models.DatastoreVersion, 'load_by_uuid')
    @patch.object(datastore_models.DatastoreVersions, 'load_all')
    def test_index_ds_version(self, mock_ds_version_load_all,
                              mock_ds_version_load_by_uuid):
        mock_id = Mock()
        mock_ds_version = Mock()
        mock_ds_version.id = mock_id
        mock_ds_version_load_all.return_value = [mock_ds_version]

        self.controller.index(self.req, self.tenant_id)
        mock_ds_version_load_all.assert_called_with(only_active=False)
        mock_ds_version_load_by_uuid.assert_called_with(mock_id)

    @patch.object(clients, 'create_glance_client')
    @patch.object(datastore_models.DatastoreVersion, 'load_by_uuid')
    @patch.object(datastore_models, 'update_datastore_version')
    def test_edit_datastore_versions(self, mock_ds_version_update,
                                     mock_ds_version_load,
                                     mock_glance_client):
        body = {'image': '21c8805a-a800-4bca-a192-3a5a2519044d'}

        mock_ds_version = MagicMock()
        type(mock_ds_version).datastore_name = PropertyMock(
            return_value=self.version['version']['datastore_name'])
        type(mock_ds_version).name = PropertyMock(
            return_value=self.version['version']['name'])
        type(mock_ds_version).image_id = PropertyMock(
            return_value=self.version['version']['image'])
        type(mock_ds_version).packages = PropertyMock(
            return_value=self.version['version']['packages'])
        type(mock_ds_version).active = PropertyMock(
            return_value=self.version['version']['active'])
        type(mock_ds_version).manager = PropertyMock(
            return_value=self.version['version']['datastore_manager'])
        mock_ds_version_load.return_value = mock_ds_version

        self.controller.edit(self.req, body, self.tenant_id, Mock())
        mock_ds_version_update.assert_called_with(
            'test_dsx', 'test_vr1', 'mysql',
            '21c8805a-a800-4bca-a192-3a5a2519044d',
            'mysql-server-5.7', True)
