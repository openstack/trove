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
from oslo_service import service as openstack_service

from trove.cmd.common import with_initialize
from trove.taskmanager import api as task_api


extra_opts = [openstack_cfg.StrOpt('taskmanager_manager')]


def startup(conf, topic):
    from trove.common import notification
    from trove.common.rpc import service as rpc_service
    from trove.instance import models as inst_models

    notification.DBaaSAPINotification.register_notify_callback(
        inst_models.persist_instance_fault)

    if conf.enable_secure_rpc_messaging:
        key = conf.taskmanager_rpc_encr_key
    else:
        key = None

    server = rpc_service.RpcService(
        key=key, manager=conf.taskmanager_manager, topic=topic,
        rpc_api_version=task_api.API.API_LATEST_VERSION)
    launcher = openstack_service.launch(conf, server)
    launcher.wait()


@with_initialize(extra_opts=extra_opts)
def main(conf):
    startup(conf, conf.taskmanager_queue)


@with_initialize(extra_opts=extra_opts)
def mgmt_main(conf):
    startup(conf, "mgmt-taskmanager")
