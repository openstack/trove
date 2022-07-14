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

from unittest.mock import Mock
from unittest.mock import patch

from trove.backup import models as backup_models
from trove.common import cfg
from trove.common import clients
from trove.common import exception
from trove.common import neutron
from trove.datastore import models as datastore_models
from trove.instance import models
from trove.instance.models import DBInstance
from trove.instance.models import DBInstanceFault
from trove.instance.models import Instance
from trove.instance.models import InstanceServiceStatus
from trove.instance.models import SimpleInstance
from trove.instance.models import instance_encryption_key_cache
from trove.instance.service_status import ServiceStatuses
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
        db_info.addresses = [{
            'type': 'private',
            'address': '123.123.123.123',
            'network': 'net-id-private'}, {
            'type': 'private',
            'address': '10.123.123.123',
            'network': 'net-id-private'}, {
            'type': 'public',
            'address': '15.123.123.123',
            'network': 'net-id-public'}]

        self.orig_ip_regex = CONF.ip_regex
        self.orig_black_list_regex = CONF.black_list_regex

    def tearDown(self):
        super(SimpleInstanceTest, self).tearDown()
        CONF.ip_start = None
        CONF.management_networks = []
        CONF.ip_regex = self.orig_ip_regex
        CONF.black_list_regex = self.orig_black_list_regex

        neutron.reset_management_networks()

    def test_get_root_on_create(self):
        root_on_create_val = Instance.get_root_on_create(
            'redis')
        self.assertFalse(root_on_create_val)

    def test_filter_ips_white_list(self):
        CONF.ip_regex = '^(15.|123.)'
        CONF.black_list_regex = '^10.123.123.*'
        ip = self.instance.get_visible_ip_addresses()
        self.assertEqual(2, len(ip))
        self.assertIn('123.123.123.123', ip[0].get('address'))
        self.assertIn('15.123.123.123', ip[1].get('address'))

    def test_filter_ips_black_list(self):
        CONF.ip_regex = '.*'
        CONF.black_list_regex = '^10.123.123.*'
        ip = self.instance.get_visible_ip_addresses()
        self.assertEqual(2, len(ip))
        self.assertNotIn('10.123.123.123', ip)

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
        self.backup_id = self.backup.id

        self.orig_client = clients.create_nova_client
        clients.create_nova_client = nova.fake_create_nova_client

        self.orig_api = task_api.API(self.context).create_instance
        task_api.API(self.context).create_instance = Mock()
        self.run_with_quotas = models.run_with_quotas
        models.run_with_quotas = Mock()
        self.check = backup_models.DBBackup.check_swift_object_exist
        backup_models.DBBackup.check_swift_object_exist = Mock(
            return_value=True)
        self.locality = 'affinity'

        self.swift_verify_patch = patch.object(models.Backup,
                                               'verify_swift_auth_token')
        self.addCleanup(self.swift_verify_patch.stop)
        self.swift_verify_patch.start()

        super(CreateInstanceTest, self).setUp()

    @patch.object(task_api.API, 'get_client', Mock(return_value=Mock()))
    def tearDown(self):
        self.db_info.delete()
        self.backup.delete()
        self.datastore.delete()
        self.datastore_version.delete()
        clients.create_nova_client = self.orig_client
        task_api.API(self.context).create_instance = self.orig_api
        models.run_with_quotas = self.run_with_quotas
        backup_models.DBBackup.check_swift_object_exist = self.check
        self.backup.delete()
        self.db_info.delete()
        super(CreateInstanceTest, self).tearDown()

    def test_exception_on_invalid_backup_size(self):
        self.backup.size = 1.1
        self.backup.save()
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

        self.safe_nova_client = clients.create_nova_client
        clients.create_nova_client = nova.fake_create_nova_client
        super(TestInstanceUpgrade, self).setUp()

    def tearDown(self):
        self.datastore.delete()
        self.datastore_version1.delete()
        self.datastore_version2.delete()
        clients.create_nova_client = self.safe_nova_client
        super(TestInstanceUpgrade, self).tearDown()

    @patch('trove.common.clients.create_neutron_client')
    @patch.object(task_api.API, 'get_client', Mock(return_value=Mock()))
    @patch.object(task_api.API, 'upgrade')
    @patch('trove.tests.fakes.nova.LOG')
    def test_upgrade(self, mock_logging, task_upgrade, mock_neutron_client):
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

        self.databases = []

        self.users = []

        self.master = DBInstance(
            InstanceTasks.NONE,
            id=str(uuid.uuid4()),
            name="TestMasterInstance",
            datastore_version_id=self.datastore_version.id,
            flavor_id=str(uuid.uuid4()),
            volume_size=2)
        self.master.set_task_status(InstanceTasks.NONE)
        self.master.save()
        self.master_status = InstanceServiceStatus(
            ServiceStatuses.RUNNING,
            id=str(uuid.uuid4()),
            instance_id=self.master.id)
        self.master_status.save()

        self.safe_nova_client = clients.create_nova_client
        clients.create_nova_client = nova.fake_create_nova_client

        self.swift_verify_patch = patch.object(models.Backup,
                                               'verify_swift_auth_token')
        self.addCleanup(self.swift_verify_patch.stop)
        self.swift_verify_patch.start()

        super(TestReplication, self).setUp()

    def tearDown(self):
        self.master.delete()
        self.master_status.delete()
        self.datastore.delete()
        self.datastore_version.delete()
        clients.create_nova_client = self.safe_nova_client
        super(TestReplication, self).tearDown()

    @patch('trove.instance.models.LOG')
    def test_replica_with_invalid_slave_of_id(self, mock_logging):
        self.assertRaises(exception.NotFound,
                          Instance.create,
                          None, 'name', 1, "UUID", [], [], self.datastore,
                          self.datastore_version, 2,
                          None, slave_of_id=str(uuid.uuid4()))


def trivial_key_function(id):
    return id * id


class TestInstanceKeyCaching(trove_testtools.TestCase):

    def setUp(self):
        super(TestInstanceKeyCaching, self).setUp()

    def tearDown(self):
        super(TestInstanceKeyCaching, self).tearDown()

    def test_basic_caching(self):
        keycache = instance_encryption_key_cache(trivial_key_function, 5)
        self.assertEqual(keycache[5], 25)
        self.assertEqual(keycache[5], 25)
        self.assertEqual(keycache[25], 625)

    def test_caching(self):
        keyfn = Mock(return_value=123)
        keycache = instance_encryption_key_cache(keyfn, 5)
        self.assertEqual(keycache[5], 123)
        self.assertEqual(keyfn.call_count, 1)
        self.assertEqual(keycache[5], 123)
        self.assertEqual(keyfn.call_count, 1)
        self.assertEqual(keycache[6], 123)
        self.assertEqual(keyfn.call_count, 2)
        self.assertEqual(keycache[7], 123)
        self.assertEqual(keyfn.call_count, 3)
        self.assertEqual(keycache[8], 123)
        self.assertEqual(keyfn.call_count, 4)
        self.assertEqual(keycache[9], 123)
        self.assertEqual(keyfn.call_count, 5)
        self.assertEqual(keycache[10], 123)
        self.assertEqual(keyfn.call_count, 6)
        self.assertEqual(keycache[10], 123)
        self.assertEqual(keyfn.call_count, 6)
        self.assertEqual(keycache[5], 123)
        self.assertEqual(keyfn.call_count, 7)

    # BUG(1650518): Cleanup in the Pike release
    def test_not_caching_none(self):
        keyfn = Mock(return_value=None)
        keycache = instance_encryption_key_cache(keyfn, 5)
        self.assertIsNone(keycache[30])
        self.assertEqual(keyfn.call_count, 1)
        self.assertIsNone(keycache[30])
        self.assertEqual(keyfn.call_count, 2)
