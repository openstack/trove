#    Copyright 2012 OpenStack Foundation
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

import mock
import pymongo

import trove.common.context as context
import trove.common.utils as utils
import trove.guestagent.backup as backup
import trove.guestagent.datastore.experimental.mongodb.manager as manager
import trove.guestagent.datastore.experimental.mongodb.service as service
import trove.guestagent.volume as volume
import trove.tests.unittests.trove_testtools as trove_testtools


class GuestAgentMongoDBManagerTest(trove_testtools.TestCase):

    def setUp(self):
        super(GuestAgentMongoDBManagerTest, self).setUp()
        self.context = context.TroveContext()
        self.manager = manager.Manager()

        self.execute_with_timeout_patch = mock.patch.object(
            utils, 'execute_with_timeout'
        )
        self.addCleanup(self.execute_with_timeout_patch.stop)
        self.execute_with_timeout_patch.start()

        self.pymongo_patch = mock.patch.object(
            pymongo, 'MongoClient'
        )
        self.addCleanup(self.pymongo_patch.stop)
        self.pymongo_patch.start()

        self.mount_point = '/var/lib/mongodb'

    def tearDown(self):
        super(GuestAgentMongoDBManagerTest, self).tearDown()

    def test_update_status(self):
        with mock.patch.object(self.manager, 'status') as status:
            self.manager.update_status(self.context)
            status.update.assert_any_call()

    def _prepare_method(self, databases=None, users=None, device_path=None,
                        mount_point=None, backup_info=None,
                        cluster_config=None, overrides=None, memory_mb='2048',
                        packages=['packages']):
        """self.manager.app must be correctly mocked before calling."""

        self.manager.status = mock.Mock()
        self.manager.get_config_changes = mock.Mock()

        self.manager.prepare(self.context, packages,
                             databases, memory_mb, users,
                             device_path=device_path,
                             mount_point=mount_point,
                             backup_info=backup_info,
                             overrides=overrides,
                             cluster_config=cluster_config)

        self.manager.status.begin_install.assert_any_call()
        self.manager.app.install_if_needed.assert_called_with(packages)
        self.manager.app.stop_db.assert_any_call()
        self.manager.app.clear_storage.assert_any_call()
        self.manager.get_config_changes.assert_called_with(cluster_config,
                                                           self.mount_point)

    @mock.patch.object(volume, 'VolumeDevice')
    @mock.patch('os.path.exists')
    def test_prepare_for_volume(self, exists, mocked_volume):
        device_path = '/dev/vdb'

        self.manager.app = mock.Mock()

        self._prepare_method(device_path=device_path)

        mocked_volume().unmount_device.assert_called_with(device_path)
        mocked_volume().format.assert_any_call()
        mocked_volume().migrate_data.assert_called_with(self.mount_point)
        mocked_volume().mount.assert_called_with(self.mount_point)

    def test_secure(self):
        self.manager.app = mock.Mock()

        mock_secure = mock.Mock()
        self.manager.app.secure = mock_secure

        self._prepare_method()

        mock_secure.assert_called_with(None)

    @mock.patch.object(backup, 'restore')
    def test_prepare_from_backup(self, mocked_restore):
        self.manager.app = mock.Mock()

        backup_info = {'id': 'backup_id_123abc',
                       'location': 'fake-location',
                       'type': 'MongoDBDump',
                       'checksum': 'fake-checksum'}

        self._prepare_method(backup_info=backup_info)

        mocked_restore.assert_called_with(self.context, backup_info,
                                          '/var/lib/mongodb')

    # This is used in the test_*_user tests below
    _serialized_user = {'_name': 'testdb.testuser', '_password': None,
                        '_roles': [{'db': 'testdb', 'role': 'testrole'}],
                        '_username': 'testuser', '_databases': [],
                        '_host': None,
                        '_database': {'_name': 'testdb',
                                      '_character_set': None,
                                      '_collate': None}}

    @mock.patch.object(service, 'MongoDBClient')
    @mock.patch.object(service.MongoDBAdmin, '_admin_user')
    def test_create_user(self, mocked_admin_user, mocked_client):
        user = self._serialized_user.copy()
        user['_password'] = 'testpassword'
        users = [user]

        client = mocked_client().__enter__()['testdb']

        self.manager.create_user(self.context, users)

        client.add_user.assert_called_with('testuser', password='testpassword',
                                           roles=[{'db': 'testdb',
                                                   'role': 'testrole'}])

    @mock.patch.object(service, 'MongoDBClient')
    @mock.patch.object(service.MongoDBAdmin, '_admin_user')
    def test_delete_user(self, mocked_admin_user, mocked_client):
        client = mocked_client().__enter__()['testdb']

        self.manager.delete_user(self.context, self._serialized_user)

        client.remove_user.assert_called_with('testuser')

    @mock.patch.object(service, 'MongoDBClient')
    @mock.patch.object(service.MongoDBAdmin, '_admin_user')
    def test_get_user(self, mocked_admin_user, mocked_client):
        mocked_find = mock.MagicMock(return_value={
            '_id': 'testdb.testuser',
            'user': 'testuser', 'db': 'testdb',
            'roles': [{'db': 'testdb', 'role': 'testrole'}]
        })
        client = mocked_client().__enter__().admin
        client.system.users.find_one = mocked_find

        result = self.manager.get_user(self.context, 'testdb.testuser', None)

        mocked_find.assert_called_with({'user': 'testuser', 'db': 'testdb'})
        self.assertEqual(self._serialized_user, result)

    @mock.patch.object(service, 'MongoDBClient')
    @mock.patch.object(service.MongoDBAdmin, '_admin_user')
    def test_list_users(self, mocked_admin_user, mocked_client):
        # roles are NOT returned by list_users
        user1 = self._serialized_user.copy()
        user1['_roles'] = []
        user2 = self._serialized_user.copy()
        user2['_name'] = 'testdb.otheruser'
        user2['_username'] = 'otheruser'
        user2['_roles'] = []

        mocked_find = mock.MagicMock(return_value=[
            {
                '_id': 'admin.os_admin',
                'user': 'os_admin', 'db': 'admin',
                'roles': [{'db': 'admin', 'role': 'root'}]
            },
            {
                '_id': 'testdb.testuser',
                'user': 'testuser', 'db': 'testdb',
                'roles': [{'db': 'testdb', 'role': 'testrole'}]
            },
            {
                '_id': 'testdb.otheruser',
                'user': 'otheruser', 'db': 'testdb',
                'roles': []
            }
        ])

        client = mocked_client().__enter__().admin
        client.system.users.find = mocked_find

        users, next_marker = self.manager.list_users(self.context)

        self.assertEqual(None, next_marker)
        self.assertEqual(sorted([user1, user2]), users)
