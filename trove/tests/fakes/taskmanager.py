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

import eventlet
from trove.taskmanager import api
from trove.taskmanager.manager import Manager


class FakeApi(api.API):

    def __init__(self, context):
        self.context = context

    def make_msg(self, method_name, *args, **kwargs):
        return {"name": method_name, "args": args, "kwargs": kwargs}

    def call(self, context, msg):
        manager, method = self.get_tm_method(msg['name'])
        return method(manager, context, *msg['args'], **msg['kwargs'])

    def cast(self, context, msg):
        manager, method = self.get_tm_method(msg['name'])

        def func():
            method(manager, context, *msg['args'], **msg['kwargs'])

        eventlet.spawn_after(0.1, func)

    def get_tm_method(self, method_name):
        manager = Manager()
        method = getattr(Manager, method_name)
        return manager, method


def monkey_patch():
    api.API = FakeApi

    def fake_load(context, manager=None):
        return FakeApi(context)
    api.load = fake_load
