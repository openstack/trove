# Copyright [2015] Hewlett-Packard Development Company, L.P.
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


import abc

from oslo_config.cfg import NoSuchOptError
from oslo_log import log as logging
from oslo_utils import importutils

from trove.cluster import models as cluster_models
from trove.cluster.models import DBCluster
from trove.common import cfg
from trove.common import exception
from trove.common.i18n import _
from trove.common import policy
from trove.common import wsgi
from trove.datastore import models as datastore_models
from trove.extensions.common import models
from trove.extensions.common import views
from trove.instance import models as instance_models
from trove.instance.models import DBInstance

from oslo_utils import strutils
import webob.exc

import trove.common.apischema as apischema
from trove.common.db import models as guest_models
from trove.common import notification
from trove.common.notification import StartNotification
from trove.common import pagination
from trove.common.utils import correct_id_with_req
from trove.extensions.common.common import populate_users
from trove.extensions.common.common import populate_validated_databases
from trove.extensions.common.common import unquote_user_host


LOG = logging.getLogger(__name__)
import_class = importutils.import_class
CONF = cfg.CONF


class ExtensionController(wsgi.Controller):

    @classmethod
    def authorize_target_action(cls, context, target_rule_name,
                                target_id, is_cluster=False):
        target = None
        if is_cluster:
            target = cluster_models.Cluster.load(context, target_id)
        else:
            target = instance_models.Instance.load(context, target_id)

        if not target:
            if is_cluster:
                raise exception.ClusterNotFound(cluster=target_id)
            raise exception.InstanceNotFound(instance=target_id)

        target_type = 'cluster' if is_cluster else 'instance'
        policy.authorize_on_target(
            context, '%s:extension:%s' % (target_type, target_rule_name),
            {'tenant': target.tenant_id})


class BaseDatastoreRootController(ExtensionController, metaclass=abc.ABCMeta):
    """Base class that defines the contract for root controllers."""

    @abc.abstractmethod
    def root_index(self, req, tenant_id, instance_id, is_cluster):
        pass

    @abc.abstractmethod
    def root_create(self, req, body, tenant_id, instance_id, is_cluster):
        pass

    @abc.abstractmethod
    def root_delete(self, req, tenant_id, instance_id, is_cluster):
        pass

    @staticmethod
    def _get_password_from_body(body=None):
        if body:
            return body['password'] if 'password' in body else None
        return None


class DefaultRootController(BaseDatastoreRootController):

    def root_index(self, req, tenant_id, instance_id, is_cluster):
        """Returns True if root is enabled; False otherwise."""
        if is_cluster:
            raise exception.ClusterOperationNotSupported(
                operation='show_root')
        LOG.info("Getting root enabled for instance '%s'.", instance_id)
        LOG.info("req : '%s'\n\n", req)
        context = req.environ[wsgi.CONTEXT_KEY]
        is_root_enabled = models.Root.load(context, instance_id)
        return wsgi.Result(views.RootEnabledView(is_root_enabled).data(), 200)

    def root_create(self, req, body, tenant_id, instance_id, is_cluster):
        if is_cluster:
            raise exception.ClusterOperationNotSupported(
                operation='enable_root')
        LOG.info("Enabling root for instance '%s'.", instance_id)
        LOG.info("req : '%s'\n\n", req)
        context = req.environ[wsgi.CONTEXT_KEY]
        password = DefaultRootController._get_password_from_body(body)
        root = models.Root.create(context, instance_id, password)
        return wsgi.Result(views.RootCreatedView(root).data(), 200)

    def root_delete(self, req, tenant_id, instance_id, is_cluster):
        if is_cluster:
            raise exception.ClusterOperationNotSupported(
                operation='disable_root')
        LOG.info("Disabling root for instance '%s'.", instance_id)
        LOG.info("req : '%s'\n\n", req)
        context = req.environ[wsgi.CONTEXT_KEY]
        is_root_enabled = models.Root.load(context, instance_id)
        if not is_root_enabled:
            raise exception.RootHistoryNotFound()
        models.Root.delete(context, instance_id)
        return wsgi.Result(None, 204)


class ClusterRootController(DefaultRootController):

    def root_index(self, req, tenant_id, instance_id, is_cluster):
        """Returns True if root is enabled; False otherwise."""
        if is_cluster:
            return self.cluster_root_index(req, tenant_id, instance_id)
        else:
            return self.instance_root_index(req, tenant_id, instance_id)

    def instance_root_index(self, req, tenant_id, instance_id):
        LOG.info("Getting root enabled for instance '%s'.", instance_id)
        LOG.info("req : '%s'\n\n", req)
        context = req.environ[wsgi.CONTEXT_KEY]
        try:
            is_root_enabled = models.ClusterRoot.load(context, instance_id)
        except exception.UnprocessableEntity:
            raise exception.UnprocessableEntity(
                _("Cluster %s is not ready.") % instance_id)
        return wsgi.Result(views.RootEnabledView(is_root_enabled).data(), 200)

    def cluster_root_index(self, req, tenant_id, cluster_id):
        LOG.info("Getting root enabled for cluster '%s'.", cluster_id)
        single_instance_id, cluster_instances = self._get_cluster_instance_id(
            tenant_id, cluster_id)
        return self.instance_root_index(req, tenant_id, single_instance_id)

    def _block_cluster_instance_actions(self):
        return False

    def check_cluster_instance_actions(self, instance_id):
        # Check if instance is in a cluster and if actions are allowed
        instance = DBInstance.find_by(id=instance_id)
        if instance.cluster_id and self._block_cluster_instance_actions():
            raise exception.ClusterInstanceOperationNotSupported()

    def root_create(self, req, body, tenant_id, instance_id, is_cluster):
        if is_cluster:
            return self.cluster_root_create(req, body, tenant_id, instance_id)
        else:
            self.check_cluster_instance_actions(instance_id)
            return self.instance_root_create(req, body, instance_id)

    def instance_root_create(self, req, body, instance_id,
                             cluster_instances=None):
        LOG.info("Enabling root for instance '%s'.", instance_id)
        LOG.info("req : '%s'\n\n", req)
        context = req.environ[wsgi.CONTEXT_KEY]
        password = ClusterRootController._get_password_from_body(body)
        root = models.ClusterRoot.create(context, instance_id,
                                         password, cluster_instances)
        return wsgi.Result(views.RootCreatedView(root).data(), 200)

    def cluster_root_create(self, req, body, tenant_id, cluster_id):
        LOG.info("Enabling root for cluster '%s'.", cluster_id)
        single_instance_id, cluster_instances = self._get_cluster_instance_id(
            tenant_id, cluster_id)
        return self.instance_root_create(req, body, single_instance_id,
                                         cluster_instances)

    def _find_cluster_node_ids(self, tenant_id, cluster_id):
        args = {'tenant_id': tenant_id,
                'cluster_id': cluster_id,
                'deleted': False}
        cluster_instances = DBInstance.find_all(**args).all()
        return [db_instance.id for db_instance in cluster_instances]

    def _get_cluster_instance_id(self, tenant_id, cluster_id):
        instance_ids = self._find_cluster_node_ids(tenant_id, cluster_id)
        single_instance_id = instance_ids[0]
        return single_instance_id, instance_ids


class RootController(ExtensionController):
    """Controller for instance functionality."""

    def index(self, req, tenant_id, instance_id):
        """Returns True if root is enabled; False otherwise."""
        datastore_manager, is_cluster = self._get_datastore(tenant_id,
                                                            instance_id)
        context = req.environ[wsgi.CONTEXT_KEY]
        self.authorize_target_action(context, 'root:index', instance_id,
                                     is_cluster=is_cluster)
        root_controller = self.load_root_controller(datastore_manager)
        return root_controller.root_index(req, tenant_id, instance_id,
                                          is_cluster)

    def create(self, req, tenant_id, instance_id, body=None):
        """Enable the root user for the db instance."""
        datastore_manager, is_cluster = self._get_datastore(tenant_id,
                                                            instance_id)
        context = req.environ[wsgi.CONTEXT_KEY]
        self.authorize_target_action(context, 'root:create', instance_id,
                                     is_cluster=is_cluster)
        root_controller = self.load_root_controller(datastore_manager)
        if root_controller is not None:
            return root_controller.root_create(req, body, tenant_id,
                                               instance_id, is_cluster)
        else:
            opt = 'root_controller'
            raise NoSuchOptError(opt, group='datastore_manager')

    def delete(self, req, tenant_id, instance_id):
        datastore_manager, is_cluster = self._get_datastore(tenant_id,
                                                            instance_id)
        context = req.environ[wsgi.CONTEXT_KEY]
        self.authorize_target_action(context, 'root:delete', instance_id,
                                     is_cluster=is_cluster)
        root_controller = self.load_root_controller(datastore_manager)
        if root_controller is not None:
            return root_controller.root_delete(req, tenant_id,
                                               instance_id, is_cluster)
        else:
            opt = 'root_controller'
            raise NoSuchOptError(opt, group='datastore_manager')

    def _get_datastore(self, tenant_id, instance_or_cluster_id):
        """
        Returns datastore manager and a boolean
        showing if instance_or_cluster_id is a cluster id
        """
        args = {'id': instance_or_cluster_id, 'tenant_id': tenant_id}
        is_cluster = False
        try:
            db_info = DBInstance.find_by(**args)
        except exception.ModelNotFoundError:
            is_cluster = True
            db_info = DBCluster.find_by(**args)

        ds_version = (datastore_models.DatastoreVersion.
                      load_by_uuid(db_info.datastore_version_id))
        ds_manager = ds_version.manager
        return (ds_manager, is_cluster)

    def load_root_controller(self, manager):
        try:
            clazz = CONF.get(manager).get('root_controller')
            LOG.debug("Loading Root Controller class %s.", clazz)

            if not clazz:
                raise exception.DatastoreOperationNotSupported(
                    datastore=manager, operation='root')

            root_controller = import_class(clazz)
            return root_controller()
        except NoSuchOptError:
            LOG.warning(
                f"root_controller not configured for datastore {manager}")
            raise exception.DatastoreOperationNotSupported(
                datastore=manager, operation='root')


class UserController(ExtensionController):
    """Controller for instance functionality."""
    schemas = apischema.user

    @classmethod
    def get_schema(cls, action, body):
        action_schema = super(UserController, cls).get_schema(action, body)
        if 'update_all' == action:
            update_type = list(body.keys())[0]
            action_schema = action_schema.get(update_type, {})
        return action_schema

    def index(self, req, tenant_id, instance_id):
        """Return all users."""
        LOG.info("Listing users for instance '%(id)s'\n"
                 "req : '%(req)s'\n\n",
                 {"id": instance_id, "req": req})
        context = req.environ[wsgi.CONTEXT_KEY]
        self.authorize_target_action(context, 'user:index', instance_id)
        users, next_marker = models.Users.load(context, instance_id)
        view = views.UsersView(users)
        paged = pagination.SimplePaginatedDataView(req.url, 'users', view,
                                                   next_marker)
        return wsgi.Result(paged.data(), 200)

    def create(self, req, body, tenant_id, instance_id):
        """Creates a set of users."""
        LOG.info("Creating users for instance '%(id)s'\n"
                 "req : '%(req)s'\n\n"
                 "body: '%(body)s'\n'n",
                 {"id": instance_id,
                  "req": strutils.mask_password(req),
                  "body": strutils.mask_password(body)})
        context = req.environ[wsgi.CONTEXT_KEY]
        self.authorize_target_action(context, 'user:create', instance_id)
        context.notification = notification.DBaaSUserCreate(context,
                                                            request=req)
        users = body['users']
        with StartNotification(context, instance_id=instance_id,
                               username=",".join([user['name']
                                                  for user in users])):
            try:
                model_users = populate_users(users)
                models.User.create(context, instance_id, model_users)
            except (ValueError, AttributeError) as e:
                raise exception.BadRequest(_("User create error: %(e)s")
                                           % {'e': e})
        return wsgi.Result(None, 202)

    def delete(self, req, tenant_id, instance_id, id):
        LOG.info("Delete instance '%(id)s'\n"
                 "req : '%(req)s'\n\n",
                 {"id": instance_id, "req": req})
        context = req.environ[wsgi.CONTEXT_KEY]
        self.authorize_target_action(context, 'user:delete', instance_id)
        id = correct_id_with_req(id, req)
        username, host = unquote_user_host(id)
        user = None
        context.notification = notification.DBaaSUserDelete(context,
                                                            request=req)
        with StartNotification(context, instance_id=instance_id,
                               username=username):
            try:
                user = guest_models.DatastoreUser(name=username,
                                                  host=host)
                found_user = models.User.load(context, instance_id, username,
                                              host)
                if not found_user:
                    user = None
            except (ValueError, AttributeError) as e:
                raise exception.BadRequest(_("User delete error: %(e)s")
                                           % {'e': e})
            if not user:
                raise exception.UserNotFound(uuid=id)
            models.User.delete(context, instance_id, user.serialize())
        return wsgi.Result(None, 202)

    def show(self, req, tenant_id, instance_id, id):
        """Return a single user."""
        LOG.info("Showing a user for instance '%(id)s'\n"
                 "req : '%(req)s'\n\n",
                 {"id": instance_id, "req": req})
        context = req.environ[wsgi.CONTEXT_KEY]
        self.authorize_target_action(context, 'user:show', instance_id)
        id = correct_id_with_req(id, req)
        username, host = unquote_user_host(id)
        user = None
        try:
            user = models.User.load(context, instance_id, username, host)
        except (ValueError, AttributeError) as e:
            raise exception.BadRequest(_("User show error: %(e)s")
                                       % {'e': e})
        if not user:
            raise exception.UserNotFound(uuid=id)
        view = views.UserView(user)
        return wsgi.Result(view.data(), 200)

    def update(self, req, body, tenant_id, instance_id, id):
        """Change attributes for one user."""
        LOG.info("Updating user attributes for instance '%(id)s'\n"
                 "req : '%(req)s'\n\n",
                 {"id": instance_id, "req": strutils.mask_password(req)})
        context = req.environ[wsgi.CONTEXT_KEY]
        self.authorize_target_action(context, 'user:update', instance_id)
        id = correct_id_with_req(id, req)
        username, hostname = unquote_user_host(id)
        user = None
        user_attrs = body['user']
        context.notification = notification.DBaaSUserUpdateAttributes(
            context, request=req)
        with StartNotification(context, instance_id=instance_id,
                               username=username):
            try:
                user = models.User.load(context, instance_id, username,
                                        hostname)
            except (ValueError, AttributeError) as e:
                raise exception.BadRequest(_("Error loading user: %(e)s")
                                           % {'e': e})
            if not user:
                raise exception.UserNotFound(uuid=id)
            try:
                models.User.update_attributes(context, instance_id, username,
                                              hostname, user_attrs)
            except (ValueError, AttributeError) as e:
                raise exception.BadRequest(_("User update error: %(e)s")
                                           % {'e': e})
        return wsgi.Result(None, 202)

    def update_all(self, req, body, tenant_id, instance_id):
        """Change the password of one or more users."""
        LOG.info("Updating user password for instance '%(id)s'\n"
                 "req : '%(req)s'\n\n",
                 {"id": instance_id, "req": strutils.mask_password(req)})
        context = req.environ[wsgi.CONTEXT_KEY]
        self.authorize_target_action(context, 'user:update_all', instance_id)
        context.notification = notification.DBaaSUserChangePassword(
            context, request=req)
        users = body['users']
        model_users = []
        with StartNotification(context, instance_id=instance_id,
                               username=",".join([user['name']
                                                  for user in users])):
            for user in users:
                try:
                    mu = guest_models.DatastoreUser(name=user['name'],
                                                    host=user.get('host'),
                                                    password=user['password'])
                    found_user = models.User.load(context, instance_id,
                                                  mu.name, mu.host)
                    if not found_user:
                        user_and_host = mu.name
                        if mu.host:
                            user_and_host += '@' + mu.host
                        raise exception.UserNotFound(uuid=user_and_host)
                    model_users.append(mu)
                except (ValueError, AttributeError) as e:
                    raise exception.BadRequest(_("Error loading user: %(e)s")
                                               % {'e': e})
            try:
                models.User.change_password(context, instance_id, model_users)
            except (ValueError, AttributeError) as e:
                raise exception.BadRequest(_("User password update error: "
                                             "%(e)s")
                                           % {'e': e})
        return wsgi.Result(None, 202)


class UserAccessController(ExtensionController):
    """Controller for adding and removing database access for a user."""
    schemas = apischema.user

    @classmethod
    def get_schema(cls, action, body):
        schema = {}
        if 'update_all' == action:
            schema = cls.schemas.get(action).get('databases')
        return schema

    def _get_user(self, context, instance_id, user_id):
        username, hostname = unquote_user_host(user_id)
        try:
            user = models.User.load(context, instance_id, username, hostname)
        except (ValueError, AttributeError) as e:
            raise exception.BadRequest(_("Error loading user: %(e)s")
                                       % {'e': e})
        if not user:
            raise exception.UserNotFound(uuid=user_id)
        return user

    def index(self, req, tenant_id, instance_id, user_id):
        """Show permissions for the given user."""
        LOG.info("Showing user access for instance '%(id)s'\n"
                 "req : '%(req)s'\n\n",
                 {"id": instance_id, "req": req})

        context = req.environ[wsgi.CONTEXT_KEY]
        self.authorize_target_action(
            context, 'user_access:index', instance_id)
        # Make sure this user exists.
        user_id = correct_id_with_req(user_id, req)
        user = self._get_user(context, instance_id, user_id)
        if not user:
            LOG.error("No such user: %(user)s ", {'user': user})
            raise exception.UserNotFound(uuid=user)
        username, hostname = unquote_user_host(user_id)
        access = models.User.access(context, instance_id, username, hostname)
        view = views.UserAccessView(access.databases)
        return wsgi.Result(view.data(), 200)

    def update(self, req, body, tenant_id, instance_id, user_id):
        """Grant access for a user to one or more databases."""
        LOG.info("Granting user access for instance '%(id)s'\n"
                 "req : '%(req)s'\n\n",
                 {"id": instance_id, "req": req})
        context = req.environ[wsgi.CONTEXT_KEY]
        self.authorize_target_action(
            context, 'user_access:update', instance_id)
        context.notification = notification.DBaaSUserGrant(
            context, request=req)
        user_id = correct_id_with_req(user_id, req)
        user = self._get_user(context, instance_id, user_id)
        if not user:
            LOG.error("No such user: %(user)s ", {'user': user})
            raise exception.UserNotFound(uuid=user)
        username, hostname = unquote_user_host(user_id)
        databases = [db['name'] for db in body['databases']]
        with StartNotification(context, instance_id=instance_id,
                               username=username, database=databases):
            models.User.grant(context, instance_id, username, hostname,
                              databases)
        return wsgi.Result(None, 202)

    def delete(self, req, tenant_id, instance_id, user_id, id):
        """Revoke access for a user."""
        LOG.info("Revoking user access for instance '%(id)s'\n"
                 "req : '%(req)s'\n\n",
                 {"id": instance_id, "req": req})
        context = req.environ[wsgi.CONTEXT_KEY]
        self.authorize_target_action(
            context, 'user_access:delete', instance_id)
        context.notification = notification.DBaaSUserRevoke(
            context, request=req)
        user_id = correct_id_with_req(user_id, req)
        user = self._get_user(context, instance_id, user_id)
        if not user:
            LOG.error("No such user: %(user)s ", {'user': user})
            raise exception.UserNotFound(uuid=user)
        username, hostname = unquote_user_host(user_id)
        access = models.User.access(context, instance_id, username, hostname)
        databases = [db.name for db in access.databases]
        with StartNotification(context, instance_id=instance_id,
                               username=username, database=databases):
            if id not in databases:
                raise exception.DatabaseNotFound(uuid=id)
            models.User.revoke(context, instance_id, username, hostname, id)
        return wsgi.Result(None, 202)


class SchemaController(ExtensionController):
    """Controller for instance functionality."""
    schemas = apischema.dbschema

    def index(self, req, tenant_id, instance_id):
        """Return all schemas."""
        LOG.info("Listing schemas for instance '%(id)s'\n"
                 "req : '%(req)s'\n\n",
                 {"id": instance_id, "req": req})

        context = req.environ[wsgi.CONTEXT_KEY]
        self.authorize_target_action(
            context, 'database:index', instance_id)
        schemas, next_marker = models.Schemas.load(context, instance_id)
        view = views.SchemasView(schemas)
        paged = pagination.SimplePaginatedDataView(req.url, 'databases', view,
                                                   next_marker)
        return wsgi.Result(paged.data(), 200)

    def create(self, req, body, tenant_id, instance_id):
        """Creates a set of schemas."""
        LOG.info("Creating schema for instance '%(id)s'\n"
                 "req : '%(req)s'\n\n"
                 "body: '%(body)s'\n'n",
                 {"id": instance_id,
                  "req": req,
                  "body": body})

        context = req.environ[wsgi.CONTEXT_KEY]
        self.authorize_target_action(
            context, 'database:create', instance_id)
        schemas = body['databases']
        context.notification = notification.DBaaSDatabaseCreate(context,
                                                                request=req)
        with StartNotification(context, instance_id=instance_id,
                               dbname=".".join([db['name']
                                                for db in schemas])):
            try:
                model_schemas = populate_validated_databases(schemas)
                models.Schema.create(context, instance_id, model_schemas)
            except (ValueError, AttributeError) as e:
                raise exception.BadRequest(_("Database create error: %(e)s")
                                           % {'e': e})
        return wsgi.Result(None, 202)

    def delete(self, req, tenant_id, instance_id, id):
        LOG.info("Deleting schema for instance '%(id)s'\n"
                 "req : '%(req)s'\n\n",
                 {"id": instance_id, "req": req})
        context = req.environ[wsgi.CONTEXT_KEY]
        self.authorize_target_action(
            context, 'database:delete', instance_id)
        context.notification = notification.DBaaSDatabaseDelete(
            context, request=req)
        with StartNotification(context, instance_id=instance_id, dbname=id):
            try:
                schema = guest_models.DatastoreSchema(name=id)
                schema.check_delete()
                if not models.Schemas.find(context, instance_id, id):
                    raise exception.DatabaseNotFound(uuid=id)
                models.Schema.delete(context, instance_id, schema.serialize())
            except (ValueError, AttributeError) as e:
                raise exception.BadRequest(_("Database delete error: %(e)s")
                                           % {'e': e})
        return wsgi.Result(None, 202)

    def show(self, req, tenant_id, instance_id, id):
        context = req.environ[wsgi.CONTEXT_KEY]
        self.authorize_target_action(
            context, 'database:show', instance_id)
        raise webob.exc.HTTPNotImplemented()
