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

from oslo_log import log as logging
from oslo_service import periodic_task
from oslo_utils import importutils

from trove.backup.models import Backup
import trove.common.cfg as cfg
from trove.common.context import TroveContext
from trove.common import exception
from trove.common.exception import ReplicationSlaveAttachError
from trove.common.exception import TroveError
from trove.common.i18n import _
from trove.common.notification import DBaaSQuotas, EndNotification
from trove.common import remote
from trove.common import server_group as srv_grp
from trove.common.strategies.cluster import strategy
from trove.datastore.models import DatastoreVersion
import trove.extensions.mgmt.instances.models as mgmtmodels
from trove.instance.tasks import InstanceTasks
from trove.taskmanager import models
from trove.taskmanager.models import FreshInstanceTasks, BuiltInstanceTasks
from trove.quota.quota import QUOTAS

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class Manager(periodic_task.PeriodicTasks):

    def __init__(self):
        super(Manager, self).__init__(CONF)
        self.admin_context = TroveContext(
            user=CONF.nova_proxy_admin_user,
            auth_token=CONF.nova_proxy_admin_pass,
            tenant=CONF.nova_proxy_admin_tenant_id)
        if CONF.exists_notification_transformer:
            self.exists_transformer = importutils.import_object(
                CONF.exists_notification_transformer,
                context=self.admin_context)

    def resize_volume(self, context, instance_id, new_size):
        with EndNotification(context):
            instance_tasks = models.BuiltInstanceTasks.load(context,
                                                            instance_id)
            instance_tasks.resize_volume(new_size)

    def resize_flavor(self, context, instance_id, old_flavor, new_flavor):
        with EndNotification(context):
            instance_tasks = models.BuiltInstanceTasks.load(context,
                                                            instance_id)
            instance_tasks.resize_flavor(old_flavor, new_flavor)

    def reboot(self, context, instance_id):
        with EndNotification(context):
            instance_tasks = models.BuiltInstanceTasks.load(context,
                                                            instance_id)
            instance_tasks.reboot()

    def restart(self, context, instance_id):
        with EndNotification(context):
            instance_tasks = models.BuiltInstanceTasks.load(context,
                                                            instance_id)
            instance_tasks.restart()

    def detach_replica(self, context, instance_id):
        with EndNotification(context):
            slave = models.BuiltInstanceTasks.load(context, instance_id)
            master_id = slave.slave_of_id
            master = models.BuiltInstanceTasks.load(context, master_id)
            slave.detach_replica(master)

    def _set_task_status(self, instances, status):
        for instance in instances:
            setattr(instance.db_info, 'task_status', status)
            instance.db_info.save()

    def promote_to_replica_source(self, context, instance_id):
        # TODO(atomic77) Promote and eject need to be able to handle the case
        # where a datastore like Postgresql needs to treat the slave to be
        # promoted differently from the old master and the slaves which will
        # be simply reassigned to a new master. See:
        # https://bugs.launchpad.net/trove/+bug/1553339

        def _promote_to_replica_source(old_master, master_candidate,
                                       replica_models):
            # First, we transition from the old master to new as quickly as
            # possible to minimize the scope of unrecoverable error
            old_master.make_read_only(True)
            master_ips = old_master.detach_public_ips()
            slave_ips = master_candidate.detach_public_ips()
            latest_txn_id = old_master.get_latest_txn_id()
            master_candidate.wait_for_txn(latest_txn_id)
            master_candidate.detach_replica(old_master, for_failover=True)
            master_candidate.enable_as_master()
            old_master.attach_replica(master_candidate)
            master_candidate.attach_public_ips(master_ips)
            master_candidate.make_read_only(False)
            old_master.attach_public_ips(slave_ips)

            # At this point, should something go wrong, there
            # should be a working master with some number of working slaves,
            # and possibly some number of "orphaned" slaves

            exception_replicas = []
            error_messages = ""
            for replica in replica_models:
                try:
                    if replica.id != master_candidate.id:
                        replica.detach_replica(old_master, for_failover=True)
                        replica.attach_replica(master_candidate)
                except exception.TroveError as ex:
                    msg = (_("Unable to migrate replica %(slave)s from "
                             "old replica source %(old_master)s to "
                             "new source %(new_master)s on promote.") %
                           {"slave": replica.id,
                            "old_master": old_master.id,
                            "new_master": master_candidate.id})
                    LOG.exception(msg)
                    exception_replicas.append(replica)
                    error_messages += "%s (%s)\n" % (msg, ex)

            try:
                old_master.demote_replication_master()
            except Exception as ex:
                msg = (_("Exception demoting old replica source %s.") %
                       old_master.id)
                LOG.exception(msg)
                exception_replicas.append(old_master)
                error_messages += "%s (%s)\n" % (msg, ex)

            self._set_task_status([old_master] + replica_models,
                                  InstanceTasks.NONE)
            if exception_replicas:
                self._set_task_status(exception_replicas,
                                      InstanceTasks.PROMOTION_ERROR)
                msg = (_("promote-to-replica-source %(id)s: The following "
                         "replicas may not have been switched: %(replicas)s") %
                       {"id": master_candidate.id,
                        "replicas": [repl.id for repl in exception_replicas]})
                raise ReplicationSlaveAttachError("%s:\n%s" %
                                                  (msg, error_messages))

        with EndNotification(context):
            master_candidate = BuiltInstanceTasks.load(context, instance_id)
            old_master = BuiltInstanceTasks.load(context,
                                                 master_candidate.slave_of_id)
            replicas = []
            for replica_dbinfo in old_master.slaves:
                if replica_dbinfo.id == instance_id:
                    replica = master_candidate
                else:
                    replica = BuiltInstanceTasks.load(context,
                                                      replica_dbinfo.id)
                replicas.append(replica)

            try:
                _promote_to_replica_source(old_master, master_candidate,
                                           replicas)
            except ReplicationSlaveAttachError:
                raise
            except Exception:
                self._set_task_status([old_master] + replicas,
                                      InstanceTasks.PROMOTION_ERROR)
                raise

    # pulled out to facilitate testing
    def _get_replica_txns(self, replica_models):
        return [[repl] + repl.get_last_txn() for repl in replica_models]

    def _most_current_replica(self, old_master, replica_models):
        last_txns = self._get_replica_txns(replica_models)
        master_ids = [txn[1] for txn in last_txns if txn[1]]
        if len(set(master_ids)) > 1:
            raise TroveError(_("Replicas of %s not all replicating"
                               " from same master") % old_master.id)
        return sorted(last_txns, key=lambda x: x[2], reverse=True)[0][0]

    def eject_replica_source(self, context, instance_id):

        def _eject_replica_source(old_master, replica_models):

            master_candidate = self._most_current_replica(old_master,
                                                          replica_models)

            master_ips = old_master.detach_public_ips()
            slave_ips = master_candidate.detach_public_ips()
            master_candidate.detach_replica(old_master, for_failover=True)
            master_candidate.enable_as_master()
            master_candidate.attach_public_ips(master_ips)
            master_candidate.make_read_only(False)
            old_master.attach_public_ips(slave_ips)

            exception_replicas = []
            error_messages = ""
            for replica in replica_models:
                try:
                    if replica.id != master_candidate.id:
                        replica.detach_replica(old_master, for_failover=True)
                        replica.attach_replica(master_candidate)
                except exception.TroveError as ex:
                    msg = (_("Unable to migrate replica %(slave)s from "
                             "old replica source %(old_master)s to "
                             "new source %(new_master)s on eject.") %
                           {"slave": replica.id,
                            "old_master": old_master.id,
                            "new_master": master_candidate.id})
                    LOG.exception(msg)
                    exception_replicas.append(replica)
                    error_messages += "%s (%s)\n" % (msg, ex)

            self._set_task_status([old_master] + replica_models,
                                  InstanceTasks.NONE)
            if exception_replicas:
                self._set_task_status(exception_replicas,
                                      InstanceTasks.EJECTION_ERROR)
                msg = (_("eject-replica-source %(id)s: The following "
                         "replicas may not have been switched: %(replicas)s") %
                       {"id": master_candidate.id,
                        "replicas": [repl.id for repl in exception_replicas]})
                raise ReplicationSlaveAttachError("%s:\n%s" %
                                                  (msg, error_messages))

        with EndNotification(context):
            master = BuiltInstanceTasks.load(context, instance_id)
            replicas = [BuiltInstanceTasks.load(context, dbinfo.id)
                        for dbinfo in master.slaves]
            try:
                _eject_replica_source(master, replicas)
            except ReplicationSlaveAttachError:
                raise
            except Exception:
                self._set_task_status([master] + replicas,
                                      InstanceTasks.EJECTION_ERROR)
                raise

    def migrate(self, context, instance_id, host):
        with EndNotification(context):
            instance_tasks = models.BuiltInstanceTasks.load(context,
                                                            instance_id)
            instance_tasks.migrate(host)

    def delete_instance(self, context, instance_id):
        with EndNotification(context):
            try:
                instance_tasks = models.BuiltInstanceTasks.load(context,
                                                                instance_id)
                instance_tasks.delete_async()
            except exception.UnprocessableEntity:
                instance_tasks = models.FreshInstanceTasks.load(context,
                                                                instance_id)
                instance_tasks.delete_async()

    def delete_backup(self, context, backup_id):
        with EndNotification(context):
            models.BackupTasks.delete_backup(context, backup_id)

    def create_backup(self, context, backup_info, instance_id):
        with EndNotification(context, backup_id=backup_info['id']):
            instance_tasks = models.BuiltInstanceTasks.load(context,
                                                            instance_id)
            instance_tasks.create_backup(backup_info)

    def _create_replication_slave(self, context, instance_id, name, flavor,
                                  image_id, databases, users,
                                  datastore_manager, packages, volume_size,
                                  availability_zone, root_password, nics,
                                  overrides, slave_of_id, backup_id,
                                  volume_type, modules):

        if type(instance_id) in [list]:
            ids = instance_id
            root_passwords = root_password
        else:
            ids = [instance_id]
            root_passwords = [root_password]
        replica_number = 0
        replica_backup_id = backup_id
        replica_backup_created = False
        replicas = []

        master_instance_tasks = BuiltInstanceTasks.load(context, slave_of_id)
        server_group = master_instance_tasks.server_group
        scheduler_hints = srv_grp.ServerGroup.convert_to_hint(server_group)
        LOG.debug("Using scheduler hints for locality: %s" % scheduler_hints)

        try:
            for replica_index in range(0, len(ids)):
                try:
                    replica_number += 1
                    LOG.debug("Creating replica %d of %d."
                              % (replica_number, len(ids)))
                    instance_tasks = FreshInstanceTasks.load(
                        context, ids[replica_index])
                    snapshot = instance_tasks.get_replication_master_snapshot(
                        context, slave_of_id, flavor, replica_backup_id,
                        replica_number=replica_number)
                    replica_backup_id = snapshot['dataset']['snapshot_id']
                    replica_backup_created = (replica_backup_id is not None)
                    instance_tasks.create_instance(
                        flavor, image_id, databases, users, datastore_manager,
                        packages, volume_size, replica_backup_id,
                        availability_zone, root_passwords[replica_index],
                        nics, overrides, None, snapshot, volume_type,
                        modules, scheduler_hints)
                    replicas.append(instance_tasks)
                except Exception:
                    # if it's the first replica, then we shouldn't continue
                    LOG.exception(_(
                        "Could not create replica %(num)d of %(count)d.")
                        % {'num': replica_number, 'count': len(ids)})
                    if replica_number == 1:
                        raise

            for replica in replicas:
                replica.wait_for_instance(CONF.restore_usage_timeout, flavor)

        finally:
            if replica_backup_created:
                Backup.delete(context, replica_backup_id)

    def _create_instance(self, context, instance_id, name, flavor,
                         image_id, databases, users, datastore_manager,
                         packages, volume_size, backup_id, availability_zone,
                         root_password, nics, overrides, slave_of_id,
                         cluster_config, volume_type, modules, locality):
        if slave_of_id:
            self._create_replication_slave(context, instance_id, name,
                                           flavor, image_id, databases, users,
                                           datastore_manager, packages,
                                           volume_size,
                                           availability_zone, root_password,
                                           nics, overrides, slave_of_id,
                                           backup_id, volume_type, modules)
        else:
            if type(instance_id) in [list]:
                raise AttributeError(_(
                    "Cannot create multiple non-replica instances."))
            instance_tasks = FreshInstanceTasks.load(context, instance_id)

            scheduler_hints = srv_grp.ServerGroup.build_scheduler_hint(
                context, locality, instance_id)
            instance_tasks.create_instance(flavor, image_id, databases, users,
                                           datastore_manager, packages,
                                           volume_size, backup_id,
                                           availability_zone, root_password,
                                           nics, overrides, cluster_config,
                                           None, volume_type, modules,
                                           scheduler_hints)
            timeout = (CONF.restore_usage_timeout if backup_id
                       else CONF.usage_timeout)
            instance_tasks.wait_for_instance(timeout, flavor)

    def create_instance(self, context, instance_id, name, flavor,
                        image_id, databases, users, datastore_manager,
                        packages, volume_size, backup_id, availability_zone,
                        root_password, nics, overrides, slave_of_id,
                        cluster_config, volume_type, modules, locality):
        with EndNotification(context,
                             instance_id=(instance_id[0]
                                          if type(instance_id) is list
                                          else instance_id)):
            self._create_instance(context, instance_id, name, flavor,
                                  image_id, databases, users,
                                  datastore_manager, packages, volume_size,
                                  backup_id, availability_zone,
                                  root_password, nics, overrides, slave_of_id,
                                  cluster_config, volume_type, modules,
                                  locality)

    def upgrade(self, context, instance_id, datastore_version_id):
        instance_tasks = models.BuiltInstanceTasks.load(context, instance_id)
        datastore_version = DatastoreVersion.load_by_uuid(datastore_version_id)
        with EndNotification(context):
            instance_tasks.upgrade(datastore_version)

    def update_overrides(self, context, instance_id, overrides):
        instance_tasks = models.BuiltInstanceTasks.load(context, instance_id)
        instance_tasks.update_overrides(overrides)

    def unassign_configuration(self, context, instance_id, flavor,
                               configuration_id):
        instance_tasks = models.BuiltInstanceTasks.load(context, instance_id)
        instance_tasks.unassign_configuration(flavor, configuration_id)

    def create_cluster(self, context, cluster_id):
        with EndNotification(context, cluster_id=cluster_id):
            cluster_tasks = models.load_cluster_tasks(context, cluster_id)
            cluster_tasks.create_cluster(context, cluster_id)

    def grow_cluster(self, context, cluster_id, new_instance_ids):
        cluster_tasks = models.load_cluster_tasks(context, cluster_id)
        cluster_tasks.grow_cluster(context, cluster_id, new_instance_ids)

    def shrink_cluster(self, context, cluster_id, instance_ids):
        cluster_tasks = models.load_cluster_tasks(context, cluster_id)
        cluster_tasks.shrink_cluster(context, cluster_id, instance_ids)

    def delete_cluster(self, context, cluster_id):
        with EndNotification(context):
            cluster_tasks = models.load_cluster_tasks(context, cluster_id)
            cluster_tasks.delete_cluster(context, cluster_id)

    if CONF.exists_notification_transformer:
        @periodic_task.periodic_task
        def publish_exists_event(self, context):
            """
            Push this in Instance Tasks to fetch a report/collection
            :param context: currently None as specied in bin script
            """
            mgmtmodels.publish_exist_events(self.exists_transformer,
                                            self.admin_context)

    @periodic_task.periodic_task(spacing=CONF.quota_notification_interval)
    def publish_quota_notifications(self, context):
        nova_client = remote.create_nova_client(self.admin_context)
        for tenant in nova_client.tenants.list():
            for quota in QUOTAS.get_all_quotas_by_tenant(tenant.id):
                usage = QUOTAS.get_quota_usage(quota)
                DBaaSQuotas(self.admin_context, quota, usage).notify()

    def __getattr__(self, name):
        """
        We should only get here if Python couldn't find a "real" method.
        """

        def raise_error(msg):
            raise AttributeError(msg)

        manager, sep, method = name.partition('_')
        if not manager:
            raise_error('Cannot derive manager from attribute name "%s"' %
                        name)

        task_strategy = strategy.load_taskmanager_strategy(manager)
        if not task_strategy:
            raise_error('No task manager strategy for manager "%s"' % manager)

        if method not in task_strategy.task_manager_manager_actions:
            raise_error('No method "%s" for task manager strategy for manager'
                        ' "%s"' % (method, manager))

        return task_strategy.task_manager_manager_actions.get(method)
