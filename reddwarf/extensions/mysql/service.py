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
import webob.exc

from reddwarf.common import context as rd_context
from reddwarf.common import wsgi
from reddwarf.extensions.mysql import models
from reddwarf.extensions.mysql import views

LOG = logging.getLogger(__name__)


class BaseController(wsgi.Controller):
    """Base controller class."""


class UserController(BaseController):
    """Controller for instance functionality"""

    def index(self, req, tenant_id, instance_id):
        """Return all users."""
        context = rd_context.ReddwarfContext(
                          auth_tok=req.headers["X-Auth-Token"],
                          tenant=tenant_id)
        users = models.Users.load(context, instance_id)
        # Not exactly sure why we cant return a wsgi.Result() here
        return views.UsersView(users).data()

    def create(self, req, body, tenant_id, instance_id):
        """Creates a set of users"""
        LOG.info("Creating users for instance '%s'" % instance_id)
        LOG.info("req : '%s'\n\n" % req)
        LOG.info("body : '%s'\n\n" % body)
        context = rd_context.ReddwarfContext(
                          auth_tok=req.headers["X-Auth-Token"],
                          tenant=tenant_id)
        users = body['users']
        models.User.create(context, instance_id, users)
        return webob.exc.HTTPAccepted()


class SchemaController(BaseController):
    """Controller for instance functionality"""

    def index(self, req, tenant_id):
        """Return all schemas."""
        return "Schema list"
