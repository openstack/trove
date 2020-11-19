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
from unittest import mock
from unittest.mock import MagicMock
from unittest.mock import Mock
from unittest.mock import patch

from glanceclient import exc as glance_exceptions
import jsonschema

from trove.common import clients
from trove.common import exception
from trove.configuration import models as config_models
from trove.datastore import models
from trove.extensions.mgmt.datastores.service import DatastoreVersionController
from trove.tests.unittests import trove_testtools
from trove.tests.unittests.util import util


class TestDatastoreVersionController(trove_testtools.TestCase):
    @classmethod
    def setUpClass(cls):
        util.init_db()
        cls.ds_name = cls.random_name('datastore')
        cls.ds_version_number = '5.7.30'
        models.update_datastore(name=cls.ds_name, default_version=None)

        models.update_datastore_version(
            cls.ds_name, 'test_vr1', 'mysql', cls.random_uuid(), '', 'pkg-1',
            1)
        models.update_datastore_version(
            cls.ds_name, 'test_vr2', 'mysql', cls.random_uuid(), '', 'pkg-1',
            1, version=cls.ds_version_number)

        cls.ds = models.Datastore.load(cls.ds_name)
        cls.ds_version1 = models.DatastoreVersion.load(cls.ds, 'test_vr1')
        cls.ds_version2 = models.DatastoreVersion.load(
            cls.ds, 'test_vr2', version=cls.ds_version_number)
        cls.version_controller = DatastoreVersionController()

        super(TestDatastoreVersionController, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        util.cleanup_db()

        super(TestDatastoreVersionController, cls).tearDownClass()

    def test_create_schema(self):
        image_id = self.random_uuid()
        ver_name = self.random_name('dsversion')
        body = {
            "version": {
                "datastore_name": self.ds_name,
                "name": ver_name,
                "datastore_manager": "mysql",
                "image": image_id,
                "image_tags": [],
                "active": True,
                "default": False
            }
        }

        schema = self.version_controller.get_schema('create', body)
        validator = jsonschema.Draft4Validator(schema)

        self.assertTrue(validator.is_valid(body))

    def test_create_schema_too_many_image_tags(self):
        ver_name = self.random_name('dsversion')
        body = {
            "version": {
                "datastore_name": self.ds_name,
                "name": ver_name,
                "datastore_manager": "mysql",
                "image_tags": ['a', 'b', 'c', 'd', 'e', 'f'],
                "active": True,
                "default": False
            }
        }

        schema = self.version_controller.get_schema('create', body)
        validator = jsonschema.Draft4Validator(schema)

        self.assertFalse(validator.is_valid(body))

    def test_create_schema_emptyname(self):
        image_id = self.random_uuid()
        body = {
            "version": {
                "datastore_name": self.ds_name,
                "name": " ",
                "datastore_manager": "mysql",
                "image": image_id,
                "image_tags": [],
                "active": True,
                "default": False
            }
        }
        schema = self.version_controller.get_schema('create', body)
        validator = jsonschema.Draft4Validator(schema)

        self.assertFalse(validator.is_valid(body))

        errors = sorted(validator.iter_errors(body), key=lambda e: e.path)
        self.assertEqual(1, len(errors))
        self.assertEqual("' ' does not match '^.*[0-9a-zA-Z]+.*$'",
                         errors[0].message)

    @patch.object(clients, 'create_glance_client')
    def test_create(self, mock_glance_client):
        image_id = self.random_uuid()
        ver_name = self.random_name('dsversion')
        body = {
            "version": {
                "datastore_name": self.ds_name,
                "name": ver_name,
                "datastore_manager": "mysql",
                "image": image_id,
                "image_tags": [],
                "packages": "test-pkg",
                "active": True,
                "default": True
            }
        }
        output = self.version_controller.create(MagicMock(), body, mock.ANY)
        self.assertEqual(202, output.status)

        new_ver = models.DatastoreVersion.load(self.ds, ver_name)
        self.assertEqual(image_id, new_ver.image_id)
        self.assertEqual(ver_name, new_ver.version)

    @patch.object(clients, 'create_glance_client')
    def test_create_same_version_number(self, mock_glance_client):
        image_id = self.random_uuid()
        ver_name = self.random_name('dsversion')
        body = {
            "version": {
                "datastore_name": self.ds_name,
                "name": ver_name,
                "datastore_manager": "mysql",
                "image": image_id,
                "image_tags": [],
                "packages": "",
                "active": True,
                "default": False,
                "version": self.ds_version_number
            }
        }
        output = self.version_controller.create(MagicMock(), body, mock.ANY)
        self.assertEqual(202, output.status)

        new_ver = models.DatastoreVersion.load(self.ds, ver_name,
                                               version=self.ds_version_number)
        self.assertEqual(image_id, new_ver.image_id)
        self.assertEqual(ver_name, new_ver.name)
        self.assertEqual(self.ds_version_number, new_ver.version)
        self.assertNotEqual(self.ds_version2.id, new_ver.id)

    @patch.object(clients, 'create_glance_client')
    def test_create_by_image_tags(self, mock_create_client):
        ver_name = self.random_name('dsversion')
        body = {
            "version": {
                "datastore_name": self.ds_name,
                "name": ver_name,
                "datastore_manager": "mysql",
                "image_tags": ["trove", "mysql"],
                "active": True,
                "default": True
            }
        }
        mock_client = MagicMock()
        mock_client.images.list.return_value = [{"id": self.random_uuid()}]
        mock_create_client.return_value = mock_client

        output = self.version_controller.create(MagicMock(), body, mock.ANY)
        self.assertEqual(202, output.status)

        mock_client.images.list.assert_called_once_with(
            filters={'tag': ["trove", "mysql"], 'status': 'active'},
            sort='created_at:desc',
            limit=1
        )

        new_ver = models.DatastoreVersion.load(self.ds, ver_name)
        self.assertIsNone(new_ver.image_id)
        self.assertEqual('trove,mysql', new_ver.image_tags)

    @patch.object(clients, 'create_glance_client')
    def test_create_exist(self, mock_glance_client):
        image_id = self.random_uuid()
        ver_name = 'test_vr1'
        body = {
            "version": {
                "datastore_name": self.ds_name,
                "name": ver_name,
                "datastore_manager": "mysql",
                "image": image_id,
                "image_tags": [],
                "packages": "test-pkg",
                "active": True,
                "default": True
            }
        }
        self.assertRaises(
            exception.DatastoreVersionAlreadyExists,
            self.version_controller.create, MagicMock(), body, mock.ANY)

    def test_create_no_image(self):
        ver_name = self.random_name('dsversion')
        body = {
            "version": {
                "datastore_name": self.ds_name,
                "name": ver_name,
                "datastore_manager": "mysql",
                "active": True,
                "default": False
            }
        }
        self.assertRaises(
            exception.BadRequest,
            self.version_controller.create, MagicMock(), body, mock.ANY)

    @patch.object(clients, 'create_glance_client')
    def test_create_image_notfound(self, mock_create_client):
        image_id = self.random_uuid()
        ver_name = self.random_name('dsversion')
        body = {
            "version": {
                "datastore_name": self.ds_name,
                "name": ver_name,
                "datastore_manager": "mysql",
                "image": image_id,
                "active": True,
                "default": False
            }
        }
        mock_client = Mock()
        mock_client.images.get.side_effect = [glance_exceptions.HTTPNotFound()]
        mock_create_client.return_value = mock_client

        self.assertRaises(
            exception.ImageNotFound,
            self.version_controller.create, MagicMock(), body, mock.ANY)

    def test_update_name(self):
        new_name = self.random_name('ds-version-name')
        body = {
            "name": new_name
        }

        orig_ver = models.DatastoreVersion.load(self.ds, self.ds_version1.id)

        output = self.version_controller.edit(MagicMock(), body, mock.ANY,
                                              self.ds_version1.id)
        self.assertEqual(202, output.status)

        updated_ver = models.DatastoreVersion.load(self.ds,
                                                   self.ds_version1.id)

        self.assertEqual(new_name, updated_ver.name)
        self.assertEqual(orig_ver.image_id, updated_ver.image_id)
        self.assertEqual(orig_ver.image_tags, updated_ver.image_tags)
        self.assertEqual(orig_ver.version, updated_ver.version)

    @patch.object(clients, 'create_glance_client')
    def test_update_image(self, mock_create_client):
        new_image = self.random_uuid()
        body = {
            "image": new_image
        }

        output = self.version_controller.edit(MagicMock(), body, mock.ANY,
                                              self.ds_version1.id)
        self.assertEqual(202, output.status)

        updated_ver = models.DatastoreVersion.load(self.ds,
                                                   self.ds_version1.id)
        self.assertEqual(new_image, updated_ver.image_id)

    @patch.object(clients, 'create_glance_client')
    def test_update_image_tags(self, mock_create_client):
        name = self.random_name('dsversion')
        models.update_datastore_version(
            self.ds_name, name, 'mysql', self.random_uuid(), '', '', 1)
        ver = models.DatastoreVersion.load(self.ds, name)

        mock_client = MagicMock()
        mock_client.images.list.return_value = [{"id": self.random_uuid()}]
        mock_create_client.return_value = mock_client

        body = {
            "image_tags": ['trove', 'mysql']
        }

        output = self.version_controller.edit(MagicMock(), body, mock.ANY,
                                              ver.id)
        self.assertEqual(202, output.status)

        updated_ver = models.DatastoreVersion.load(self.ds, ver.id)
        self.assertEqual("", updated_ver.image_id)
        self.assertEqual("trove,mysql", updated_ver.image_tags)

    def test_delete(self):
        name = self.random_name('dsversion')
        models.update_datastore_version(
            self.ds_name, name, 'mysql', self.random_uuid(), '', '', 1)
        ver = models.DatastoreVersion.load(self.ds, name)

        # Add config param for the datastore version. Should be automatically
        # removed.
        param_name = self.random_name('param')
        config_models.create_or_update_datastore_configuration_parameter(
            param_name, ver.id, False, 'string', None, None)

        output = self.version_controller.delete(MagicMock(),
                                                mock.ANY,
                                                ver.id)
        self.assertEqual(202, output.status)

        self.assertRaises(
            exception.DatastoreVersionNotFound,
            models.DatastoreVersion.load_by_uuid, ver.id)

        config_params_cls = config_models.DatastoreConfigurationParameters
        self.assertRaises(
            exception.NotFound,
            config_params_cls.load_parameter_by_name,
            ver.id, param_name)

    def test_index(self):
        output = self.version_controller.index(MagicMock(), mock.ANY)
        self.assertEqual(200, output.status)

        data = output.data(None)
        self.assertGreater(len(data['versions']), 0)

    def test_show(self):
        output = self.version_controller.show(
            MagicMock(), mock.ANY, self.ds_version2.id)
        self.assertEqual(200, output.status)
        self.assertEqual(self.ds_version2.id,
                         output._data['version']['id'])
        self.assertEqual(self.ds_version2.name,
                         output._data['version']['name'])
        self.assertEqual(self.ds_version2.datastore_id,
                         output._data['version']['datastore_id'])
        self.assertEqual(self.ds_version2.datastore_name,
                         output._data['version']['datastore_name'])
        self.assertEqual(self.ds_version2.manager,
                         output._data['version']['datastore_manager'])
        self.assertEqual(self.ds_version2.image_id,
                         output._data['version']['image'])
        self.assertEqual(self.ds_version2.packages.split(','),
                         output._data['version']['packages'])
        self.assertEqual(self.ds_version2.active,
                         output._data['version']['active'])
        self.assertEqual(self.ds_version2.version,
                         output._data['version']['version'])

    def test_show_image_tags(self):
        ver_name = self.random_name('dsversion')
        tags = ['trove', 'mysql']
        models.update_datastore_version(self.ds_name, ver_name, 'mysql', '',
                                        tags, '', 1)
        ver = models.DatastoreVersion.load(self.ds, ver_name)

        output = self.version_controller.show(
            MagicMock(), mock.ANY, ver.id)
        self.assertEqual(200, output.status)

        data = output.data(None)
        self.assertEqual(tags, data['version']['image_tags'])
