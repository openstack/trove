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

import os
import random
import string

from mock import ANY
from mock import call
from mock import DEFAULT
from mock import MagicMock
from mock import Mock
from mock import NonCallableMagicMock
from mock import patch
from oslo_utils import netutils
from testtools import ExpectedException

from trove.common import exception
from trove.common.instance import ServiceStatuses
from trove.guestagent import backup
from trove.guestagent.common.configuration import ImportOverrideStrategy
from trove.guestagent.common import operating_system
from trove.guestagent.datastore.experimental.cassandra import (
    manager as cass_manager)
from trove.guestagent.datastore.experimental.cassandra import (
    service as cass_service)
from trove.guestagent.db import models
from trove.guestagent import pkg as pkg
from trove.guestagent import volume
from trove.tests.unittests import trove_testtools


class GuestAgentCassandraDBManagerTest(trove_testtools.TestCase):

    __MOUNT_POINT = '/var/lib/cassandra'

    __N_GAK = '_get_available_keyspaces'
    __N_GLU = '_get_listed_users'
    __N_BU = '_build_user'
    __N_RU = '_rename_user'
    __N_AUP = '_alter_user_password'
    __N_CAU = 'trove.guestagent.db.models.CassandraUser'
    __N_CU = '_create_user'
    __N_GFA = '_grant_full_access_on_keyspace'
    __N_DU = '_drop_user'

    __ACCESS_MODIFIERS = ('ALTER', 'CREATE', 'DROP', 'MODIFY', 'SELECT')
    __CREATE_DB_FORMAT = (
        "CREATE KEYSPACE \"{}\" WITH REPLICATION = "
        "{{ 'class' : 'SimpleStrategy', 'replication_factor' : 1 }};"
    )
    __DROP_DB_FORMAT = "DROP KEYSPACE \"{}\";"
    __CREATE_USR_FORMAT = "CREATE USER '{}' WITH PASSWORD %s NOSUPERUSER;"
    __ALTER_USR_FORMAT = "ALTER USER '{}' WITH PASSWORD %s;"
    __DROP_USR_FORMAT = "DROP USER '{}';"
    __GRANT_FORMAT = "GRANT {} ON KEYSPACE \"{}\" TO '{}';"
    __REVOKE_FORMAT = "REVOKE ALL PERMISSIONS ON KEYSPACE \"{}\" FROM '{}';"
    __LIST_PERMISSIONS_FORMAT = "LIST ALL PERMISSIONS NORECURSIVE;"
    __LIST_PERMISSIONS_OF_FORMAT = "LIST ALL PERMISSIONS OF '{}' NORECURSIVE;"
    __LIST_DB_FORMAT = "SELECT * FROM system.schema_keyspaces;"
    __LIST_USR_FORMAT = "LIST USERS;"

    @patch.object(ImportOverrideStrategy, '_initialize_import_directory')
    @patch('trove.guestagent.datastore.experimental.cassandra.service.LOG')
    def setUp(self, *args, **kwargs):
        super(GuestAgentCassandraDBManagerTest, self).setUp()
        self.real_status = cass_service.CassandraAppStatus.set_status

        class FakeInstanceServiceStatus(object):
            status = ServiceStatuses.NEW

            def save(self):
                pass

        cass_service.CassandraAppStatus.set_status = MagicMock(
            return_value=FakeInstanceServiceStatus())
        self.context = trove_testtools.TroveTestContext(self)
        self.manager = cass_manager.Manager()
        self.manager._Manager__admin = cass_service.CassandraAdmin(
            models.CassandraUser('Test'))
        self.admin = self.manager._Manager__admin
        self.pkg = cass_service.packager
        self.origin_os_path_exists = os.path.exists
        self.origin_format = volume.VolumeDevice.format
        self.origin_migrate_data = volume.VolumeDevice.migrate_data
        self.origin_mount = volume.VolumeDevice.mount
        self.origin_mount_points = volume.VolumeDevice.mount_points
        self.origin_stop_db = cass_service.CassandraApp.stop_db
        self.origin_start_db = cass_service.CassandraApp.start_db
        self.origin_install_db = cass_service.CassandraApp._install_db
        self.original_get_ip = netutils.get_my_ipv4
        self.orig_make_host_reachable = (
            cass_service.CassandraApp.apply_initial_guestagent_configuration)

    def tearDown(self):
        super(GuestAgentCassandraDBManagerTest, self).tearDown()
        cass_service.packager = self.pkg
        os.path.exists = self.origin_os_path_exists
        volume.VolumeDevice.format = self.origin_format
        volume.VolumeDevice.migrate_data = self.origin_migrate_data
        volume.VolumeDevice.mount = self.origin_mount
        volume.VolumeDevice.mount_points = self.origin_mount_points
        cass_service.CassandraApp.stop_db = self.origin_stop_db
        cass_service.CassandraApp.start_db = self.origin_start_db
        cass_service.CassandraApp._install_db = self.origin_install_db
        netutils.get_my_ipv4 = self.original_get_ip
        cass_service.CassandraApp.apply_initial_guestagent_configuration = (
            self.orig_make_host_reachable)
        cass_service.CassandraAppStatus.set_status = self.real_status

    def test_update_status(self):
        mock_status = MagicMock()
        self.manager.app.status = mock_status
        self.manager.update_status(self.context)
        mock_status.update.assert_any_call()

    def test_prepare_pkg(self):
        self._prepare_dynamic(['cassandra'])

    def test_prepare_no_pkg(self):
        self._prepare_dynamic([])

    def test_prepare_db_not_installed(self):
        self._prepare_dynamic([], is_db_installed=False)

    def test_prepare_db_not_installed_no_package(self):
        self._prepare_dynamic([],
                              is_db_installed=True)

    @patch.object(backup, 'restore')
    def test_prepare_db_restore(self, restore):
        backup_info = {'id': 'backup_id',
                       'instance_id': 'fake-instance-id',
                       'location': 'fake-location',
                       'type': 'InnoBackupEx',
                       'checksum': 'fake-checksum'}

        self._prepare_dynamic(['cassandra'], is_db_installed=False,
                              backup_info=backup_info)
        restore.assert_called_once_with(
            self.context, backup_info, self.__MOUNT_POINT)

    @patch.multiple(operating_system, enable_service_on_boot=DEFAULT,
                    disable_service_on_boot=DEFAULT)
    @patch('trove.guestagent.datastore.experimental.cassandra.service.LOG')
    def test_superuser_password_reset(
            self, _, enable_service_on_boot, disable_service_on_boot):
        fake_status = MagicMock()
        fake_status.is_running = False

        test_app = cass_service.CassandraApp()
        test_app.status = fake_status
        with patch.multiple(
                test_app,
                start_db=DEFAULT,
                stop_db=DEFAULT,
                restart=DEFAULT,
                _CassandraApp__disable_remote_access=DEFAULT,
                _CassandraApp__enable_remote_access=DEFAULT,
                _CassandraApp__disable_authentication=DEFAULT,
                _CassandraApp__enable_authentication=DEFAULT,
                _CassandraApp__reset_user_password_to_default=DEFAULT,
                secure=DEFAULT) as calls:

            test_app._reset_admin_password()

            disable_service_on_boot.assert_called_once_with(
                test_app.service_candidates)
            calls[
                '_CassandraApp__disable_remote_access'
            ].assert_called_once_with()
            calls[
                '_CassandraApp__disable_authentication'
            ].assert_called_once_with()
            calls['start_db'].assert_called_once_with(update_db=False,
                                                      enable_on_boot=False),
            calls[
                '_CassandraApp__enable_authentication'
            ].assert_called_once_with()

            pw_reset_mock = calls[
                '_CassandraApp__reset_user_password_to_default'
            ]
            pw_reset_mock.assert_called_once_with(test_app._ADMIN_USER)
            calls['secure'].assert_called_once_with(
                update_user=pw_reset_mock.return_value)
            calls['restart'].assert_called_once_with()
            calls['stop_db'].assert_called_once_with()
            calls[
                '_CassandraApp__enable_remote_access'
            ].assert_called_once_with()
            enable_service_on_boot.assert_called_once_with(
                test_app.service_candidates)

    @patch('trove.guestagent.datastore.experimental.cassandra.service.LOG')
    def test_change_cluster_name(self, _):
        fake_status = MagicMock()
        fake_status.is_running = True

        test_app = cass_service.CassandraApp()
        test_app.status = fake_status
        with patch.multiple(
                test_app,
                start_db=DEFAULT,
                stop_db=DEFAULT,
                restart=DEFAULT,
                _update_cluster_name_property=DEFAULT,
                _CassandraApp__reset_cluster_name=DEFAULT) as calls:

            sample_name = NonCallableMagicMock()
            test_app.change_cluster_name(sample_name)
            calls['_CassandraApp__reset_cluster_name'].assert_called_once_with(
                sample_name)
            calls['_update_cluster_name_property'].assert_called_once_with(
                sample_name)
            calls['restart'].assert_called_once_with()

    @patch.object(cass_service, 'CONF', DEFAULT)
    @patch('trove.guestagent.datastore.experimental.cassandra.service.LOG')
    def test_apply_post_restore_updates(self, _, conf_mock):
        fake_status = MagicMock()
        fake_status.is_running = False

        test_app = cass_service.CassandraApp()
        test_app.status = fake_status
        with patch.multiple(
                test_app,
                start_db=DEFAULT,
                stop_db=DEFAULT,
                _update_cluster_name_property=DEFAULT,
                _reset_admin_password=DEFAULT,
                change_cluster_name=DEFAULT) as calls:
            backup_info = {'instance_id': 'old_id'}
            conf_mock.guest_id = 'new_id'
            test_app._apply_post_restore_updates(backup_info)
            calls['_update_cluster_name_property'].assert_called_once_with(
                'old_id')
            calls['_reset_admin_password'].assert_called_once_with()
            calls['start_db'].assert_called_once_with(update_db=False)
            calls['change_cluster_name'].assert_called_once_with('new_id')
            calls['stop_db'].assert_called_once_with()

    def _prepare_dynamic(self, packages,
                         config_content='MockContent', device_path='/dev/vdb',
                         is_db_installed=True, backup_info=None,
                         is_root_enabled=False,
                         overrides=None):

        mock_status = MagicMock()
        mock_app = MagicMock()
        mock_app.status = mock_status
        self.manager._app = mock_app

        mock_status.begin_install = MagicMock(return_value=None)
        mock_app.install_if_needed = MagicMock(return_value=None)
        mock_app.init_storage_structure = MagicMock(return_value=None)
        mock_app.write_config = MagicMock(return_value=None)
        mock_app.apply_initial_guestagent_configuration = MagicMock(
            return_value=None)
        mock_app.restart = MagicMock(return_value=None)
        mock_app.start_db = MagicMock(return_value=None)
        mock_app.stop_db = MagicMock(return_value=None)
        mock_app._remove_system_tables = MagicMock(return_value=None)
        os.path.exists = MagicMock(return_value=True)
        volume.VolumeDevice.format = MagicMock(return_value=None)
        volume.VolumeDevice.migrate_data = MagicMock(return_value=None)
        volume.VolumeDevice.mount = MagicMock(return_value=None)
        volume.VolumeDevice.mount_points = MagicMock(return_value=[])

        with patch.object(pkg.Package, 'pkg_is_installed',
                          return_value=is_db_installed):
            # invocation
            self.manager.prepare(context=self.context, packages=packages,
                                 config_contents=config_content,
                                 databases=None,
                                 memory_mb='2048', users=None,
                                 device_path=device_path,
                                 mount_point=self.__MOUNT_POINT,
                                 backup_info=backup_info,
                                 overrides=None,
                                 cluster_config=None)

        # verification/assertion
        mock_status.begin_install.assert_any_call()
        mock_app.install_if_needed.assert_any_call(packages)
        mock_app._remove_system_tables.assert_any_call()
        mock_app.init_storage_structure.assert_any_call('/var/lib/cassandra')
        mock_app.apply_initial_guestagent_configuration.assert_any_call(
            cluster_name=None)
        mock_app.start_db.assert_any_call(update_db=False)
        mock_app.stop_db.assert_any_call()
        if backup_info:
            mock_app._apply_post_restore_updates.assert_called_once_with(
                backup_info)

    def test_keyspace_validation(self):
        valid_name = self._get_random_name(32)
        db = models.CassandraSchema(valid_name)
        self.assertEqual(valid_name, db.name)
        with ExpectedException(ValueError):
            models.CassandraSchema(self._get_random_name(33))

    def test_user_validation(self):
        valid_name = self._get_random_name(65535)
        usr = models.CassandraUser(valid_name, 'password')
        self.assertEqual(valid_name, usr.name)
        self.assertEqual('password', usr.password)
        with ExpectedException(ValueError):
            models.CassandraUser(self._get_random_name(65536))

    @classmethod
    def _serialize_collection(self, *collection):
        return [item.serialize() for item in collection]

    @classmethod
    def _get_random_name(self, size, chars=string.letters + string.digits):
        return ''.join(random.choice(chars) for _ in range(size))

    @patch.object(cass_service.CassandraLocalhostConnection, '__enter__')
    def test_create_database(self, conn):
        db1 = models.CassandraSchema('db1')
        db2 = models.CassandraSchema('db2')
        db3 = models.CassandraSchema(self._get_random_name(32))

        self.manager.create_database(self.context,
                                     self._serialize_collection(db1, db2, db3))
        conn.return_value.execute.assert_has_calls([
            call(self.__CREATE_DB_FORMAT, (db1.name,)),
            call(self.__CREATE_DB_FORMAT, (db2.name,)),
            call(self.__CREATE_DB_FORMAT, (db3.name,))
        ])

    @patch.object(cass_service.CassandraLocalhostConnection, '__enter__')
    def test_delete_database(self, conn):
        db = models.CassandraSchema(self._get_random_name(32))
        self.manager.delete_database(self.context, db.serialize())
        conn.return_value.execute.assert_called_once_with(
            self.__DROP_DB_FORMAT, (db.name,))

    @patch.object(cass_service.CassandraLocalhostConnection, '__enter__')
    def test_create_user(self, conn):
        usr1 = models.CassandraUser('usr1')
        usr2 = models.CassandraUser('usr2', '')
        usr3 = models.CassandraUser(self._get_random_name(1025), 'password')

        self.manager.create_user(self.context,
                                 self._serialize_collection(usr1, usr2, usr3))
        conn.return_value.execute.assert_has_calls([
            call(self.__CREATE_USR_FORMAT, (usr1.name,), (usr1.password,)),
            call(self.__CREATE_USR_FORMAT, (usr2.name,), (usr2.password,)),
            call(self.__CREATE_USR_FORMAT, (usr3.name,), (usr3.password,))
        ])

    @patch.object(cass_service.CassandraLocalhostConnection, '__enter__')
    def test_delete_user(self, conn):
        usr = models.CassandraUser(self._get_random_name(1025), 'password')
        self.manager.delete_user(self.context, usr.serialize())
        conn.return_value.execute.assert_called_once_with(
            self.__DROP_USR_FORMAT, (usr.name,))

    @patch.object(cass_service.CassandraLocalhostConnection, '__enter__')
    def test_change_passwords(self, conn):
        usr1 = models.CassandraUser('usr1')
        usr2 = models.CassandraUser('usr2', '')
        usr3 = models.CassandraUser(self._get_random_name(1025), 'password')

        self.manager.change_passwords(self.context, self._serialize_collection(
            usr1, usr2, usr3))
        conn.return_value.execute.assert_has_calls([
            call(self.__ALTER_USR_FORMAT, (usr1.name,), (usr1.password,)),
            call(self.__ALTER_USR_FORMAT, (usr2.name,), (usr2.password,)),
            call(self.__ALTER_USR_FORMAT, (usr3.name,), (usr3.password,))
        ])

    @patch.object(cass_service.CassandraLocalhostConnection, '__enter__')
    def test_alter_user_password(self, conn):
        usr1 = models.CassandraUser('usr1')
        usr2 = models.CassandraUser('usr2', '')
        usr3 = models.CassandraUser(self._get_random_name(1025), 'password')

        self.admin.alter_user_password(usr1)
        self.admin.alter_user_password(usr2)
        self.admin.alter_user_password(usr3)
        conn.return_value.execute.assert_has_calls([
            call(self.__ALTER_USR_FORMAT, (usr1.name,), (usr1.password,)),
            call(self.__ALTER_USR_FORMAT, (usr2.name,), (usr2.password,)),
            call(self.__ALTER_USR_FORMAT, (usr3.name,), (usr3.password,))
        ])

    @patch.object(cass_service.CassandraLocalhostConnection, '__enter__')
    def test_grant_access(self, conn):
        usr1 = models.CassandraUser('usr1')
        usr2 = models.CassandraUser('usr1', 'password')
        db1 = models.CassandraSchema('db1')
        db2 = models.CassandraSchema('db2')
        db3 = models.CassandraSchema('db3')

        self.manager.grant_access(self.context, usr1.name, None, [db1.name,
                                                                  db2.name])
        self.manager.grant_access(self.context, usr2.name, None, [db3.name])

        expected = []
        for modifier in self.__ACCESS_MODIFIERS:
            expected.append(call(self.__GRANT_FORMAT,
                                 (modifier, db1.name, usr1.name)))
            expected.append(call(self.__GRANT_FORMAT,
                                 (modifier, db3.name, usr2.name)))

        conn.return_value.execute.assert_has_calls(expected, any_order=True)

    @patch.object(cass_service.CassandraLocalhostConnection, '__enter__')
    def test_revoke_access(self, conn):
        usr1 = models.CassandraUser('usr1')
        usr2 = models.CassandraUser('usr1', 'password')
        db1 = models.CassandraSchema('db1')
        db2 = models.CassandraSchema('db2')

        self.manager.revoke_access(self.context, usr1.name, None, db1.name)
        self.manager.revoke_access(self.context, usr2.name, None, db2.name)
        conn.return_value.execute.assert_has_calls([
            call(self.__REVOKE_FORMAT, (db1.name, usr1.name)),
            call(self.__REVOKE_FORMAT, (db2.name, usr2.name))
        ])

    @patch.object(cass_service.CassandraLocalhostConnection, '__enter__')
    def test_get_available_keyspaces(self, conn):
        self.manager.list_databases(self.context)
        conn.return_value.execute.assert_called_once_with(
            self.__LIST_DB_FORMAT)

    @patch.object(cass_service.CassandraLocalhostConnection, '__enter__')
    def test_list_databases(self, conn):
        db1 = models.CassandraSchema('db1')
        db2 = models.CassandraSchema('db2')
        db3 = models.CassandraSchema(self._get_random_name(32))

        with patch.object(self.admin, self.__N_GAK, return_value={db1, db2,
                                                                  db3}):
            found = self.manager.list_databases(self.context)
            self.assertEqual(2, len(found))
            self.assertEqual(3, len(found[0]))
            self.assertEqual(None, found[1])
            self.assertIn(db1.serialize(), found[0])
            self.assertIn(db2.serialize(), found[0])
            self.assertIn(db3.serialize(), found[0])

        with patch.object(self.admin, self.__N_GAK, return_value=set()):
            found = self.manager.list_databases(self.context)
            self.assertEqual(([], None), found)

    def test_get_acl(self):
        r0 = NonCallableMagicMock(username='user1', resource='<all keyspaces>',
                                  permission='SELECT')
        r1 = NonCallableMagicMock(username='user2', resource='<keyspace ks1>',
                                  permission='SELECT')
        r2 = NonCallableMagicMock(username='user2', resource='<keyspace ks2>',
                                  permission='SELECT')
        r3 = NonCallableMagicMock(username='user2', resource='<keyspace ks2>',
                                  permission='ALTER')
        r4 = NonCallableMagicMock(username='user3', resource='<table ks2.t1>',
                                  permission='SELECT')
        r5 = NonCallableMagicMock(username='user3', resource='',
                                  permission='ALTER')
        r6 = NonCallableMagicMock(username='user3', resource='<keyspace ks2>',
                                  permission='')
        r7 = NonCallableMagicMock(username='user3', resource='',
                                  permission='')
        r8 = NonCallableMagicMock(username='user3', resource='<keyspace ks1>',
                                  permission='DELETE')
        r9 = NonCallableMagicMock(username='user4', resource='<all keyspaces>',
                                  permission='UPDATE')
        r10 = NonCallableMagicMock(username='user4', resource='<keyspace ks1>',
                                   permission='DELETE')

        available_ks = {models.CassandraSchema('ks1'),
                        models.CassandraSchema('ks2'),
                        models.CassandraSchema('ks3')}

        mock_result_set = [r0, r1, r2, r3, r4, r5, r6, r7, r8, r9, r9, r9, r10]
        execute_mock = MagicMock(return_value=mock_result_set)
        mock_client = MagicMock(execute=execute_mock)

        with patch.object(self.admin,
                          self.__N_GAK, return_value=available_ks) as gak_mock:
            acl = self.admin._get_acl(mock_client)
            execute_mock.assert_called_once_with(
                self.__LIST_PERMISSIONS_FORMAT)
            gak_mock.assert_called_once_with(mock_client)

            self.assertEqual({'user1': {'ks1': {'SELECT'},
                                        'ks2': {'SELECT'},
                                        'ks3': {'SELECT'}},
                              'user2': {'ks1': {'SELECT'},
                                        'ks2': {'SELECT', 'ALTER'}},
                              'user3': {'ks1': {'DELETE'}},
                              'user4': {'ks1': {'UPDATE', 'DELETE'},
                                        'ks2': {'UPDATE'},
                                        'ks3': {'UPDATE'}}
                              },
                             acl)

        mock_result_set = [r1, r2, r3]
        execute_mock = MagicMock(return_value=mock_result_set)
        mock_client = MagicMock(execute=execute_mock)

        with patch.object(self.admin,
                          self.__N_GAK, return_value=available_ks) as gak_mock:
            acl = self.admin._get_acl(mock_client, username='user2')
            execute_mock.assert_called_once_with(
                self.__LIST_PERMISSIONS_OF_FORMAT.format('user2'))
            gak_mock.assert_not_called()

            self.assertEqual({'user2': {'ks1': {'SELECT'},
                                        'ks2': {'SELECT', 'ALTER'}}}, acl)

        mock_result_set = []
        execute_mock = MagicMock(return_value=mock_result_set)
        mock_client = MagicMock(execute=execute_mock)

        with patch.object(self.admin,
                          self.__N_GAK, return_value=available_ks) as gak_mock:
            acl = self.admin._get_acl(mock_client, username='nonexisting')
            execute_mock.assert_called_once_with(
                self.__LIST_PERMISSIONS_OF_FORMAT.format('nonexisting'))
            gak_mock.assert_not_called()

            self.assertEqual({}, acl)

    @patch.object(cass_service.CassandraLocalhostConnection, '__enter__')
    def test_get_listed_users(self, conn):
        usr1 = models.CassandraUser(self._get_random_name(1025))
        usr2 = models.CassandraUser(self._get_random_name(1025))
        usr3 = models.CassandraUser(self._get_random_name(1025))
        db1 = models.CassandraSchema('db1')
        db2 = models.CassandraSchema('db2')
        usr1.databases.append(db1.serialize())
        usr3.databases.append(db2.serialize())

        rv_1 = NonCallableMagicMock()
        rv_1.configure_mock(name=usr1.name, super=False)
        rv_2 = NonCallableMagicMock()
        rv_2.configure_mock(name=usr2.name, super=False)
        rv_3 = NonCallableMagicMock()
        rv_3.configure_mock(name=usr3.name, super=True)

        with patch.object(conn.return_value, 'execute', return_value=iter(
                [rv_1, rv_2, rv_3])):
            with patch.object(self.admin, '_get_acl',
                              return_value={usr1.name: {db1.name: {'SELECT'},
                                                        db2.name: {}},
                                            usr3.name: {db2.name: {'SELECT'}}}
                              ):
                usrs = self.manager.list_users(self.context)
                conn.return_value.execute.assert_has_calls([
                    call(self.__LIST_USR_FORMAT),
                ], any_order=True)
                self.assertIn(usr1.serialize(), usrs[0])
                self.assertIn(usr2.serialize(), usrs[0])
                self.assertIn(usr3.serialize(), usrs[0])

    @patch.object(cass_service.CassandraLocalhostConnection, '__enter__')
    def test_list_access(self, conn):
        usr1 = models.CassandraUser('usr1')
        usr2 = models.CassandraUser('usr2')
        usr3 = models.CassandraUser(self._get_random_name(1025), 'password')
        db1 = models.CassandraSchema('db1').serialize()
        db2 = models.CassandraSchema('db2').serialize()
        usr2.databases.append(db1)
        usr3.databases.append(db1)
        usr3.databases.append(db2)

        with patch.object(self.admin, self.__N_GLU, return_value={usr1, usr2,
                                                                  usr3}):
            usr1_dbs = self.manager.list_access(self.context, usr1.name, None)
            usr2_dbs = self.manager.list_access(self.context, usr2.name, None)
            usr3_dbs = self.manager.list_access(self.context, usr3.name, None)
            self.assertEqual([], usr1_dbs)
            self.assertEqual([db1], usr2_dbs)
            self.assertEqual([db1, db2], usr3_dbs)

        with patch.object(self.admin, self.__N_GLU, return_value=set()):
            with ExpectedException(exception.UserNotFound):
                self.manager.list_access(self.context, usr3.name, None)

    @patch.object(cass_service.CassandraLocalhostConnection, '__enter__')
    def test_list_users(self, conn):
        usr1 = models.CassandraUser('usr1')
        usr2 = models.CassandraUser('usr2')
        usr3 = models.CassandraUser(self._get_random_name(1025), 'password')

        with patch.object(self.admin, self.__N_GLU, return_value={usr1, usr2,
                                                                  usr3}):
            found = self.manager.list_users(self.context)
            self.assertEqual(2, len(found))
            self.assertEqual(3, len(found[0]))
            self.assertEqual(None, found[1])
            self.assertIn(usr1.serialize(), found[0])
            self.assertIn(usr2.serialize(), found[0])
            self.assertIn(usr3.serialize(), found[0])

        with patch.object(self.admin, self.__N_GLU, return_value=set()):
            self.assertEqual(([], None), self.manager.list_users(self.context))

    @patch.object(cass_service.CassandraLocalhostConnection, '__enter__')
    def test_get_user(self, conn):
        usr1 = models.CassandraUser('usr1')
        usr2 = models.CassandraUser('usr2')
        usr3 = models.CassandraUser(self._get_random_name(1025), 'password')

        with patch.object(self.admin, self.__N_GLU, return_value={usr1, usr2,
                                                                  usr3}):
            found = self.manager.get_user(self.context, usr2.name, None)
            self.assertEqual(usr2.serialize(), found)

        with patch.object(self.admin, self.__N_GLU, return_value=set()):
            self.assertIsNone(
                self.manager.get_user(self.context, usr2.name, None))

    @patch.object(cass_service.CassandraAdmin, '_deserialize_keyspace',
                  side_effect=lambda p1: p1)
    @patch.object(cass_service.CassandraLocalhostConnection, '__enter__')
    def test_rename_user(self, conn, ks_deserializer):
        usr = models.CassandraUser('usr')
        db1 = models.CassandraSchema('db1').serialize()
        db2 = models.CassandraSchema('db2').serialize()
        usr.databases.append(db1)
        usr.databases.append(db2)

        new_user = models.CassandraUser('new_user')
        with patch(self.__N_CAU, return_value=new_user):
            with patch.object(self.admin, self.__N_BU, return_value=usr):
                with patch.object(self.admin, self.__N_CU) as create:
                    with patch.object(self.admin, self.__N_GFA) as grant:
                        with patch.object(self.admin, self.__N_DU) as drop:
                            usr_attrs = {'name': 'user', 'password': 'trove'}
                            self.manager.update_attributes(self.context,
                                                           usr.name, None,
                                                           usr_attrs)
                            create.assert_called_once_with(ANY, new_user)
                            grant.assert_has_calls([call(ANY, db1, ANY),
                                                    call(ANY, db2, ANY)])
                            drop.assert_called_once_with(ANY, usr)

    @patch.object(cass_service.CassandraLocalhostConnection, '__enter__')
    def test_update_attributes(self, conn):
        usr = models.CassandraUser('usr', 'pwd')

        with patch.object(self.admin, self.__N_BU, return_value=usr):
            usr_attrs = {'name': usr.name, 'password': usr.password}
            with patch.object(self.admin, self.__N_RU) as rename:
                with patch.object(self.admin, self.__N_AUP) as alter:
                    self.manager.update_attributes(self.context, usr.name,
                                                   None, usr_attrs)
                    self.assertEqual(0, rename.call_count)
                    self.assertEqual(0, alter.call_count)

            usr_attrs = {'name': 'user', 'password': 'password'}
            with patch.object(self.admin, self.__N_RU) as rename:
                with patch.object(self.admin, self.__N_AUP) as alter:
                    self.manager.update_attributes(self.context, usr.name,
                                                   None, usr_attrs)
                    rename.assert_called_once_with(ANY, usr, usr_attrs['name'],
                                                   usr_attrs['password'])
                    self.assertEqual(0, alter.call_count)

            usr_attrs = {'name': 'user', 'password': usr.password}
            with patch.object(self.admin, self.__N_RU) as rename:
                with patch.object(self.admin, self.__N_AUP) as alter:
                    self.manager.update_attributes(self.context, usr.name,
                                                   None, usr_attrs)
                    rename.assert_called_once_with(ANY, usr, usr_attrs['name'],
                                                   usr_attrs['password'])
                    self.assertEqual(0, alter.call_count)

            usr_attrs = {'name': 'user'}
            with patch.object(self.admin, self.__N_RU) as rename:
                with patch.object(self.admin, self.__N_AUP) as alter:
                    with ExpectedException(
                            exception.UnprocessableEntity, "Updating username "
                            "requires specifying a password as well."):
                        self.manager.update_attributes(self.context, usr.name,
                                                       None, usr_attrs)
                        self.assertEqual(0, rename.call_count)
                        self.assertEqual(0, alter.call_count)

            usr_attrs = {'name': usr.name, 'password': 'password'}
            with patch.object(self.admin, self.__N_RU) as rename:
                with patch.object(self.admin, self.__N_AUP) as alter:
                    self.manager.update_attributes(self.context, usr.name,
                                                   None, usr_attrs)
                    alter.assert_called_once_with(ANY, usr)
                    self.assertEqual(0, rename.call_count)

            usr_attrs = {'password': usr.password}
            with patch.object(self.admin, self.__N_RU) as rename:
                with patch.object(self.admin, self.__N_AUP) as alter:
                    self.manager.update_attributes(self.context, usr.name,
                                                   None, usr_attrs)
                    self.assertEqual(0, rename.call_count)
                    self.assertEqual(0, alter.call_count)

            usr_attrs = {'password': 'trove'}
            with patch.object(self.admin, self.__N_RU) as rename:
                with patch.object(self.admin, self.__N_AUP) as alter:
                    self.manager.update_attributes(self.context, usr.name,
                                                   None, usr_attrs)
                    alter.assert_called_once_with(ANY, usr)
                    self.assertEqual(0, rename.call_count)

    def test_update_overrides(self):
        cfg_mgr_mock = MagicMock()
        self.manager._app.configuration_manager = cfg_mgr_mock
        overrides = NonCallableMagicMock()
        self.manager.update_overrides(Mock(), overrides)
        cfg_mgr_mock.apply_user_override.assert_called_once_with(overrides)
        cfg_mgr_mock.remove_user_override.assert_not_called()

    def test_remove_overrides(self):
        cfg_mgr_mock = MagicMock()
        self.manager._app.configuration_manager = cfg_mgr_mock
        self.manager.update_overrides(Mock(), {}, remove=True)
        cfg_mgr_mock.remove_user_override.assert_called_once_with()
        cfg_mgr_mock.apply_user_override.assert_not_called()

    def test_apply_overrides(self):
        self.assertIsNone(
            self.manager.apply_overrides(Mock(), NonCallableMagicMock()))

    @patch('trove.guestagent.datastore.experimental.cassandra.service.LOG')
    def test_enable_root(self, _):
        with patch.object(self.manager._app, 'is_root_enabled',
                          return_value=False):
            with patch.object(cass_service.CassandraAdmin,
                              '_create_superuser') as create_mock:
                self.manager.enable_root(self.context)
                create_mock.assert_called_once_with(ANY)

        with patch.object(self.manager._app, 'is_root_enabled',
                          return_value=True):
            with patch.object(cass_service.CassandraAdmin,
                              'alter_user_password') as alter_mock:
                self.manager.enable_root(self.context)
                alter_mock.assert_called_once_with(ANY)

    @patch('trove.guestagent.datastore.experimental.cassandra.service.LOG')
    def test_is_root_enabled(self, _):
        trove_admin = Mock()
        trove_admin.configure_mock(name=self.manager._app._ADMIN_USER)
        other_admin = Mock()
        other_admin.configure_mock(name='someuser')

        with patch.object(cass_service.CassandraAdmin,
                          'list_superusers', return_value=[]):
            self.assertFalse(self.manager.is_root_enabled(self.context))

        with patch.object(cass_service.CassandraAdmin,
                          'list_superusers', return_value=[trove_admin]):
            self.assertFalse(self.manager.is_root_enabled(self.context))

        with patch.object(cass_service.CassandraAdmin,
                          'list_superusers', return_value=[other_admin]):
            self.assertTrue(self.manager.is_root_enabled(self.context))

        with patch.object(cass_service.CassandraAdmin,
                          'list_superusers',
                          return_value=[trove_admin, other_admin]):
            self.assertTrue(self.manager.is_root_enabled(self.context))
