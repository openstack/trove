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

from reddwarf.common import exception
from reddwarf.common import pagination
from reddwarf.common import wsgi
from reddwarf.guestagent.db import models as guest_models
from reddwarf.extensions.mysql.common import populate_databases
from reddwarf.extensions.mysql.common import populate_users
from reddwarf.extensions.mysql import models
from reddwarf.extensions.mysql import views

LOG = logging.getLogger(__name__)


class RootController(wsgi.Controller):
    """Controller for instance functionality"""

    def index(self, req, tenant_id, instance_id):
        """ Returns True if root is enabled for the given instance;
                    False otherwise. """
        LOG.info(_("Getting root enabled for instance '%s'") % instance_id)
        LOG.info(_("req : '%s'\n\n") % req)
        context = req.environ[wsgi.CONTEXT_KEY]
        is_root_enabled = models.Root.load(context, instance_id)
        return wsgi.Result(views.RootEnabledView(is_root_enabled).data(), 200)

    def create(self, req, body, tenant_id, instance_id):
        """ Enable the root user for the db instance """
        LOG.info(_("Enabling root for instance '%s'") % instance_id)
        LOG.info(_("req : '%s'\n\n") % req)
        context = req.environ[wsgi.CONTEXT_KEY]
        user_name = context.user
        root = models.Root.create(context, instance_id, user_name)
        return wsgi.Result(views.RootCreatedView(root).data(), 200)


class UserController(wsgi.Controller):
    """Controller for instance functionality"""

    @classmethod
    def validate(cls, body):
        """Validate that the request has all the required parameters"""
        if not body:
            raise exception.BadRequest("The request contains an empty body")

        if not body.get('users', ''):
            raise exception.MissingKey(key='users')
        for user in body.get('users'):
            if not user.get('name'):
                raise exception.MissingKey(key='name')
            if not user.get('password'):
                raise exception.MissingKey(key='password')

    def index(self, req, tenant_id, instance_id):
        """Return all users."""
        LOG.info(_("Listing users for instance '%s'") % instance_id)
        LOG.info(_("req : '%s'\n\n") % req)
        context = req.environ[wsgi.CONTEXT_KEY]
        users, next_marker = models.Users.load(context, instance_id)
        view = views.UsersView(users)
        paged = pagination.SimplePaginatedDataView(req.url, 'users', view,
                                                   next_marker)
        return wsgi.Result(paged.data(), 200)

    def create(self, req, body, tenant_id, instance_id):
        """Creates a set of users"""
        LOG.info(_("Creating users for instance '%s'") % instance_id)
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("body : '%s'\n\n") % body)
        context = req.environ[wsgi.CONTEXT_KEY]
        self.validate(body)
        users = body['users']
        model_users = populate_users(users)
        models.User.create(context, instance_id, model_users)
        return wsgi.Result(None, 202)

    def delete(self, req, tenant_id, instance_id, id):
        LOG.info(_("Deleting user for instance '%s'") % instance_id)
        LOG.info(_("req : '%s'\n\n") % req)
        context = req.environ[wsgi.CONTEXT_KEY]
        try:
            user = guest_models.MySQLUser()
            user.name = id
            models.User.delete(context, instance_id, user.serialize())
        except ValueError as ve:
            raise exception.BadRequest(ve.message)
        return wsgi.Result(None, 202)

    def show(self, req, tenant_id, instance_id, id):
        raise webob.exc.HTTPNotImplemented()


class SchemaController(wsgi.Controller):
    """Controller for instance functionality"""

    @classmethod
    def validate(cls, body):
        """Validate that the request has all the required parameters"""
        if not body:
            raise exception.BadRequest("The request contains an empty body")
        if not body.get('databases', ''):
            raise exception.MissingKey(key='databases')
        for database in body.get('databases'):
            if not database.get('name', ''):
                raise exception.MissingKey(key='name')

    def index(self, req, tenant_id, instance_id):
        """Return all schemas."""
        LOG.info(_("Listing schemas for instance '%s'") % instance_id)
        LOG.info(_("req : '%s'\n\n") % req)
        context = req.environ[wsgi.CONTEXT_KEY]
        schemas, next_marker = models.Schemas.load(context, instance_id)
        view = views.SchemasView(schemas)
        paged = pagination.SimplePaginatedDataView(req.url, 'databases', view,
                                                   next_marker)
        return wsgi.Result(paged.data(), 200)

    def create(self, req, body, tenant_id, instance_id):
        """Creates a set of schemas"""
        LOG.info(_("Creating schema for instance '%s'") % instance_id)
        LOG.info(_("req : '%s'\n\n") % req)
        LOG.info(_("body : '%s'\n\n") % body)
        context = req.environ[wsgi.CONTEXT_KEY]
        self.validate(body)
        schemas = body['databases']
        model_schemas = populate_databases(schemas)
        models.Schema.create(context, instance_id, model_schemas)
        return wsgi.Result(None, 202)

    def delete(self, req, tenant_id, instance_id, id):
        LOG.info(_("Deleting schema for instance '%s'") % instance_id)
        LOG.info(_("req : '%s'\n\n") % req)
        context = req.environ[wsgi.CONTEXT_KEY]
        try:
            schema = guest_models.MySQLDatabase()
            schema.name = id
            models.Schema.delete(context, instance_id, schema.serialize())
        except ValueError as ve:
            raise exception.BadRequest(ve.message)
        return wsgi.Result(None, 202)

    def show(self, req, tenant_id, instance_id, id):
        raise webob.exc.HTTPNotImplemented()
