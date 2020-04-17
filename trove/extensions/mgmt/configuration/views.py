# Copyright 2014 Rackspace
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
#
from oslo_log import log as logging

LOG = logging.getLogger(__name__)


class MgmtConfigurationParameterView(object):

    def __init__(self, config):
        self.config = config

    def data(self):
        # v1 api is to be a 'true' or 'false' json boolean instead of 1/0
        restart_required = True if self.config.restart_required else False
        ret = {
            "name": self.config.name,
            "datastore_version_id": self.config.datastore_version_id,
            "restart_required": restart_required,
            "type": self.config.data_type,
        }
        if self.config.max_size:
            ret["max_size"] = int(self.config.max_size)
        if self.config.min_size:
            ret["min_size"] = int(self.config.min_size)
        return ret


class MgmtConfigurationParametersView(object):

    def __init__(self, configs):
        self.configs = configs

    def data(self):
        params = []
        LOG.debug(self.configs.__dict__)
        for p in self.configs:
            param = MgmtConfigurationParameterView(p)
            params.append(param.data())
        return {"configuration-parameters": params}
