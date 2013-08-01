#Copyright 2013 Hewlett-Packard Development Company, L.P.
#Licensed under the Apache License, Version 2.0 (the "License");
#you may not use this file except in compliance with the License.
#You may obtain a copy of the License at
#
#http://www.apache.org/licenses/LICENSE-2.0
#
#Unless required by applicable law or agreed to in writing, software
#distributed under the License is distributed on an "AS IS" BASIS,
#WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#See the License for the specific language governing permissions and
#limitations under the License.


import testtools
from trove.backup import models
from trove.tests.unittests.util import util
from trove.common import utils, exception
from trove.common.context import TroveContext
from trove.instance.models import BuiltInstance, InstanceTasks, Instance
from mockito import mock, when, unstub, any
from trove.taskmanager import api


def _prep_conf(current_time):
    current_time = str(current_time)
    context = TroveContext(tenant='TENANT-' + current_time)
    instance_id = 'INSTANCE-' + current_time
    return context, instance_id

BACKUP_NAME = 'WORKS'
BACKUP_NAME_2 = 'IT-WORKS'
BACKUP_STATE = "NEW"
BACKUP_DESC = 'Backup test'
BACKUP_FILENAME = '45a3d8cb-ade8-484c-a8a5-0c3c7286fb2f.xbstream.gz'
BACKUP_LOCATION = 'https://hpcs.com/tenant/database_backups/' + BACKUP_FILENAME


class BackupCreateTest(testtools.TestCase):
    def setUp(self):
        super(BackupCreateTest, self).setUp()
        util.init_db()
        self.context, self.instance_id = _prep_conf(utils.utcnow())
        self.created = False

    def tearDown(self):
        super(BackupCreateTest, self).tearDown()
        unstub()
        if self.created:
            models.DBBackup.find_by(
                tenant_id=self.context.tenant).delete()

    def test_create(self):
        instance = mock(Instance)
        when(BuiltInstance).load(any(), any()).thenReturn(instance)
        when(instance).validate_can_perform_action().thenReturn(None)
        when(models.Backup).verify_swift_auth_token(any()).thenReturn(
            None)
        when(api.API).create_backup(any()).thenReturn(None)

        bu = models.Backup.create(self.context, self.instance_id,
                                  BACKUP_NAME, BACKUP_DESC)
        self.created = True

        self.assertEqual(BACKUP_NAME, bu.name)
        self.assertEqual(BACKUP_DESC, bu.description)
        self.assertEqual(self.instance_id, bu.instance_id)
        self.assertEqual(models.BackupState.NEW, bu.state)

        db_record = models.DBBackup.find_by(id=bu.id)
        self.assertEqual(bu.id, db_record['id'])
        self.assertEqual(BACKUP_NAME, db_record['name'])
        self.assertEqual(BACKUP_DESC, db_record['description'])
        self.assertEqual(self.instance_id, db_record['instance_id'])
        self.assertEqual(models.BackupState.NEW, db_record['state'])

    def test_create_instance_not_found(self):
        self.assertRaises(exception.NotFound, models.Backup.create,
                          self.context, self.instance_id,
                          BACKUP_NAME, BACKUP_DESC)

    def test_create_instance_not_active(self):
        instance = mock(Instance)
        when(BuiltInstance).load(any(), any()).thenReturn(instance)
        when(instance).validate_can_perform_action().thenRaise(
            exception.UnprocessableEntity)
        self.assertRaises(exception.UnprocessableEntity, models.Backup.create,
                          self.context, self.instance_id,
                          BACKUP_NAME, BACKUP_DESC)

    def test_create_backup_swift_token_invalid(self):
        instance = mock(Instance)
        when(BuiltInstance).load(any(), any()).thenReturn(instance)
        when(instance).validate_can_perform_action().thenReturn(None)
        when(models.Backup).verify_swift_auth_token(any()).thenRaise(
            exception.SwiftAuthError)
        self.assertRaises(exception.SwiftAuthError, models.Backup.create,
                          self.context, self.instance_id,
                          BACKUP_NAME, BACKUP_DESC)


class BackupDeleteTest(testtools.TestCase):
    def setUp(self):
        super(BackupDeleteTest, self).setUp()
        util.init_db()
        self.context, self.instance_id = _prep_conf(utils.utcnow())

    def tearDown(self):
        super(BackupDeleteTest, self).tearDown()
        unstub()

    def test_delete_backup_not_found(self):
        self.assertRaises(exception.NotFound, models.Backup.delete,
                          self.context, 'backup-id')

    def test_delete_backup_is_running(self):
        backup = mock()
        backup.is_running = True
        when(models.Backup).get_by_id(any(), any()).thenReturn(backup)
        self.assertRaises(exception.UnprocessableEntity,
                          models.Backup.delete, self.context, 'backup_id')

    def test_delete_backup_swift_token_invalid(self):
        backup = mock()
        backup.is_running = False
        when(models.Backup).get_by_id(any(), any()).thenReturn(backup)
        when(models.Backup).verify_swift_auth_token(any()).thenRaise(
            exception.SwiftAuthError)
        self.assertRaises(exception.SwiftAuthError, models.Backup.delete,
                          self.context, 'backup_id')


class BackupORMTest(testtools.TestCase):
    def setUp(self):
        super(BackupORMTest, self).setUp()
        util.init_db()
        self.context, self.instance_id = _prep_conf(utils.utcnow())
        self.backup = models.DBBackup.create(tenant_id=self.context.tenant,
                                             name=BACKUP_NAME,
                                             state=BACKUP_STATE,
                                             instance_id=self.instance_id,
                                             deleted=False,
                                             size=2.0,
                                             location=BACKUP_LOCATION)
        self.deleted = False

    def tearDown(self):
        super(BackupORMTest, self).tearDown()
        unstub()
        if not self.deleted:
            models.DBBackup.find_by(tenant_id=self.context.tenant).delete()

    def test_list(self):
        db_record = models.Backup.list(self.context)
        self.assertEqual(1, db_record.count())

    def test_list_for_instance(self):
        models.DBBackup.create(tenant_id=self.context.tenant,
                               name=BACKUP_NAME_2,
                               state=BACKUP_STATE,
                               instance_id=self.instance_id,
                               size=2.0,
                               deleted=False)
        db_record = models.Backup.list_for_instance(self.instance_id)
        self.assertEqual(2, db_record.count())

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
        self.backup.state = models.BackupState.COMPLETED
        self.backup.save()
        self.assertTrue(self.backup.is_done)

    def test_not_is_running(self):
        self.backup.state = models.BackupState.COMPLETED
        self.backup.save()
        self.assertFalse(self.backup.is_running)

    def test_not_is_done(self):
        self.assertFalse(self.backup.is_done)

    def test_backup_size(self):
        db_record = models.DBBackup.find_by(id=self.backup.id)
        self.assertEqual(db_record.size, self.backup.size)

    def test_backup_delete(self):
        backup = models.DBBackup.find_by(id=self.backup.id)
        backup.delete()
        query = models.Backup.list_for_instance(self.instance_id)
        self.assertEqual(query.count(), 0)

    def test_delete(self):
        self.backup.delete()
        db_record = models.DBBackup.find_by(id=self.backup.id, deleted=True)
        self.assertEqual(self.instance_id, db_record['instance_id'])

    def test_deleted_not_running(self):
        self.backup.delete()
        self.assertFalse(models.Backup.running(self.instance_id))

    def test_filename(self):
        self.assertEqual(BACKUP_FILENAME, self.backup.filename)
