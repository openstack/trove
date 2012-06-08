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

from reddwarf.common import config
from reddwarf.common import exception
from reddwarf.instance import models as imodels


CONFIG = config.Config
LOG = logging.getLogger(__name__)


class MgmtInstance(imodels.SimpleInstance):

    def __init__(self, *args, **kwargs):
        super(MgmtInstance, self).__init__(*args)
        self.server = kwargs['server']

    @property
    def host(self):
        return self.server.host if self.server else ""


class MgmtInstances(imodels.Instances):

    def __init__(self, *args, **kwargs):
        super(MgmtInstances, self).__init__(*args, **kwargs)

    @staticmethod
    def load_status_from_existing(context, db_infos, servers):

        def load_instance(context, db, status, server=None):
            return MgmtInstance(context, db, status, server=server)

        if context is None:
            raise TypeError("Argument context not defined.")

        find_server = imodels.create_server_list_matcher(
                                        _convert_server_objects(servers))
        ret = imodels.Instances._load_servers_status(load_instance, context,
                                                     db_infos, find_server)
        return ret


def _convert_server_objects(servers):
    server_objs = []
    for server in servers:
        server_objs.append(Server(server))
    return server_objs


class Server(object):

    def __init__(self, server):
        self.id = server['id']
        self.status = server['status']
        self.name = server['name']
        self.host = server['host']
