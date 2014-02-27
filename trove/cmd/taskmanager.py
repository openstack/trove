#!/usr/bin/env python
# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack Foundation
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

import sys

import eventlet

from trove.common import cfg
from oslo.config import cfg as openstack_cfg
from trove.openstack.common import log as logging
from trove.common import debug_utils

# Apply whole eventlet.monkey_patch excluding 'thread' module.
# Decision for 'thread' module patching will be made
# after debug_utils setting up
eventlet.monkey_patch(all=True, thread=False)

CONF = cfg.CONF
CONF.register_opts([openstack_cfg.StrOpt('taskmanager_manager')])


def startup(topic):
    cfg.parse_args(sys.argv)
    logging.setup(None)

    debug_utils.setup()

    # Patch 'thread' module if debug is disabled
    if not debug_utils.enabled():
        eventlet.monkey_patch(thread=True)

    from trove.common.rpc import service as rpc_service
    from trove.openstack.common import service as openstack_service
    from trove.db import get_db_api

    get_db_api().configure_db(CONF)
    server = rpc_service.RpcService(manager=CONF.taskmanager_manager,
                                    topic=topic)
    launcher = openstack_service.launch(server)
    launcher.wait()


def main():
    startup(None)


def mgmt_main():
    startup("mgmt-taskmanager")
