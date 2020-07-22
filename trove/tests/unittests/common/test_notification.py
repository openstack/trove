# Copyright 2015 Tesora Inc.
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
from unittest.mock import Mock
from unittest.mock import patch

from oslo_utils import timeutils

from trove import rpc
from trove.common import cfg
from trove.common import exception
from trove.common import notification
from trove.common.context import TroveContext
from trove.common.notification import EndNotification
from trove.common.notification import StartNotification
from trove.conductor import api as conductor_api
from trove.tests.unittests import trove_testtools


class TestEndNotification(trove_testtools.TestCase):

    def setUp(self):
        super(TestEndNotification, self).setUp()
        self.context = trove_testtools.TroveTestContext(self)

    def _server_call(self, server_type):
        with patch.object(self.context, "notification",
                          server_type=server_type) as notification:
            with EndNotification(self.context):
                pass
            self.assertTrue(notification.notify_end.called)

    def _server_exception(self, server_type):
        with patch.object(self.context, "notification",
                          server_type=server_type) as notification:
            try:
                with EndNotification(self.context):
                    raise exception.TroveError()
            except Exception:
                self.assertTrue(notification.notify_exc_info.called)

    def test_api_server_call(self):
        self._server_call('api')

    def test_api_server_exception(self):
        self._server_exception('api')

    def test_taskmanager_server_call(self):
        self._server_call('taskmanager')

    def test_taskmanager_server_exception(self):
        self._server_exception('taskmanager')

    def test_conductor_server_call(self):
        with patch.object(conductor_api, 'API') as api:
            with patch.object(self.context, "notification",
                              server_type='conductor'):
                with EndNotification(self.context):
                    pass
                self.assertTrue(api(self.context).notify_end.called)

    def test_conductor_server_exception(self):
        with patch.object(conductor_api, 'API') as api:
            with patch.object(self.context, "notification",
                              server_type='conductor'):
                try:
                    with EndNotification(self.context):
                        raise exception.TroveError()
                except Exception:
                    self.assertTrue(api(self.context).notify_exc_info.called)


class TestStartNotification(trove_testtools.TestCase):

    def setUp(self):
        super(TestStartNotification, self).setUp()
        self.context = trove_testtools.TroveTestContext(self)

    def test_api_call(self):
        with patch.object(self.context, "notification",
                          server_type='api') as notification:
            with StartNotification(self.context):
                pass
            self.assertTrue(notification.notify_start.called)

    def test_taskmanager_call(self):
        with patch.object(self.context, "notification",
                          server_type='taskmanager') as notification:
            with StartNotification(self.context):
                pass
            self.assertTrue(notification.notify_start.called)

    def test_conductor_call(self):
        with patch.object(conductor_api, 'API'):
            with patch.object(self.context, "notification",
                              server_type='conductor') as notification:
                with StartNotification(self.context):
                    pass
                self.assertTrue(notification.notify_start.called)


class TestNotificationCastWrapper(trove_testtools.TestCase):

    def test_no_notification(self):
        with notification.NotificationCastWrapper(TroveContext(), "foo"):
            pass

    def test_with_notification(self):
        context = trove_testtools.TroveTestContext(self)
        self.assertTrue(context.notification.needs_end_notification)
        with notification.NotificationCastWrapper(context, "foo"):
            self.assertEqual('foo', context.notification.server_type)
        self.assertEqual('api', context.notification.server_type)
        self.assertFalse(context.notification.needs_end_notification)


class TestTroveBaseTraits(trove_testtools.TestCase):

    def setUp(self):
        super(TestTroveBaseTraits, self).setUp()
        self.instance = Mock(db_info=Mock(created=timeutils.utcnow()))

    @patch.object(rpc, 'get_notifier')
    def test_n(self, notifier):
        notification.TroveBaseTraits(
            instance=self.instance).notify('event_type', 'publisher')
        self.assertTrue(notifier().info.called)
        a, _ = notifier().info.call_args
        payload = a[2]
        required_payload_keys = [
            'created_at', 'name', 'instance_id', 'instance_name',
            'instance_type_id', 'launched_at', 'nova_instance_id', 'region',
            'state_description', 'state', 'tenant_id', 'user_id'
        ]
        self.assertTrue(set(required_payload_keys).issubset(set(payload)))

    @patch.object(rpc, 'get_notifier')
    def test_notification_after_serialization(self, notifier):
        orig_notify = notification.TroveBaseTraits(instance=self.instance)
        serialized = orig_notify.serialize(None)
        new_notify = notification.TroveBaseTraits().deserialize(None,
                                                                serialized)
        new_notify.notify('event_type', 'publisher')
        self.assertTrue(notifier().info.called)


class TestTroveCommonTraits(trove_testtools.TestCase):

    def setUp(self):
        super(TestTroveCommonTraits, self).setUp()
        self.instance = Mock(db_info=Mock(created=timeutils.utcnow()))

    @patch.object(cfg.CONF, 'get', Mock())
    @patch.object(rpc, 'get_notifier')
    def test_notification(self, notifier):
        notification.TroveCommonTraits(
            instance=self.instance).notify('event_type', 'publisher')
        self.assertTrue(notifier().info.called)
        a, _ = notifier().info.call_args
        payload = a[2]
        self.assertIn('availability_zone', payload)

    @patch.object(cfg.CONF, 'get', Mock())
    @patch.object(rpc, 'get_notifier')
    def test_notification_after_serialization(self, notifier):
        orig_notify = notification.TroveCommonTraits(instance=self.instance)
        serialized = orig_notify.serialize(None)
        new_notify = notification.TroveCommonTraits().deserialize(None,
                                                                  serialized)
        new_notify.notify('event_type', 'publisher')
        self.assertTrue(notifier().info.called)


class TestTroveInstanceCreate(trove_testtools.TestCase):

    def setUp(self):
        super(TestTroveInstanceCreate, self).setUp()
        self.instance = Mock(db_info=Mock(created=timeutils.utcnow()))

    @patch.object(cfg.CONF, 'get', Mock())
    @patch.object(rpc, 'get_notifier')
    def test_notification(self, notifier):
        notification.TroveInstanceCreate(instance=self.instance).notify()
        self.assertTrue(notifier().info.called)

    @patch.object(cfg.CONF, 'get', Mock())
    @patch.object(rpc, 'get_notifier')
    def test_notification_after_serialization(self, notifier):
        orig_notify = notification.TroveInstanceCreate(instance=self.instance)
        serialized = orig_notify.serialize(None)
        new_notify = notification.TroveInstanceCreate().deserialize(None,
                                                                    serialized)
        new_notify.notify()
        self.assertTrue(notifier().info.called)


class TestTroveInstanceDelete(trove_testtools.TestCase):

    def setUp(self):
        super(TestTroveInstanceDelete, self).setUp()
        self.instance = Mock(db_info=Mock(created=timeutils.utcnow()))

    @patch.object(cfg.CONF, 'get', Mock())
    @patch.object(rpc, 'get_notifier')
    def test_notification(self, notifier):
        notification.TroveInstanceDelete(instance=self.instance).notify()
        self.assertTrue(notifier().info.called)

    @patch.object(cfg.CONF, 'get', Mock())
    @patch.object(rpc, 'get_notifier')
    def test_notification_after_serialization(self, notifier):
        orig_notify = notification.TroveInstanceDelete(instance=self.instance)
        serialized = orig_notify.serialize(None)
        new_notify = notification.TroveInstanceDelete().deserialize(None,
                                                                    serialized)
        new_notify.notify()
        self.assertTrue(notifier().info.called)


class TestTroveInstanceModifyFlavor(trove_testtools.TestCase):

    def setUp(self):
        super(TestTroveInstanceModifyFlavor, self).setUp()
        self.instance = Mock(db_info=Mock(created=timeutils.utcnow()))

    @patch.object(cfg.CONF, 'get', Mock())
    @patch.object(rpc, 'get_notifier')
    def test_notification(self, notifier):
        notification.TroveInstanceModifyFlavor(instance=self.instance).notify()
        self.assertTrue(notifier().info.called)

    @patch.object(cfg.CONF, 'get', Mock())
    @patch.object(rpc, 'get_notifier')
    def test_notification_after_serialization(self, notifier):
        orig_notify = notification.TroveInstanceModifyFlavor(
            instance=self.instance)
        serialized = orig_notify.serialize(None)
        new_notify = notification.TroveInstanceModifyFlavor().deserialize(
            None, serialized)
        new_notify.notify()
        self.assertTrue(notifier().info.called)


class TestDBaaSQuota(trove_testtools.TestCase):

    @patch.object(rpc, 'get_notifier')
    def test_notification(self, notifier):
        notification.DBaaSQuotas(None, Mock(), Mock()).notify()
        self.assertTrue(notifier().info.called)


class DBaaSTestNotification(notification.DBaaSAPINotification):

    def event_type(self):
        return 'instance_test'

    def required_start_traits(self):
        return ['name', 'flavor_id', 'datastore']

    def optional_start_traits(self):
        return ['databases', 'users']

    def required_end_traits(self):
        return ['instance_id']


class TestDBaaSNotification(trove_testtools.TestCase):

    def setUp(self):
        super(TestDBaaSNotification, self).setUp()
        self.test_n = DBaaSTestNotification(Mock(), request=Mock())

    def test_missing_required_start_traits(self):
        self.assertRaisesRegex(exception.TroveError,
                               self.test_n.required_start_traits()[0],
                               self.test_n.notify_start)

    def test_invalid_start_traits(self):
        self.assertRaisesRegex(exception.TroveError,
                               "The following required keys",
                               self.test_n.notify_start, foo='bar')

    def test_missing_required_end_traits(self):
        self.assertRaisesRegex(exception.TroveError,
                               self.test_n.required_end_traits()[0],
                               self.test_n.notify_end)

    def test_invalid_end_traits(self):
        self.assertRaisesRegex(exception.TroveError,
                               "The following required keys",
                               self.test_n.notify_end, foo='bar')

    def test_missing_required_error_traits(self):
        self.assertRaisesRegex(exception.TroveError,
                               self.test_n.required_error_traits()[0],
                               self.test_n._notify, 'error',
                               self.test_n.required_error_traits(), [])

    @patch.object(rpc, 'get_notifier')
    def test_start_event(self, notifier):
        self.test_n.notify_start(name='foo', flavor_id=7, datastore='db')
        self.assertTrue(notifier().info.called)
        a, _ = notifier().info.call_args
        self.assertEqual('dbaas.instance_test.start', a[1])

    @patch.object(rpc, 'get_notifier')
    def test_end_event(self, notifier):
        self.test_n.notify_end(instance_id='foo')
        self.assertTrue(notifier().info.called)
        a, _ = notifier().info.call_args
        self.assertEqual('dbaas.instance_test.end', a[1])

    @patch.object(rpc, 'get_notifier')
    def test_verify_base_values(self, notifier):
        self.test_n.notify_start(name='foo', flavor_id=7, datastore='db')
        self.assertTrue(notifier().info.called)
        a, _ = notifier().info.call_args
        payload = a[2]
        self.assertIn('client_ip', payload)
        self.assertIn('request_id', payload)
        self.assertIn('server_type', payload)
        self.assertIn('server_ip', payload)
        self.assertIn('tenant_id', payload)

    @patch.object(rpc, 'get_notifier')
    def test_verify_required_start_args(self, notifier):
        self.test_n.notify_start(name='foo', flavor_id=7, datastore='db')
        self.assertTrue(notifier().info.called)
        a, _ = notifier().info.call_args
        payload = a[2]
        self.assertIn('name', payload)
        self.assertIn('flavor_id', payload)
        self.assertIn('datastore', payload)
        self.assertNotIn('users', payload)

    @patch.object(rpc, 'get_notifier')
    def test_verify_optional_start_args(self, notifier):
        self.test_n.notify_start(name='foo', flavor_id=7, datastore='db',
                                 users='the users')
        self.assertTrue(notifier().info.called)
        a, _ = notifier().info.call_args
        payload = a[2]
        self.assertIn('users', payload)

    @patch.object(rpc, 'get_notifier')
    def test_verify_required_end_args(self, notifier):
        self.test_n.notify_end(instance_id='foo')
        self.assertTrue(notifier().info.called)
        a, _ = notifier().info.call_args
        payload = a[2]
        self.assertIn('instance_id', payload)

    def _test_notify_callback(self, fn, *args, **kwargs):
        with patch.object(rpc, 'get_notifier') as notifier:
            mock_callback = Mock()
            self.test_n.register_notify_callback(mock_callback)
            mock_context = Mock()
            mock_context.notification = Mock()
            self.test_n.context = mock_context
            fn(*args, **kwargs)
            self.assertTrue(notifier().info.called)
            self.assertTrue(mock_callback.called)
            self.test_n.register_notify_callback(None)

    def test_notify_callback(self):
        required_keys = {
            'datastore': 'ds',
            'name': 'name',
            'flavor_id': 'flav_id',
            'instance_id': 'inst_id',
        }
        self._test_notify_callback(self.test_n.notify_start,
                                   **required_keys)
        self._test_notify_callback(self.test_n.notify_end,
                                   **required_keys)
        self._test_notify_callback(self.test_n.notify_exc_info,
                                   'error', 'exc')
