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
from trove.common.instance import ServiceStatuses
from trove.datastore import models
from trove.instance.models import InstanceServiceStatus
from trove.instance.models import InstanceStatus
from trove.instance.models import SimpleInstance
from trove.instance.tasks import InstanceTasks
from trove.tests.unittests import trove_testtools
from trove.tests.unittests.util import util
import uuid


class FakeInstanceTask(object):

    def __init__(self):
        self.is_error = False
        self.action = None


class FakeDBInstance(object):

    def __init__(self):
        self.id = str(uuid.uuid4())
        self.deleted = False
        self.datastore_version_id = str(uuid.uuid4())
        self.server_status = "ACTIVE"
        self.task_status = FakeInstanceTask()


class BaseInstanceStatusTestCase(trove_testtools.TestCase):

    def setUp(self):
        util.init_db()
        self.db_info = FakeDBInstance()
        self.status = InstanceServiceStatus(
            ServiceStatuses.RUNNING)
        self.datastore = models.DBDatastore.create(
            id=str(uuid.uuid4()),
            name='mysql' + str(uuid.uuid4()),
            default_version_id=self.db_info.datastore_version_id
        )
        self.version = models.DBDatastoreVersion.create(
            id=self.db_info.datastore_version_id,
            datastore_id=self.datastore.id,
            name='5.7' + str(uuid.uuid4()),
            manager='mysql',
            image_id=str(uuid.uuid4()),
            active=1,
            packages="mysql-server-5.7"
        )
        super(BaseInstanceStatusTestCase, self).setUp()

    def tearDown(self):
        self.datastore.delete()
        self.version.delete()
        super(BaseInstanceStatusTestCase, self).tearDown()


class InstanceStatusTest(BaseInstanceStatusTestCase):

    def test_task_status_error_reports_error(self):
        self.db_info.task_status.is_error = True
        instance = SimpleInstance('dummy context', self.db_info, self.status)
        self.assertEqual(InstanceStatus.ERROR, instance.status)

    def test_task_status_action_building_reports_build(self):
        self.db_info.task_status.action = "BUILDING"
        instance = SimpleInstance('dummy context', self.db_info, self.status)
        self.assertEqual(InstanceStatus.BUILD, instance.status)

    def test_task_status_action_rebooting_reports_reboot(self):
        self.db_info.task_status.action = "REBOOTING"
        instance = SimpleInstance('dummy context', self.db_info, self.status)
        self.assertEqual(InstanceStatus.REBOOT, instance.status)

    def test_task_status_action_resizing_reports_resize(self):
        self.db_info.task_status.action = "RESIZING"
        instance = SimpleInstance('dummy context', self.db_info, self.status)
        self.assertEqual(InstanceStatus.RESIZE, instance.status)

    def test_task_status_action_deleting_reports_shutdown(self):
        self.db_info.task_status.action = "DELETING"
        instance = SimpleInstance('dummy context', self.db_info, self.status)
        self.assertEqual(InstanceStatus.SHUTDOWN, instance.status)

    def test_nova_server_build_reports_build(self):
        self.db_info.server_status = "BUILD"
        instance = SimpleInstance('dummy context', self.db_info, self.status)
        self.assertEqual(InstanceStatus.BUILD, instance.status)

    def test_nova_server_error_reports_error(self):
        self.db_info.server_status = "ERROR"
        instance = SimpleInstance('dummy context', self.db_info, self.status)
        self.assertEqual(InstanceStatus.ERROR, instance.status)

    def test_nova_server_reboot_reports_reboot(self):
        self.db_info.server_status = "REBOOT"
        instance = SimpleInstance('dummy context', self.db_info, self.status)
        self.assertEqual(InstanceStatus.REBOOT, instance.status)

    def test_nova_server_resize_reports_resize(self):
        self.db_info.server_status = "RESIZE"
        instance = SimpleInstance('dummy context', self.db_info, self.status)
        self.assertEqual(InstanceStatus.RESIZE, instance.status)

    def test_nova_server_verify_resize_reports_resize(self):
        self.db_info.server_status = "VERIFY_RESIZE"
        instance = SimpleInstance('dummy context', self.db_info, self.status)
        self.assertEqual(InstanceStatus.RESIZE, instance.status)

    def test_service_status_paused_reports_reboot(self):
        self.status.set_status(ServiceStatuses.PAUSED)
        instance = SimpleInstance('dummy context', self.db_info, self.status)
        self.assertEqual(InstanceStatus.REBOOT, instance.status)

    def test_service_status_new_reports_build(self):
        self.status.set_status(ServiceStatuses.NEW)
        instance = SimpleInstance('dummy context', self.db_info, self.status)
        self.assertEqual(InstanceStatus.BUILD, instance.status)

    def test_service_status_running_reports_active(self):
        self.status.set_status(ServiceStatuses.RUNNING)
        instance = SimpleInstance('dummy context', self.db_info, self.status)
        self.assertEqual(InstanceStatus.ACTIVE, instance.status)

    def test_service_status_reset_status(self):
        self.status.set_status(ServiceStatuses.UNKNOWN)
        instance = SimpleInstance('dummy context', self.db_info, self.status)
        self.assertEqual(InstanceStatus.ERROR, instance.status)

    def test_service_status_force_deleteing(self):
        self.status.set_status(ServiceStatuses.UNKNOWN)
        self.db_info.task_status = InstanceTasks.DELETING
        instance = SimpleInstance('dummy context', self.db_info, self.status)
        self.assertEqual(InstanceStatus.SHUTDOWN, instance.status)
