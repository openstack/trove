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
from mockito import mock, when, verify, unstub, any
from testtools import TestCase
from testtools.matchers import Equals, Is, Not

from novaclient.v1_1 import Client
from novaclient.v1_1.flavors import FlavorManager, Flavor
from novaclient.v1_1.servers import Server, ServerManager
from trove.backup.models import Backup

from trove.common.context import TroveContext
from trove.db.models import DatabaseModelBase
from trove.extensions.mgmt.instances.models import NotificationTransformer
from trove.extensions.mgmt.instances.models import \
    NovaNotificationTransformer
from trove.extensions.mgmt.instances.models import SimpleMgmtInstance
from trove.instance.models import DBInstance
from trove.instance.models import InstanceServiceStatus
from trove.instance.models import ServiceStatuses
from trove.instance.tasks import InstanceTasks
import trove.extensions.mgmt.instances.models as mgmtmodels
from trove.openstack.common.notifier import api as notifier
from trove.common import remote


class MockMgmtInstanceTest(TestCase):
    def setUp(self):
        super(MockMgmtInstanceTest, self).setUp()
        self.context = TroveContext()
        self.client = mock(Client)
        self.server_mgr = mock(ServerManager)
        self.client.servers = self.server_mgr
        self.flavor_mgr = mock(FlavorManager)
        self.client.flavors = self.flavor_mgr
        when(remote).create_admin_nova_client(self.context).thenReturn(
            self.client)

    def tearDown(self):
        super(MockMgmtInstanceTest, self).tearDown()
        unstub()


class TestNotificationTransformer(MockMgmtInstanceTest):
    def test_tranformer(self):
        transformer = NotificationTransformer(context=self.context)
        status = ServiceStatuses.BUILDING.api_status
        db_instance = DBInstance(InstanceTasks.BUILDING,
                                 created='xyz',
                                 name='test_name',
                                 id='1',
                                 flavor_id='flavor_1',
                                 compute_instance_id='compute_id_1',
                                 server_id='server_id_1',
                                 tenant_id='tenant_id_1',
                                 server_status=status)
        when(DatabaseModelBase).find_all(deleted=False).thenReturn(
            [db_instance])
        when(DatabaseModelBase).find_by(instance_id='1').thenReturn(
            InstanceServiceStatus(ServiceStatuses.BUILDING))

        payloads = transformer()
        self.assertIsNotNone(payloads)
        self.assertThat(len(payloads), Equals(1))
        payload = payloads[0]
        self.assertThat(payload['audit-period-beginning'], Not(Is(None)))
        self.assertThat(payload['audit-period-ending'], Not(Is(None)))
        self.assertThat(payload['state'], Equals(status.lower()))


class TestNovaNotificationTransformer(MockMgmtInstanceTest):
    def test_transformer_cache(self):
        flavor = mock(Flavor)
        flavor.name = 'db.small'
        when(self.flavor_mgr).get('flavor_1').thenReturn(flavor)
        transformer = NovaNotificationTransformer(context=self.context)
        transformer2 = NovaNotificationTransformer(context=self.context)
        self.assertThat(transformer._flavor_cache,
                        Not(Is(transformer2._flavor_cache)))

    def test_lookup_flavor(self):
        flavor = mock(Flavor)
        flavor.name = 'flav_1'
        when(self.flavor_mgr).get('1').thenReturn(flavor)
        transformer = NovaNotificationTransformer(context=self.context)
        self.assertThat(transformer._lookup_flavor('1'), Equals(flavor.name))
        self.assertThat(transformer._lookup_flavor('2'), Equals('unknown'))

    def test_tranformer(self):
        status = ServiceStatuses.BUILDING.api_status
        db_instance = DBInstance(InstanceTasks.BUILDING,
                                 created='xyz',
                                 name='test_name',
                                 id='1',
                                 flavor_id='flavor_1',
                                 compute_instance_id='compute_id_1',
                                 server_id='server_id_1',
                                 tenant_id='tenant_id_1',
                                 server_status=status)

        server = mock(Server)
        server.user_id = 'test_user_id'
        mgmt_instance = SimpleMgmtInstance(self.context,
                                           db_instance,
                                           server,
                                           None)
        when(mgmtmodels).load_mgmt_instances(
            self.context,
            deleted=False,
            client=self.client).thenReturn(
                [mgmt_instance])
        flavor = mock(Flavor)
        flavor.name = 'db.small'
        when(self.flavor_mgr).get('flavor_1').thenReturn(flavor)
        # invocation
        transformer = NovaNotificationTransformer(context=self.context)
        payloads = transformer()
        # assertions
        self.assertIsNotNone(payloads)
        self.assertThat(len(payloads), Equals(1))
        payload = payloads[0]
        self.assertThat(payload['audit-period-beginning'], Not(Is(None)))
        self.assertThat(payload['audit-period-ending'], Not(Is(None)))
        self.assertThat(payload['state'], Equals(status.lower()))
        self.assertThat(payload['instance_type'], Equals('db.small'))
        self.assertThat(payload['instance_type_id'], Equals('flavor_1'))
        self.assertThat(payload['user_id'], Equals('test_user_id'))

    def test_tranformer_shutdown_instance(self):
        status = ServiceStatuses.SHUTDOWN.api_status
        db_instance = DBInstance(InstanceTasks.DELETING,
                                 created='xyz',
                                 name='test_name',
                                 id='1',
                                 flavor_id='flavor_1',
                                 compute_instance_id='compute_id_1',
                                 server_id='server_id_1',
                                 tenant_id='tenant_id_1',
                                 server_status=status)

        server = mock(Server)
        server.user_id = 'test_user_id'
        mgmt_instance = SimpleMgmtInstance(self.context,
                                           db_instance,
                                           server,
                                           None)
        when(Backup).running('1').thenReturn(None)
        self.assertThat(mgmt_instance.status, Equals('SHUTDOWN'))
        when(mgmtmodels).load_mgmt_instances(
            self.context,
            deleted=False,
            client=self.client).thenReturn(
                [mgmt_instance])
        flavor = mock(Flavor)
        flavor.name = 'db.small'
        when(self.flavor_mgr).get('flavor_1').thenReturn(flavor)
        # invocation
        transformer = NovaNotificationTransformer(context=self.context)
        payloads = transformer()
        # assertion that SHUTDOWN instances are not reported
        self.assertIsNotNone(payloads)
        self.assertThat(len(payloads), Equals(0))

    def test_tranformer_no_nova_instance(self):
        status = ServiceStatuses.SHUTDOWN.api_status
        db_instance = DBInstance(InstanceTasks.DELETING,
                                 created='xyz',
                                 name='test_name',
                                 id='1',
                                 flavor_id='flavor_1',
                                 compute_instance_id='compute_id_1',
                                 server_id='server_id_1',
                                 tenant_id='tenant_id_1',
                                 server_status=status)

        mgmt_instance = SimpleMgmtInstance(self.context,
                                           db_instance,
                                           None,
                                           None)
        when(Backup).running('1').thenReturn(None)
        self.assertThat(mgmt_instance.status, Equals('SHUTDOWN'))
        when(mgmtmodels).load_mgmt_instances(
            self.context,
            deleted=False,
            client=self.client).thenReturn(
                [mgmt_instance])
        flavor = mock(Flavor)
        flavor.name = 'db.small'
        when(self.flavor_mgr).get('flavor_1').thenReturn(flavor)
        # invocation
        transformer = NovaNotificationTransformer(context=self.context)
        payloads = transformer()
        # assertion that SHUTDOWN instances are not reported
        self.assertIsNotNone(payloads)
        self.assertThat(len(payloads), Equals(0))

    def test_tranformer_flavor_cache(self):
        status = ServiceStatuses.BUILDING.api_status
        db_instance = DBInstance(InstanceTasks.BUILDING,
                                 created='xyz',
                                 name='test_name',
                                 id='1',
                                 flavor_id='flavor_1',
                                 compute_instance_id='compute_id_1',
                                 server_id='server_id_1',
                                 tenant_id='tenant_id_1',
                                 server_status=status)

        server = mock(Server)
        server.user_id = 'test_user_id'
        mgmt_instance = SimpleMgmtInstance(self.context,
                                           db_instance,
                                           server,
                                           None)
        when(mgmtmodels).load_mgmt_instances(
            self.context,
            deleted=False,
            client=self.client).thenReturn(
                [mgmt_instance])
        flavor = mock(Flavor)
        flavor.name = 'db.small'
        when(self.flavor_mgr).get('flavor_1').thenReturn(flavor)
        transformer = NovaNotificationTransformer(context=self.context)
        transformer()
        # call twice ensure client.flavor invoked once
        payloads = transformer()
        self.assertIsNotNone(payloads)
        self.assertThat(len(payloads), Equals(1))
        payload = payloads[0]
        self.assertThat(payload['audit-period-beginning'], Not(Is(None)))
        self.assertThat(payload['audit-period-ending'], Not(Is(None)))
        self.assertThat(payload['state'], Equals(status.lower()))
        self.assertThat(payload['instance_type'], Equals('db.small'))
        self.assertThat(payload['instance_type_id'], Equals('flavor_1'))
        self.assertThat(payload['user_id'], Equals('test_user_id'))
        # ensure cache was used to get flavor second time
        verify(self.flavor_mgr).get('flavor_1')


class TestMgmtInstanceTasks(MockMgmtInstanceTest):
    def test_public_exists_events(self):
        status = ServiceStatuses.BUILDING.api_status
        db_instance = DBInstance(InstanceTasks.BUILDING,
                                 created='xyz',
                                 name='test_name',
                                 id='1',
                                 flavor_id='flavor_1',
                                 compute_instance_id='compute_id_1',
                                 server_id='server_id_1',
                                 tenant_id='tenant_id_1',
                                 server_status=status)

        server = mock(Server)
        server.user_id = 'test_user_id'
        mgmt_instance = SimpleMgmtInstance(self.context,
                                           db_instance,
                                           server,
                                           None)
        when(mgmtmodels).load_mgmt_instances(
            self.context,
            deleted=False,
            client=self.client).thenReturn(
                [mgmt_instance, mgmt_instance])
        flavor = mock(Flavor)
        flavor.name = 'db.small'
        when(self.flavor_mgr).get('flavor_1').thenReturn(flavor)
        when(notifier).notify(self.context,
                              any(str),
                              'trove.instance.exists',
                              'INFO',
                              any(dict)).thenReturn(None)
        # invocation
        mgmtmodels.publish_exist_events(
            NovaNotificationTransformer(context=self.context), self.context)
        # assertion
        verify(notifier, times=2).notify(self.context,
                                         any(str),
                                         'trove.instance.exists',
                                         'INFO',
                                         any(dict))
