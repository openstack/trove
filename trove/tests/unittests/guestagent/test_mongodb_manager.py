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

import trove.common.db.mongodb.models as models
import trove.common.utils as utils
import trove.guestagent.backup as backup
from trove.guestagent.common.configuration import ImportOverrideStrategy
import trove.guestagent.datastore.experimental.mongodb.manager as manager
import trove.guestagent.datastore.experimental.mongodb.service as service
import trove.guestagent.volume as volume
from trove.tests.unittests.guestagent.test_datastore_manager import \
    DatastoreManagerTest


class GuestAgentMongoDBManagerTest(DatastoreManagerTest):

    @mock.patch.object(ImportOverrideStrategy, '_initialize_import_directory')
    def setUp(self, _):
        super(GuestAgentMongoDBManagerTest, self).setUp('mongodb')
        self.manager = manager.Manager()

        self.execute_with_timeout_patch = mock.patch.object(
            utils, 'execute_with_timeout', return_value=('0', '')
        )
        self.addCleanup(self.execute_with_timeout_patch.stop)
        self.execute_with_timeout_patch.start()

        self.pymongo_patch = mock.patch.object(
            pymongo, 'MongoClient'
        )
        self.addCleanup(self.pymongo_patch.stop)
        self.pymongo_patch.start()

        self.mount_point = '/var/lib/mongodb'
        self.host_wildcard = '%'  # This is used in the test_*_user tests below
        self.serialized_user = {
            '_name': 'testdb.testuser', '_password': None,
            '_roles': [{'db': 'testdb', 'role': 'testrole'}],
            '_username': 'testuser', '_databases': [],
            '_host': self.host_wildcard,
            '_database': {'_name': 'testdb',
                          '_character_set': None,
                          '_collate': None},
            '_is_root': False
        }

    def tearDown(self):
        super(GuestAgentMongoDBManagerTest, self).tearDown()

    def test_update_status(self):
        self.manager.app.status = mock.MagicMock()
        self.manager.update_status(self.context)
        self.manager.app.status.update.assert_any_call()

    def _prepare_method(self, packages=['packages'], databases=None,
                        memory_mb='2048', users=None, device_path=None,
                        mount_point=None, backup_info=None,
                        config_contents=None, root_password=None,
                        overrides=None, cluster_config=None,):
        """self.manager.app must be correctly mocked before calling."""

        self.manager.app.status = mock.Mock()

        self.manager.prepare(self.context, packages,
                             databases, memory_mb, users,
                             device_path=device_path,
                             mount_point=mount_point,
                             backup_info=backup_info,
                             config_contents=config_contents,
                             root_password=root_password,
                             overrides=overrides,
                             cluster_config=cluster_config)

        self.manager.app.status.begin_install.assert_any_call()
        self.manager.app.install_if_needed.assert_called_with(packages)
        self.manager.app.stop_db.assert_any_call()
        self.manager.app.clear_storage.assert_any_call()

        (self.manager.app.apply_initial_guestagent_configuration.
         assert_called_once_with(cluster_config, self.mount_point))

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

        mock_secure.assert_called_with()

    @mock.patch.object(backup, 'restore')
    @mock.patch.object(service.MongoDBAdmin, 'is_root_enabled')
    def test_prepare_from_backup(self, mocked_root_check, mocked_restore):
        self.manager.app = mock.Mock()

        backup_info = {'id': 'backup_id_123abc',
                       'location': 'fake-location',
                       'type': 'MongoDBDump',
                       'checksum': 'fake-checksum'}

        self._prepare_method(backup_info=backup_info)

        mocked_restore.assert_called_with(self.context, backup_info,
                                          '/var/lib/mongodb')
        mocked_root_check.assert_any_call()

    def test_prepare_with_databases(self):
        self.manager.app = mock.Mock()

        database = mock.Mock()
        mock_create_databases = mock.Mock()
        self.manager.create_database = mock_create_databases

        self._prepare_method(databases=[database])

        mock_create_databases.assert_called_with(self.context, [database])

    def test_prepare_with_users(self):
        self.manager.app = mock.Mock()

        user = mock.Mock()
        mock_create_users = mock.Mock()
        self.manager.create_user = mock_create_users

        self._prepare_method(users=[user])

        mock_create_users.assert_called_with(self.context, [user])

    @mock.patch.object(service.MongoDBAdmin, 'enable_root')
    def test_provide_root_password(self, mocked_enable_root):
        self.manager.app = mock.Mock()

        self._prepare_method(root_password='test_password')

        mocked_enable_root.assert_called_with('test_password')

    @mock.patch.object(service, 'MongoDBClient')
    @mock.patch.object(service.MongoDBAdmin, '_admin_user')
    @mock.patch.object(service.MongoDBAdmin, '_get_user_record')
    def test_create_user(self, mocked_get_user, mocked_admin_user,
                         mocked_client):
        user = self.serialized_user.copy()
        user['_password'] = 'testpassword'
        users = [user]

        client = mocked_client().__enter__()['testdb']
        mocked_get_user.return_value = None

        self.manager.create_user(self.context, users)

        client.add_user.assert_called_with('testuser', password='testpassword',
                                           roles=[{'db': 'testdb',
                                                   'role': 'testrole'}])

    @mock.patch.object(service, 'MongoDBClient')
    @mock.patch.object(service.MongoDBAdmin, '_admin_user')
    def test_delete_user(self, mocked_admin_user, mocked_client):
        client = mocked_client().__enter__()['testdb']

        self.manager.delete_user(self.context, self.serialized_user)

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
        self.assertEqual(self.serialized_user, result)

    @mock.patch.object(service, 'MongoDBClient')
    @mock.patch.object(service.MongoDBAdmin, '_admin_user')
    def test_list_users(self, mocked_admin_user, mocked_client):
        # roles are NOT returned by list_users
        user1 = self.serialized_user.copy()
        user2 = self.serialized_user.copy()
        user2['_name'] = 'testdb.otheruser'
        user2['_username'] = 'otheruser'
        user2['_roles'] = [{'db': 'testdb2', 'role': 'readWrite'}]
        user2['_databases'] = [{'_name': 'testdb2',
                                '_character_set': None,
                                '_collate': None}]

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
                'roles': [{'db': 'testdb2', 'role': 'readWrite'}]
            }
        ])

        client = mocked_client().__enter__().admin
        client.system.users.find = mocked_find

        users, next_marker = self.manager.list_users(self.context)

        self.assertIsNone(next_marker)
        self.assertEqual(sorted([user1, user2], key=lambda x: x['_name']),
                         users)

    @mock.patch.object(service.MongoDBAdmin, 'create_validated_user')
    @mock.patch.object(utils, 'generate_random_password',
                       return_value='password')
    def test_enable_root(self, mock_gen_rand_pwd, mock_create_user):
        root_user = {'_name': 'admin.root',
                     '_username': 'root',
                     '_database': {'_name': 'admin',
                                   '_character_set': None,
                                   '_collate': None},
                     '_password': 'password',
                     '_roles': [{'db': 'admin', 'role': 'root'}],
                     '_databases': [],
                     '_host': self.host_wildcard,
                     '_is_root': True}

        result = self.manager.enable_root(self.context)

        self.assertTrue(mock_create_user.called)
        self.assertEqual(root_user, result)

    @mock.patch.object(service, 'MongoDBClient')
    @mock.patch.object(service.MongoDBAdmin, '_admin_user')
    @mock.patch.object(service.MongoDBAdmin, '_get_user_record',
                       return_value=models.MongoDBUser('testdb.testuser'))
    def test_grant_access(self, mocked_get_user,
                          mocked_admin_user, mocked_client):
        client = mocked_client().__enter__()['testdb']

        self.manager.grant_access(self.context, 'testdb.testuser',
                                  None, ['db1', 'db2', 'db3'])

        client.add_user.assert_called_with('testuser', roles=[
            {'db': 'db1', 'role': 'readWrite'},
            {'db': 'db2', 'role': 'readWrite'},
            {'db': 'db3', 'role': 'readWrite'}
        ])

    @mock.patch.object(service, 'MongoDBClient')
    @mock.patch.object(service.MongoDBAdmin, '_admin_user')
    @mock.patch.object(service.MongoDBAdmin, '_get_user_record',
                       return_value=models.MongoDBUser('testdb.testuser'))
    def test_revoke_access(self, mocked_get_user,
                           mocked_admin_user, mocked_client):
        client = mocked_client().__enter__()['testdb']

        mocked_get_user.return_value.roles = [
            {'db': 'db1', 'role': 'readWrite'},
            {'db': 'db2', 'role': 'readWrite'},
            {'db': 'db3', 'role': 'readWrite'}
        ]

        self.manager.revoke_access(self.context, 'testdb.testuser',
                                   None, 'db2')

        client.add_user.assert_called_with('testuser', roles=[
            {'db': 'db1', 'role': 'readWrite'},
            {'db': 'db3', 'role': 'readWrite'}
        ])

    @mock.patch.object(service, 'MongoDBClient')
    @mock.patch.object(service.MongoDBAdmin, '_admin_user')
    @mock.patch.object(service.MongoDBAdmin, '_get_user_record',
                       return_value=models.MongoDBUser('testdb.testuser'))
    def test_list_access(self, mocked_get_user,
                         mocked_admin_user, mocked_client):
        mocked_get_user.return_value.roles = [
            {'db': 'db1', 'role': 'readWrite'},
            {'db': 'db2', 'role': 'readWrite'},
            {'db': 'db3', 'role': 'readWrite'}
        ]

        accessible_databases = self.manager.list_access(
            self.context, 'testdb.testuser', None
        )

        self.assertEqual(['db1', 'db2', 'db3'],
                         [db['_name'] for db in accessible_databases])

    @mock.patch.object(service, 'MongoDBClient')
    @mock.patch.object(service.MongoDBAdmin, '_admin_user')
    def test_create_databases(self, mocked_admin_user, mocked_client):
        schema = models.MongoDBSchema('testdb').serialize()
        db_client = mocked_client().__enter__()['testdb']

        self.manager.create_database(self.context, [schema])

        db_client['dummy'].insert.assert_called_with({'dummy': True})
        db_client.drop_collection.assert_called_with('dummy')

    @mock.patch.object(service, 'MongoDBClient')
    @mock.patch.object(service.MongoDBAdmin, '_admin_user')
    def test_list_databases(self,  # mocked_ignored_dbs,
                            mocked_admin_user, mocked_client):
        # This list contains the special 'admin', 'local' and 'config' dbs;
        # the special dbs should be skipped in the output.
        # Pagination is tested by starting at 'db1', so 'db0' should not
        # be in the output. The limit is set to 2, meaning the result
        # should be 'db1' and 'db2'. The next_marker should be 'db3'.
        mocked_list = mock.MagicMock(
            return_value=['admin', 'local', 'config',
                          'db0', 'db1', 'db2', 'db3'])
        mocked_client().__enter__().database_names = mocked_list

        dbs, next_marker = self.manager.list_databases(
            self.context, limit=2, marker='db1', include_marker=True)

        mocked_list.assert_any_call()
        self.assertEqual([models.MongoDBSchema('db1').serialize(),
                          models.MongoDBSchema('db2').serialize()],
                         dbs)
        self.assertEqual('db2', next_marker)

    @mock.patch.object(service, 'MongoDBClient')
    @mock.patch.object(service.MongoDBAdmin, '_admin_user')
    def test_delete_database(self, mocked_admin_user, mocked_client):
        schema = models.MongoDBSchema('testdb').serialize()

        self.manager.delete_database(self.context, schema)

        mocked_client().__enter__().drop_database.assert_called_with('testdb')
