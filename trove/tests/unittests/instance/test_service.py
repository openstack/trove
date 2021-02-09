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
            cls.ds_name, 'test_image_id', 'mysql', cls.random_uuid(), '', 1)

        cls.ds_version_imageid = ds_models.DatastoreVersion.load(
            cls.ds, 'test_image_id')

        cls.controller = service.InstanceController()

        super(TestInstanceController, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        util.cleanup_db()

        super(TestInstanceController, cls).tearDownClass()

    def setUp(self):
        trove_testtools.patch_notifier(self)
        super(TestInstanceController, self).setUp()

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
        self.assertEqual('RESTART_REQUIRED', ret_instance.get('status'))

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
        self.assertEqual('ERROR', ret_instance.get('status'))
