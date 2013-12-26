# Copyright 2013 OpenStack Foundation
# All Rights Reserved.
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
#
from testtools import TestCase
from trove.common.instance import ServiceStatuses
from trove.instance.models import InstanceStatus
from trove.instance.models import SimpleInstance
from trove.tests.util import test_config


class FakeInstanceTask(object):

    def __init__(self):
        self.is_error = False
        self.action = None


class FakeDBInstance(object):

    def __init__(self):
        self.id = None
        self.deleted = False
        self.datastore_version_id = test_config.dbaas_datastore_version_id
        self.server_status = "ACTIVE"
        self.task_status = FakeInstanceTask()


class FakeInstanceServiceStatus(object):

    def __init__(self):
        self.status = ServiceStatuses.RUNNING

    def set_status(self, status):
        self.status = status

    def get_status(self):
        return self.status


class InstanceStatusTest(TestCase):

    def setUp(self):
        super(InstanceStatusTest, self).setUp()

    def tearDown(self):
        super(InstanceStatusTest, self).tearDown()

    def test_task_status_error_reports_error(self):
        fake_db_info = FakeDBInstance()
        fake_status = FakeInstanceServiceStatus()
        fake_db_info.task_status.is_error = True
        instance = SimpleInstance('dummy context', fake_db_info, fake_status)
        self.assertEqual(InstanceStatus.ERROR, instance.status)

    def test_task_status_action_building_reports_build(self):
        fake_db_info = FakeDBInstance()
        fake_status = FakeInstanceServiceStatus()
        fake_db_info.task_status.action = "BUILDING"
        instance = SimpleInstance('dummy context', fake_db_info, fake_status)
        self.assertEqual(InstanceStatus.BUILD, instance.status)

    def test_task_status_action_rebooting_reports_reboot(self):
        fake_db_info = FakeDBInstance()
        fake_status = FakeInstanceServiceStatus()
        fake_db_info.task_status.action = "REBOOTING"
        instance = SimpleInstance('dummy context', fake_db_info, fake_status)
        self.assertEqual(InstanceStatus.REBOOT, instance.status)

    def test_task_status_action_resizing_reports_resize(self):
        fake_db_info = FakeDBInstance()
        fake_status = FakeInstanceServiceStatus()
        fake_db_info.task_status.action = "RESIZING"
        instance = SimpleInstance('dummy context', fake_db_info, fake_status)
        self.assertEqual(InstanceStatus.RESIZE, instance.status)

    def test_task_status_action_deleting_reports_shutdown(self):
        fake_db_info = FakeDBInstance()
        fake_status = FakeInstanceServiceStatus()
        fake_db_info.task_status.action = "DELETING"
        instance = SimpleInstance('dummy context', fake_db_info, fake_status)
        self.assertEqual(InstanceStatus.SHUTDOWN, instance.status)

    def test_nova_server_build_reports_build(self):
        fake_db_info = FakeDBInstance()
        fake_status = FakeInstanceServiceStatus()
        fake_db_info.server_status = "BUILD"
        instance = SimpleInstance('dummy context', fake_db_info, fake_status)
        self.assertEqual(InstanceStatus.BUILD, instance.status)

    def test_nova_server_error_reports_error(self):
        fake_db_info = FakeDBInstance()
        fake_status = FakeInstanceServiceStatus()
        fake_db_info.server_status = "ERROR"
        instance = SimpleInstance('dummy context', fake_db_info, fake_status)
        self.assertEqual(InstanceStatus.ERROR, instance.status)

    def test_nova_server_reboot_reports_reboot(self):
        fake_db_info = FakeDBInstance()
        fake_status = FakeInstanceServiceStatus()
        fake_db_info.server_status = "REBOOT"
        instance = SimpleInstance('dummy context', fake_db_info, fake_status)
        self.assertEqual(InstanceStatus.REBOOT, instance.status)

    def test_nova_server_resize_reports_resize(self):
        fake_db_info = FakeDBInstance()
        fake_status = FakeInstanceServiceStatus()
        fake_db_info.server_status = "RESIZE"
        instance = SimpleInstance('dummy context', fake_db_info, fake_status)
        self.assertEqual(InstanceStatus.RESIZE, instance.status)

    def test_nova_server_verify_resize_reports_resize(self):
        fake_db_info = FakeDBInstance()
        fake_status = FakeInstanceServiceStatus()
        fake_db_info.server_status = "VERIFY_RESIZE"
        instance = SimpleInstance('dummy context', fake_db_info, fake_status)
        self.assertEqual(InstanceStatus.RESIZE, instance.status)

    def test_service_status_paused_reports_reboot(self):
        fake_db_info = FakeDBInstance()
        fake_status = FakeInstanceServiceStatus()
        fake_status.set_status(ServiceStatuses.PAUSED)
        instance = SimpleInstance('dummy context', fake_db_info, fake_status)
        self.assertEqual(InstanceStatus.REBOOT, instance.status)

    def test_service_status_new_reports_build(self):
        fake_db_info = FakeDBInstance()
        fake_status = FakeInstanceServiceStatus()
        fake_status.set_status(ServiceStatuses.NEW)
        instance = SimpleInstance('dummy context', fake_db_info, fake_status)
        self.assertEqual(InstanceStatus.BUILD, instance.status)

    def test_service_status_running_reports_active(self):
        fake_db_info = FakeDBInstance()
        fake_status = FakeInstanceServiceStatus()
        fake_status.set_status(ServiceStatuses.RUNNING)
        instance = SimpleInstance('dummy context', fake_db_info, fake_status)
        self.assertEqual(InstanceStatus.ACTIVE, instance.status)
