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
from unittest import mock
import uuid

from trove.datastore import models
from trove.instance.models import InstanceServiceStatus
from trove.instance.models import InstanceStatus
from trove.instance.models import SimpleInstance
from trove.instance.service_status import ServiceStatuses
from trove.instance.tasks import InstanceTasks
from trove.tests.unittests import trove_testtools
from trove.tests.unittests.util import util


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
    @classmethod
    def setUpClass(cls):
        util.init_db()
        cls.db_info = FakeDBInstance()
        cls.datastore = models.DBDatastore.create(
            id=str(uuid.uuid4()),
            name='mysql' + str(uuid.uuid4()),
            default_version_id=cls.db_info.datastore_version_id
        )
        cls.version = models.DBDatastoreVersion.create(
            id=cls.db_info.datastore_version_id,
            datastore_id=cls.datastore.id,
            name='5.7' + str(uuid.uuid4()),
            manager='mysql',
            image_id=str(uuid.uuid4()),
            active=1,
            packages="mysql-server-5.7"
        )
        super(BaseInstanceStatusTestCase, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        util.cleanup_db()
        super(BaseInstanceStatusTestCase, cls).tearDownClass()


class InstanceStatusTest(BaseInstanceStatusTestCase):
    def setUp(self):
        self.db_info.task_status = FakeInstanceTask()
        self.db_info.server_status = "ACTIVE"
        self.ds_status = InstanceServiceStatus(ServiceStatuses.HEALTHY)
        super(InstanceStatusTest, self).setUp()

    def test_task_status_error_reports_error(self):
        self.db_info.task_status.is_error = True
        instance = SimpleInstance('dummy context', self.db_info,
                                  self.ds_status)
        self.assertEqual(InstanceStatus.ERROR, instance.status)

    def test_task_status_action_building_reports_build(self):
        self.db_info.task_status.action = "BUILDING"
        instance = SimpleInstance('dummy context', self.db_info,
                                  self.ds_status)
        self.assertEqual(InstanceStatus.BUILD, instance.status)

    def test_task_status_action_rebooting_reports_reboot(self):
        self.db_info.task_status.action = "REBOOTING"
        instance = SimpleInstance('dummy context', self.db_info,
                                  self.ds_status)
        self.assertEqual(InstanceStatus.REBOOT, instance.status)

    def test_task_status_action_resizing_reports_resize(self):
        self.db_info.task_status.action = "RESIZING"
        instance = SimpleInstance('dummy context', self.db_info,
                                  self.ds_status)
        self.assertEqual(InstanceStatus.RESIZE, instance.status)

    def test_task_deleting_server_active(self):
        self.db_info.task_status.action = "DELETING"
        instance = SimpleInstance('dummy context', self.db_info,
                                  self.ds_status)
        self.assertEqual(InstanceStatus.SHUTDOWN, instance.status)

    def test_nova_server_build_reports_build(self):
        self.db_info.server_status = "BUILD"
        instance = SimpleInstance('dummy context', self.db_info,
                                  self.ds_status)
        self.assertEqual(InstanceStatus.BUILD, instance.status)

    def test_nova_server_error_reports_error(self):
        self.db_info.server_status = "ERROR"
        instance = SimpleInstance('dummy context', self.db_info,
                                  self.ds_status)
        self.assertEqual(InstanceStatus.ERROR, instance.status)

    def test_nova_server_reboot_reports_reboot(self):
        self.db_info.server_status = "REBOOT"
        instance = SimpleInstance('dummy context', self.db_info,
                                  self.ds_status)
        self.assertEqual(InstanceStatus.REBOOT, instance.status)

    def test_nova_server_resize_reports_resize(self):
        self.db_info.server_status = "RESIZE"
        instance = SimpleInstance('dummy context', self.db_info,
                                  self.ds_status)
        self.assertEqual(InstanceStatus.RESIZE, instance.status)

    def test_nova_server_verify_resize_reports_resize(self):
        self.db_info.server_status = "VERIFY_RESIZE"
        instance = SimpleInstance('dummy context', self.db_info,
                                  self.ds_status)
        self.assertEqual(InstanceStatus.RESIZE, instance.status)

    def test_operating_status_healthy(self):
        self.db_info.task_status = InstanceTasks.NONE
        instance = SimpleInstance(mock.MagicMock(), self.db_info,
                                  self.ds_status)
        self.assertEqual(repr(ServiceStatuses.HEALTHY),
                         instance.operating_status)

    def test_operating_status_task_not_none(self):
        self.db_info.task_status = InstanceTasks.RESIZING
        instance = SimpleInstance(mock.MagicMock(), self.db_info,
                                  self.ds_status)
        self.assertEqual("",
                         instance.operating_status)
