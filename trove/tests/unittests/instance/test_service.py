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
from datetime import timedelta
from unittest import mock

from trove.common import cfg
from trove.common import clients
from trove.common import exception
from trove.common import timeutils
from trove.datastore import models as ds_models
from trove.instance import models as ins_models
from trove.instance import service
from trove.instance import service_status as srvstatus
from trove.tests.unittests import trove_testtools
from trove.tests.unittests.util import util

CONF = cfg.CONF


class TestInstanceController(trove_testtools.TestCase):
    @classmethod
    def setUpClass(cls):
        util.init_db()

        cls.ds_name = cls.random_name('datastore',
                                      prefix='TestInstanceController')
        ds_models.update_datastore(name=cls.ds_name, default_version=None)
        cls.ds = ds_models.Datastore.load(cls.ds_name)

        ds_models.update_datastore_version(
            cls.ds_name, 'test_image_id', 'mysql', cls.random_uuid(), [], '',
            1)
        ds_models.update_datastore_version(
            cls.ds_name, 'test_image_tags', 'mysql', '', ['trove', 'mysql'],
            '', 1, version='test_image_tags version')
        ds_models.update_datastore_version(
            cls.ds_name, 'test_version', 'mysql', '', ['trove'], '', 1,
            version='version 1')
        ds_models.update_datastore_version(
            cls.ds_name, 'test_version', 'mysql', '', ['trove'], '', 1,
            version='version 2')

        cls.ds_version_imageid = ds_models.DatastoreVersion.load(
            cls.ds, 'test_image_id')
        cls.ds_version_imagetags = ds_models.DatastoreVersion.load(
            cls.ds, 'test_image_tags')

        cls.controller = service.InstanceController()

        super(TestInstanceController, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        util.cleanup_db()

        super(TestInstanceController, cls).tearDownClass()

    def setUp(self):
        trove_testtools.patch_notifier(self)
        super(TestInstanceController, self).setUp()

    @mock.patch.object(clients, 'create_glance_client')
    @mock.patch('trove.instance.models.Instance.create')
    def test_create_by_ds_version_image_tags(self, mock_model_create,
                                             mock_create_client):
        image_id = self.random_uuid()
        mock_glance_client = mock.MagicMock()
        mock_glance_client.images.list.return_value = [{'id': image_id}]
        mock_create_client.return_value = mock_glance_client

        name = self.random_name(name='instance',
                                prefix='TestInstanceController')
        flavor = self.random_uuid()
        body = {
            'instance': {
                'name': name,
                'flavorRef': flavor,
                'datastore': {
                    'type': self.ds_name,
                    'version': self.ds_version_imagetags.name,
                    'version_number': self.ds_version_imagetags.version
                }
            }
        }
        ret = self.controller.create(mock.MagicMock(), body, mock.ANY)

        self.assertEqual(200, ret.status)
        mock_glance_client.images.list.assert_called_once_with(
            filters={'tag': ['trove', 'mysql'], 'status': 'active'},
            sort='created_at:desc', limit=1
        )

        mock_model_create.assert_called_once_with(
            mock.ANY, name, flavor, image_id,
            [], [],
            mock.ANY, mock.ANY,
            None, None, None, [], None, None,
            replica_count=None, volume_type=None, modules=None, locality=None,
            region_name=CONF.service_credentials.region_name, access=None
        )
        args = mock_model_create.call_args[0]
        actual_ds_version = args[7]
        self.assertEqual(self.ds_version_imagetags.name,
                         actual_ds_version.name)
        self.assertEqual(self.ds_version_imagetags.version,
                         actual_ds_version.version)

    def test_create_multiple_versions(self):
        body = {
            'instance': {
                'name': self.random_name(name='instance',
                                         prefix='TestInstanceController'),
                'flavorRef': self.random_uuid(),
                'datastore': {
                    'type': self.ds_name,
                    'version': 'test_version'
                }
            }
        }

        self.assertRaises(
            exception.DatastoreVersionsNoUniqueMatch,
            self.controller.create,
            mock.MagicMock(), body, mock.ANY
        )

    @mock.patch.object(clients, 'create_nova_client',
                       return_value=mock.MagicMock())
    @mock.patch('trove.rpc.get_client')
    def test_update_datastore_version(self, mock_get_rpc_client,
                                      mock_create_nova_client):
        # Create an instance in db.
        instance = ins_models.DBInstance.create(
            name=self.random_name('instance'),
            flavor_id=self.random_uuid(),
            tenant_id=self.random_uuid(),
            volume_size=1,
            datastore_version_id=self.ds_version_imageid.id,
            task_status=ins_models.InstanceTasks.BUILDING,
            compute_instance_id=self.random_uuid()
        )
        ins_models.InstanceServiceStatus.create(
            instance_id=instance.id,
            status=srvstatus.ServiceStatuses.NEW
        )

        # Create a new datastore version in db.
        new_version_name = self.random_name('version')
        ds_models.update_datastore_version(
            self.ds_name, new_version_name,
            'mysql', self.random_uuid(), [], '', 1
        )
        new_ds_version = ds_models.DatastoreVersion.load(
            self.ds, new_version_name)

        body = {
            'instance': {
                'datastore_version': new_ds_version.id
            }
        }
        self.controller.update(mock.MagicMock(), instance.id, body, mock.ANY)

        rpc_ctx = mock_get_rpc_client.return_value.prepare.return_value
        rpc_ctx.cast.assert_called_once_with(
            mock.ANY, "upgrade",
            instance_id=instance.id,
            datastore_version_id=new_ds_version.id)

    @mock.patch('trove.instance.models.load_server_group_info')
    @mock.patch('trove.instance.models.load_guest_info')
    @mock.patch('trove.instance.models.load_simple_instance_addresses')
    @mock.patch('trove.instance.models.load_simple_instance_server_status')
    def test_show_with_restart_required(self, load_server_mock,
                                        load_addr_mock, load_guest_mock,
                                        load_server_grp_mock):
        # Create an instance in db.
        instance = ins_models.DBInstance.create(
            name=self.random_name('instance'),
            flavor_id=self.random_uuid(),
            tenant_id=self.random_uuid(),
            volume_size=1,
            datastore_version_id=self.ds_version_imageid.id,
            task_status=ins_models.InstanceTasks.NONE,
            compute_instance_id=self.random_uuid(),
            server_status='ACTIVE'
        )
        ins_models.InstanceServiceStatus.create(
            instance_id=instance.id,
            status=srvstatus.ServiceStatuses.RESTART_REQUIRED,
        )

        # workaround to reset updated_at field.
        service_status = ins_models.InstanceServiceStatus.find_by(
            instance_id=instance.id)
        service_status.updated_at = timeutils.utcnow() - timedelta(
            seconds=(CONF.agent_heartbeat_expiry + 60))
        ins_models.get_db_api().save(service_status)

        ret = self.controller.show(mock.MagicMock(), mock.ANY, instance.id)
        self.assertEqual(200, ret.status)

        ret_instance = ret.data(None)['instance']

        self.assertEqual('ACTIVE', ret_instance.get('status'))
        self.assertEqual('RESTART_REQUIRED',
                         ret_instance.get('operating_status'))

    @mock.patch('trove.instance.models.load_server_group_info')
    @mock.patch('trove.instance.models.load_guest_info')
    @mock.patch('trove.instance.models.load_simple_instance_addresses')
    @mock.patch('trove.instance.models.load_simple_instance_server_status')
    def test_show_without_restart_required(self, load_server_mock,
                                           load_addr_mock, load_guest_mock,
                                           load_server_grp_mock):
        # Create an instance in db.
        instance = ins_models.DBInstance.create(
            name=self.random_name('instance'),
            flavor_id=self.random_uuid(),
            tenant_id=self.random_uuid(),
            volume_size=1,
            datastore_version_id=self.ds_version_imageid.id,
            task_status=ins_models.InstanceTasks.NONE,
            compute_instance_id=self.random_uuid(),
            server_status='ACTIVE'
        )
        ins_models.InstanceServiceStatus.create(
            instance_id=instance.id,
            status=srvstatus.ServiceStatuses.HEALTHY,
        )

        # workaround to reset updated_at field.
        service_status = ins_models.InstanceServiceStatus.find_by(
            instance_id=instance.id)
        service_status.updated_at = timeutils.utcnow() - timedelta(
            seconds=(CONF.agent_heartbeat_expiry + 60))
        ins_models.get_db_api().save(service_status)

        ret = self.controller.show(mock.MagicMock(), mock.ANY, instance.id)
        self.assertEqual(200, ret.status)

        ret_instance = ret.data(None)['instance']

        self.assertEqual('ACTIVE', ret_instance.get('status'))
        self.assertEqual('ERROR', ret_instance.get('operating_status'))
