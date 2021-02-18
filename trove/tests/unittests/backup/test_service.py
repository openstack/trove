# Copyright 2021 Catalyst Cloud
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.
from unittest import mock

from trove.backup import service
from trove.backup.state import BackupState
from trove.common import context
from trove.common import wsgi
from trove.datastore import models as ds_models
from trove.tests.unittests import trove_testtools
from trove.tests.unittests.util import util


class TestBackupController(trove_testtools.TestCase):
    @classmethod
    def setUpClass(cls):
        util.init_db()

        cls.ds_name = cls.random_name('datastore',
                                      prefix='TestBackupController')
        ds_models.update_datastore(name=cls.ds_name, default_version=None)
        cls.ds = ds_models.Datastore.load(cls.ds_name)

        ds_models.update_datastore_version(
            cls.ds_name, 'fake-ds-version', 'mysql', '', ['trove', 'mysql'],
            '', 1)
        cls.ds_version = ds_models.DatastoreVersion.load(
            cls.ds, 'fake-ds-version')

        cls.controller = service.BackupController()

        super(TestBackupController, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        util.cleanup_db()
        super(TestBackupController, cls).tearDownClass()

    def setUp(self):
        trove_testtools.patch_notifier(self)
        self.context = context.TroveContext(project_id=self.random_uuid())

        super(TestBackupController, self).setUp()

    @mock.patch('trove.common.clients.create_swift_client')
    def test_create_restore_from(self, mock_swift_client):
        swift_client = mock.MagicMock()
        swift_client.head_object.return_value = {'etag': 'fake-etag'}
        mock_swift_client.return_value = swift_client

        req = mock.MagicMock(environ={wsgi.CONTEXT_KEY: self.context})

        name = self.random_name(
            name='backup', prefix='TestBackupController')
        body = {
            'backup': {
                "name": name,
                "restore_from": {
                    "remote_location": "http://192.168.206.8:8080/v1/"
                                       "AUTH_055b2fb9a2264ae5a5f6b3cc066c4a1d/"
                                       "fake-container/fake-object",
                    "local_datastore_version_id": self.ds_version.id,
                    "size": 0.2
                }
            }
        }
        ret = self.controller.create(req, body, self.context.project_id)
        self.assertEqual(202, ret.status)

        ret_backup = ret.data(None)['backup']

        self.assertEqual(BackupState.RESTORED, ret_backup.get('status'))
        self.assertEqual(name, ret_backup.get('name'))
