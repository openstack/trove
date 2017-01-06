#    Copyright 2014 Rackspace Hosting
#    Copyright 2014 Hewlett-Packard Development Company, L.P.
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
import uuid

from mock import Mock, patch

from trove.backup import models as backup_models
from trove.common import cfg
from trove.common import crypto_utils
from trove.common import exception
from trove.common.instance import ServiceStatuses
from trove.datastore import models as datastore_models
from trove.instance import models
from trove.instance.models import DBInstance
from trove.instance.models import DBInstanceFault
from trove.instance.models import filter_ips
from trove.instance.models import Instance
from trove.instance.models import InstanceServiceStatus
from trove.instance.models import SimpleInstance
from trove.instance.tasks import InstanceTasks
from trove.taskmanager import api as task_api
from trove.tests.fakes import nova
from trove.tests.unittests import trove_testtools
from trove.tests.unittests.util import util

CONF = cfg.CONF


class SimpleInstanceTest(trove_testtools.TestCase):

    def setUp(self):
        super(SimpleInstanceTest, self).setUp()
        self.context = trove_testtools.TroveTestContext(self, is_admin=True)
        db_info = DBInstance(
            InstanceTasks.BUILDING, name="TestInstance")
        self.instance = SimpleInstance(
            None, db_info, InstanceServiceStatus(
                ServiceStatuses.BUILDING), ds_version=Mock(), ds=Mock(),
            locality='affinity')
        self.instance.context = self.context
        db_info.addresses = {"private": [{"addr": "123.123.123.123"}],
                             "internal": [{"addr": "10.123.123.123"}],
                             "public": [{"addr": "15.123.123.123"}]}
        self.orig_conf = CONF.network_label_regex
        self.orig_ip_regex = CONF.ip_regex
        self.orig_black_list_regex = CONF.black_list_regex

    def tearDown(self):
        super(SimpleInstanceTest, self).tearDown()
        CONF.network_label_regex = self.orig_conf
        CONF.ip_start = None

    def test_get_root_on_create(self):
        root_on_create_val = Instance.get_root_on_create(
            'redis')
        self.assertFalse(root_on_create_val)

    def test_filter_ips_white_list(self):
        CONF.network_label_regex = '.*'
        CONF.ip_regex = '^(15.|123.)'
        CONF.black_list_regex = '^10.123.123.*'
        ip = self.instance.get_visible_ip_addresses()
        ip = filter_ips(
            ip, CONF.ip_regex, CONF.black_list_regex)
        self.assertEqual(2, len(ip))
        self.assertIn('123.123.123.123', ip)
        self.assertIn('15.123.123.123', ip)

    def test_filter_ips_black_list(self):
        CONF.network_label_regex = '.*'
        CONF.ip_regex = '.*'
        CONF.black_list_regex = '^10.123.123.*'
        ip = self.instance.get_visible_ip_addresses()
        ip = filter_ips(
            ip, CONF.ip_regex, CONF.black_list_regex)
        self.assertEqual(2, len(ip))
        self.assertNotIn('10.123.123.123', ip)

    def test_one_network_label(self):
        CONF.network_label_regex = 'public'
        ip = self.instance.get_visible_ip_addresses()
        self.assertEqual(['15.123.123.123'], ip)

    def test_two_network_labels(self):
        CONF.network_label_regex = '^(private|public)$'
        ip = self.instance.get_visible_ip_addresses()
        self.assertEqual(2, len(ip))
        self.assertIn('123.123.123.123', ip)
        self.assertIn('15.123.123.123', ip)

    def test_all_network_labels(self):
        CONF.network_label_regex = '.*'
        ip = self.instance.get_visible_ip_addresses()
        self.assertEqual(3, len(ip))
        self.assertIn('10.123.123.123', ip)
        self.assertIn('123.123.123.123', ip)
        self.assertIn('15.123.123.123', ip)

    def test_locality(self):
        self.assertEqual('affinity', self.instance.locality)

    def test_fault(self):
        fault_message = 'Error'
        fault_details = 'details'
        fault_date = 'now'
        temp_fault = Mock()
        temp_fault.message = fault_message
        temp_fault.details = fault_details
        temp_fault.updated = fault_date
        fault_mock = Mock(return_value=temp_fault)
        with patch.object(DBInstanceFault, 'find_by', fault_mock):
            fault = self.instance.fault
            self.assertEqual(fault_message, fault.message)
            self.assertEqual(fault_details, fault.details)
            self.assertEqual(fault_date, fault.updated)


class CreateInstanceTest(trove_testtools.TestCase):

    @patch.object(task_api.API, 'get_client', Mock(return_value=Mock()))
    def setUp(self):
        util.init_db()
        self.context = trove_testtools.TroveTestContext(self, is_admin=True)
        self.name = "name"
        self.flavor_id = 5
        self.image_id = "UUID"
        self.databases = []
        self.users = []
        self.datastore = datastore_models.DBDatastore.create(
            id=str(uuid.uuid4()),
            name='mysql' + str(uuid.uuid4()),
        )
        self.datastore_version = (
            datastore_models.DBDatastoreVersion.create(
                id=str(uuid.uuid4()),
                datastore_id=self.datastore.id,
                name="5.5" + str(uuid.uuid4()),
                manager="mysql",
                image_id="image_id",
                packages="",
                active=True))
        self.volume_size = 1
        self.az = "az"
        self.nics = None
        self.configuration = None
        self.tenant_id = "UUID"
        self.datastore_version_id = str(uuid.uuid4())

        self.db_info = DBInstance.create(
            name=self.name, flavor_id=self.flavor_id,
            tenant_id=self.tenant_id,
            volume_size=self.volume_size,
            datastore_version_id=self.datastore_version.id,
            task_status=InstanceTasks.BUILDING,
            configuration_id=self.configuration
        )

        self.backup_name = "name"
        self.descr = None
        self.backup_state = backup_models.BackupState.COMPLETED
        self.instance_id = self.db_info.id
        self.parent_id = None
        self.deleted = False

        self.backup = backup_models.DBBackup.create(
            name=self.backup_name,
            description=self.descr,
            tenant_id=self.tenant_id,
            state=self.backup_state,
            instance_id=self.instance_id,
            parent_id=self.parent_id,
            datastore_version_id=self.datastore_version.id,
            deleted=False
        )
        self.backup.size = 1.1
        self.backup.save()
        self.backup_id = self.backup.id
        self.orig_client = models.create_nova_client
        models.create_nova_client = nova.fake_create_nova_client
        self.orig_api = task_api.API(self.context).create_instance
        task_api.API(self.context).create_instance = Mock()
        self.run_with_quotas = models.run_with_quotas
        models.run_with_quotas = Mock()
        self.check = backup_models.DBBackup.check_swift_object_exist
        backup_models.DBBackup.check_swift_object_exist = Mock(
            return_value=True)
        self.locality = 'affinity'
        super(CreateInstanceTest, self).setUp()

    @patch.object(task_api.API, 'get_client', Mock(return_value=Mock()))
    def tearDown(self):
        self.db_info.delete()
        self.backup.delete()
        self.datastore.delete()
        self.datastore_version.delete()
        models.create_nova_client = self.orig_client
        task_api.API(self.context).create_instance = self.orig_api
        models.run_with_quotas = self.run_with_quotas
        backup_models.DBBackup.check_swift_object_exist = self.check
        self.backup.delete()
        self.db_info.delete()
        super(CreateInstanceTest, self).tearDown()

    def test_exception_on_invalid_backup_size(self):
        self.assertEqual(self.backup.id, self.backup_id)
        exc = self.assertRaises(
            exception.BackupTooLarge, models.Instance.create,
            self.context, self.name, self.flavor_id,
            self.image_id, self.databases, self.users,
            self.datastore, self.datastore_version,
            self.volume_size, self.backup_id,
            self.az, self.nics, self.configuration
        )
        self.assertIn("Backup is too large for "
                      "given flavor or volume.", str(exc))

    def test_can_restore_from_backup_with_almost_equal_size(self):
        # target size equals to "1Gb"
        self.backup.size = 0.99
        self.backup.save()
        instance = models.Instance.create(
            self.context, self.name, self.flavor_id,
            self.image_id, self.databases, self.users,
            self.datastore, self.datastore_version,
            self.volume_size, self.backup_id,
            self.az, self.nics, self.configuration)
        self.assertIsNotNone(instance)

    def test_can_instantiate_with_locality(self):
        # make sure the backup will fit
        self.backup.size = 0.2
        self.backup.save()
        instance = models.Instance.create(
            self.context, self.name, self.flavor_id,
            self.image_id, self.databases, self.users,
            self.datastore, self.datastore_version,
            self.volume_size, self.backup_id,
            self.az, self.nics, self.configuration,
            locality=self.locality)
        self.assertIsNotNone(instance)


class TestInstanceUpgrade(trove_testtools.TestCase):

    def setUp(self):
        self.context = trove_testtools.TroveTestContext(self, is_admin=True)
        util.init_db()

        self.datastore = datastore_models.DBDatastore.create(
            id=str(uuid.uuid4()),
            name='test' + str(uuid.uuid4()),
            default_version_id=str(uuid.uuid4()))

        self.datastore_version1 = datastore_models.DBDatastoreVersion.create(
            id=self.datastore.default_version_id,
            name='name' + str(uuid.uuid4()),
            image_id='old_image',
            packages=str(uuid.uuid4()),
            datastore_id=self.datastore.id,
            manager='test',
            active=1)

        self.datastore_version2 = datastore_models.DBDatastoreVersion.create(
            id=str(uuid.uuid4()),
            name='name' + str(uuid.uuid4()),
            image_id='new_image',
            packages=str(uuid.uuid4()),
            datastore_id=self.datastore.id,
            manager='test',
            active=1)

        self.safe_nova_client = models.create_nova_client
        models.create_nova_client = nova.fake_create_nova_client
        super(TestInstanceUpgrade, self).setUp()

    def tearDown(self):
        self.datastore.delete()
        self.datastore_version1.delete()
        self.datastore_version2.delete()
        models.create_nova_client = self.safe_nova_client
        super(TestInstanceUpgrade, self).tearDown()

    @patch.object(task_api.API, 'get_client', Mock(return_value=Mock()))
    @patch.object(task_api.API, 'upgrade')
    @patch('trove.tests.fakes.nova.LOG')
    def test_upgrade(self, mock_logging, task_upgrade):
        instance_model = DBInstance(
            InstanceTasks.NONE,
            id=str(uuid.uuid4()),
            name="TestUpgradeInstance",
            datastore_version_id=self.datastore_version1.id)
        instance_model.set_task_status(InstanceTasks.NONE)
        instance_model.save()
        instance_status = InstanceServiceStatus(
            ServiceStatuses.RUNNING,
            id=str(uuid.uuid4()),
            instance_id=instance_model.id)
        instance_status.save()
        self.assertIsNotNone(instance_model)
        instance = models.load_instance(models.Instance, self.context,
                                        instance_model.id)

        try:
            instance.upgrade(self.datastore_version2)

            self.assertEqual(self.datastore_version2.id,
                             instance.db_info.datastore_version_id)
            self.assertEqual(InstanceTasks.UPGRADING,
                             instance.db_info.task_status)
            self.assertTrue(task_upgrade.called)
        finally:
            instance_status.delete()
            instance_model.delete()


class TestReplication(trove_testtools.TestCase):

    def setUp(self):
        util.init_db()

        self.datastore = datastore_models.DBDatastore.create(
            id=str(uuid.uuid4()),
            name='name' + str(uuid.uuid4()),
            default_version_id=str(uuid.uuid4()))

        self.datastore_version = datastore_models.DBDatastoreVersion.create(
            id=self.datastore.default_version_id,
            name='name' + str(uuid.uuid4()),
            image_id=str(uuid.uuid4()),
            packages=str(uuid.uuid4()),
            datastore_id=self.datastore.id,
            manager='mysql',
            active=1)

        self.master = DBInstance(
            InstanceTasks.NONE,
            id=str(uuid.uuid4()),
            name="TestMasterInstance",
            datastore_version_id=self.datastore_version.id)
        self.master.set_task_status(InstanceTasks.NONE)
        self.master.save()
        self.master_status = InstanceServiceStatus(
            ServiceStatuses.RUNNING,
            id=str(uuid.uuid4()),
            instance_id=self.master.id)
        self.master_status.save()

        self.safe_nova_client = models.create_nova_client
        models.create_nova_client = nova.fake_create_nova_client
        super(TestReplication, self).setUp()

    def tearDown(self):
        self.master.delete()
        self.master_status.delete()
        self.datastore.delete()
        self.datastore_version.delete()
        models.create_nova_client = self.safe_nova_client
        super(TestReplication, self).tearDown()

    @patch('trove.instance.models.LOG')
    def test_replica_of_not_active_master(self, mock_logging):
        self.master.set_task_status(InstanceTasks.BUILDING)
        self.master.save()
        self.master_status.set_status(ServiceStatuses.BUILDING)
        self.master_status.save()
        self.assertRaises(exception.UnprocessableEntity,
                          Instance.create,
                          None, 'name', 1, "UUID", [], [], None,
                          self.datastore_version, 1,
                          None, slave_of_id=self.master.id)

    @patch('trove.instance.models.LOG')
    def test_replica_with_invalid_slave_of_id(self, mock_logging):
        self.assertRaises(exception.NotFound,
                          Instance.create,
                          None, 'name', 1, "UUID", [], [], None,
                          self.datastore_version, 1,
                          None, slave_of_id=str(uuid.uuid4()))

    def test_create_replica_from_replica(self):
        self.replica_datastore_version = Mock(
            spec=datastore_models.DBDatastoreVersion)
        self.replica_datastore_version.id = "UUID"
        self.replica_datastore_version.manager = 'mysql'
        self.replica_info = DBInstance(
            InstanceTasks.NONE,
            id="UUID",
            name="TestInstance",
            datastore_version_id=self.replica_datastore_version.id,
            slave_of_id=self.master.id)
        self.replica_info.save()
        self.assertRaises(exception.Forbidden, Instance.create,
                          None, 'name', 2, "UUID", [], [], None,
                          self.datastore_version, 1,
                          None, slave_of_id=self.replica_info.id)


class TestModules(trove_testtools.TestCase):

    def setUp(self):
        super(TestModules, self).setUp()

    def tearDown(self):
        super(TestModules, self).tearDown()

    def _build_module(self, ds_id, ds_ver_id):
        module = Mock()
        module.datastore_id = ds_id
        module.datastore_version_id = ds_ver_id
        module.contents = crypto_utils.encode_data(
            crypto_utils.encrypt_data(
                'VGhpc2lzbXlkYXRhc3RyaW5n',
                'thisismylongkeytouse'))
        return module

    def test_validate_modules_for_apply(self):
        data = [
            [[self._build_module('ds', 'ds_ver')], 'ds', 'ds_ver', True],
            [[self._build_module('ds', None)], 'ds', 'ds_ver', True],
            [[self._build_module(None, None)], 'ds', 'ds_ver', True],

            [[self._build_module('ds', 'ds_ver')], 'ds', 'ds2_ver', False,
             exception.TroveError],
            [[self._build_module('ds', 'ds_ver')], 'ds2', 'ds_ver', False,
             exception.TroveError],
            [[self._build_module('ds', 'ds_ver')], 'ds2', 'ds2_ver', False,
             exception.TroveError],
            [[self._build_module('ds', None)], 'ds2', 'ds2_ver', False,
             exception.TroveError],
            [[self._build_module(None, None)], 'ds2', 'ds2_ver', True],

            [[self._build_module(None, 'ds_ver')], 'ds2', 'ds_ver', True],
        ]
        for datum in data:
            modules = datum[0]
            ds_id = datum[1]
            ds_ver_id = datum[2]
            match = datum[3]
            expected_exception = None
            if not match:
                expected_exception = datum[4]
            ds = Mock()
            ds.id = ds_id
            ds.name = ds_id
            ds_ver = Mock()
            ds_ver.id = ds_ver_id
            ds_ver.name = ds_ver_id
            ds_ver.datastore_id = ds_id
            with patch.object(datastore_models.Datastore, 'load',
                              return_value=ds):
                with patch.object(datastore_models.DatastoreVersion, 'load',
                                  return_value=ds_ver):
                    if match:
                        models.validate_modules_for_apply(
                            modules, ds_id, ds_ver_id)
                    else:
                        self.assertRaises(
                            expected_exception,
                            models.validate_modules_for_apply,
                            modules, ds_id, ds_ver_id)
