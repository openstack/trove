#!/usr/bin/env python

# Copyright 2013 Rackspace Hosting
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

import eventlet
eventlet.monkey_patch(all=True, thread=False)

import gettext
import sys


gettext.install('trove', unicode=1)


from trove.common import cfg
from trove.common import debug_utils
from trove.common.rpc import service as rpc_service
from trove.db import get_db_api
from trove.openstack.common import log as logging
from trove.openstack.common import service as openstack_service

CONF = cfg.CONF


def launch_services():
    get_db_api().configure_db(CONF)
    manager = 'trove.conductor.manager.Manager'
    topic = CONF.conductor_queue
    server = rpc_service.RpcService(manager=manager, topic=topic)
    launcher = openstack_service.launch(server,
                                        workers=CONF.trove_conductor_workers)
    launcher.wait()


def main():
    cfg.parse_args(sys.argv)
    logging.setup(None)

    debug_utils.setup()

    if not debug_utils.enabled():
        eventlet.monkey_patch(thread=True)

    launch_services()
