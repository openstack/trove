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
from oslo_config import cfg as openstack_cfg
from trove.cmd.common import with_initialize


extra_opts = [openstack_cfg.StrOpt('taskmanager_manager')]


def startup(conf, topic):
    from trove.common.rpc import service as rpc_service
    from trove.common.rpc import version as rpc_version
    from trove.openstack.common import service as openstack_service

    server = rpc_service.RpcService(
        manager=conf.taskmanager_manager, topic=topic,
        rpc_api_version=rpc_version.RPC_API_VERSION)
    launcher = openstack_service.launch(server)
    launcher.wait()


@with_initialize(extra_opts=extra_opts)
def main(conf):
    startup(conf, conf.taskmanager_queue)


@with_initialize(extra_opts=extra_opts)
def mgmt_main(conf):
    startup(conf, "mgmt-taskmanager")
