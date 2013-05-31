# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack Foundation
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

import webob.exc

from reddwarf.common import exception
from reddwarf.common import pagination
from reddwarf.common import wsgi
from reddwarf.extensions.mysql.common import populate_validated_databases
from reddwarf.extensions.mysql.common import populate_users
from reddwarf.extensions.mysql.common import unquote_user_host
from reddwarf.extensions.mysql import models
from reddwarf.extensions.mysql import views
from reddwarf.guestagent.db import models as guest_models
from reddwarf.openstack.common import log as logging
from reddwarf.openstack.common.gettextutils import _

from urllib import unquote

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

    def create(self, req, tenant_id, instance_id):
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
        if body.get('users') is None:
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
        try:
            model_users = populate_users(users)
            models.User.create(context, instance_id, model_users)
        except (ValueError, AttributeError) as e:
            raise exception.BadRequest(msg=str(e))
        return wsgi.Result(None, 202)

    def delete(self, req, tenant_id, instance_id, id):
        LOG.info(_("Deleting user for instance '%s'") % instance_id)
        LOG.info(_("req : '%s'\n\n") % req)
        context = req.environ[wsgi.CONTEXT_KEY]
        username, host = unquote_user_host(id)
        user = None
        try:
            user = guest_models.MySQLUser()
            user.name = username
            user.host = host
            found_user = models.User.load(context, instance_id, username,
                                          host)
            if not found_user:
                user = None
        except (ValueError, AttributeError) as e:
            raise exception.BadRequest(msg=str(e))
        if not user:
            raise exception.UserNotFound(uuid=id)
        models.User.delete(context, instance_id, user.serialize())
        return wsgi.Result(None, 202)

    def show(self, req, tenant_id, instance_id, id):
        """Return a single user."""
        LOG.info(_("Showing a user for instance '%s'") % instance_id)
        LOG.info(_("req : '%s'\n\n") % req)
        context = req.environ[wsgi.CONTEXT_KEY]
        username, host = unquote_user_host(id)
        user = None
        try:
            user = models.User.load(context, instance_id, username, host)
        except (ValueError, AttributeError) as e:
            raise exception.BadRequest(msg=str(e))
        if not user:
            raise exception.UserNotFound(uuid=id)
        view = views.UserView(user)
        return wsgi.Result(view.data(), 200)

    def update(self, req, body, tenant_id, instance_id):
        """Change the password of one or more users."""
        LOG.info(_("Updating user passwords for instance '%s'") % instance_id)
        LOG.info(_("req : '%s'\n\n") % req)
        context = req.environ[wsgi.CONTEXT_KEY]
        self.validate(body)
        users = body['users']
        model_users = []
        for user in users:
            try:
                mu = guest_models.MySQLUser()
                mu.name = user['name']
                mu.host = user.get('host')
                mu.password = user['password']
                found_user = models.User.load(context, instance_id,
                                              mu.name, mu.host)
                if not found_user:
                    user_and_host = mu.name
                    if mu.host:
                        user_and_host += '@' + mu.host
                    raise exception.UserNotFound(uuid=user_and_host)
                model_users.append(mu)
            except (ValueError, AttributeError) as e:
                raise exception.BadRequest(msg=str(e))
        models.User.change_password(context, instance_id, model_users)
        return wsgi.Result(None, 202)


class UserAccessController(wsgi.Controller):
    """Controller for adding and removing database access for a user."""

    @classmethod
    def validate(cls, body):
        """Validate that the request has all the required parameters"""
        if not body:
            raise exception.BadRequest("The request contains an empty body")
        if not body.get('databases', []):
            raise exception.MissingKey(key='databases')
        if type(body['databases']) is not list:
            raise exception.BadRequest("Databases must be provided as a list.")
        for database in body.get('databases'):
            if not database.get('name', ''):
                raise exception.MissingKey(key='name')

    def _get_user(self, context, instance_id, user_id):
        username, hostname = unquote_user_host(user_id)
        try:
            user = models.User.load(context, instance_id, username, hostname)
        except (ValueError, AttributeError) as e:
            raise exception.BadRequest(msg=str(e))
        if not user:
            raise exception.UserNotFound(uuid=user_id)
        return user

    def index(self, req, tenant_id, instance_id, user_id):
        """Show permissions for the given user."""
        LOG.info(_("Showing user access for instance '%s'") % instance_id)
        LOG.info(_("req : '%s'\n\n") % req)
        context = req.environ[wsgi.CONTEXT_KEY]
        # Make sure this user exists.
        user = self._get_user(context, instance_id, user_id)
        username, hostname = unquote_user_host(user_id)
        access = models.User.access(context, instance_id, username, hostname)
        view = views.UserAccessView(access.databases)
        return wsgi.Result(view.data(), 200)

    def update(self, req, body, tenant_id, instance_id, user_id):
        """Grant access for a user to one or more databases."""
        LOG.info(_("Granting user access for instance '%s'") % instance_id)
        LOG.info(_("req : '%s'\n\n") % req)
        context = req.environ[wsgi.CONTEXT_KEY]
        self.validate(body)
        user = self._get_user(context, instance_id, user_id)
        username, hostname = unquote_user_host(user_id)
        databases = [db['name'] for db in body['databases']]
        models.User.grant(context, instance_id, username, hostname, databases)
        return wsgi.Result(None, 202)

    def delete(self, req, tenant_id, instance_id, user_id, id):
        """Revoke access for a user."""
        LOG.info(_("Revoking user access for instance '%s'") % instance_id)
        LOG.info(_("req : '%s'\n\n") % req)
        context = req.environ[wsgi.CONTEXT_KEY]
        user = self._get_user(context, instance_id, user_id)
        username, hostname = unquote_user_host(user_id)
        access = models.User.access(context, instance_id, username, hostname)
        databases = [db.name for db in access.databases]
        if not id in databases:
            raise exception.DatabaseNotFound(uuid=id)
        models.User.revoke(context, instance_id, username, hostname, id)
        return wsgi.Result(None, 202)


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
        model_schemas = populate_validated_databases(schemas)
        models.Schema.create(context, instance_id, model_schemas)
        return wsgi.Result(None, 202)

    def delete(self, req, tenant_id, instance_id, id):
        LOG.info(_("Deleting schema for instance '%s'") % instance_id)
        LOG.info(_("req : '%s'\n\n") % req)
        context = req.environ[wsgi.CONTEXT_KEY]
        try:
            schema = guest_models.ValidatedMySQLDatabase()
            schema.name = id
            models.Schema.delete(context, instance_id, schema.serialize())
        except (ValueError, AttributeError) as e:
            raise exception.BadRequest(msg=str(e))
        return wsgi.Result(None, 202)

    def show(self, req, tenant_id, instance_id, id):
        raise webob.exc.HTTPNotImplemented()
