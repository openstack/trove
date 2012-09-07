#    Copyright 2012 OpenStack LLC
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

import logging

from reddwarf.openstack.common import rpc
from reddwarf.common import config
from reddwarf.common import exception


CONFIG = config.Config
LOG = logging.getLogger(__name__)


class ManagerAPI(object):
    """Extend this API for interacting with the common methods of managers"""

    def __init__(self, context):
        self.context = context

    def _cast(self, method_name, **kwargs):
        if CONFIG.get("remote_implementation", "real") == "fake":
            self._fake_cast(method_name, **kwargs)
        else:
            self._real_cast(method_name, **kwargs)

    def _real_cast(self, method_name, **kwargs):
        try:
            rpc.cast(self.context, self._get_routing_key(),
                     {"method": method_name, "args": kwargs})
        except Exception as e:
            LOG.error(e)
            raise exception.TaskManagerError(original_message=str(e))

    def _fake_cast(self, method_name, **kwargs):
        pass
