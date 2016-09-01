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
from oslo_concurrency import processutils
from oslo_config import cfg as openstack_cfg

from trove.cmd.common import with_initialize


opts = [
    openstack_cfg.BoolOpt('fork', short='f', default=False, dest='fork'),
    openstack_cfg.StrOpt('pid-file', default='.pid'),
    openstack_cfg.StrOpt('override-logfile', default=None),
]


def setup_logging(conf):
    if conf.override_logfile:
        conf.use_stderr = False
        conf.log_file = conf.override_logfile


@with_initialize(extra_opts=opts, pre_logging=setup_logging)
def main(conf):
    if conf.fork:
        pid = os.fork()
        if pid == 0:
            start_server(conf)
        else:
            print("Starting server:%s" % pid)
            pid_file = conf.pid_file
            with open(pid_file, 'w') as f:
                f.write(str(pid))
    else:
        start_server(conf)


def start_fake_taskmanager(conf):
    topic = conf.taskmanager_queue
    from trove.common.rpc import service as rpc_service
    from trove.common.rpc import version as rpc_version
    taskman_service = rpc_service.RpcService(
        topic=topic, rpc_api_version=rpc_version.RPC_API_VERSION,
        manager='trove.taskmanager.manager.Manager')
    taskman_service.start()


def start_server(conf):
    from trove.common import wsgi
    conf_file = conf.find_file(conf.api_paste_config)
    workers = conf.trove_api_workers or processutils.get_worker_count()
    launcher = wsgi.launch('trove', conf.bind_port or 8779, conf_file,
                           workers=workers)
    start_fake_taskmanager(conf)
    launcher.wait()
