# Copyright 2014 Rackspace Hosting
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

from collections import defaultdict

import eventlet

import trove.openstack.common.log as logging
from trove import rpc
from trove.taskmanager.api import API
from trove.taskmanager.manager import Manager
import trove.tests.util.usage as usage

LOG = logging.getLogger(__name__)
MESSAGE_QUEUE = defaultdict(list)


class FakeRpcClient(object):

    def call(self, context, method_name, *args, **kwargs):
        manager, method = self._get_tm_method(method_name)
        return method(manager, context, *args, **kwargs)

    def cast(self, context, method_name, *args, **kwargs):
        manager, method = self._get_tm_method(method_name)

        def func():
            method(manager, context, *args, **kwargs)

        eventlet.spawn_after(0.1, func)

    def _get_tm_method(self, method_name):
        manager = Manager()
        method = getattr(Manager, method_name)
        return manager, method

    def prepare(self, *args, **kwargs):
        return self


class FakeNotifier:

    def info(self, ctxt, event_type, payload):
        usage.notify(event_type, payload)


def monkey_patch():
    def fake_get_client(self, *args, **kwargs):
        return FakeRpcClient()

    def fake_get_notifier(service=None, host=None, publisher_id=None):
        return FakeNotifier()

    API.get_client = fake_get_client
    rpc.get_notifier = fake_get_notifier
