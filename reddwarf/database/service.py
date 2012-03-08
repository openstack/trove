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

from reddwarf import rpc
from reddwarf.common import config
from reddwarf.common import context
from reddwarf.common import exception
from reddwarf.common import wsgi
from reddwarf.database import models
from reddwarf.database import views

CONFIG = config.Config
LOG = logging.getLogger('reddwarf.database.service')


class BaseController(wsgi.Controller):
    """Base controller class."""

    def __init__(self):
        pass


class InstanceController(BaseController):
    """Controller for instance functionality"""

    def index(self, req, tenant_id):
        """Return all instances."""
        servers = models.Instances(req.headers["X-Auth-Token"]).data()
        #TODO(hub-cap): Remove this, this is only for testing communication
        #               between services
        # rpc.cast(context.ReddwarfContext(), "taskmanager.None",
        #         {"method": "test_method", "BARRRR": "ARGGGGG"})

        #TODO(cp16net): need to set the return code correctly
        return wsgi.Result(views.InstancesView(servers).data(), 201)

    def show(self, req, tenant_id, id):
        """Return a single instance."""
        server = models.Instance(proxy_token=req.headers["X-Auth-Token"],
                                 uuid=id).data()
        #TODO(cp16net): need to set the return code correctly
        return wsgi.Result(views.InstanceView(server).data(), 201)

    def delete(self, req, tenant_id, id):
        """Delete a single instance."""

        models.Instance.delete(proxy_token=req.headers["X-Auth-Token"],
                               uuid=id)

        # TODO(hub-cap): fixgure out why the result is coming back as None
        LOG.info("result of delete %s" % result)
        #TODO(cp16net): need to set the return code correctly
        return wsgi.Result(202)

    def create(self, req, body, tenant_id):
        # find the service id (cant be done yet at startup due to
        # inconsitencies w/ the load app paste
        # TODO(hub-cap): figure out how to get this to work in __init__ time
        # TODO(hub-cap): The problem with this in __init__ is that the paste
        #   config is generated w/ the same config file as the db flags that
        #   are needed for init. These need to be split so the db can be init'd
        #   w/o the paste stuff. Since the paste stuff inits the
        #   database.service module, it is a chicken before the egg problem.
        #   Simple refactor will fix it and we can move this into the __init__
        #   code. Or maybe we shouldnt due to the nature of changing images.
        #   This needs discussion.
        database = models.ServiceImage.find_by(service_name="database")
        image_id = database['image_id']
        server = models.Instance.create(req.headers["X-Auth-Token"],
                                        body['name'],
                                        image_id,
                                        body['flavor']).data()

        # Now wait for the response from the create to do additional work
        #TODO(cp16net): need to set the return code correctly
        return wsgi.Result(views.InstanceView(server).data(), 201)


class API(wsgi.Router):
    """API"""
    def __init__(self):
        mapper = routes.Mapper()
        super(API, self).__init__(mapper)
        self._instance_router(mapper)

    def _instance_router(self, mapper):
        instance_resource = InstanceController().create_resource()
        path = "/{tenant_id}/instances"
        mapper.resource("instance", path, controller=instance_resource)


def app_factory(global_conf, **local_conf):
    return API()
