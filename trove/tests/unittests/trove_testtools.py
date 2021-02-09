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

import abc
import random
import testtools
from unittest import mock
import uuid

from trove.common import cfg
from trove.common.context import TroveContext
from trove.common.notification import DBaaSAPINotification
from trove.common import policy
from trove.tests import root_logger


def is_bool(val):
    return str(val).lower() in ['true', '1', 't', 'y', 'yes', 'on', 'set']


def patch_notifier(test_case):
    notification_notify = mock.patch.object(
        DBaaSAPINotification, "_notify")
    notification_notify.start()
    test_case.addCleanup(notification_notify.stop)


class TroveTestNotification(DBaaSAPINotification):

    @abc.abstractmethod
    def event_type(self):
        return 'test_notification'

    @abc.abstractmethod
    def required_start_traits(self):
        return []


class TroveTestContext(TroveContext):

    def __init__(self, test_case, **kwargs):
        super(TroveTestContext, self).__init__(**kwargs)
        self.notification = TroveTestNotification(
            self, request_id='req_id', flavor_id='7')
        self.notification.server_type = 'api'
        patch_notifier(test_case)


class TestCase(testtools.TestCase):
    @classmethod
    def setUpClass(cls):
        super(TestCase, cls).setUpClass()
        root_logger.DefaultRootLogger(enable_backtrace=False)

    def setUp(self):
        super(TestCase, self).setUp()

        self.addCleanup(cfg.CONF.reset)

        root_logger.DefaultRootHandler.set_info(self.id())

        # Default manager used by all unittsest unless explicitly overridden.
        self.patch_datastore_manager('mysql')

        policy_patcher = mock.patch.object(policy, 'get_enforcer',
                                           return_value=mock.MagicMock())
        self.addCleanup(policy_patcher.stop)
        policy_patcher.start()

    def tearDown(self):
        # yes, this is gross and not thread aware.
        # but the only way to make it thread aware would require that
        # we single thread all testing
        root_logger.DefaultRootHandler.set_info(info=None)
        super(TestCase, self).tearDown()

    def patch_datastore_manager(self, manager_name):
        return self.patch_conf_property('datastore_manager', manager_name)

    def patch_conf_property(self, property_name, value, section=None):
        target = cfg.CONF
        if section:
            target = target.get(section)
        conf_patcher = mock.patch.object(
            target, property_name,
            new_callable=mock.PropertyMock(return_value=value))
        self.addCleanup(conf_patcher.stop)
        return conf_patcher.start()

    @classmethod
    def random_name(cls, name='', prefix=None):
        """Generate a random name that inclues a random number.

        :param str name: The name that you want to include
        :param str prefix: The prefix that you want to include

        :return: a random name. The format is
                 '<prefix>-<name>-<random number>'.
                 (e.g. 'prefixfoo-namebar-154876201')
        :rtype: string
        """
        randbits = str(random.randint(1, 0x7fffffff))
        rand_name = randbits
        if name:
            rand_name = name + '-' + rand_name
        if prefix:
            rand_name = prefix + '-' + rand_name
        return rand_name

    @classmethod
    def random_uuid(cls):
        return str(uuid.uuid4())

    def assertDictContains(self, parent, child):
        """Checks whether child dict is a subset of parent.

        assertDictContainsSubset() in standard Python 2.7 has been deprecated
        since Python 3.2
        """
        self.assertEqual(parent, dict(parent, **child))
