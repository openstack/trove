#    Copyright 2012 OpenStack Foundation
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
import testtools
from mockito import mock, when, unstub, any, verify, never, times
from mock import Mock
from trove.quota.quota import DbQuotaDriver
from trove.quota.models import Resource
from trove.quota.models import Quota
from trove.quota.models import QuotaUsage
from trove.quota.models import Reservation
from trove.db.models import DatabaseModelBase
from trove.extensions.mgmt.quota.service import QuotaController
from trove.common import exception
from trove.common import cfg
from trove.quota.quota import run_with_quotas
from trove.quota.quota import QUOTAS
"""
Unit tests for the classes and functions in DbQuotaDriver.py.
"""

CONF = cfg.CONF
resources = {
    Resource.INSTANCES: Resource(Resource.INSTANCES, 'max_instances_per_user'),
    Resource.VOLUMES: Resource(Resource.VOLUMES, 'max_volumes_per_user'),
}

FAKE_TENANT1 = "123456"
FAKE_TENANT2 = "654321"


class Run_with_quotasTest(testtools.TestCase):

    def setUp(self):
        super(Run_with_quotasTest, self).setUp()
        self.quota_reserve_orig = QUOTAS.reserve
        self.quota_rollback_orig = QUOTAS.rollback
        self.quota_commit_orig = QUOTAS.commit
        QUOTAS.reserve = Mock()
        QUOTAS.rollback = Mock()
        QUOTAS.commit = Mock()

    def tearDown(self):
        super(Run_with_quotasTest, self).tearDown()
        QUOTAS.reserve = self.quota_reserve_orig
        QUOTAS.rollback = self.quota_rollback_orig
        QUOTAS.commit = self.quota_commit_orig

    def test_run_with_quotas(self):

        f = Mock()
        run_with_quotas(FAKE_TENANT1, {'instances': 1, 'volumes': 5}, f)

        self.assertTrue(QUOTAS.reserve.called)
        self.assertTrue(QUOTAS.commit.called)
        self.assertFalse(QUOTAS.rollback.called)
        self.assertTrue(f.called)

    def test_run_with_quotas_error(self):

        f = Mock(side_effect=Exception())

        self.assertRaises(Exception, run_with_quotas, FAKE_TENANT1,
                          {'instances': 1, 'volumes': 5}, f)
        self.assertTrue(QUOTAS.reserve.called)
        self.assertTrue(QUOTAS.rollback.called)
        self.assertFalse(QUOTAS.commit.called)
        self.assertTrue(f.called)


class QuotaControllerTest(testtools.TestCase):

    def setUp(self):
        super(QuotaControllerTest, self).setUp()
        context = mock()
        context.is_admin = True
        req = mock()
        req.environ = mock()
        when(req.environ).get(any()).thenReturn(context)
        self.req = req
        self.controller = QuotaController()

    def tearDown(self):
        super(QuotaControllerTest, self).tearDown()
        unstub()

    def test_update_unknown_resource(self):
        body = {'quotas': {'unknown_resource': 5}}
        self.assertRaises(exception.QuotaResourceUnknown,
                          self.controller.update, self.req, body,
                          FAKE_TENANT1, FAKE_TENANT2)

    def test_update_resource_no_value(self):
        quota = mock(Quota)
        when(DatabaseModelBase).find_by(tenant_id=FAKE_TENANT2,
                                        resource='instances').thenReturn(quota)
        body = {'quotas': {'instances': None}}
        result = self.controller.update(self.req, body, FAKE_TENANT1,
                                        FAKE_TENANT2)
        verify(quota, never).save()
        self.assertEqual(200, result.status)

    def test_update_resource_instance(self):
        instance_quota = mock(Quota)
        when(DatabaseModelBase).find_by(
            tenant_id=FAKE_TENANT2,
            resource='instances').thenReturn(instance_quota)
        body = {'quotas': {'instances': 2}}
        result = self.controller.update(self.req, body, FAKE_TENANT1,
                                        FAKE_TENANT2)
        verify(instance_quota, times=1).save()
        self.assertTrue('instances' in result._data['quotas'])
        self.assertEqual(200, result.status)
        self.assertEqual(2, result._data['quotas']['instances'])

    @testtools.skipIf(not CONF.trove_volume_support,
                      'Volume support is not enabled')
    def test_update_resource_volume(self):
        instance_quota = mock(Quota)
        when(DatabaseModelBase).find_by(
            tenant_id=FAKE_TENANT2,
            resource='instances').thenReturn(instance_quota)
        volume_quota = mock(Quota)
        when(DatabaseModelBase).find_by(
            tenant_id=FAKE_TENANT2,
            resource='volumes').thenReturn(volume_quota)
        body = {'quotas': {'instances': None, 'volumes': 10}}
        result = self.controller.update(self.req, body, FAKE_TENANT1,
                                        FAKE_TENANT2)
        verify(instance_quota, never).save()
        self.assertFalse('instances' in result._data['quotas'])
        verify(volume_quota, times=1).save()
        self.assertEqual(200, result.status)
        self.assertEqual(10, result._data['quotas']['volumes'])


class DbQuotaDriverTest(testtools.TestCase):

    def setUp(self):

        super(DbQuotaDriverTest, self).setUp()
        self.driver = DbQuotaDriver(resources)
        self.orig_Quota_find_all = Quota.find_all
        self.orig_QuotaUsage_find_all = QuotaUsage.find_all
        self.orig_QuotaUsage_find_by = QuotaUsage.find_by
        self.orig_Reservation_create = Reservation.create
        self.orig_QuotaUsage_create = QuotaUsage.create
        self.orig_QuotaUsage_save = QuotaUsage.save
        self.orig_Reservation_save = Reservation.save
        self.mock_quota_result = Mock()
        self.mock_usage_result = Mock()
        Quota.find_all = Mock(return_value=self.mock_quota_result)
        QuotaUsage.find_all = Mock(return_value=self.mock_usage_result)

    def tearDown(self):
        super(DbQuotaDriverTest, self).tearDown()
        Quota.find_all = self.orig_Quota_find_all
        QuotaUsage.find_all = self.orig_QuotaUsage_find_all
        QuotaUsage.find_by = self.orig_QuotaUsage_find_by
        Reservation.create = self.orig_Reservation_create
        QuotaUsage.create = self.orig_QuotaUsage_create
        QuotaUsage.save = self.orig_QuotaUsage_save
        Reservation.save = self.orig_Reservation_save

    def test_get_defaults(self):
        defaults = self.driver.get_defaults(resources)
        self.assertEqual(CONF.max_instances_per_user,
                         defaults[Resource.INSTANCES])
        self.assertEqual(CONF.max_volumes_per_user,
                         defaults[Resource.VOLUMES])

    def test_get_quota_by_tenant(self):

        FAKE_QUOTAS = [Quota(tenant_id=FAKE_TENANT1,
                             resource=Resource.INSTANCES,
                             hard_limit=12)]

        self.mock_quota_result.all = Mock(return_value=FAKE_QUOTAS)

        quota = self.driver.get_quota_by_tenant(FAKE_TENANT1,
                                                Resource.VOLUMES)

        self.assertEqual(FAKE_TENANT1, quota.tenant_id)
        self.assertEqual(Resource.INSTANCES, quota.resource)
        self.assertEqual(12, quota.hard_limit)

    def test_get_quota_by_tenant_default(self):

        self.mock_quota_result.all = Mock(return_value=[])

        quota = self.driver.get_quota_by_tenant(FAKE_TENANT1,
                                                Resource.VOLUMES)

        self.assertEqual(FAKE_TENANT1, quota.tenant_id)
        self.assertEqual(Resource.VOLUMES, quota.resource)
        self.assertEqual(CONF.max_volumes_per_user, quota.hard_limit)

    def test_get_all_quotas_by_tenant(self):

        FAKE_QUOTAS = [Quota(tenant_id=FAKE_TENANT1,
                             resource=Resource.INSTANCES,
                             hard_limit=22),
                       Quota(tenant_id=FAKE_TENANT1,
                             resource=Resource.VOLUMES,
                             hard_limit=15)]

        self.mock_quota_result.all = Mock(return_value=FAKE_QUOTAS)

        quotas = self.driver.get_all_quotas_by_tenant(FAKE_TENANT1,
                                                      resources.keys())

        self.assertEqual(FAKE_TENANT1, quotas[Resource.INSTANCES].tenant_id)
        self.assertEqual(Resource.INSTANCES,
                         quotas[Resource.INSTANCES].resource)
        self.assertEqual(22, quotas[Resource.INSTANCES].hard_limit)
        self.assertEqual(FAKE_TENANT1, quotas[Resource.VOLUMES].tenant_id)
        self.assertEqual(Resource.VOLUMES, quotas[Resource.VOLUMES].resource)
        self.assertEqual(15, quotas[Resource.VOLUMES].hard_limit)

    def test_get_all_quotas_by_tenant_with_all_default(self):

        self.mock_quota_result.all = Mock(return_value=[])

        quotas = self.driver.get_all_quotas_by_tenant(FAKE_TENANT1,
                                                      resources.keys())

        self.assertEqual(FAKE_TENANT1, quotas[Resource.INSTANCES].tenant_id)
        self.assertEqual(Resource.INSTANCES,
                         quotas[Resource.INSTANCES].resource)
        self.assertEqual(CONF.max_instances_per_user,
                         quotas[Resource.INSTANCES].hard_limit)
        self.assertEqual(FAKE_TENANT1, quotas[Resource.VOLUMES].tenant_id)
        self.assertEqual(Resource.VOLUMES, quotas[Resource.VOLUMES].resource)
        self.assertEqual(CONF.max_volumes_per_user,
                         quotas[Resource.VOLUMES].hard_limit)

    def test_get_all_quotas_by_tenant_with_one_default(self):

        FAKE_QUOTAS = [Quota(tenant_id=FAKE_TENANT1,
                             resource=Resource.INSTANCES,
                             hard_limit=22)]

        self.mock_quota_result.all = Mock(return_value=FAKE_QUOTAS)

        quotas = self.driver.get_all_quotas_by_tenant(FAKE_TENANT1,
                                                      resources.keys())

        self.assertEqual(FAKE_TENANT1, quotas[Resource.INSTANCES].tenant_id)
        self.assertEqual(Resource.INSTANCES,
                         quotas[Resource.INSTANCES].resource)
        self.assertEqual(22, quotas[Resource.INSTANCES].hard_limit)
        self.assertEqual(FAKE_TENANT1, quotas[Resource.VOLUMES].tenant_id)
        self.assertEqual(Resource.VOLUMES, quotas[Resource.VOLUMES].resource)
        self.assertEqual(CONF.max_volumes_per_user,
                         quotas[Resource.VOLUMES].hard_limit)

    def test_get_quota_usage_by_tenant(self):

        FAKE_QUOTAS = [QuotaUsage(tenant_id=FAKE_TENANT1,
                                  resource=Resource.VOLUMES,
                                  in_use=3,
                                  reserved=1)]

        self.mock_usage_result.all = Mock(return_value=FAKE_QUOTAS)

        usage = self.driver.get_quota_usage_by_tenant(FAKE_TENANT1,
                                                      Resource.VOLUMES)

        self.assertEqual(FAKE_TENANT1, usage.tenant_id)
        self.assertEqual(Resource.VOLUMES, usage.resource)
        self.assertEqual(3, usage.in_use)
        self.assertEqual(1, usage.reserved)

    def test_get_quota_usage_by_tenant_default(self):

        FAKE_QUOTA = QuotaUsage(tenant_id=FAKE_TENANT1,
                                resource=Resource.VOLUMES,
                                in_use=0,
                                reserved=0)

        self.mock_usage_result.all = Mock(return_value=[])
        QuotaUsage.create = Mock(return_value=FAKE_QUOTA)

        usage = self.driver.get_quota_usage_by_tenant(FAKE_TENANT1,
                                                      Resource.VOLUMES)

        self.assertEqual(FAKE_TENANT1, usage.tenant_id)
        self.assertEqual(Resource.VOLUMES, usage.resource)
        self.assertEqual(0, usage.in_use)
        self.assertEqual(0, usage.reserved)

    def test_get_all_quota_usages_by_tenant(self):

        FAKE_QUOTAS = [QuotaUsage(tenant_id=FAKE_TENANT1,
                                  resource=Resource.INSTANCES,
                                  in_use=2,
                                  reserved=1),
                       QuotaUsage(tenant_id=FAKE_TENANT1,
                                  resource=Resource.VOLUMES,
                                  in_use=1,
                                  reserved=1)]

        self.mock_usage_result.all = Mock(return_value=FAKE_QUOTAS)

        usages = self.driver.get_all_quota_usages_by_tenant(FAKE_TENANT1,
                                                            resources.keys())

        self.assertEqual(FAKE_TENANT1, usages[Resource.INSTANCES].tenant_id)
        self.assertEqual(Resource.INSTANCES,
                         usages[Resource.INSTANCES].resource)
        self.assertEqual(2, usages[Resource.INSTANCES].in_use)
        self.assertEqual(1, usages[Resource.INSTANCES].reserved)
        self.assertEqual(FAKE_TENANT1, usages[Resource.VOLUMES].tenant_id)
        self.assertEqual(Resource.VOLUMES, usages[Resource.VOLUMES].resource)
        self.assertEqual(1, usages[Resource.VOLUMES].in_use)
        self.assertEqual(1, usages[Resource.VOLUMES].reserved)

    def test_get_all_quota_usages_by_tenant_with_all_default(self):

        FAKE_QUOTAS = [QuotaUsage(tenant_id=FAKE_TENANT1,
                                  resource=Resource.INSTANCES,
                                  in_use=0,
                                  reserved=0),
                       QuotaUsage(tenant_id=FAKE_TENANT1,
                                  resource=Resource.VOLUMES,
                                  in_use=0,
                                  reserved=0)]

        self.mock_usage_result.all = Mock(return_value=[])
        QuotaUsage.create = Mock(side_effect=FAKE_QUOTAS)

        usages = self.driver.get_all_quota_usages_by_tenant(FAKE_TENANT1,
                                                            resources.keys())

        self.assertEqual(FAKE_TENANT1, usages[Resource.INSTANCES].tenant_id)
        self.assertEqual(Resource.INSTANCES,
                         usages[Resource.INSTANCES].resource)
        self.assertEqual(0, usages[Resource.INSTANCES].in_use)
        self.assertEqual(0, usages[Resource.INSTANCES].reserved)
        self.assertEqual(FAKE_TENANT1, usages[Resource.VOLUMES].tenant_id)
        self.assertEqual(Resource.VOLUMES, usages[Resource.VOLUMES].resource)
        self.assertEqual(0, usages[Resource.VOLUMES].in_use)
        self.assertEqual(0, usages[Resource.VOLUMES].reserved)

    def test_get_all_quota_usages_by_tenant_with_one_default(self):

        FAKE_QUOTAS = [QuotaUsage(tenant_id=FAKE_TENANT1,
                                  resource=Resource.INSTANCES,
                                  in_use=0,
                                  reserved=0)]

        NEW_FAKE_QUOTA = QuotaUsage(tenant_id=FAKE_TENANT1,
                                    resource=Resource.VOLUMES,
                                    in_use=0,
                                    reserved=0)
        self.mock_usage_result.all = Mock(return_value=FAKE_QUOTAS)
        QuotaUsage.create = Mock(return_value=NEW_FAKE_QUOTA)

        usages = self.driver.get_all_quota_usages_by_tenant(FAKE_TENANT1,
                                                            resources.keys())

        self.assertEqual(FAKE_TENANT1, usages[Resource.INSTANCES].tenant_id)
        self.assertEqual(Resource.INSTANCES,
                         usages[Resource.INSTANCES].resource)
        self.assertEqual(0, usages[Resource.INSTANCES].in_use)
        self.assertEqual(0, usages[Resource.INSTANCES].reserved)
        self.assertEqual(FAKE_TENANT1, usages[Resource.VOLUMES].tenant_id)
        self.assertEqual(Resource.VOLUMES, usages[Resource.VOLUMES].resource)
        self.assertEqual(0, usages[Resource.VOLUMES].in_use)
        self.assertEqual(0, usages[Resource.VOLUMES].reserved)

    def test_reserve(self):

        FAKE_QUOTAS = [QuotaUsage(id=1,
                                  tenant_id=FAKE_TENANT1,
                                  resource=Resource.INSTANCES,
                                  in_use=1,
                                  reserved=2),
                       QuotaUsage(id=2,
                                  tenant_id=FAKE_TENANT1,
                                  resource=Resource.VOLUMES,
                                  in_use=1,
                                  reserved=1)]

        self.mock_quota_result.all = Mock(return_value=[])
        self.mock_usage_result.all = Mock(return_value=FAKE_QUOTAS)
        QuotaUsage.save = Mock()
        Reservation.create = Mock()

        delta = {'instances': 2, 'volumes': 3}
        self.driver.reserve(FAKE_TENANT1, resources, delta)
        _, kw = Reservation.create.call_args_list[0]
        self.assertEqual(1, kw['usage_id'])
        self.assertEqual(2, kw['delta'])
        self.assertEqual(Reservation.Statuses.RESERVED, kw['status'])
        _, kw = Reservation.create.call_args_list[1]
        self.assertEqual(2, kw['usage_id'])
        self.assertEqual(3, kw['delta'])
        self.assertEqual(Reservation.Statuses.RESERVED, kw['status'])

    def test_reserve_resource_unknown(self):

        delta = {'instances': 10, 'volumes': 2000, 'Fake_resource': 123}
        self.assertRaises(exception.QuotaResourceUnknown,
                          self.driver.reserve,
                          FAKE_TENANT1,
                          resources,
                          delta)

    def test_reserve_over_quota(self):

        FAKE_QUOTAS = [QuotaUsage(id=1,
                                  tenant_id=FAKE_TENANT1,
                                  resource=Resource.INSTANCES,
                                  in_use=0,
                                  reserved=0),
                       QuotaUsage(id=2,
                                  tenant_id=FAKE_TENANT1,
                                  resource=Resource.VOLUMES,
                                  in_use=0,
                                  reserved=0)]

        self.mock_quota_result.all = Mock(return_value=[])
        self.mock_usage_result.all = Mock(return_value=FAKE_QUOTAS)

        delta = {'instances': 1, 'volumes': CONF.max_volumes_per_user + 1}
        self.assertRaises(exception.QuotaExceeded,
                          self.driver.reserve,
                          FAKE_TENANT1,
                          resources,
                          delta)

    def test_reserve_over_quota_with_usage(self):

        FAKE_QUOTAS = [QuotaUsage(id=1,
                                  tenant_id=FAKE_TENANT1,
                                  resource=Resource.INSTANCES,
                                  in_use=1,
                                  reserved=0),
                       QuotaUsage(id=2,
                                  tenant_id=FAKE_TENANT1,
                                  resource=Resource.VOLUMES,
                                  in_use=0,
                                  reserved=0)]

        self.mock_quota_result.all = Mock(return_value=[])
        self.mock_usage_result.all = Mock(return_value=FAKE_QUOTAS)

        delta = {'instances': 5, 'volumes': 3}
        self.assertRaises(exception.QuotaExceeded,
                          self.driver.reserve,
                          FAKE_TENANT1,
                          resources,
                          delta)

    def test_reserve_over_quota_with_reserved(self):

        FAKE_QUOTAS = [QuotaUsage(id=1,
                                  tenant_id=FAKE_TENANT1,
                                  resource=Resource.INSTANCES,
                                  in_use=1,
                                  reserved=2),
                       QuotaUsage(id=2,
                                  tenant_id=FAKE_TENANT1,
                                  resource=Resource.VOLUMES,
                                  in_use=0,
                                  reserved=0)]

        self.mock_quota_result.all = Mock(return_value=[])
        self.mock_usage_result.all = Mock(return_value=FAKE_QUOTAS)

        delta = {'instances': 4, 'volumes': 2}
        self.assertRaises(exception.QuotaExceeded,
                          self.driver.reserve,
                          FAKE_TENANT1,
                          resources,
                          delta)

    def test_reserve_over_quota_but_can_apply_negative_deltas(self):

        FAKE_QUOTAS = [QuotaUsage(id=1,
                                  tenant_id=FAKE_TENANT1,
                                  resource=Resource.INSTANCES,
                                  in_use=10,
                                  reserved=0),
                       QuotaUsage(id=2,
                                  tenant_id=FAKE_TENANT1,
                                  resource=Resource.VOLUMES,
                                  in_use=50,
                                  reserved=0)]

        self.mock_quota_result.all = Mock(return_value=[])
        self.mock_usage_result.all = Mock(return_value=FAKE_QUOTAS)

        QuotaUsage.save = Mock()
        Reservation.create = Mock()

        delta = {'instances': -1, 'volumes': -3}
        self.driver.reserve(FAKE_TENANT1, resources, delta)
        _, kw = Reservation.create.call_args_list[0]
        self.assertEqual(1, kw['usage_id'])
        self.assertEqual(-1, kw['delta'])
        self.assertEqual(Reservation.Statuses.RESERVED, kw['status'])
        _, kw = Reservation.create.call_args_list[1]
        self.assertEqual(2, kw['usage_id'])
        self.assertEqual(-3, kw['delta'])
        self.assertEqual(Reservation.Statuses.RESERVED, kw['status'])

    def test_commit(self):

        Reservation.save = Mock()
        QuotaUsage.save = Mock()

        FAKE_QUOTAS = [QuotaUsage(id=1,
                                  tenant_id=FAKE_TENANT1,
                                  resource=Resource.INSTANCES,
                                  in_use=5,
                                  reserved=2),
                       QuotaUsage(id=2,
                                  tenant_id=FAKE_TENANT1,
                                  resource=Resource.VOLUMES,
                                  in_use=1,
                                  reserved=2)]

        FAKE_RESERVATIONS = [Reservation(usage_id=1,
                                         delta=1,
                                         status=Reservation.Statuses.RESERVED),
                             Reservation(usage_id=2,
                                         delta=2,
                                         status=Reservation.Statuses.RESERVED)]

        QuotaUsage.find_by = Mock(side_effect=FAKE_QUOTAS)
        self.driver.commit(FAKE_RESERVATIONS)

        self.assertEqual(6, FAKE_QUOTAS[0].in_use)
        self.assertEqual(1, FAKE_QUOTAS[0].reserved)
        self.assertEqual(Reservation.Statuses.COMMITTED,
                         FAKE_RESERVATIONS[0].status)

        self.assertEqual(3, FAKE_QUOTAS[1].in_use)
        self.assertEqual(0, FAKE_QUOTAS[1].reserved)
        self.assertEqual(Reservation.Statuses.COMMITTED,
                         FAKE_RESERVATIONS[1].status)

    def test_commit_cannot_be_less_than_zero(self):

        Reservation.save = Mock()
        QuotaUsage.save = Mock()

        FAKE_QUOTAS = [QuotaUsage(id=1,
                                  tenant_id=FAKE_TENANT1,
                                  resource=Resource.INSTANCES,
                                  in_use=0,
                                  reserved=-1)]

        FAKE_RESERVATIONS = [Reservation(usage_id=1,
                                         delta=-1,
                                         status=Reservation.Statuses.RESERVED)]

        QuotaUsage.find_by = Mock(side_effect=FAKE_QUOTAS)
        self.driver.commit(FAKE_RESERVATIONS)

        self.assertEqual(0, FAKE_QUOTAS[0].in_use)
        self.assertEqual(0, FAKE_QUOTAS[0].reserved)
        self.assertEqual(Reservation.Statuses.COMMITTED,
                         FAKE_RESERVATIONS[0].status)

    def test_rollback(self):

        Reservation.save = Mock()
        QuotaUsage.save = Mock()

        FAKE_QUOTAS = [QuotaUsage(id=1,
                                  tenant_id=FAKE_TENANT1,
                                  resource=Resource.INSTANCES,
                                  in_use=5,
                                  reserved=2),
                       QuotaUsage(id=2,
                                  tenant_id=FAKE_TENANT1,
                                  resource=Resource.VOLUMES,
                                  in_use=1,
                                  reserved=2)]

        FAKE_RESERVATIONS = [Reservation(usage_id=1,
                                         delta=1,
                                         status=Reservation.Statuses.RESERVED),
                             Reservation(usage_id=2,
                                         delta=2,
                                         status=Reservation.Statuses.RESERVED)]

        QuotaUsage.find_by = Mock(side_effect=FAKE_QUOTAS)
        self.driver.rollback(FAKE_RESERVATIONS)

        self.assertEqual(5, FAKE_QUOTAS[0].in_use)
        self.assertEqual(1, FAKE_QUOTAS[0].reserved)
        self.assertEqual(Reservation.Statuses.ROLLEDBACK,
                         FAKE_RESERVATIONS[0].status)

        self.assertEqual(1, FAKE_QUOTAS[1].in_use)
        self.assertEqual(0, FAKE_QUOTAS[1].reserved)
        self.assertEqual(Reservation.Statuses.ROLLEDBACK,
                         FAKE_RESERVATIONS[1].status)
