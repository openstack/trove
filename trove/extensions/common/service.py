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
import six

from trove.cluster import models as cluster_models
from trove.cluster.models import DBCluster
from trove.common import cfg
from trove.common import exception
from trove.common.i18n import _
from trove.common.i18n import _LI
from trove.common import policy
from trove.common import wsgi
from trove.datastore import models as datastore_models
from trove.extensions.common import models
from trove.extensions.common import views
from trove.instance import models as instance_models
from trove.instance.models import DBInstance


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


@six.add_metaclass(abc.ABCMeta)
class BaseDatastoreRootController(ExtensionController):
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
        LOG.info(_LI("Getting root enabled for instance '%s'."), instance_id)
        LOG.info(_LI("req : '%s'\n\n"), req)
        context = req.environ[wsgi.CONTEXT_KEY]
        is_root_enabled = models.Root.load(context, instance_id)
        return wsgi.Result(views.RootEnabledView(is_root_enabled).data(), 200)

    def root_create(self, req, body, tenant_id, instance_id, is_cluster):
        if is_cluster:
            raise exception.ClusterOperationNotSupported(
                operation='enable_root')
        LOG.info(_LI("Enabling root for instance '%s'."), instance_id)
        LOG.info(_LI("req : '%s'\n\n"), req)
        context = req.environ[wsgi.CONTEXT_KEY]
        user_name = context.user
        password = DefaultRootController._get_password_from_body(body)
        root = models.Root.create(context, instance_id,
                                  user_name, password)
        return wsgi.Result(views.RootCreatedView(root).data(), 200)

    def root_delete(self, req, tenant_id, instance_id, is_cluster):
        if is_cluster:
            raise exception.ClusterOperationNotSupported(
                operation='disable_root')
        LOG.info(_LI("Disabling root for instance '%s'."), instance_id)
        LOG.info(_LI("req : '%s'\n\n"), req)
        context = req.environ[wsgi.CONTEXT_KEY]
        try:
            found_user = self._find_root_user(context, instance_id)
        except (ValueError, AttributeError) as e:
            raise exception.BadRequest(msg=str(e))
        if not found_user:
            raise exception.UserNotFound(uuid="root")
        models.Root.delete(context, instance_id)
        return wsgi.Result(None, 200)


class ClusterRootController(DefaultRootController):

    def root_index(self, req, tenant_id, instance_id, is_cluster):
        """Returns True if root is enabled; False otherwise."""
        if is_cluster:
            return self.cluster_root_index(req, tenant_id, instance_id)
        else:
            return self.instance_root_index(req, tenant_id, instance_id)

    def instance_root_index(self, req, tenant_id, instance_id):
        LOG.info(_LI("Getting root enabled for instance '%s'."), instance_id)
        LOG.info(_LI("req : '%s'\n\n"), req)
        context = req.environ[wsgi.CONTEXT_KEY]
        try:
            is_root_enabled = models.ClusterRoot.load(context, instance_id)
        except exception.UnprocessableEntity:
            raise exception.UnprocessableEntity(
                _("Cluster %s is not ready.") % instance_id)
        return wsgi.Result(views.RootEnabledView(is_root_enabled).data(), 200)

    def cluster_root_index(self, req, tenant_id, cluster_id):
        LOG.info(_LI("Getting root enabled for cluster '%s'."), cluster_id)
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
        LOG.info(_LI("Enabling root for instance '%s'."), instance_id)
        LOG.info(_LI("req : '%s'\n\n"), req)
        context = req.environ[wsgi.CONTEXT_KEY]
        user_name = context.user
        password = ClusterRootController._get_password_from_body(body)
        root = models.ClusterRoot.create(context, instance_id, user_name,
                                         password, cluster_instances)
        return wsgi.Result(views.RootCreatedView(root).data(), 200)

    def cluster_root_create(self, req, body, tenant_id, cluster_id):
        LOG.info(_LI("Enabling root for cluster '%s'."), cluster_id)
        single_instance_id, cluster_instances = self._get_cluster_instance_id(
            tenant_id, cluster_id)
        return self.instance_root_create(req, body, single_instance_id,
                                         cluster_instances)

    def _find_cluster_node_ids(self, tenant_id, cluster_id):
        args = {'tenant_id': tenant_id, 'cluster_id': cluster_id}
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
            raise NoSuchOptError

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
            root_controller = import_class(clazz)
            return root_controller()
        except NoSuchOptError:
            return None
