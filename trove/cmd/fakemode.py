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

import gettext
import sys


gettext.install('trove', unicode=1)


from trove.common import cfg
from oslo.config import cfg as openstack_cfg
from trove.openstack.common import log as logging
from trove.common import wsgi
from trove.db import get_db_api

extra_opts = [
    openstack_cfg.BoolOpt('fork',
                          short='f',
                          default=False,
                          dest='fork'),
    openstack_cfg.StrOpt('pid-file',
                         default='.pid'),
    openstack_cfg.StrOpt('override-logfile',
                         default=None),
]

CONF = cfg.CONF
CONF.register_cli_opts(extra_opts)


def start_fake_taskmanager():
    topic = CONF.taskmanager_queue
    from trove.openstack.common.rpc import service as rpc_service
    from trove.taskmanager import manager
    manager_impl = manager.Manager()
    taskman_service = rpc_service.Service(None, topic=topic,
                                          manager=manager_impl)
    taskman_service.start()


def run_server():
    get_db_api().configure_db(CONF)
    conf_file = CONF.find_file(CONF.api_paste_config)
    launcher = wsgi.launch('trove', CONF.bind_port or 8779, conf_file,
                           workers=CONF.trove_api_workers)
    start_fake_taskmanager()
    launcher.wait()


def main():
    cfg.parse_args(sys.argv)
    if CONF.override_logfile:
        CONF.use_stderr = False
        CONF.log_file = CONF.override_logfile

    logging.setup(None)

    if CONF.fork:
        pid = os.fork()
        if pid == 0:
            run_server()
        else:
            print("Starting server:%s" % pid)
            pid_file = CONF.pid_file
            with open(pid_file, 'w') as f:
                f.write(str(pid))
    else:
        run_server()
