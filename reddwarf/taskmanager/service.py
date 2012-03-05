# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack LLC.
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

import logging
import routes
import webob.exc

from reddwarf.common import wsgi
from reddwarf import rpc

LOG = logging.getLogger('reddwarf.taskmanager.service')


class Controller(wsgi.Controller):
    """Base controller class."""
    connected = False

    #TODO(hub-cap):Make this not so nasty, this should not be here
    def _create_connection(self, topic, host):
        # Create a connection for rpc usage
        if (self.connected):
            return
        self.conn = rpc.create_connection(new=True)
        LOG.debug(_("Creating Consumer connection for Service %s") %
                  topic)

        # Share this same connection for these Consumers
        self.conn.create_consumer(topic, self, fanout=False)

        node_topic = '%s.%s' % (topic, host)
        self.conn.create_consumer(node_topic, self, fanout=False)

        self.conn.create_consumer(topic, self, fanout=True)

        # Consume from all consumers in a thread
        self.conn.consume_in_thread()

    def index(self, req):
        """Gets a list of all tasks available"""
        self._create_connection("foo", "ubuntu")
        return "All Tasks -- Impl TBD"

    def show(self, req, id):
        """Gets detailed information about an individual task"""
        return "Single Task -- Impl TBD"


class API(wsgi.Router):
    """API"""
    def __init__(self):
        mapper = routes.Mapper()
        super(API, self).__init__(mapper)
        self._instance_router(mapper)

    def _instance_router(self, mapper):
        resource = Controller().create_resource()
        path = "/tasks"
        mapper.resource("task", path, controller=resource)


def app_factory(global_conf, **local_conf):
    return API()

