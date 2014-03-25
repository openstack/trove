#    Copyright 2013 OpenStack Foundation
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

import testtools
from trove.backup import models as bkup_models
from trove.common import exception as t_exception
from trove.common import utils
from trove.common.instance import ServiceStatuses
from trove.conductor import manager as conductor_manager
from trove.guestagent.common import timeutils
from trove.instance import models as t_models
from trove.tests.unittests.util import util


# See LP bug #1255178
OLD_DBB_SAVE = bkup_models.DBBackup.save


class ConductorMethodTests(testtools.TestCase):
    def setUp(self):
        # See LP bug #1255178
        bkup_models.DBBackup.save = OLD_DBB_SAVE
        super(ConductorMethodTests, self).setUp()
        util.init_db()
        self.cond_mgr = conductor_manager.Manager()
        self.instance_id = utils.generate_uuid()

    def tearDown(self):
        super(ConductorMethodTests, self).tearDown()

    def _create_iss(self):
        new_id = utils.generate_uuid()
        iss = t_models.InstanceServiceStatus(
            id=new_id,
            instance_id=self.instance_id,
            status=ServiceStatuses.NEW)
        iss.save()
        return new_id

    def _get_iss(self, id):
        return t_models.InstanceServiceStatus.find_by(id=id)

    def _create_backup(self, name='fake backup'):
        new_id = utils.generate_uuid()
        backup = bkup_models.DBBackup.create(
            id=new_id,
            name=name,
            description='This is a fake backup object.',
            tenant_id=utils.generate_uuid(),
            state=bkup_models.BackupState.NEW,
            instance_id=self.instance_id)
        backup.save()
        return new_id

    def _get_backup(self, id):
        return bkup_models.DBBackup.find_by(id=id)

    # --- Tests for heartbeat ---

    def test_heartbeat_instance_not_found(self):
        new_id = utils.generate_uuid()
        self.assertRaises(t_exception.ModelNotFoundError,
                          self.cond_mgr.heartbeat, None, new_id, {})

    def test_heartbeat_instance_no_changes(self):
        iss_id = self._create_iss()
        old_iss = self._get_iss(iss_id)
        self.cond_mgr.heartbeat(None, self.instance_id, {})
        new_iss = self._get_iss(iss_id)
        self.assertEqual(old_iss.status_id, new_iss.status_id)
        self.assertEqual(old_iss.status_description,
                         new_iss.status_description)

    def test_heartbeat_instance_status_bogus_change(self):
        iss_id = self._create_iss()
        old_iss = self._get_iss(iss_id)
        new_status = 'potato salad'
        payload = {
            'service_status': new_status,
        }
        self.assertRaises(ValueError, self.cond_mgr.heartbeat,
                          None, self.instance_id, payload)
        new_iss = self._get_iss(iss_id)
        self.assertEqual(old_iss.status_id, new_iss.status_id)
        self.assertEqual(old_iss.status_description,
                         new_iss.status_description)

    def test_heartbeat_instance_status_changed(self):
        iss_id = self._create_iss()
        payload = {'service_status': ServiceStatuses.BUILDING.description}
        self.cond_mgr.heartbeat(None, self.instance_id, payload)
        iss = self._get_iss(iss_id)
        self.assertEqual(ServiceStatuses.BUILDING, iss.status)

    # --- Tests for update_backup ---

    def test_backup_not_found(self):
        new_bkup_id = utils.generate_uuid()
        self.assertRaises(t_exception.ModelNotFoundError,
                          self.cond_mgr.update_backup,
                          None, self.instance_id, new_bkup_id)

    def test_backup_instance_id_nomatch(self):
        new_iid = utils.generate_uuid()
        bkup_id = self._create_backup('nomatch')
        old_name = self._get_backup(bkup_id).name
        self.cond_mgr.update_backup(None, new_iid, bkup_id,
                                    name="remains unchanged")
        bkup = self._get_backup(bkup_id)
        self.assertEqual(old_name, bkup.name)

    def test_backup_bogus_fields_not_changed(self):
        bkup_id = self._create_backup('bogus')
        self.cond_mgr.update_backup(None, self.instance_id, bkup_id,
                                    not_a_valid_field="INVALID")
        bkup = self._get_backup(bkup_id)
        self.assertFalse(hasattr(bkup, 'not_a_valid_field'))

    def test_backup_real_fields_changed(self):
        bkup_id = self._create_backup('realrenamed')
        new_name = "recently renamed"
        self.cond_mgr.update_backup(None, self.instance_id, bkup_id,
                                    name=new_name)
        bkup = self._get_backup(bkup_id)
        self.assertEqual(new_name, bkup.name)

    # --- Tests for discarding old messages ---

    def test_heartbeat_newer_timestamp_accepted(self):
        new_p = {'service_status': ServiceStatuses.NEW.description}
        build_p = {'service_status': ServiceStatuses.BUILDING.description}
        iss_id = self._create_iss()
        iss = self._get_iss(iss_id)
        now = timeutils.float_utcnow()
        future = now + 60
        self.cond_mgr.heartbeat(None, self.instance_id, new_p, sent=now)
        self.cond_mgr.heartbeat(None, self.instance_id, build_p, sent=future)
        iss = self._get_iss(iss_id)
        self.assertEqual(ServiceStatuses.BUILDING, iss.status)

    def test_heartbeat_older_timestamp_discarded(self):
        new_p = {'service_status': ServiceStatuses.NEW.description}
        build_p = {'service_status': ServiceStatuses.BUILDING.description}
        iss_id = self._create_iss()
        iss = self._get_iss(iss_id)
        now = timeutils.float_utcnow()
        past = now - 60
        self.cond_mgr.heartbeat(None, self.instance_id, new_p, sent=past)
        self.cond_mgr.heartbeat(None, self.instance_id, build_p, sent=past)
        iss = self._get_iss(iss_id)
        self.assertEqual(ServiceStatuses.NEW, iss.status)

    def test_backup_newer_timestamp_accepted(self):
        old_name = "oldname"
        new_name = "renamed"
        bkup_id = self._create_backup(old_name)
        bkup = self._get_backup(bkup_id)
        now = timeutils.float_utcnow()
        future = now + 60
        self.cond_mgr.update_backup(None, self.instance_id, bkup_id,
                                    sent=now, name=old_name)
        self.cond_mgr.update_backup(None, self.instance_id, bkup_id,
                                    sent=future, name=new_name)
        bkup = self._get_backup(bkup_id)
        self.assertEqual(new_name, bkup.name)

    def test_backup_older_timestamp_discarded(self):
        old_name = "oldname"
        new_name = "renamed"
        bkup_id = self._create_backup(old_name)
        bkup = self._get_backup(bkup_id)
        now = timeutils.float_utcnow()
        past = now - 60
        self.cond_mgr.update_backup(None, self.instance_id, bkup_id,
                                    sent=now, name=old_name)
        self.cond_mgr.update_backup(None, self.instance_id, bkup_id,
                                    sent=past, name=new_name)
        bkup = self._get_backup(bkup_id)
        self.assertEqual(old_name, bkup.name)
