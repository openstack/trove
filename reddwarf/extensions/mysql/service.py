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
from reddwarf.common import exception
from reddwarf.common import wsgi
from reddwarf.guestagent.db import models as guest_models
from reddwarf.extensions.mysql import models
from reddwarf.extensions.mysql import views

LOG = logging.getLogger(__name__)


class BaseController(wsgi.Controller):
    """Base controller class."""


class RootController(BaseController):
    """Controller for instance functionality"""

    def index(self, req, tenant_id, instance_id):
        """ Returns True if root is enabled for the given instance;
                    False otherwise. """
        LOG.info("Getting root enabled for instance '%s'" % instance_id)
        LOG.info("req : '%s'\n\n" % req)
        context = rd_context.ReddwarfContext(
                          auth_tok=req.headers["X-Auth-Token"],
                          tenant=tenant_id)
        is_root_enabled = models.Root.load(context, instance_id)
        return views.RootEnabledView(is_root_enabled).data()

    def create(self, req, body, tenant_id, instance_id):
        """ Enable the root user for the db instance """
        LOG.info("Enabling root for instance '%s'" % instance_id)
        LOG.info("req : '%s'\n\n" % req)
        context = rd_context.ReddwarfContext(
                          auth_tok=req.headers["X-Auth-Token"],
                          tenant=tenant_id)
        root = models.Root.create(context, instance_id)
        return views.RootCreatedView(root).data()


class UserController(BaseController):
    """Controller for instance functionality"""

    @classmethod
    def validate(cls, body):
        """Validate that the request has all the required parameters"""
        if not body:
            raise exception.BadRequest("The request contains an empty body")

        if not body.get('users', ''):
            raise exception.BadRequest("Required element/key 'users' was not "
                                       "specified")
        for user in body.get('users'):
            if not user.get('name'):
                raise exception.BadRequest("Required attribute/key 'name' was "
                                           "not specified")
            if not user.get('password'):
                raise exception.BadRequest("Required attribute/key 'password' "
                                           "was not specified")

    def index(self, req, tenant_id, instance_id):
        """Return all users."""
        LOG.info("Listing users for instance '%s'" % instance_id)
        LOG.info("req : '%s'\n\n" % req)
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
        try:
            self.validate(body)
        except exception.BadRequest as br:
            return webob.exc.HTTPBadRequest(br)
        users = body['users']
        model_users = models.populate_users(users)
        models.User.create(context, instance_id, model_users)
        return webob.exc.HTTPAccepted()

    def delete(self, req, tenant_id, instance_id, id):
        LOG.info("Deleting user for instance '%s'" % instance_id)
        LOG.info("req : '%s'\n\n" % req)
        context = rd_context.ReddwarfContext(
                          auth_tok=req.headers["X-Auth-Token"],
                          tenant=tenant_id)
        user = guest_models.MySQLUser()
        user.name = id
        models.User.delete(context, instance_id, user.serialize())
        return webob.exc.HTTPAccepted()


class SchemaController(BaseController):
    """Controller for instance functionality"""

    @classmethod
    def validate(cls, body):
        """Validate that the request has all the required parameters"""
        if not body:
            raise exception.BadRequest("The request contains an empty body")
        if not body.get('databases', ''):
            raise exception.BadRequest(key='databases')
        for database in body.get('databases'):
            if not database.get('name', ''):
                raise exception.BadRequest(key='name')

    def index(self, req, tenant_id, instance_id):
        """Return all schemas."""
        LOG.info("Listing schemas for instance '%s'" % instance_id)
        LOG.info("req : '%s'\n\n" % req)
        context = rd_context.ReddwarfContext(
                          auth_tok=req.headers["X-Auth-Token"],
                          tenant=tenant_id)
        schemas = models.Schemas.load(context, instance_id)
        # Not exactly sure why we cant return a wsgi.Result() here
        return views.SchemasView(schemas).data()

    def create(self, req, body, tenant_id, instance_id):
        """Creates a set of schemas"""
        LOG.info("Creating schema for instance '%s'" % instance_id)
        LOG.info("req : '%s'\n\n" % req)
        LOG.info("body : '%s'\n\n" % body)
        context = rd_context.ReddwarfContext(
                          auth_tok=req.headers["X-Auth-Token"],
                          tenant=tenant_id)
        try:
            self.validate(body)
        except exception.BadRequest as br:
            return webob.exc.HTTPBadRequest(br)
        schemas = body['databases']
        model_schemas = models.populate_databases(schemas)
        models.Schema.create(context, instance_id, model_schemas)
        return webob.exc.HTTPAccepted()

    def delete(self, req, tenant_id, instance_id, id):
        LOG.info("Deleting schema for instance '%s'" % instance_id)
        LOG.info("req : '%s'\n\n" % req)
        context = rd_context.ReddwarfContext(
                          auth_tok=req.headers["X-Auth-Token"],
                          tenant=tenant_id)
        schema = guest_models.MySQLDatabase()
        schema.name = id
        models.Schema.delete(context, instance_id, schema.serialize())
        return webob.exc.HTTPAccepted()
