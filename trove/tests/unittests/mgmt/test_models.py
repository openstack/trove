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
import uuid

from mock import MagicMock, patch, ANY
from novaclient.v2 import Client
from novaclient.v2.flavors import FlavorManager, Flavor
from novaclient.v2.servers import Server, ServerManager
from oslo_config import cfg
from testtools.matchers import Equals, Is, Not

from trove.backup.models import Backup
from trove.common.context import TroveContext
from trove.common import exception
from trove.common import instance as rd_instance
from trove.common import remote
from trove.datastore import models as datastore_models
import trove.extensions.mgmt.instances.models as mgmtmodels
from trove.guestagent.api import API
from trove.instance.models import DBInstance
from trove.instance.models import InstanceServiceStatus
from trove.instance.tasks import InstanceTasks
from trove import rpc
from trove.tests.unittests import trove_testtools
from trove.tests.unittests.util import util

CONF = cfg.CONF


class MockMgmtInstanceTest(trove_testtools.TestCase):

    @classmethod
    def setUpClass(cls):
        util.init_db()
        cls.version_id = str(uuid.uuid4())
        cls.datastore = datastore_models.DBDatastore.create(
            id=str(uuid.uuid4()),
            name='mysql',
            default_version_id=cls.version_id
        )
        cls.version = datastore_models.DBDatastoreVersion.create(
            id=cls.version_id,
            datastore_id=cls.datastore.id,
            name='5.5',
            manager='mysql',
            image_id=str(uuid.uuid4()),
            active=1,
            packages="mysql-server-5.5"
        )
        super(MockMgmtInstanceTest, cls).setUpClass()

    def setUp(self):
        self.context = TroveContext()
        self.context.auth_token = 'some_secret_password'
        self.client = MagicMock(spec=Client)
        self.server_mgr = MagicMock(spec=ServerManager)
        self.client.servers = self.server_mgr
        self.flavor_mgr = MagicMock(spec=FlavorManager)
        self.client.flavors = self.flavor_mgr
        remote.create_admin_nova_client = MagicMock(return_value=self.client)
        CONF.set_override('host', 'test_host')
        CONF.set_override('exists_notification_ticks', 1)
        CONF.set_override('report_interval', 20)
        CONF.set_override('notification_service_id', {'mysql': '123'})

        super(MockMgmtInstanceTest, self).setUp()

    def do_cleanup(self, instance, status):
        instance.delete()
        status.delete()

    def build_db_instance(self, status, task_status=InstanceTasks.NONE):
        version = datastore_models.DBDatastoreVersion.get_by(name='5.5')
        instance = DBInstance(InstanceTasks.NONE,
                              name='test_name',
                              id=str(uuid.uuid4()),
                              flavor_id='flavor_1',
                              datastore_version_id=version.id,
                              compute_instance_id='compute_id_1',
                              server_id='server_id_1',
                              tenant_id='tenant_id_1',
                              server_status=rd_instance.ServiceStatuses.
                              BUILDING.api_status,
                              deleted=False)
        instance.save()
        service_status = InstanceServiceStatus(
            rd_instance.ServiceStatuses.RUNNING,
            id=str(uuid.uuid4()),
            instance_id=instance.id,
        )
        service_status.save()
        instance.set_task_status(task_status)
        instance.server_status = status
        instance.save()
        return instance, service_status


class TestNotificationTransformer(MockMgmtInstanceTest):

    @classmethod
    def setUpClass(cls):
        super(TestNotificationTransformer, cls).setUpClass()

    def test_tranformer(self):
        status = rd_instance.ServiceStatuses.BUILDING.api_status
        instance, service_status = self.build_db_instance(
            status, InstanceTasks.BUILDING)
        payloads = mgmtmodels.NotificationTransformer(
            context=self.context)()
        self.assertIsNotNone(payloads)
        payload = payloads[0]
        self.assertThat(payload['audit_period_beginning'],
                        Not(Is(None)))
        self.assertThat(payload['audit_period_ending'], Not(Is(None)))
        self.assertTrue(status.lower() in [db['state'] for db in payloads])
        self.addCleanup(self.do_cleanup, instance, service_status)

    def test_get_service_id(self):
        id_map = {
            'mysql': '123',
            'percona': 'abc'
        }
        transformer = mgmtmodels.NotificationTransformer(context=self.context)
        self.assertThat(transformer._get_service_id('mysql', id_map),
                        Equals('123'))

    def test_get_service_id_unknown(self):
        id_map = {
            'mysql': '123',
            'percona': 'abc'
        }
        transformer = mgmtmodels.NotificationTransformer(context=self.context)
        self.assertThat(transformer._get_service_id('m0ng0', id_map),
                        Equals('unknown-service-id-error'))


class TestNovaNotificationTransformer(MockMgmtInstanceTest):

    @classmethod
    def setUpClass(cls):
        super(TestNovaNotificationTransformer, cls).setUpClass()

    def test_transformer_cache(self):
        flavor = MagicMock(spec=Flavor)
        flavor.name = 'db.small'
        with patch.object(self.flavor_mgr, 'get', return_value=flavor):
            transformer = mgmtmodels.NovaNotificationTransformer(
                context=self.context)
            transformer2 = mgmtmodels.NovaNotificationTransformer(
                context=self.context)
            self.assertThat(transformer._flavor_cache,
                            Not(Is(transformer2._flavor_cache)))

    def test_lookup_flavor(self):
        flavor = MagicMock(spec=Flavor)
        flavor.name = 'flav_1'
        transformer = mgmtmodels.NovaNotificationTransformer(
            context=self.context)
        with patch.object(self.flavor_mgr, 'get', side_effect=[flavor, None]):
            self.assertThat(transformer._lookup_flavor('1'),
                            Equals(flavor.name))
            self.assertThat(transformer._lookup_flavor('2'),
                            Equals('unknown'))

    def test_tranformer(self):
        status = rd_instance.ServiceStatuses.BUILDING.api_status
        instance, service_status = self.build_db_instance(
            status, InstanceTasks.BUILDING)

        flavor = MagicMock(spec=Flavor)
        flavor.name = 'db.small'

        server = MagicMock(spec=Server)
        server.user_id = 'test_user_id'
        transformer = mgmtmodels.NovaNotificationTransformer(
            context=self.context)
        mgmt_instance = mgmtmodels.SimpleMgmtInstance(self.context,
                                                      instance,
                                                      server,
                                                      service_status)

        with patch.object(mgmtmodels, 'load_mgmt_instances',
                          return_value=[mgmt_instance]):
            with patch.object(self.flavor_mgr, 'get', return_value=flavor):

                payloads = transformer()

                self.assertIsNotNone(payloads)
                payload = payloads[0]
                self.assertThat(payload['audit_period_beginning'],
                                Not(Is(None)))
                self.assertThat(payload['audit_period_ending'],
                                Not(Is(None)))
                self.assertThat(payload['state'], Not(Is(None)))
                self.assertThat(payload['instance_type'],
                                Equals('db.small'))
                self.assertThat(payload['instance_type_id'],
                                Equals('flavor_1'))
                self.assertThat(payload['user_id'], Equals('test_user_id'))
                self.assertThat(payload['service_id'], Equals('123'))
        self.addCleanup(self.do_cleanup, instance, service_status)

    def test_tranformer_invalid_datastore_manager(self):
        status = rd_instance.ServiceStatuses.BUILDING.api_status
        instance, service_status = self.build_db_instance(
            status, InstanceTasks.BUILDING)
        version = datastore_models.DBDatastoreVersion.get_by(
            id=instance.datastore_version_id)
        version.update(manager='something invalid')
        server = MagicMock(spec=Server)
        server.user_id = 'test_user_id'

        flavor = MagicMock(spec=Flavor)
        flavor.name = 'db.small'

        mgmt_instance = mgmtmodels.SimpleMgmtInstance(self.context,
                                                      instance,
                                                      server,
                                                      service_status)
        transformer = mgmtmodels.NovaNotificationTransformer(
            context=self.context)
        with patch.object(mgmtmodels, 'load_mgmt_instances',
                          return_value=[mgmt_instance]):
            with patch.object(self.flavor_mgr,
                              'get', return_value=flavor):
                payloads = transformer()
                # assertions
                self.assertIsNotNone(payloads)
                payload = payloads[0]
                self.assertThat(payload['audit_period_beginning'],
                                Not(Is(None)))
                self.assertThat(payload['audit_period_ending'],
                                Not(Is(None)))
                self.assertIn(status.lower(),
                              [db['state']
                              for db in payloads])
                self.assertThat(payload['instance_type'],
                                Equals('db.small'))
                self.assertThat(payload['instance_type_id'],
                                Equals('flavor_1'))
                self.assertThat(payload['user_id'],
                                Equals('test_user_id'))
                self.assertThat(payload['service_id'],
                                Equals('unknown-service-id-error'))
        version.update(manager='mysql')
        self.addCleanup(self.do_cleanup, instance, service_status)

    def test_tranformer_shutdown_instance(self):
        status = rd_instance.ServiceStatuses.SHUTDOWN.api_status
        instance, service_status = self.build_db_instance(status)
        service_status.set_status(rd_instance.ServiceStatuses.SHUTDOWN)
        server = MagicMock(spec=Server)
        server.user_id = 'test_user_id'

        mgmt_instance = mgmtmodels.SimpleMgmtInstance(self.context,
                                                      instance,
                                                      server,
                                                      service_status)
        flavor = MagicMock(spec=Flavor)
        flavor.name = 'db.small'
        transformer = mgmtmodels.NovaNotificationTransformer(
            context=self.context)
        with patch.object(Backup, 'running', return_value=None):
            self.assertThat(mgmt_instance.status, Equals('SHUTDOWN'))
            with patch.object(mgmtmodels, 'load_mgmt_instances',
                              return_value=[mgmt_instance]):
                with patch.object(self.flavor_mgr, 'get', return_value=flavor):
                    payloads = transformer()
                    # assertion that SHUTDOWN instances are not reported
                    self.assertIsNotNone(payloads)
                    self.assertNotIn(status.lower(),
                                     [db['status']
                                      for db in payloads])
        self.addCleanup(self.do_cleanup, instance, service_status)

    def test_tranformer_no_nova_instance(self):
        status = rd_instance.ServiceStatuses.SHUTDOWN.api_status
        instance, service_status = self.build_db_instance(status)
        service_status.set_status(rd_instance.ServiceStatuses.SHUTDOWN)
        mgmt_instance = mgmtmodels.SimpleMgmtInstance(self.context,
                                                      instance,
                                                      None,
                                                      service_status)
        flavor = MagicMock(spec=Flavor)
        flavor.name = 'db.small'
        transformer = mgmtmodels.NovaNotificationTransformer(
            context=self.context)
        with patch.object(Backup, 'running', return_value=None):
            self.assertThat(mgmt_instance.status, Equals('SHUTDOWN'))
            with patch.object(mgmtmodels, 'load_mgmt_instances',
                              return_value=[mgmt_instance]):
                with patch.object(self.flavor_mgr, 'get', return_value=flavor):
                    payloads = transformer()
                    # assertion that SHUTDOWN instances are not reported
                    self.assertIsNotNone(payloads)
                    self.assertNotIn(status.lower(),
                                     [db['status']
                                      for db in payloads])
        self.addCleanup(self.do_cleanup, instance, service_status)

    def test_tranformer_flavor_cache(self):
        status = rd_instance.ServiceStatuses.BUILDING.api_status
        instance, service_status = self.build_db_instance(
            status, InstanceTasks.BUILDING)

        server = MagicMock(spec=Server)
        server.user_id = 'test_user_id'
        mgmt_instance = mgmtmodels.SimpleMgmtInstance(self.context,
                                                      instance,
                                                      server,
                                                      service_status)
        flavor = MagicMock(spec=Flavor)
        flavor.name = 'db.small'
        transformer = mgmtmodels.NovaNotificationTransformer(
            context=self.context)
        with patch.object(mgmtmodels, 'load_mgmt_instances',
                          return_value=[mgmt_instance]):
            with patch.object(self.flavor_mgr, 'get', return_value=flavor):

                transformer()
                payloads = transformer()
                self.assertIsNotNone(payloads)
                self.assertThat(len(payloads), Equals(1))
                payload = payloads[0]
                self.assertThat(payload['audit_period_beginning'],
                                Not(Is(None)))
                self.assertThat(payload['audit_period_ending'], Not(Is(None)))
                self.assertIn(status.lower(),
                              [db['state']
                              for db in payloads])
                self.assertThat(payload['instance_type'], Equals('db.small'))
                self.assertThat(payload['instance_type_id'],
                                Equals('flavor_1'))
                self.assertThat(payload['user_id'], Equals('test_user_id'))
                # ensure cache was used to get flavor second time
                self.flavor_mgr.get.assert_any_call('flavor_1')
        self.addCleanup(self.do_cleanup, instance, service_status)


class TestMgmtInstanceTasks(MockMgmtInstanceTest):

    @classmethod
    def setUpClass(cls):
        super(TestMgmtInstanceTasks, cls).setUpClass()

    def test_public_exists_events(self):
        status = rd_instance.ServiceStatuses.BUILDING.api_status
        instance, service_status = self.build_db_instance(
            status, task_status=InstanceTasks.BUILDING)
        server = MagicMock(spec=Server)
        server.user_id = 'test_user_id'
        mgmt_instance = mgmtmodels.SimpleMgmtInstance(self.context,
                                                      instance,
                                                      server,
                                                      service_status)

        flavor = MagicMock(spec=Flavor)
        flavor.name = 'db.small'

        notifier = MagicMock()
        with patch.object(rpc, 'get_notifier', return_value=notifier):
            with patch.object(mgmtmodels, 'load_mgmt_instances',
                              return_value=[mgmt_instance]):
                with patch.object(self.flavor_mgr, 'get', return_value=flavor):
                    self.assertThat(self.context.auth_token,
                                    Is('some_secret_password'))
                    with patch.object(notifier, 'info', return_value=None):
                        # invocation
                        mgmtmodels.publish_exist_events(
                            mgmtmodels.NovaNotificationTransformer(
                                context=self.context),
                            self.context)
                        # assertion
                        notifier.info.assert_any_call(
                            self.context, 'trove.instance.exists', ANY)
                        self.assertThat(self.context.auth_token, Is(None))
        self.addCleanup(self.do_cleanup, instance, service_status)


class TestMgmtInstanceDeleted(MockMgmtInstanceTest):

    def test_show_deleted_mgmt_instances(self):
        args = {'deleted': 0, 'cluster_id': None}
        db_infos_active = DBInstance.find_all(**args)
        args = {'deleted': 1, 'cluster_id': None}
        db_infos_deleted = DBInstance.find_all(**args)
        args = {'cluster_id': None}
        # db_infos_all = DBInstance.find_all(**args)

        # TODO(SlickNik) Fix this assert to work reliably in the gate.
        # This fails intermittenly when the unit tests run in parallel.
        # self.assertTrue(db_infos_all.count() ==
        #                 db_infos_active.count() +
        #                 db_infos_deleted.count())

        with patch.object(self.context, 'is_admin', return_value=True):
            deleted_instance = db_infos_deleted.all()[0]
            active_instance = db_infos_active.all()[0]

            instance = DBInstance.find_by(context=self.context,
                                          id=active_instance.id)
            self.assertEqual(active_instance.id, instance.id)

            self.assertRaises(
                exception.ModelNotFoundError,
                DBInstance.find_by,
                context=self.context,
                id=deleted_instance.id,
                deleted=False)

            instance = DBInstance.find_by(context=self.context,
                                          id=deleted_instance.id,
                                          deleted=True)
            self.assertEqual(deleted_instance.id, instance.id)


class TestMgmtInstancePing(MockMgmtInstanceTest):

    def test_rpc_ping(self):
        status = rd_instance.ServiceStatuses.RUNNING.api_status
        instance, service_status = self.build_db_instance(
            status, task_status=InstanceTasks.NONE)
        mgmt_instance = mgmtmodels.MgmtInstance(instance,
                                                instance,
                                                None,
                                                service_status)

        with patch.object(API, 'rpc_ping', return_value=True):
            with patch.object(API, 'get_client'):
                self.assertTrue(mgmt_instance.rpc_ping())

        self.addCleanup(self.do_cleanup, instance, service_status)
