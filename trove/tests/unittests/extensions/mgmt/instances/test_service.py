# Copyright 2020 Catalyst Cloud
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.
from unittest import mock

from trove.datastore import models as ds_models
from trove.extensions.mgmt.instances import service as ins_service
from trove.instance import models as ins_models
from trove.instance import service_status as srvstatus
from trove.tests.unittests import trove_testtools
from trove.tests.unittests.util import util


class TestMgmtInstanceController(trove_testtools.TestCase):
    @classmethod
    def setUpClass(cls):
        util.init_db()
        cls.controller = ins_service.MgmtInstanceController()

        cls.ds_name = cls.random_name('datastore')
        ds_models.update_datastore(name=cls.ds_name, default_version=None)
        ds_models.update_datastore_version(
            cls.ds_name, 'test_version', 'mysql', cls.random_uuid(), '', '', 1)
        cls.ds = ds_models.Datastore.load(cls.ds_name)
        cls.ds_version = ds_models.DatastoreVersion.load(cls.ds,
                                                         'test_version')

        cls.ins_name = cls.random_name('instance')
        cls.project_id = cls.random_uuid()
        cls.server_id = cls.random_uuid()
        cls.instance = ins_models.DBInstance.create(
            name=cls.ins_name, flavor_id=cls.random_uuid(),
            tenant_id=cls.project_id,
            volume_size=1,
            datastore_version_id=cls.ds_version.id,
            task_status=ins_models.InstanceTasks.BUILDING,
            compute_instance_id=cls.server_id
        )
        ins_models.InstanceServiceStatus.create(
            instance_id=cls.instance.id,
            status=srvstatus.ServiceStatuses.NEW
        )

        super(TestMgmtInstanceController, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        util.cleanup_db()

        super(TestMgmtInstanceController, cls).tearDownClass()

    @mock.patch('trove.common.clients.create_nova_client')
    def test_index_project_id(self, mock_create_client):
        req = mock.MagicMock()
        req.GET = {
            'project_id': self.project_id
        }

        mock_nova_client = mock.MagicMock()
        mock_nova_client.servers.list.return_value = [
            mock.MagicMock(id=self.server_id)]
        mock_create_client.return_value = mock_nova_client

        result = self.controller.index(req, mock.ANY)

        self.assertEqual(200, result.status)
        data = result.data(None)
        self.assertEqual(1, len(data['instances']))

        req.GET = {
            'project_id': self.random_uuid()
        }

        result = self.controller.index(req, mock.ANY)

        self.assertEqual(200, result.status)
        data = result.data(None)
        self.assertEqual(0, len(data['instances']))
