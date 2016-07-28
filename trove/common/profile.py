# Copyright 2015 IBM Corp.
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

from oslo_context import context
from oslo_log import log as logging
import oslo_messaging as messaging
from osprofiler import notifier
from osprofiler import web

from trove.common import cfg
from trove.common.i18n import _LW
from trove import rpc


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


def setup_profiler(binary, host):
    if CONF.profiler.enabled:
        _notifier = notifier.create(
            "Messaging", messaging, context.get_admin_context().to_dict(),
            rpc.TRANSPORT, "trove", binary, host)
        notifier.set(_notifier)
        web.enable(CONF.profiler.hmac_keys)
        LOG.warning(_LW("The OpenStack Profiler is enabled. Using one"
                        " of the hmac_keys specified in the trove.conf file "
                        "(typically in /etc/trove), a trace can be made of "
                        "all requests. Only an admin user can retrieve "
                        "the trace information, however.\n"
                        "To disable the profiler, add the following to the "
                        "configuration file:\n"
                        "[profiler]\n"
                        "enabled=false"))
    else:
        web.disable()
