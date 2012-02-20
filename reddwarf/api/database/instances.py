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

from nova import flags
from nova import log as logging
from nova.api.openstack import wsgi
from novaclient.v1_1.client import Client
from nova.openstack.common import cfg
from reddwarf.api.database.views import instances as views_instances

LOG = logging.getLogger('reddwarf.api.database.instances')

reddwarf_opts = [
    cfg.StrOpt('reddwarf_proxy_admin_user',
        default='admin',
        help='User by which you make proxy requests to the nova api with'),
    cfg.StrOpt('reddwarf_proxy_admin_pass',
        default='3de4922d8b6ac5a1aad9',
        help='Password for the admin user defined in reddwarf_proxy_admin_user'),
    cfg.StrOpt('reddwarf_proxy_admin_tenant_name',
        default='admin',
        help='Tenant name fro teh admin user defined in reddwarf_proxy_admin_user'),
    cfg.StrOpt('reddwarf_auth_url',
        default='http://0.0.0.0:5000/v2.0',
        help='Auth url for authing against reddwarf_proxy_admin_user'),
    ]

FLAGS = flags.FLAGS
FLAGS.register_opts(reddwarf_opts)


class Controller(wsgi.Controller):

    _view_builder_class = views_instances.ViewBuilder

    def __init__(self, **kwargs):
        super(Controller, self).__init__(**kwargs)

    def get_client(self, proxy_token):
        client = Client(FLAGS.reddwarf_proxy_admin_user, FLAGS.reddwarf_proxy_admin_pass,
            FLAGS.reddwarf_proxy_admin_tenant_name, FLAGS.reddwarf_auth_url, token=proxy_token)
        client.authenticate()
        return client

    def index(self, req):
        """Return all instances."""
        servers = self.get_client(req.headers["X-Auth-Token"]).servers.list()
        for server in servers:
            LOG.info(server.__dict__)
        return self._view_builder.index(req, servers)

    def create(self, req, body):
        resp = self.get_client(req.headers["X-Auth-Token"]).servers.create(body['name'], body['image'], body['flavor'])
        LOG.info(resp)
        return "i got a server back %s " % resp.__dict__

def create_resource():
    return wsgi.Resource(Controller())
