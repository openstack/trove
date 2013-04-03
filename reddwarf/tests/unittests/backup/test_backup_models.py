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
from reddwarf.backup import models
from reddwarf.tests.unittests.util import util
from reddwarf.common import utils
from reddwarf.common.context import ReddwarfContext


def _prep_conf(current_time):
    current_time = str(current_time)
    context = ReddwarfContext(tenant='TENANT-' + current_time)
    instance_id = 'INSTANCE-' + current_time
    return context, instance_id

BACKUP_NAME = 'WORKS'
BACKUP_NAME_2 = 'IT-WORKS'
BACKUP_STATE = "NEW"


class BackupCreateTest(testtools.TestCase):
    def setUp(self):
        super(BackupCreateTest, self).setUp()
        util.init_db()
        self.context, self.instance_id = _prep_conf(utils.utcnow())
        self.created = False

    def tearDown(self):
        super(BackupCreateTest, self).tearDown()
        if self.created:
            models.DBBackup.find_by(
                tenant_id=self.context.tenant).delete()

    def test_create(self):
        models.Backup.create(
            self.context, self.instance_id, BACKUP_NAME)
        self.created = True
        db_record = models.DBBackup.find_by(
            tenant_id=self.context.tenant)
        self.assertEqual(self.instance_id, db_record['instance_id'])


class BackupORMTest(testtools.TestCase):
    def setUp(self):
        super(BackupORMTest, self).setUp()
        util.init_db()
        self.context, self.instance_id = _prep_conf(utils.utcnow())
        self.backup = models.DBBackup.create(tenant_id=self.context.tenant,
                                             name=BACKUP_NAME,
                                             state=BACKUP_STATE,
                                             instance_id=self.instance_id,
                                             deleted=False)
        self.deleted = False

    def tearDown(self):
        super(BackupORMTest, self).tearDown()
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

    def test_backup_delete(self):
        models.Backup.delete(self.backup.id)
        query = models.Backup.list_for_instance(self.instance_id)
        self.assertEqual(query.count(), 0)

    def test_delete(self):
        self.backup.delete()
        db_record = models.DBBackup.find_by(id=self.backup.id, deleted=True)
        self.assertEqual(self.instance_id, db_record['instance_id'])

    def test_deleted_not_running(self):
        self.backup.delete()
        self.assertFalse(models.Backup.running(self.instance_id))
