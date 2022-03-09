# Copyright 2013 Hewlett-Packard Development Company, L.P.
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


import datetime
from unittest.mock import DEFAULT
from unittest.mock import MagicMock
from unittest.mock import patch
from swiftclient.client import ClientException

from trove.backup import models
from trove.backup import state
from trove.common import context
from trove.common import exception
from trove.common import timeutils
from trove.common import utils
from trove.db.models import DatabaseModelBase
from trove.instance import models as instance_models
from trove.taskmanager import api
from trove.tests.unittests import trove_testtools
from trove.tests.unittests.util import util


def _prep_conf(current_time):
    current_time = str(current_time)
    _context = context.TroveContext(project_id='TENANT-' + current_time)
    instance_id = 'INSTANCE-' + current_time
    return _context, instance_id


BACKUP_NAME = 'WORKS'
BACKUP_NAME_2 = 'IT-WORKS'
BACKUP_NAME_3 = 'SECOND-LAST-ONE'
BACKUP_NAME_4 = 'LAST-ONE-FULL'
BACKUP_NAME_5 = 'LAST-ONE-INCREMENTAL'
BACKUP_NAME_6 = 'LAST-ONE-DELETED'
BACKUP_STATE = state.BackupState.NEW
BACKUP_STATE_COMPLETED = state.BackupState.COMPLETED
BACKUP_DESC = 'Backup test'
BACKUP_FILENAME = '45a3d8cb-ade8-484c-a8a5-0c3c7286fb2f.xbstream.gz'
BACKUP_LOCATION = 'https://hpcs.com/tenant/database_backups/' + BACKUP_FILENAME


class BackupCreateTest(trove_testtools.TestCase):
    def setUp(self):
        super(BackupCreateTest, self).setUp()
        util.init_db()
        self.context, self.instance_id = _prep_conf(timeutils.utcnow())
        self.created = False

    def tearDown(self):
        super(BackupCreateTest, self).tearDown()
        if self.created:
            models.DBBackup.find_by(
                tenant_id=self.context.project_id).delete()

    @patch.object(api.API, 'get_client', MagicMock(return_value=MagicMock()))
    def test_create(self):
        instance = MagicMock()
        with patch.object(instance_models.BuiltInstance, 'load',
                          return_value=instance):
            instance.validate_can_perform_action = MagicMock(
                return_value=None)
            instance.datastore_version = MagicMock()
            instance.datastore_version.id = 'datastore-id-999'
            instance.cluster_id = None
            with patch.multiple(models.Backup,
                                validate_can_perform_action=DEFAULT,
                                verify_swift_auth_token=DEFAULT):
                with patch.object(api.API, 'create_backup',
                                  MagicMock(return_value=None)):
                    bu = models.Backup.create(self.context, self.instance_id,
                                              BACKUP_NAME, BACKUP_DESC)
                    self.created = True

                    self.assertEqual(BACKUP_NAME, bu.name)
                    self.assertEqual(BACKUP_DESC, bu.description)
                    self.assertEqual(self.instance_id, bu.instance_id)
                    self.assertEqual(state.BackupState.NEW, bu.state)

                    db_record = models.DBBackup.find_by(id=bu.id)
                    self.assertEqual(bu.id, db_record['id'])
                    self.assertEqual(BACKUP_NAME, db_record['name'])
                    self.assertEqual(BACKUP_DESC, db_record['description'])
                    self.assertEqual(self.instance_id,
                                     db_record['instance_id'])
                    self.assertEqual(state.BackupState.NEW,
                                     db_record['state'])
                    self.assertEqual(instance.datastore_version.id,
                                     db_record['datastore_version_id'])

    @patch.object(api.API, 'get_client', MagicMock(return_value=MagicMock()))
    def test_create_incremental(self):
        instance = MagicMock()
        parent = MagicMock(spec=models.DBBackup)
        with patch.object(instance_models.BuiltInstance, 'load',
                          return_value=instance):
            instance.validate_can_perform_action = MagicMock(
                return_value=None)
            instance.validate_can_perform_action = MagicMock(
                return_value=None)
            instance.datastore_version = MagicMock()
            instance.datastore_version.id = 'datastore-id-999'
            instance.cluster_id = None
            with patch.multiple(models.Backup,
                                validate_can_perform_action=DEFAULT,
                                verify_swift_auth_token=DEFAULT,
                                get_by_id=MagicMock(return_value=parent)):
                with patch.object(api.API, 'create_backup',
                                  MagicMock(return_value=None)):
                    incremental = models.Backup.create(
                        self.context,
                        self.instance_id,
                        BACKUP_NAME,
                        BACKUP_DESC,
                        parent_id='parent_uuid')

                    self.created = True

                    db_record = models.DBBackup.find_by(id=incremental.id)
                    self.assertEqual(incremental.id,
                                     db_record['id'])
                    self.assertEqual(BACKUP_NAME,
                                     db_record['name'])
                    self.assertEqual(BACKUP_DESC,
                                     db_record['description'])
                    self.assertEqual(self.instance_id,
                                     db_record['instance_id'])
                    self.assertEqual(state.BackupState.NEW,
                                     db_record['state'])
                    self.assertEqual('parent_uuid',
                                     db_record['parent_id'])
                    self.assertEqual(instance.datastore_version.id,
                                     db_record['datastore_version_id'])

    def test_create_instance_not_found(self):
        self.assertRaises(exception.NotFound, models.Backup.create,
                          self.context, self.instance_id,
                          BACKUP_NAME, BACKUP_DESC)

    def test_create_incremental_not_found(self):
        instance = MagicMock()
        with patch.object(instance_models.BuiltInstance, 'load',
                          return_value=instance):
            instance.validate_can_perform_action = MagicMock(
                return_value=None)
            instance.cluster_id = None
            with patch.object(models.Backup, 'validate_can_perform_action',
                              return_value=None):
                with patch.object(models.Backup, 'verify_swift_auth_token',
                                  return_value=None):
                    self.assertRaises(exception.NotFound, models.Backup.create,
                                      self.context, self.instance_id,
                                      BACKUP_NAME, BACKUP_DESC,
                                      parent_id='BAD')

    def test_create_instance_not_active(self):
        instance = MagicMock()
        with patch.object(instance_models.BuiltInstance, 'load',
                          return_value=instance):
            instance.validate_can_perform_action = MagicMock(
                side_effect=exception.UnprocessableEntity)
            self.assertRaises(exception.UnprocessableEntity,
                              models.Backup.create,
                              self.context, self.instance_id,
                              BACKUP_NAME, BACKUP_DESC)

    def test_create_backup_swift_token_invalid(self):
        instance = MagicMock(cluster_id=None)
        with patch.object(instance_models.BuiltInstance, 'load',
                          return_value=instance):
            instance.validate_can_perform_action = MagicMock(
                return_value=None)
            with patch.object(models.Backup, 'validate_can_perform_action',
                              return_value=None):
                with patch.object(models.Backup, 'verify_swift_auth_token',
                                  side_effect=exception.SwiftAuthError):
                    self.assertRaises(exception.SwiftAuthError,
                                      models.Backup.create,
                                      self.context, self.instance_id,
                                      BACKUP_NAME, BACKUP_DESC)

    def test_create_backup_datastore_operation_not_supported(self):
        instance = MagicMock(cluster_id=None)
        with patch.object(instance_models.BuiltInstance, 'load',
                          return_value=instance):
            with patch.object(
                models.Backup, 'validate_can_perform_action',
                side_effect=exception.DatastoreOperationNotSupported
            ):
                self.assertRaises(exception.DatastoreOperationNotSupported,
                                  models.Backup.create,
                                  self.context, self.instance_id,
                                  BACKUP_NAME, BACKUP_DESC)

    def test_create_backup_cluster_instance_operation_not_supported(self):
        instance = MagicMock()
        instance.cluster_id = 'bad_id'
        with patch.object(instance_models.BuiltInstance, 'load',
                          return_value=instance),\
            patch.object(models.Backup, 'validate_can_perform_action',
                         return_value=None),\
            patch.object(models.Backup, 'verify_swift_auth_token',
                         return_value=None):
            self.assertRaises(exception.ClusterInstanceOperationNotSupported,
                              models.Backup.create,
                              self.context, self.instance_id,
                              BACKUP_NAME, BACKUP_DESC)

    @patch('trove.backup.models.LOG')
    def test_create_backup_creation_error(self, mock_logging):
        instance = MagicMock()
        instance.cluster_id = None
        with patch.object(instance_models.BuiltInstance, 'load',
                          return_value=instance),\
            patch.object(models.Backup, 'validate_can_perform_action',
                         return_value=None),\
            patch.object(models.Backup, 'verify_swift_auth_token',
                         return_value=None),\
            patch.object(DatabaseModelBase, 'is_valid',
                         return_value=False),\
            patch('trove.quota.quota.QuotaEngine.reserve',
                  return_value=[]):
            DatabaseModelBase.errors = {}
            self.assertRaises(exception.BackupCreationError,
                              models.Backup.create,
                              self.context, self.instance_id,
                              BACKUP_NAME, BACKUP_DESC)


class BackupDeleteTest(trove_testtools.TestCase):
    def setUp(self):
        super(BackupDeleteTest, self).setUp()
        util.init_db()
        self.context, self.instance_id = _prep_conf(timeutils.utcnow())

    def tearDown(self):
        super(BackupDeleteTest, self).tearDown()

    def test_delete_backup_not_found(self):
        self.assertRaises(exception.NotFound, models.Backup.delete,
                          self.context, 'backup-id')

    def test_delete_backup_is_running(self):
        backup = MagicMock()
        backup.is_running = True
        with patch.object(models.Backup, 'get_by_id', return_value=backup):
            self.assertRaises(exception.UnprocessableEntity,
                              models.Backup.delete, self.context, 'backup_id')

    def test_delete_backup_swift_token_invalid(self):
        backup = MagicMock()
        backup.is_running = False
        with patch.object(models.Backup, 'get_by_id', return_value=backup):
            with patch.object(models.Backup, 'verify_swift_auth_token',
                              side_effect=exception.SwiftAuthError):
                self.assertRaises(exception.SwiftAuthError,
                                  models.Backup.delete,
                                  self.context, 'backup_id')


class BackupORMTest(trove_testtools.TestCase):
    def setUp(self):
        super(BackupORMTest, self).setUp()
        util.init_db()
        self.context, self.instance_id = _prep_conf(timeutils.utcnow())
        self.backup = models.DBBackup.create(tenant_id=self.context.project_id,
                                             name=BACKUP_NAME,
                                             state=BACKUP_STATE,
                                             instance_id=self.instance_id,
                                             deleted=False,
                                             size=2.0,
                                             location=BACKUP_LOCATION)
        self.deleted = False

    def tearDown(self):
        super(BackupORMTest, self).tearDown()
        if not self.deleted:
            models.DBBackup.find_by(tenant_id=self.context.project_id).delete()

    def test_list(self):
        backups, marker = models.Backup.list(self.context)
        self.assertIsNone(marker)
        self.assertEqual(1, len(backups))

    def test_list_for_instance(self):
        models.DBBackup.create(tenant_id=self.context.project_id,
                               name=BACKUP_NAME_2,
                               state=BACKUP_STATE,
                               instance_id=self.instance_id,
                               size=2.0,
                               deleted=False)
        backups, marker = models.Backup.list_for_instance(self.context,
                                                          self.instance_id)
        self.assertIsNone(marker)
        self.assertEqual(2, len(backups))

    def test_get_last_completed(self):
        models.DBBackup.create(tenant_id=self.context.project_id,
                               name=BACKUP_NAME_3,
                               state=BACKUP_STATE_COMPLETED,
                               instance_id=self.instance_id,
                               size=2.0,
                               deleted=False)
        models.DBBackup.create(tenant_id=self.context.project_id,
                               name=BACKUP_NAME_4,
                               state=BACKUP_STATE_COMPLETED,
                               instance_id=self.instance_id,
                               size=2.0,
                               deleted=False)
        models.DBBackup.create(tenant_id=self.context.project_id,
                               name=BACKUP_NAME_5,
                               state=BACKUP_STATE_COMPLETED,
                               instance_id=self.instance_id,
                               parent_id='parent_uuid',
                               size=2.0,
                               deleted=False)
        models.DBBackup.create(tenant_id=self.context.project_id,
                               name=BACKUP_NAME_6,
                               state=BACKUP_STATE_COMPLETED,
                               instance_id=self.instance_id,
                               size=2.0,
                               deleted=True)

        backup = models.Backup.get_last_completed(
            self.context, self.instance_id, include_incremental=True)
        self.assertEqual(BACKUP_NAME_5, backup.name)

        backup = models.Backup.get_last_completed(
            self.context, self.instance_id, include_incremental=False)
        self.assertEqual(BACKUP_NAME_4, backup.name)

    def test_running(self):
        running = models.Backup.running(instance_id=self.instance_id)
        self.assertTrue(running)

    def test_not_running(self):
        not_running = models.Backup.running(instance_id='non-existent')
        self.assertFalse(not_running)

    def test_running_exclude(self):
        not_running = models.Backup.running(instance_id=self.instance_id,
                                            exclude=self.backup.id)
        self.assertFalse(not_running)

    def test_is_running(self):
        self.assertTrue(self.backup.is_running)

    def test_is_done(self):
        self.backup.state = state.BackupState.COMPLETED
        self.backup.save()
        self.assertTrue(self.backup.is_done)

    def test_not_is_running(self):
        self.backup.state = state.BackupState.COMPLETED
        self.backup.save()
        self.assertFalse(self.backup.is_running)

    def test_not_is_done(self):
        self.assertFalse(self.backup.is_done)

    def test_backup_size(self):
        db_record = models.DBBackup.find_by(id=self.backup.id)
        self.assertEqual(self.backup.size, db_record.size)

    def test_backup_delete(self):
        backup = models.DBBackup.find_by(id=self.backup.id)
        backup.delete()
        backups, marker = models.Backup.list_for_instance(self.context,
                                                          self.instance_id)
        self.assertIsNone(marker)
        self.assertEqual(0, len(backups))

    def test_delete(self):
        self.backup.delete()
        db_record = models.DBBackup.find_by(id=self.backup.id, deleted=True)
        self.assertEqual(self.instance_id, db_record['instance_id'])

    def test_deleted_not_running(self):
        self.backup.delete()
        self.assertFalse(models.Backup.running(self.instance_id))

    def test_filename(self):
        self.assertEqual(BACKUP_FILENAME, self.backup.filename)

    def test_filename_bad(self):

        def _set_bad_filename():
            self.backup.location = 'bad'
            self.backup.filename

        self.assertRaises(ValueError, _set_bad_filename)

    @patch('trove.common.clients.create_swift_client')
    def test_check_swift_object_exist_integrity_error(self, mock_swift_client):
        mock_swift_client.return_value.head_object.return_value = {'etag': ''}

        self.assertRaises(exception.RestoreBackupIntegrityError,
                          self.backup.check_swift_object_exist,
                          self.context, True)

    @patch('trove.common.clients.create_swift_client')
    def test_check_swift_object_exist_client_exception(self,
                                                       mock_swift_client):
        mock_swift_client.side_effect = ClientException(
            self.context.project_id
        )
        self.assertRaises(exception.SwiftAuthError,
                          self.backup.check_swift_object_exist,
                          self.context)

    @patch('trove.common.clients.create_swift_client')
    def test_check_swift_object_exist_client_exception_404(self,
                                                           mock_swift_client):
        e = ClientException(self.context.project_id)
        e.http_status = 404
        mock_swift_client.side_effect = e

        self.assertFalse(self.backup.check_swift_object_exist(self.context))

    @patch('trove.common.clients.create_swift_client')
    def test_swift_auth_token_client_exception(self, mock_swift_client):
        mock_swift_client.side_effect = ClientException(
            self.context.project_id
        )

        self.assertRaises(exception.SwiftAuthError,
                          models.Backup.verify_swift_auth_token,
                          self.context)

    @patch('trove.common.clients.create_swift_client')
    def test_swift_auth_token_no_service_endpoint(self, mock_swift_client):
        mock_swift_client.side_effect = exception.NoServiceEndpoint

        self.assertRaises(exception.SwiftNotFound,
                          models.Backup.verify_swift_auth_token,
                          self.context)


class PaginationTests(trove_testtools.TestCase):

    def setUp(self):
        super(PaginationTests, self).setUp()
        util.init_db()
        self.context, self.instance_id = _prep_conf(timeutils.utcnow())
        # Create a bunch of backups
        bkup_info = {
            'tenant_id': self.context.project_id,
            'state': BACKUP_STATE,
            'instance_id': self.instance_id,
            'size': 2.0,
            'deleted': False
        }
        for backup in range(50):
            bkup_info.update({'name': 'Backup-%s' % backup})
            models.DBBackup.create(**bkup_info)

    def tearDown(self):
        super(PaginationTests, self).tearDown()
        query = models.DBBackup.query()
        query.filter_by(instance_id=self.instance_id).delete()

    def test_pagination_list(self):
        # page one
        backups, marker = models.Backup.list(self.context)
        self.assertEqual(20, marker)
        self.assertEqual(20, len(backups))
        # page two
        self.context.marker = 20
        backups, marker = models.Backup.list(self.context)
        self.assertEqual(40, marker)
        self.assertEqual(20, len(backups))
        # page three
        self.context.marker = 40
        backups, marker = models.Backup.list(self.context)
        self.assertIsNone(marker)
        self.assertEqual(10, len(backups))

    def test_pagination_list_for_instance(self):
        # page one
        backups, marker = models.Backup.list_for_instance(self.context,
                                                          self.instance_id)
        self.assertEqual(20, marker)
        self.assertEqual(20, len(backups))
        # page two
        self.context.marker = 20
        backups, marker = models.Backup.list(self.context)
        self.assertEqual(40, marker)
        self.assertEqual(20, len(backups))
        # page three
        self.context.marker = 40
        backups, marker = models.Backup.list_for_instance(self.context,
                                                          self.instance_id)
        self.assertIsNone(marker)
        self.assertEqual(10, len(backups))


class OrderingTests(trove_testtools.TestCase):

    def setUp(self):
        super(OrderingTests, self).setUp()
        util.init_db()
        now = timeutils.utcnow()
        self.context, self.instance_id = _prep_conf(now)
        info = {
            'tenant_id': self.context.project_id,
            'state': BACKUP_STATE,
            'instance_id': self.instance_id,
            'size': 2.0,
            'deleted': False
        }
        four = now - datetime.timedelta(days=4)
        one = now - datetime.timedelta(days=1)
        three = now - datetime.timedelta(days=3)
        two = now - datetime.timedelta(days=2)
        # Create backups out of order, save/create set the 'updated' field,
        # so we need to use the db_api directly.
        models.DBBackup().db_api.save(
            models.DBBackup(name='four', updated=four,
                            id=utils.generate_uuid(), **info))
        models.DBBackup().db_api.save(
            models.DBBackup(name='one', updated=one,
                            id=utils.generate_uuid(), **info))
        models.DBBackup().db_api.save(
            models.DBBackup(name='three', updated=three,
                            id=utils.generate_uuid(), **info))
        models.DBBackup().db_api.save(
            models.DBBackup(name='two', updated=two,
                            id=utils.generate_uuid(), **info))

    def tearDown(self):
        super(OrderingTests, self).tearDown()
        query = models.DBBackup.query()
        query.filter_by(instance_id=self.instance_id).delete()

    def test_list(self):
        backups, marker = models.Backup.list(self.context)
        self.assertIsNone(marker)
        actual = [b.name for b in backups]
        expected = ['one', 'two', 'three', 'four']
        self.assertEqual(expected, actual)

    def test_list_for_instance(self):
        backups, marker = models.Backup.list_for_instance(self.context,
                                                          self.instance_id)
        self.assertIsNone(marker)
        actual = [b.name for b in backups]
        expected = ['one', 'two', 'three', 'four']
        self.assertEqual(expected, actual)


class TestBackupStrategy(trove_testtools.TestCase):
    def setUp(self):
        super(TestBackupStrategy, self).setUp()
        util.init_db()
        self.context, self.instance_id = _prep_conf(timeutils.utcnow())

    def test_create(self):
        db_backstg = models.BackupStrategy.create(self.context,
                                                  self.instance_id,
                                                  'test-container')
        self.addCleanup(models.BackupStrategy.delete, self.context,
                        self.context.project_id, self.instance_id)

        self.assertEqual('test-container', db_backstg.swift_container)

    def test_list(self):
        models.BackupStrategy.create(self.context, self.instance_id,
                                     'test_list')
        self.addCleanup(models.BackupStrategy.delete, self.context,
                        self.context.project_id, self.instance_id)

        db_backstgs = models.BackupStrategy.list(self.context,
                                                 self.context.project_id,
                                                 self.instance_id).all()

        self.assertEqual(1, len(db_backstgs))
        self.assertEqual('test_list', db_backstgs[0].swift_container)

    def test_delete(self):
        models.BackupStrategy.create(self.context, self.instance_id,
                                     'test_delete')
        db_backstgs = models.BackupStrategy.list(self.context,
                                                 self.context.project_id,
                                                 self.instance_id).all()
        self.assertEqual(1, len(db_backstgs))

        models.BackupStrategy.delete(self.context, self.context.project_id,
                                     self.instance_id)

        db_backstgs = models.BackupStrategy.list(self.context,
                                                 self.context.project_id,
                                                 self.instance_id).all()
        self.assertEqual(0, len(db_backstgs))
