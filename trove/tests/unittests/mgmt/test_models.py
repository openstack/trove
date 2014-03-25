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
from mock import MagicMock, patch, ANY
from testtools import TestCase
from testtools.matchers import Equals, Is, Not

from novaclient.v1_1 import Client
from novaclient.v1_1.flavors import FlavorManager, Flavor
from novaclient.v1_1.servers import Server, ServerManager
from oslo.config import cfg
from trove.backup.models import Backup
from trove.common.context import TroveContext
from trove.common import instance as rd_instance
from trove.datastore import models as datastore_models
from trove.db.models import DatabaseModelBase
from trove.instance.models import DBInstance
from trove.instance.models import InstanceServiceStatus
from trove.instance.tasks import InstanceTasks
import trove.extensions.mgmt.instances.models as mgmtmodels
from trove.openstack.common.notifier import api as notifier
from trove.common import remote
from trove.tests.util import test_config

CONF = cfg.CONF


class MockMgmtInstanceTest(TestCase):
    def setUp(self):
        super(MockMgmtInstanceTest, self).setUp()
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

    def tearDown(self):
        super(MockMgmtInstanceTest, self).tearDown()

    @staticmethod
    def build_db_instance(status, task_status=InstanceTasks.DELETING):
        return DBInstance(task_status,
                          created='xyz',
                          name='test_name',
                          id='1',
                          flavor_id='flavor_1',
                          datastore_version_id=
                          test_config.dbaas_datastore_version_id,
                          compute_instance_id='compute_id_1',
                          server_id='server_id_1',
                          tenant_id='tenant_id_1',
                          server_status=status)


class TestNotificationTransformer(MockMgmtInstanceTest):

    def test_tranformer(self):
        transformer = mgmtmodels.NotificationTransformer(context=self.context)
        status = rd_instance.ServiceStatuses.BUILDING.api_status
        db_instance = MockMgmtInstanceTest.build_db_instance(
            status, InstanceTasks.BUILDING)

        with patch.object(DatabaseModelBase, 'find_all',
                          return_value=[db_instance]):
            stub_dsv_db_info = MagicMock(
                spec=datastore_models.DBDatastoreVersion)
            stub_dsv_db_info.id = "test_datastore_version"
            stub_dsv_db_info.datastore_id = "mysql_test_version"
            stub_dsv_db_info.name = "test_datastore_name"
            stub_dsv_db_info.image_id = "test_datastore_image_id"
            stub_dsv_db_info.packages = "test_datastore_pacakges"
            stub_dsv_db_info.active = 1
            stub_dsv_db_info.manager = "mysql"
            stub_datastore_version = datastore_models.DatastoreVersion(
                stub_dsv_db_info)

            def side_effect_func(*args, **kwargs):
                if 'instance_id' in kwargs:
                    return InstanceServiceStatus(
                        rd_instance.ServiceStatuses.BUILDING)
                else:
                    return stub_datastore_version

            with patch.object(DatabaseModelBase, 'find_by',
                              side_effect=side_effect_func):
                payloads = transformer()
                self.assertIsNotNone(payloads)
                self.assertThat(len(payloads), Equals(1))
                payload = payloads[0]
                self.assertThat(payload['audit_period_beginning'],
                                Not(Is(None)))
                self.assertThat(payload['audit_period_ending'], Not(Is(None)))
                self.assertThat(payload['state'], Equals(status.lower()))

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
        with patch.object(self.flavor_mgr, 'get', side_effect=[flavor, None]):
            transformer = mgmtmodels.NovaNotificationTransformer(
                context=self.context)
            self.assertThat(transformer._lookup_flavor('1'),
                            Equals(flavor.name))
            self.assertThat(transformer._lookup_flavor('2'),
                            Equals('unknown'))

    def test_tranformer(self):
        status = rd_instance.ServiceStatuses.BUILDING.api_status
        db_instance = MockMgmtInstanceTest.build_db_instance(
            status, task_status=InstanceTasks.BUILDING)

        stub_dsv_db_info = MagicMock(spec=datastore_models.DBDatastoreVersion)
        stub_dsv_db_info.id = "test_datastore_version"
        stub_dsv_db_info.datastore_id = "mysql_test_version"
        stub_dsv_db_info.name = "test_datastore_name"
        stub_dsv_db_info.image_id = "test_datastore_image_id"
        stub_dsv_db_info.packages = "test_datastore_pacakges"
        stub_dsv_db_info.active = 1
        stub_dsv_db_info.manager = "mysql"
        stub_datastore_version = datastore_models.DatastoreVersion(
            stub_dsv_db_info)

        flavor = MagicMock(spec=Flavor)
        flavor.name = 'db.small'

        server = MagicMock(spec=Server)
        server.user_id = 'test_user_id'
        mgmt_instance = mgmtmodels.SimpleMgmtInstance(self.context,
                                                      db_instance,
                                                      server,
                                                      None)

        with patch.object(DatabaseModelBase, 'find_by',
                          return_value=stub_datastore_version):

            with patch.object(mgmtmodels, 'load_mgmt_instances',
                              return_value=[mgmt_instance]):

                with patch.object(self.flavor_mgr, 'get', return_value=flavor):

                    # invocation
                    transformer = mgmtmodels.NovaNotificationTransformer(
                        context=self.context)
                    payloads = transformer()

                    # assertions
                    self.assertIsNotNone(payloads)
                    self.assertThat(len(payloads), Equals(1))
                    payload = payloads[0]
                    self.assertThat(payload['audit_period_beginning'],
                                    Not(Is(None)))
                    self.assertThat(payload['audit_period_ending'],
                                    Not(Is(None)))
                    self.assertThat(payload['state'], Equals(status.lower()))
                    self.assertThat(payload['instance_type'],
                                    Equals('db.small'))
                    self.assertThat(payload['instance_type_id'],
                                    Equals('flavor_1'))
                    self.assertThat(payload['user_id'], Equals('test_user_id'))
                    self.assertThat(payload['service_id'], Equals('123'))

    def test_tranformer_invalid_datastore_manager(self):
        status = rd_instance.ServiceStatuses.BUILDING.api_status
        db_instance = MockMgmtInstanceTest.build_db_instance(
            status, task_status=InstanceTasks.BUILDING)

        server = MagicMock(spec=Server)
        server.user_id = 'test_user_id'
        stub_datastore_version = MagicMock()
        stub_datastore_version.id = "stub_datastore_version"
        stub_datastore_version.manager = "m0ng0"
        stub_datastore = MagicMock()
        stub_datastore.default_datastore_version = "stub_datastore_version"

        flavor = MagicMock(spec=Flavor)
        flavor.name = 'db.small'

        with patch.object(datastore_models.DatastoreVersion, 'load',
                          return_value=stub_datastore_version):
            with patch.object(datastore_models.DatastoreVersion,
                              'load_by_uuid',
                              return_value=stub_datastore_version):
                with patch.object(datastore_models.Datastore, 'load',
                                  return_value=stub_datastore):
                    mgmt_instance = mgmtmodels.SimpleMgmtInstance(self.context,
                                                                  db_instance,
                                                                  server,
                                                                  None)
                    with patch.object(mgmtmodels, 'load_mgmt_instances',
                                      return_value=[mgmt_instance]):
                        with patch.object(self.flavor_mgr,
                                          'get', return_value=flavor):

                            # invocation
                            transformer = (
                                mgmtmodels.NovaNotificationTransformer(
                                    context=self.context)
                            )

                            payloads = transformer()
                            # assertions
                            self.assertIsNotNone(payloads)
                            self.assertThat(len(payloads), Equals(1))
                            payload = payloads[0]
                            self.assertThat(payload['audit_period_beginning'],
                                            Not(Is(None)))
                            self.assertThat(payload['audit_period_ending'],
                                            Not(Is(None)))
                            self.assertThat(payload['state'],
                                            Equals(status.lower()))
                            self.assertThat(payload['instance_type'],
                                            Equals('db.small'))
                            self.assertThat(payload['instance_type_id'],
                                            Equals('flavor_1'))
                            self.assertThat(payload['user_id'],
                                            Equals('test_user_id'))
                            self.assertThat(payload['service_id'],
                                            Equals('unknown-service-id-error'))

    def test_tranformer_shutdown_instance(self):
        status = rd_instance.ServiceStatuses.SHUTDOWN.api_status
        db_instance = self.build_db_instance(status)

        server = MagicMock(spec=Server)
        server.user_id = 'test_user_id'
        mgmt_instance = mgmtmodels.SimpleMgmtInstance(self.context,
                                                      db_instance,
                                                      server,
                                                      None)
        flavor = MagicMock(spec=Flavor)
        flavor.name = 'db.small'

        with patch.object(Backup, 'running', return_value=None):
            self.assertThat(mgmt_instance.status, Equals('SHUTDOWN'))
            with patch.object(mgmtmodels, 'load_mgmt_instances',
                              return_value=[mgmt_instance]):
                with patch.object(self.flavor_mgr, 'get', return_value=flavor):
                    # invocation
                    transformer = mgmtmodels.NovaNotificationTransformer(
                        context=self.context)
                    payloads = transformer()
                    # assertion that SHUTDOWN instances are not reported
                    self.assertIsNotNone(payloads)
                    self.assertThat(len(payloads), Equals(0))

    def test_tranformer_no_nova_instance(self):
        status = rd_instance.ServiceStatuses.SHUTDOWN.api_status
        db_instance = MockMgmtInstanceTest.build_db_instance(status)

        mgmt_instance = mgmtmodels.SimpleMgmtInstance(self.context,
                                                      db_instance,
                                                      None,
                                                      None)
        flavor = MagicMock(spec=Flavor)
        flavor.name = 'db.small'

        with patch.object(Backup, 'running', return_value=None):
            self.assertThat(mgmt_instance.status, Equals('SHUTDOWN'))
            with patch.object(mgmtmodels, 'load_mgmt_instances',
                              return_value=[mgmt_instance]):
                with patch.object(self.flavor_mgr, 'get', return_value=flavor):
                    # invocation
                    transformer = mgmtmodels.NovaNotificationTransformer(
                        context=self.context)
                    payloads = transformer()
                    # assertion that SHUTDOWN instances are not reported
                    self.assertIsNotNone(payloads)
                    self.assertThat(len(payloads), Equals(0))

    def test_tranformer_flavor_cache(self):
        status = rd_instance.ServiceStatuses.BUILDING.api_status
        db_instance = MockMgmtInstanceTest.build_db_instance(
            status, InstanceTasks.BUILDING)

        server = MagicMock(spec=Server)
        server.user_id = 'test_user_id'
        mgmt_instance = mgmtmodels.SimpleMgmtInstance(self.context,
                                                      db_instance,
                                                      server,
                                                      None)
        flavor = MagicMock(spec=Flavor)
        flavor.name = 'db.small'

        with patch.object(mgmtmodels, 'load_mgmt_instances',
                          return_value=[mgmt_instance]):
            with patch.object(self.flavor_mgr, 'get', return_value=flavor):
                transformer = mgmtmodels.NovaNotificationTransformer(
                    context=self.context)
                transformer()
                # call twice ensure client.flavor invoked once
                payloads = transformer()
                self.assertIsNotNone(payloads)
                self.assertThat(len(payloads), Equals(1))
                payload = payloads[0]
                self.assertThat(payload['audit_period_beginning'],
                                Not(Is(None)))
                self.assertThat(payload['audit_period_ending'], Not(Is(None)))
                self.assertThat(payload['state'], Equals(status.lower()))
                self.assertThat(payload['instance_type'], Equals('db.small'))
                self.assertThat(payload['instance_type_id'],
                                Equals('flavor_1'))
                self.assertThat(payload['user_id'], Equals('test_user_id'))
                # ensure cache was used to get flavor second time
                self.flavor_mgr.get.assert_any_call('flavor_1')


class TestMgmtInstanceTasks(MockMgmtInstanceTest):
    def test_public_exists_events(self):
        status = rd_instance.ServiceStatuses.BUILDING.api_status
        db_instance = MockMgmtInstanceTest.build_db_instance(
            status, task_status=InstanceTasks.BUILDING)

        server = MagicMock(spec=Server)
        server.user_id = 'test_user_id'
        mgmt_instance = mgmtmodels.SimpleMgmtInstance(self.context,
                                                      db_instance,
                                                      server,
                                                      None)

        flavor = MagicMock(spec=Flavor)
        flavor.name = 'db.small'

        with patch.object(mgmtmodels, 'load_mgmt_instances',
                          return_value=[mgmt_instance]):
            with patch.object(self.flavor_mgr, 'get', return_value=flavor):
                self.assertThat(self.context.auth_token,
                                Is('some_secret_password'))
                with patch.object(notifier, 'notify', return_value=None):
                    # invocation
                    mgmtmodels.publish_exist_events(
                        mgmtmodels.NovaNotificationTransformer(
                            context=self.context),
                        self.context)
                    # assertion
                    notifier.notify.assert_any_call(self.context,
                                                    'test_host',
                                                    'trove.instance.exists',
                                                    'INFO',
                                                    ANY)
                    self.assertThat(self.context.auth_token, Is(None))
