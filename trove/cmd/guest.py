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

import eventlet
eventlet.monkey_patch()

import gettext
import sys


gettext.install('trove', unicode=1)


from trove.common import cfg
from trove.common.rpc import service as rpc_service
from oslo.config import cfg as openstack_cfg
from trove.openstack.common import log as logging
from trove.openstack.common import service as openstack_service


CONF = cfg.CONF
CONF.register_opts([openstack_cfg.StrOpt('guest_id')])


def main():
    cfg.parse_args(sys.argv)
    from trove.guestagent import dbaas
    logging.setup(None)

    manager = dbaas.datastore_registry().get(CONF.datastore_manager)
    if not manager:
        msg = ("Manager class not registered for datastore manager %s" %
               CONF.datastore_manager)
        raise RuntimeError(msg)
    server = rpc_service.RpcService(manager=manager, host=CONF.guest_id)
    launcher = openstack_service.launch(server)
    launcher.wait()
