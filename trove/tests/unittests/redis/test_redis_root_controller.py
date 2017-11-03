# Copyright 2017 Eayun, Inc.
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
import uuid

from mock import Mock, patch

from trove.common import exception
from trove.datastore import models as datastore_models
from trove.extensions.common import models
from trove.extensions.redis.service import RedisRootController
from trove.instance import models as instance_models
from trove.instance.models import DBInstance
from trove.instance.tasks import InstanceTasks
from trove.taskmanager import api as task_api
from trove.tests.unittests import trove_testtools
from trove.tests.unittests.util import util


class TestRedisRootController(trove_testtools.TestCase):

    @patch.object(task_api.API, 'get_client', Mock(return_value=Mock()))
    def setUp(self):
        util.init_db()
        self.context = trove_testtools.TroveTestContext(self, is_admin=True)
        self.datastore = datastore_models.DBDatastore.create(
            id=str(uuid.uuid4()),
            name='redis' + str(uuid.uuid4()),
        )
        self.datastore_version = (
            datastore_models.DBDatastoreVersion.create(
                id=str(uuid.uuid4()),
                datastore_id=self.datastore.id,
                name="3.2" + str(uuid.uuid4()),
                manager="redis",
                image_id="image_id",
                packages="",
                active=True))
        self.tenant_id = "UUID"
        self.single_db_info = DBInstance.create(
            id="redis-single",
            name="redis-single",
            flavor_id=1,
            datastore_version_id=self.datastore_version.id,
            tenant_id=self.tenant_id,
            volume_size=None,
            task_status=InstanceTasks.NONE)
        self.master_db_info = DBInstance.create(
            id="redis-master",
            name="redis-master",
            flavor_id=1,
            datastore_version_id=self.datastore_version.id,
            tenant_id=self.tenant_id,
            volume_size=None,
            task_status=InstanceTasks.NONE)
        self.slave_db_info = DBInstance.create(
            id="redis-slave",
            name="redis-slave",
            flavor_id=1,
            datastore_version_id=self.datastore_version.id,
            tenant_id=self.tenant_id,
            volume_size=None,
            task_status=InstanceTasks.NONE,
            slave_of_id=self.master_db_info.id)

        super(TestRedisRootController, self).setUp()
        self.controller = RedisRootController()

    def tearDown(self):
        self.datastore.delete()
        self.datastore_version.delete()
        self.master_db_info.delete()
        self.slave_db_info.delete()
        super(TestRedisRootController, self).tearDown()

    @patch.object(instance_models.Instance, "load")
    @patch.object(models.Root, "create")
    def test_root_create_on_single_instance(self, root_create, *args):
        user = Mock()
        context = Mock()
        context.user = Mock()
        context.user.__getitem__ = Mock(return_value=user)
        req = Mock()
        req.environ = Mock()
        req.environ.__getitem__ = Mock(return_value=context)
        tenant_id = self.tenant_id
        instance_id = self.single_db_info.id
        is_cluster = False
        password = Mock()
        body = {"password": password}
        self.controller.root_create(req, body, tenant_id,
                                    instance_id, is_cluster)
        root_create.assert_called_with(context, instance_id,
                                       context.user, password)

    @patch.object(instance_models.Instance, "load")
    @patch.object(models.Root, "create")
    def test_root_create_on_master_instance(self, root_create, *args):
        user = Mock()
        context = Mock()
        context.user = Mock()
        context.user.__getitem__ = Mock(return_value=user)
        req = Mock()
        req.environ = Mock()
        req.environ.__getitem__ = Mock(return_value=context)
        tenant_id = self.tenant_id
        instance_id = self.master_db_info.id
        slave_instance_id = self.slave_db_info.id
        is_cluster = False
        password = Mock()
        body = {"password": password}
        self.controller.root_create(req, body, tenant_id,
                                    instance_id, is_cluster)
        root_create.assert_called_with(context, slave_instance_id,
                                       context.user, password)

    def test_root_create_on_slave(self):
        user = Mock()
        context = Mock()
        context.user = Mock()
        context.user.__getitem__ = Mock(return_value=user)
        req = Mock()
        req.environ = Mock()
        req.environ.__getitem__ = Mock(return_value=context)
        tenant_id = self.tenant_id
        instance_id = self.slave_db_info.id
        is_cluster = False
        body = {}
        self.assertRaises(
            exception.SlaveOperationNotSupported,
            self.controller.root_create,
            req, body, tenant_id, instance_id, is_cluster)

    def test_root_create_with_cluster(self):
        req = Mock()
        tenant_id = self.tenant_id
        instance_id = self.master_db_info.id
        is_cluster = True
        body = {}
        self.assertRaises(
            exception.ClusterOperationNotSupported,
            self.controller.root_create,
            req, body, tenant_id, instance_id, is_cluster)

    @patch.object(instance_models.Instance, "load")
    @patch.object(models.Root, "delete")
    def test_root_delete_on_single_instance(self, root_delete, *args):
        context = Mock()
        req = Mock()
        req.environ = Mock()
        req.environ.__getitem__ = Mock(return_value=context)
        tenant_id = self.tenant_id
        instance_id = self.single_db_info.id
        is_cluster = False
        self.controller.root_delete(req, tenant_id, instance_id, is_cluster)
        root_delete.assert_called_with(context, instance_id)

    @patch.object(instance_models.Instance, "load")
    @patch.object(models.Root, "delete")
    def test_root_delete_on_master_instance(self, root_delete, *args):
        context = Mock()
        req = Mock()
        req.environ = Mock()
        req.environ.__getitem__ = Mock(return_value=context)
        tenant_id = self.tenant_id
        instance_id = self.master_db_info.id
        slave_instance_id = self.slave_db_info.id
        is_cluster = False
        self.controller.root_delete(req, tenant_id, instance_id, is_cluster)
        root_delete.assert_called_with(context, slave_instance_id)

    def test_root_delete_on_slave(self):
        context = Mock()
        req = Mock()
        req.environ = Mock()
        req.environ.__getitem__ = Mock(return_value=context)
        tenant_id = self.tenant_id
        instance_id = self.slave_db_info.id
        is_cluster = False
        self.assertRaises(
            exception.SlaveOperationNotSupported,
            self.controller.root_delete,
            req, tenant_id, instance_id, is_cluster)

    def test_root_delete_with_cluster(self):
        req = Mock()
        tenant_id = self.tenant_id
        instance_id = self.master_db_info.id
        is_cluster = True
        self.assertRaises(
            exception.ClusterOperationNotSupported,
            self.controller.root_delete,
            req, tenant_id, instance_id, is_cluster)
