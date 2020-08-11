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
from trove.common import clients
from trove.common.context import TroveContext
from trove.common import exception
from trove.common.exception import ReplicationSlaveAttachError
from trove.common.exception import TroveError
from trove.common.i18n import _
from trove.common.notification import DBaaSQuotas, EndNotification
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
            user=CONF.service_credentials.username,
            tenant=CONF.service_credentials.project_id,
            user_domain_name=CONF.service_credentials.user_domain_name)
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

            # NOTE(zhaochao): we cannot reattach the old master to the new
            # one immediately after the new master is up, because for MariaDB
            # the other replicas are still connecting to the old master, and
            # during reattaching the old master as a slave, new GTID may be
            # created and synced to the replicas. After that, when attaching
            # the replicas to the new master, 'START SLAVE' will fail by
            # 'fatal error 1236' if the binlog of the replica diverged from
            # the new master. So the proper order should be:
            # -1. make the old master read only (and detach floating ips)
            # -2. make sure the new master is up-to-date
            # -3. detach the new master from the old one
            # -4. enable the new master (and attach floating ips)
            # -5. attach the other replicas to the new master
            # -6. attach the old master to the new one
            #     (and attach floating ips)
            # -7. demote the old master
            # What we changed here is the order of the 6th step, previously
            # this step took place right after step 4, which causes failures
            # with MariaDB replications.
            old_master.make_read_only(True)
            latest_txn_id = old_master.get_latest_txn_id()
            master_candidate.wait_for_txn(latest_txn_id)
            master_candidate.detach_replica(old_master, for_failover=True)
            master_candidate.enable_as_master()
            master_candidate.make_read_only(False)

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
                    log_fmt = ("Unable to migrate replica %(slave)s from "
                               "old replica source %(old_master)s to "
                               "new source %(new_master)s on promote.")
                    exc_fmt = _("Unable to migrate replica %(slave)s from "
                                "old replica source %(old_master)s to "
                                "new source %(new_master)s on promote.")
                    msg_content = {
                        "slave": replica.id,
                        "old_master": old_master.id,
                        "new_master": master_candidate.id}
                    LOG.error(log_fmt, msg_content)

                    exception_replicas.append(replica)
                    error_messages += "%s (%s)\n" % (
                        exc_fmt % msg_content, ex)

            # dealing with the old master after all the other replicas
            # has been migrated.
            old_master.attach_replica(master_candidate)
            try:
                old_master.demote_replication_master()
            except Exception as ex:
                log_fmt = "Exception demoting old replica source %s."
                exc_fmt = _("Exception demoting old replica source %s.")
                LOG.error(log_fmt, old_master.id)
                exception_replicas.append(old_master)
                error_messages += "%s (%s)\n" % (
                    exc_fmt % old_master.id, ex)

            self._set_task_status([old_master] + replica_models,
                                  InstanceTasks.NONE)

            if exception_replicas:
                self._set_task_status(exception_replicas,
                                      InstanceTasks.PROMOTION_ERROR)
                msg = (_("promote-to-replica-source %(id)s: The following "
                         "replicas may not have been switched: %(replicas)s:"
                         "\n%(err)s") %
                       {"id": master_candidate.id,
                        "replicas": [repl.id for repl in exception_replicas],
                        "err": error_messages})
                raise ReplicationSlaveAttachError(msg)

            LOG.info('Finished to promote %s as master.', instance_id)

        with EndNotification(context):
            LOG.info('Promoting %s as replication master', instance_id)

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
        # last_txns is [instance, master UUID, last txn]
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
            LOG.info('New master selected: %s', master_candidate.id)

            master_candidate.detach_replica(old_master, for_failover=True)
            master_candidate.enable_as_master()
            master_candidate.make_read_only(False)

            exception_replicas = []
            error_messages = ""
            for replica in replica_models:
                try:
                    if replica.id != master_candidate.id:
                        replica.detach_replica(old_master, for_failover=True)
                        replica.attach_replica(master_candidate)
                except exception.TroveError as ex:
                    log_fmt = ("Unable to migrate replica %(slave)s from "
                               "old replica source %(old_master)s to "
                               "new source %(new_master)s on eject.")
                    exc_fmt = _("Unable to migrate replica %(slave)s from "
                                "old replica source %(old_master)s to "
                                "new source %(new_master)s on eject.")
                    msg_content = {
                        "slave": replica.id,
                        "old_master": old_master.id,
                        "new_master": master_candidate.id}
                    LOG.error(log_fmt, msg_content)
                    exception_replicas.append(replica)
                    error_messages += "%s (%s)\n" % (exc_fmt % msg_content, ex)

            self._set_task_status([old_master] + replica_models,
                                  InstanceTasks.NONE)
            if exception_replicas:
                self._set_task_status(exception_replicas,
                                      InstanceTasks.EJECTION_ERROR)
                msg = (_("eject-replica-source %(id)s: The following "
                         "replicas may not have been switched: %(replicas)s:"
                         "\n%(err)s") %
                       {"id": master_candidate.id,
                        "replicas": [repl.id for repl in exception_replicas],
                        "err": error_messages})
                raise ReplicationSlaveAttachError(msg)

            LOG.info('New master enabled: %s', master_candidate.id)

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

    def rebuild(self, context, instance_id, image_id):
        instance_tasks = models.BuiltInstanceTasks.load(context, instance_id)
        instance_tasks.rebuild(image_id)

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
                                  volume_type, modules, access=None,
                                  ds_version=None):

        if type(instance_id) in [list]:
            ids = instance_id
            root_passwords = root_password
        else:
            ids = [instance_id]
            root_passwords = [root_password]
        replica_number = 0
        replica_backup_id = backup_id
        replicas = []

        master_instance_tasks = BuiltInstanceTasks.load(context, slave_of_id)
        server_group = master_instance_tasks.server_group
        scheduler_hints = srv_grp.ServerGroup.convert_to_hint(server_group)
        LOG.debug("Using scheduler hints %s for creating instance %s",
                  scheduler_hints, instance_id)

        # Create backup for master
        snapshot = None
        try:
            instance_tasks = FreshInstanceTasks.load(context, ids[0])
            snapshot = instance_tasks.get_replication_master_snapshot(
                context, slave_of_id, flavor,
                parent_backup_id=replica_backup_id)
            LOG.info('Snapshot info for creating replica of %s: %s',
                     slave_of_id, snapshot)
        except Exception as err:
            LOG.error('Failed to get master snapshot info for creating '
                      'replica, error: %s', str(err))

            if snapshot and snapshot.get('dataset', {}).get('snapshot_id'):
                backup_id = snapshot['dataset']['snapshot_id']
                Backup.delete(context, backup_id)

            raise

        # Create replicas using the master backup
        replica_backup_id = snapshot['dataset']['snapshot_id']
        try:
            for replica_index in range(0, len(ids)):
                replica_number += 1
                LOG.info(f"Creating replica {replica_number} "
                         f"({ids[replica_index]}) of {len(ids)}.")

                instance_tasks = FreshInstanceTasks.load(
                    context, ids[replica_index])
                instance_tasks.create_instance(
                    flavor, image_id, databases, users, datastore_manager,
                    packages, volume_size, replica_backup_id,
                    availability_zone, root_passwords[replica_index],
                    nics, overrides, None, snapshot, volume_type,
                    modules, scheduler_hints, access=access,
                    ds_version=ds_version)
                replicas.append(instance_tasks)

            for replica in replicas:
                replica.wait_for_instance(CONF.restore_usage_timeout, flavor)
                LOG.info('Replica %s created successfully', replica.id)
        except Exception as err:
            LOG.error('Failed to create replica from %s, error: %s',
                      slave_of_id, str(err))
            raise
        finally:
            Backup.delete(context, replica_backup_id)

    def _create_instance(self, context, instance_id, name, flavor,
                         image_id, databases, users, datastore_manager,
                         packages, volume_size, backup_id, availability_zone,
                         root_password, nics, overrides, slave_of_id,
                         cluster_config, volume_type, modules, locality,
                         access=None, ds_version=None):
        if slave_of_id:
            self._create_replication_slave(context, instance_id, name,
                                           flavor, image_id, databases, users,
                                           datastore_manager, packages,
                                           volume_size,
                                           availability_zone, root_password,
                                           nics, overrides, slave_of_id,
                                           backup_id, volume_type, modules,
                                           access=access,
                                           ds_version=ds_version)
        else:
            if type(instance_id) in [list]:
                raise AttributeError(_(
                    "Cannot create multiple non-replica instances."))

            scheduler_hints = srv_grp.ServerGroup.build_scheduler_hint(
                context, locality, instance_id
            )
            LOG.debug("Using scheduler hints %s for creating instance %s",
                      scheduler_hints, instance_id)

            instance_tasks = FreshInstanceTasks.load(context, instance_id)
            instance_tasks.create_instance(
                flavor, image_id, databases, users,
                datastore_manager, packages,
                volume_size, backup_id,
                availability_zone, root_password,
                nics, overrides, cluster_config,
                None, volume_type, modules,
                scheduler_hints, access=access, ds_version=ds_version
            )

            timeout = (CONF.restore_usage_timeout if backup_id
                       else CONF.usage_timeout)
            instance_tasks.wait_for_instance(timeout, flavor)

    def create_instance(self, context, instance_id, name, flavor,
                        image_id, databases, users, datastore_manager,
                        packages, volume_size, backup_id, availability_zone,
                        root_password, nics, overrides, slave_of_id,
                        cluster_config, volume_type, modules, locality,
                        access=None, ds_version=None):
        with EndNotification(
            context,
            instance_id=(
                instance_id[0]
                if isinstance(instance_id, list)
                else instance_id
            )
        ):
            self._create_instance(context, instance_id, name, flavor,
                                  image_id, databases, users,
                                  datastore_manager, packages, volume_size,
                                  backup_id, availability_zone,
                                  root_password, nics, overrides, slave_of_id,
                                  cluster_config, volume_type, modules,
                                  locality, access=access,
                                  ds_version=ds_version)

    def upgrade(self, context, instance_id, datastore_version_id):
        instance_tasks = models.BuiltInstanceTasks.load(context, instance_id)
        datastore_version = DatastoreVersion.load_by_uuid(datastore_version_id)
        with EndNotification(context):
            instance_tasks.upgrade(datastore_version)

    def update_access(self, context, instance_id, access):
        instance_tasks = models.BuiltInstanceTasks.load(context, instance_id)

        try:
            instance_tasks.update_access(access)
        except Exception as e:
            LOG.error(f"Failed to update access configuration for "
                      f"{instance_id}: {str(e)}")
            self.update_db(task_status=InstanceTasks.UPDATING_ERROR_ACCESS)

    def create_cluster(self, context, cluster_id):
        with EndNotification(context, cluster_id=cluster_id):
            cluster_tasks = models.load_cluster_tasks(context, cluster_id)
            cluster_tasks.create_cluster(context, cluster_id)

    def grow_cluster(self, context, cluster_id, new_instance_ids):
        with EndNotification(context, cluster_id=cluster_id,
                             instance_ids=new_instance_ids):
            cluster_tasks = models.load_cluster_tasks(context, cluster_id)
            cluster_tasks.grow_cluster(context, cluster_id, new_instance_ids)

    def shrink_cluster(self, context, cluster_id, instance_ids):
        with EndNotification(context, cluster_id=cluster_id,
                             instance_ids=instance_ids):
            cluster_tasks = models.load_cluster_tasks(context, cluster_id)
            cluster_tasks.shrink_cluster(context, cluster_id, instance_ids)

    def restart_cluster(self, context, cluster_id):
        cluster_tasks = models.load_cluster_tasks(context, cluster_id)
        cluster_tasks.restart_cluster(context, cluster_id)

    def upgrade_cluster(self, context, cluster_id, datastore_version_id):
        datastore_version = DatastoreVersion.load_by_uuid(datastore_version_id)
        cluster_tasks = models.load_cluster_tasks(context, cluster_id)
        cluster_tasks.upgrade_cluster(context, cluster_id, datastore_version)

    def delete_cluster(self, context, cluster_id):
        with EndNotification(context):
            cluster_tasks = models.load_cluster_tasks(context, cluster_id)
            cluster_tasks.delete_cluster(context, cluster_id)

    def reapply_module(self, context, module_id, md5, include_clustered,
                       batch_size, batch_delay, force):
        models.ModuleTasks.reapply_module(
            context, module_id, md5, include_clustered,
            batch_size, batch_delay, force)

    if CONF.exists_notification_transformer:
        @periodic_task.periodic_task
        def publish_exists_event(self, context):
            """
            Push this in Instance Tasks to fetch a report/collection
            :param context: currently None as specied in bin script
            """
            mgmtmodels.publish_exist_events(self.exists_transformer,
                                            self.admin_context)

    if CONF.quota_notification_interval:
        @periodic_task.periodic_task(spacing=CONF.quota_notification_interval)
        def publish_quota_notifications(self, context):
            nova_client = clients.create_nova_client(self.admin_context)
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
