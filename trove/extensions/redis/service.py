# Copyright 2017 Eayun, Inc.
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
#

from oslo_log import log as logging
from trove.common import cfg
from trove.common import exception
from trove.common.i18n import _
from trove.common import wsgi
from trove.extensions.common.service import DefaultRootController
from trove.extensions.redis.models import RedisRoot
from trove.extensions.redis.views import RedisRootCreatedView
from trove.instance.models import DBInstance

LOG = logging.getLogger(__name__)
CONF = cfg.CONF
MANAGER = CONF.datastore_manager if CONF.datastore_manager else 'redis'


class RedisRootController(DefaultRootController):
    def root_create(self, req, body, tenant_id, instance_id, is_cluster):
        """Enable authentication for a redis instance and its replicas if any
        """
        self._validate_can_perform_action(tenant_id, instance_id, is_cluster,
                                          "enable_root")
        password = DefaultRootController._get_password_from_body(body)
        slave_instances = self._get_slaves(tenant_id, instance_id)
        return self._instance_root_create(req, instance_id, password,
                                          slave_instances)

    def root_delete(self, req, tenant_id, instance_id, is_cluster):
        """Disable authentication for a redis instance and its replicas if any
        """
        self._validate_can_perform_action(tenant_id, instance_id, is_cluster,
                                          "disable_root")
        slave_instances = self._get_slaves(tenant_id, instance_id)
        return self._instance_root_delete(req, instance_id, slave_instances)

    def _instance_root_create(self, req, instance_id, password,
                              slave_instances=None):
        LOG.info("Enabling authentication for instance '%s'.",
                 instance_id)
        LOG.info("req : '%s'\n\n", req)
        context = req.environ[wsgi.CONTEXT_KEY]

        original_auth_password = self._get_original_auth_password(
            context, instance_id)

        # Do root-enable and roll back once if operation fails.
        try:
            root = RedisRoot.create(context, instance_id, password)
            if not password:
                password = root.password
        except exception.TroveError:
            self._rollback_once(req, instance_id, original_auth_password)
            raise exception.TroveError(
                _("Failed to do root-enable for instance "
                  "'%(instance_id)s'.") % {'instance_id': instance_id}
            )

        failed_slaves = []
        for slave_id in slave_instances:
            try:
                LOG.info("Enabling authentication for slave instance "
                         "'%s'.", slave_id)
                RedisRoot.create(context, slave_id, password)
            except exception.TroveError:
                failed_slaves.append(slave_id)

        return wsgi.Result(
            RedisRootCreatedView(root, failed_slaves).data(), 200)

    def _instance_root_delete(self, req, instance_id, slave_instances=None):
        LOG.info("Disabling authentication for instance '%s'.",
                 instance_id)
        LOG.info("req : '%s'\n\n", req)
        context = req.environ[wsgi.CONTEXT_KEY]

        is_root_enabled = RedisRoot.load(context, instance_id)
        if not is_root_enabled:
            raise exception.RootHistoryNotFound()

        original_auth_password = self._get_original_auth_password(
            context, instance_id)

        # Do root-disable and roll back once if operation fails.
        try:
            RedisRoot.delete(context, instance_id)
        except exception.TroveError:
            self._rollback_once(req, instance_id, original_auth_password)
            raise exception.TroveError(
                _("Failed to do root-disable for instance "
                  "'%(instance_id)s'.") % {'instance_id': instance_id}
            )

        failed_slaves = []
        for slave_id in slave_instances:
            try:
                LOG.info("Disabling authentication for slave instance "
                         "'%s'.", slave_id)
                RedisRoot.delete(context, slave_id)
            except exception.TroveError:
                failed_slaves.append(slave_id)

        if len(failed_slaves) > 0:
            result = {
                'failed_slaves': failed_slaves
            }
            return wsgi.Result(result, 200)

        return wsgi.Result(None, 204)

    @staticmethod
    def _rollback_once(req, instance_id, original_auth_password):
        LOG.info("Rolling back enable/disable authentication "
                 "for instance '%s'.", instance_id)
        context = req.environ[wsgi.CONTEXT_KEY]
        try:
            if not original_auth_password:
                # Instance never did root-enable before.
                RedisRoot.delete(context, instance_id)
            else:
                # Instance has done root-enable successfully before.
                # So roll back with original password.
                RedisRoot.create(context, instance_id,
                                 original_auth_password)
        except exception.TroveError:
            LOG.exception("Rolling back failed for instance '%s'",
                          instance_id)

    @staticmethod
    def _is_slave(tenant_id, instance_id):
        args = {'id': instance_id, 'tenant_id': tenant_id}
        instance_info = DBInstance.find_by(**args)
        return instance_info.slave_of_id

    @staticmethod
    def _get_slaves(tenant_id, instance_or_cluster_id, deleted=False):
        LOG.info("Getting non-deleted slaves of instance '%s', "
                 "if any.", instance_or_cluster_id)
        args = {'slave_of_id': instance_or_cluster_id, 'tenant_id': tenant_id,
                'deleted': deleted}
        db_infos = DBInstance.find_all(**args)
        slaves = []
        for db_info in db_infos:
            slaves.append(db_info.id)
        return slaves

    @staticmethod
    def _get_original_auth_password(context, instance_id):
        # Check if instance did root-enable before and get original password.
        password = None
        if RedisRoot.load(context, instance_id):
            try:
                password = RedisRoot.get_auth_password(context, instance_id)
            except exception.TroveError:
                raise exception.TroveError(
                    _("Failed to get original auth password of instance "
                      "'%(instance_id)s'.") % {'instance_id': instance_id}
                )
        return password

    def _validate_can_perform_action(self, tenant_id, instance_id, is_cluster,
                                     operation):
        if is_cluster:
            raise exception.ClusterOperationNotSupported(
                operation=operation)

        is_slave = self._is_slave(tenant_id, instance_id)
        if is_slave:
            raise exception.SlaveOperationNotSupported(
                operation=operation)
