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

"""RPC helper for launching a rpc service."""

import kombu

from trove.openstack.common import rpc as openstack_rpc
from trove.common import cfg

CONF = cfg.CONF


def delete_queue(context, topic):
    if CONF.rpc_backend == "trove.openstack.common.rpc.impl_kombu":
        connection = openstack_rpc.create_connection()
        channel = connection.channel
        durable = connection.conf.amqp_durable_queues
        queue = kombu.entity.Queue(name=topic, channel=channel,
                                   auto_delete=False, exclusive=False,
                                   durable=durable)
        queue.delete()
