# Copyright 2013 Hewlett-Packard Development Company, L.P.
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

from mock import Mock
from mock import patch
from oslo_config.cfg import NoSuchOptError

from trove.common import exception
from trove.common import utils
from trove.extensions.common import models
from trove.extensions.common.service import ClusterRootController
from trove.extensions.common.service import DefaultRootController
from trove.extensions.common.service import RootController
from trove.instance import models as instance_models
from trove.instance.models import DBInstance
from trove.tests.unittests import trove_testtools


class TestDefaultRootController(trove_testtools.TestCase):

    def setUp(self):
        super(TestDefaultRootController, self).setUp()
        self.controller = DefaultRootController()

    @patch.object(models.Root, "load")
    def test_root_index(self, root_load):
        context = Mock()
        req = Mock()
        req.environ = Mock()
        req.environ.__getitem__ = Mock(return_value=context)
        tenant_id = Mock()
        uuid = utils.generate_uuid()
        is_cluster = False
        self.controller.root_index(req, tenant_id, uuid, is_cluster)
        root_load.assert_called_with(context, uuid)

    def test_root_index_with_cluster(self):
        req = Mock()
        tenant_id = Mock()
        uuid = utils.generate_uuid()
        is_cluster = True
        self.assertRaises(
            exception.ClusterOperationNotSupported,
            self.controller.root_index,
            req, tenant_id, uuid, is_cluster)

    @patch.object(models.Root, "create")
    def test_root_create(self, root_create):
        user = Mock()
        context = Mock()
        context.user = Mock()
        context.user.__getitem__ = Mock(return_value=user)
        req = Mock()
        req.environ = Mock()
        req.environ.__getitem__ = Mock(return_value=context)
        tenant_id = Mock()
        uuid = utils.generate_uuid()
        is_cluster = False
        password = Mock()
        body = {'password': password}
        self.controller.root_create(req, body, tenant_id, uuid, is_cluster)
        root_create.assert_called_with(context, uuid, password)

    def test_root_create_with_cluster(self):
        req = Mock()
        tenant_id = Mock()
        uuid = utils.generate_uuid()
        is_cluster = True
        password = Mock()
        body = {'password': password}
        self.assertRaises(
            exception.ClusterOperationNotSupported,
            self.controller.root_create,
            req, body, tenant_id, uuid, is_cluster)


class TestRootController(trove_testtools.TestCase):

    def setUp(self):
        super(TestRootController, self).setUp()
        self.context = trove_testtools.TroveTestContext(self)
        self.controller = RootController()

    @patch.object(instance_models.Instance, "load")
    @patch.object(RootController, "load_root_controller")
    @patch.object(RootController, "_get_datastore")
    def test_index(self, service_get_datastore, service_load_root_controller,
                   service_load_instance):
        req = Mock()
        req.environ = {'trove.context': self.context}
        tenant_id = Mock()
        uuid = utils.generate_uuid()
        ds_manager = Mock()
        is_cluster = False
        service_get_datastore.return_value = (ds_manager, is_cluster)
        root_controller = Mock()
        ret = Mock()
        root_controller.root_index = Mock(return_value=ret)
        service_load_root_controller.return_value = root_controller

        self.assertEqual(ret, self.controller.index(req, tenant_id, uuid))
        service_get_datastore.assert_called_with(tenant_id, uuid)
        service_load_root_controller.assert_called_with(ds_manager)
        root_controller.root_index.assert_called_with(
            req, tenant_id, uuid, is_cluster)

    @patch.object(instance_models.Instance, "load")
    @patch.object(RootController, "load_root_controller")
    @patch.object(RootController, "_get_datastore")
    def test_create(self, service_get_datastore, service_load_root_controller,
                    service_load_instance):
        req = Mock()
        req.environ = {'trove.context': self.context}
        body = Mock()
        tenant_id = Mock()
        uuid = utils.generate_uuid()
        ds_manager = Mock()
        is_cluster = False
        service_get_datastore.return_value = (ds_manager, is_cluster)
        root_controller = Mock()
        ret = Mock()
        root_controller.root_create = Mock(return_value=ret)
        service_load_root_controller.return_value = root_controller

        self.assertEqual(
            ret, self.controller.create(req, tenant_id, uuid, body=body))
        service_get_datastore.assert_called_with(tenant_id, uuid)
        service_load_root_controller.assert_called_with(ds_manager)
        root_controller.root_create.assert_called_with(
            req, body, tenant_id, uuid, is_cluster)

    @patch.object(instance_models.Instance, "load")
    @patch.object(RootController, "load_root_controller")
    @patch.object(RootController, "_get_datastore")
    def test_create_with_no_root_controller(self,
                                            service_get_datastore,
                                            service_load_root_controller,
                                            service_load_instance):
        req = Mock()
        req.environ = {'trove.context': self.context}
        body = Mock()
        tenant_id = Mock()
        uuid = utils.generate_uuid()
        ds_manager = Mock()
        is_cluster = False
        service_get_datastore.return_value = (ds_manager, is_cluster)
        service_load_root_controller.return_value = None

        self.assertRaises(
            NoSuchOptError,
            self.controller.create,
            req, tenant_id, uuid, body=body)
        service_get_datastore.assert_called_with(tenant_id, uuid)
        service_load_root_controller.assert_called_with(ds_manager)


class TestClusterRootController(trove_testtools.TestCase):

    def setUp(self):
        super(TestClusterRootController, self).setUp()
        self.context = trove_testtools.TroveTestContext(self)
        self.controller = ClusterRootController()

    @patch.object(ClusterRootController, "cluster_root_index")
    def test_root_index_cluster(self, mock_cluster_root_index):
        req = Mock()
        tenant_id = Mock()
        uuid = utils.generate_uuid()
        is_cluster = True
        self.controller.root_index(req, tenant_id, uuid, is_cluster)
        mock_cluster_root_index.assert_called_with(req, tenant_id, uuid)

    @patch.object(ClusterRootController, "instance_root_index")
    def test_root_index_instance(self, mock_instance_root_index):
        req = Mock()
        tenant_id = Mock()
        uuid = utils.generate_uuid()
        is_cluster = False
        self.controller.root_index(req, tenant_id, uuid, is_cluster)
        mock_instance_root_index.assert_called_with(req, tenant_id, uuid)

    @patch.object(ClusterRootController, "cluster_root_create")
    def test_root_create_cluster(self, mock_cluster_root_create):
        req = Mock()
        body = Mock()
        tenant_id = Mock()
        uuid = utils.generate_uuid()
        is_cluster = True
        self.controller.root_create(req, body, tenant_id, uuid, is_cluster)
        mock_cluster_root_create.assert_called_with(req, body, tenant_id, uuid)

    @patch.object(ClusterRootController, "check_cluster_instance_actions")
    @patch.object(ClusterRootController, "instance_root_create")
    def test_root_create_instance(self, mock_instance_root_create, mock_check):
        req = Mock()
        body = Mock()
        tenant_id = Mock()
        uuid = utils.generate_uuid()
        is_cluster = False
        self.controller.root_create(req, body, tenant_id, uuid, is_cluster)
        mock_check.assert_called_with(uuid)
        mock_instance_root_create.assert_called_with(req, body, uuid)

    @patch.object(models.ClusterRoot, "load")
    def test_instance_root_index(self, mock_cluster_root_load):
        req = Mock()
        req.environ = {'trove.context': self.context}
        tenant_id = Mock()
        instance_id = utils.generate_uuid()
        self.controller.instance_root_index(req, tenant_id, instance_id)
        mock_cluster_root_load.assert_called_with(self.context, instance_id)

    @patch.object(models.ClusterRoot, "load",
                  side_effect=exception.UnprocessableEntity())
    def test_instance_root_index_exception(self, mock_cluster_root_load):
        req = Mock()
        req.environ = {'trove.context': self.context}
        tenant_id = Mock()
        instance_id = utils.generate_uuid()
        self.assertRaises(
            exception.UnprocessableEntity,
            self.controller.instance_root_index,
            req, tenant_id, instance_id
        )
        mock_cluster_root_load.assert_called_with(self.context, instance_id)

    @patch.object(ClusterRootController, "instance_root_index")
    @patch.object(ClusterRootController, "_get_cluster_instance_id")
    def test_cluster_root_index(self, mock_get_cluster_instance,
                                mock_instance_root_index):
        req = Mock()
        tenant_id = Mock()
        cluster_id = utils.generate_uuid()
        single_instance_id = Mock()
        mock_get_cluster_instance.return_value = (single_instance_id, Mock())
        self.controller.cluster_root_index(req, tenant_id, cluster_id)
        mock_get_cluster_instance.assert_called_with(tenant_id, cluster_id)
        mock_instance_root_index.assert_called_with(req, tenant_id,
                                                    single_instance_id)

    @patch.object(ClusterRootController, "instance_root_create")
    @patch.object(ClusterRootController, "_get_cluster_instance_id")
    def test_cluster_root_create(self, mock_get_cluster_instance,
                                 mock_instance_root_create):
        req = Mock()
        body = Mock()
        tenant_id = Mock()
        cluster_id = utils.generate_uuid()
        single_instance_id = Mock()
        cluster_instances = Mock()
        mock_get_cluster_instance.return_value = (single_instance_id,
                                                  cluster_instances)
        self.controller.cluster_root_create(req, body, tenant_id, cluster_id)
        mock_get_cluster_instance.assert_called_with(tenant_id, cluster_id)
        mock_instance_root_create.assert_called_with(req, body,
                                                     single_instance_id,
                                                     cluster_instances)

    @patch.object(DBInstance, "find_all")
    def test_get_cluster_instance_id(self, mock_find_all):
        tenant_id = Mock()
        cluster_id = Mock()
        db_inst_1 = Mock()
        db_inst_1.id.return_value = utils.generate_uuid()
        db_inst_2 = Mock()
        db_inst_2.id.return_value = utils.generate_uuid()
        cluster_instances = [db_inst_1, db_inst_2]
        mock_find_all.return_value.all.return_value = cluster_instances
        ret = self.controller._get_cluster_instance_id(tenant_id, cluster_id)
        self.assertEqual(db_inst_1.id, ret[0])
        self.assertEqual([db_inst_1.id, db_inst_2.id], ret[1])

    @patch.object(models.ClusterRoot, "create")
    def test_instance_root_create(self, mock_cluster_root_create):
        user = Mock()
        self.context.user = Mock()
        self.context.user.__getitem__ = Mock(return_value=user)
        req = Mock()
        req.environ = {'trove.context': self.context}
        password = Mock()
        body = {'password': password}
        instance_id = utils.generate_uuid()
        cluster_instances = Mock()
        self.controller.instance_root_create(
            req, body, instance_id, cluster_instances)
        mock_cluster_root_create.assert_called_with(
            self.context, instance_id, password,
            cluster_instances)

    @patch.object(models.ClusterRoot, "create")
    def test_instance_root_create_no_body(self, mock_cluster_root_create):
        user = Mock()
        self.context.user = Mock()
        self.context.user.__getitem__ = Mock(return_value=user)
        req = Mock()
        req.environ = {'trove.context': self.context}
        password = None
        body = None
        instance_id = utils.generate_uuid()
        cluster_instances = Mock()
        self.controller.instance_root_create(
            req, body, instance_id, cluster_instances)
        mock_cluster_root_create.assert_called_with(
            self.context, instance_id, password,
            cluster_instances)
