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

from mock import Mock, patch
from glanceclient import exc as glance_exceptions

from trove.common import exception
from trove.common import glance_remote
from trove.datastore import models
from trove.extensions.mgmt.datastores.service import DatastoreVersionController
from trove.tests.unittests import trove_testtools
from trove.tests.unittests.util import util


class TestDatastoreVersion(trove_testtools.TestCase):

    def setUp(self):
        super(TestDatastoreVersion, self).setUp()
        util.init_db()
        models.update_datastore(name='test_ds', default_version=None)
        models.update_datastore_version(
            'test_ds', 'test_vr1', 'mysql',
            '154b350d-4d86-4214-9067-9c54b230c0da', 'pkg-1', 1)
        models.update_datastore_version(
            'test_ds', 'test_vr2', 'mysql',
            '154b350d-4d86-4214-9067-9c54b230c0da', 'pkg-1', 1)
        self.ds = models.Datastore.load('test_ds')
        self.ds_version2 = models.DatastoreVersion.load(self.ds, 'test_vr2')

        self.context = trove_testtools.TroveTestContext(self)
        self.req = Mock()
        self.req.environ = Mock()
        self.req.environ.__getitem__ = Mock(return_value=self.context)
        self.tenant_id = Mock()
        self.version_controller = DatastoreVersionController()

    def tearDown(self):
        super(TestDatastoreVersion, self).tearDown()

    @patch.object(glance_remote, 'create_glance_client')
    def test_version_create(self, mock_glance_client):
        body = {"version": {
            "datastore_name": "test_ds",
            "name": "test_version",
            "datastore_manager": "mysql",
            "image": "image-id",
            "packages": "test-pkg",
            "active": True,
            "default": True}}
        output = self.version_controller.create(
            self.req, body, self.tenant_id)
        self.assertEqual(202, output.status)

    @patch.object(glance_remote, 'create_glance_client')
    @patch.object(models.DatastoreVersion, 'load')
    def test_fail_already_exists_version_create(self, mock_load,
                                                mock_glance_client):
        body = {"version": {
            "datastore_name": "test_ds",
            "name": "test_new_vr",
            "datastore_manager": "mysql",
            "image": "image-id",
            "packages": "test-pkg",
            "active": True,
            "default": True}}
        self.assertRaisesRegex(
            exception.DatastoreVersionAlreadyExists,
            "A datastore version with the name 'test_new_vr' already exists",
            self.version_controller.create, self.req, body, self.tenant_id)

    @patch.object(glance_remote, 'create_glance_client')
    def test_fail_image_not_found_version_create(self, mock_glance_client):
        mock_glance_client.return_value.images.get = Mock(
            side_effect=glance_exceptions.HTTPNotFound())
        body = {"version": {
            "datastore_name": "test_ds",
            "name": "test_vr",
            "datastore_manager": "mysql",
            "image": "image-id",
            "packages": "test-pkg",
            "active": True,
            "default": True}}
        self.assertRaisesRegex(
            exception.ImageNotFound,
            "Image image-id cannot be found.",
            self.version_controller.create, self.req, body, self.tenant_id)

    def test_version_delete(self):
        ds_version1 = models.DatastoreVersion.load(self.ds, 'test_vr1')

        output = self.version_controller.delete(self.req,
                                                self.tenant_id,
                                                ds_version1.id)
        err_msg = ("Datastore version '%s' cannot be found." %
                   ds_version1.id)

        self.assertEqual(202, output.status)

        # Try to find deleted version, this should raise exception.
        self.assertRaisesRegex(
            exception.DatastoreVersionNotFound,
            err_msg, models.DatastoreVersion.load_by_uuid, ds_version1.id)

    @patch.object(glance_remote, 'create_glance_client')
    def test_version_update(self, mock_client):
        body = {"image": "c022f4dc-76ed-4e3f-a25e-33e031f43f8b"}
        output = self.version_controller.edit(self.req, body,
                                              self.tenant_id,
                                              self.ds_version2.id)
        self.assertEqual(202, output.status)

        # Find the details of version updated and match the updated attribute.
        test_ds_version = models.DatastoreVersion.load_by_uuid(
            self.ds_version2.id)
        self.assertEqual(body['image'], test_ds_version.image_id)

    @patch.object(glance_remote, 'create_glance_client')
    def test_version_update_fail_image_not_found(self, mock_glance_client):
        mock_glance_client.return_value.images.get = Mock(
            side_effect=glance_exceptions.HTTPNotFound())
        body = {"image": "non-existent-image-id"}

        self.assertRaisesRegex(
            exception.ImageNotFound,
            "Image non-existent-image-id cannot be found.",
            self.version_controller.edit, self.req, body,
            self.tenant_id, self.ds_version2.id)

    @patch.object(models.DatastoreVersion, 'load_by_uuid')
    def test_version_index(self, mock_load):
        output = self.version_controller.index(
            self.req, self.tenant_id)
        self.assertEqual(200, output.status)

    def test_version_show(self):
        output = self.version_controller.show(
            self.req, self.tenant_id, self.ds_version2.id)
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
