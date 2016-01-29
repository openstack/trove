# Copyright [2015] Hewlett-Packard Development Company, L.P.
# Copyright 2016 Tesora Inc.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from eventlet.timeout import Timeout
from oslo_log import log as logging

from trove.common import cfg
from trove.common.exception import PollTimeOut
from trove.common.exception import TroveError
from trove.common.i18n import _
from trove.common.remote import create_nova_client
from trove.common.strategies.cluster import base as cluster_base
from trove.common.template import ClusterConfigTemplate
from trove.common import utils
from trove.extensions.common import models as ext_models
from trove.instance.models import DBInstance
from trove.instance.models import Instance
from trove.instance import tasks as inst_tasks
from trove.taskmanager import api as task_api
import trove.taskmanager.models as task_models


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class GaleraCommonTaskManagerStrategy(cluster_base.BaseTaskManagerStrategy):

    @property
    def task_manager_api_class(self):
        return task_api.API

    @property
    def task_manager_cluster_tasks_class(self):
        return GaleraCommonClusterTasks


class GaleraCommonClusterTasks(task_models.ClusterTasks):

    CLUSTER_REPLICATION_USER = "clusterrepuser"

    def _render_cluster_config(self, context, instance, cluster_ips,
                               cluster_name, replication_user):
        client = create_nova_client(context)
        flavor = client.flavors.get(instance.flavor_id)
        instance_ip = self.get_ip(instance)
        config = ClusterConfigTemplate(
            self.datastore_version, flavor, instance.id)
        replication_user_pass = "%(name)s:%(password)s" % replication_user
        config_rendered = config.render(
            replication_user_pass=replication_user_pass,
            cluster_ips=cluster_ips,
            cluster_name=cluster_name,
            instance_ip=instance_ip,
            instance_name=instance.name,
        )
        return config_rendered

    def create_cluster(self, context, cluster_id):
        LOG.debug("Begin create_cluster for id: %s." % cluster_id)

        def _create_cluster():
            # Fetch instances by cluster_id against instances table.
            db_instances = DBInstance.find_all(cluster_id=cluster_id).all()
            instance_ids = [db_instance.id for db_instance in db_instances]

            LOG.debug("Waiting for instances to get to cluster-ready status.")
            # Wait for cluster members to get to cluster-ready status.
            if not self._all_instances_ready(instance_ids, cluster_id):
                raise TroveError("Instances in cluster did not report ACTIVE")

            LOG.debug("All members ready, proceeding for cluster setup.")
            instances = [Instance.load(context, instance_id) for instance_id
                         in instance_ids]

            cluster_ips = [self.get_ip(instance) for instance in instances]
            instance_guests = [self.get_guest(instance)
                               for instance in instances]

            # Create replication user and password for synchronizing the
            # galera cluster
            replication_user = {
                "name": self.CLUSTER_REPLICATION_USER,
                "password": utils.generate_random_password(),
            }

            # Galera cluster name must be unique and be shorter than a full
            # uuid string so we remove the hyphens and chop it off. It was
            # recommended to be 16 chars or less.
            # (this is not currently documented on Galera docs)
            cluster_name = utils.generate_uuid().replace("-", "")[:16]

            LOG.debug("Configuring cluster configuration.")
            try:
                # Set the admin password for all the instances because the
                # password in the my.cnf will be wrong after the joiner
                # instances syncs with the donor instance.
                admin_password = str(utils.generate_random_password())
                for guest in instance_guests:
                    guest.reset_admin_password(admin_password)

                bootstrap = True
                for instance in instances:
                    guest = self.get_guest(instance)

                    # render the conf.d/cluster.cnf configuration
                    cluster_configuration = self._render_cluster_config(
                        context,
                        instance,
                        ",".join(cluster_ips),
                        cluster_name,
                        replication_user)

                    # push the cluster config and bootstrap the first instance
                    guest.install_cluster(replication_user,
                                          cluster_configuration,
                                          bootstrap)
                    bootstrap = False

                LOG.debug("Finalizing cluster configuration.")
                for guest in instance_guests:
                    guest.cluster_complete()
            except Exception:
                LOG.exception(_("Error creating cluster."))
                self.update_statuses_on_failure(cluster_id)

        timeout = Timeout(CONF.cluster_usage_timeout)
        try:
            _create_cluster()
            self.reset_task()
        except Timeout as t:
            if t is not timeout:
                raise  # not my timeout
            LOG.exception(_("Timeout for building cluster."))
            self.update_statuses_on_failure(cluster_id)
        except TroveError:
            LOG.exception(_("Error creating cluster %s.") % cluster_id)
            self.update_statuses_on_failure(cluster_id)
        finally:
            timeout.cancel()

        LOG.debug("End create_cluster for id: %s." % cluster_id)

    def _check_cluster_for_root(self, context, existing_instances,
                                new_instances):
        """Check for existing instances root enabled"""
        for instance in existing_instances:
            if ext_models.Root.load(context, instance.id):
                for new_instance in new_instances:
                    ext_models.RootHistory.create(context, new_instance.id,
                                                  context.user)
                return

    def grow_cluster(self, context, cluster_id, new_instance_ids):
        LOG.debug("Begin Galera grow_cluster for id: %s." % cluster_id)

        def _grow_cluster():

            db_instances = DBInstance.find_all(
                cluster_id=cluster_id, deleted=False).all()
            existing_instances = [Instance.load(context, db_inst.id)
                                  for db_inst in db_instances
                                  if db_inst.id not in new_instance_ids]
            if not existing_instances:
                raise TroveError("Unable to determine existing cluster "
                                 "member(s)")

            # get list of ips of existing cluster members
            existing_cluster_ips = [self.get_ip(instance) for instance in
                                    existing_instances]
            existing_instance_guests = [self.get_guest(instance)
                                        for instance in existing_instances]

            # get the cluster context to setup new members
            cluster_context = existing_instance_guests[0].get_cluster_context()

            # Wait for cluster members to get to cluster-ready status.
            if not self._all_instances_ready(new_instance_ids, cluster_id):
                raise TroveError("Instances in cluster did not report ACTIVE")

            LOG.debug("All members ready, proceeding for cluster setup.")

            # Get the new instances to join the cluster
            new_instances = [Instance.load(context, instance_id)
                             for instance_id in new_instance_ids]
            new_cluster_ips = [self.get_ip(instance) for instance in
                               new_instances]
            for instance in new_instances:
                guest = self.get_guest(instance)

                guest.reset_admin_password(cluster_context['admin_password'])

                # render the conf.d/cluster.cnf configuration
                cluster_configuration = self._render_cluster_config(
                    context,
                    instance,
                    ",".join(existing_cluster_ips),
                    cluster_context['cluster_name'],
                    cluster_context['replication_user'])

                # push the cluster config and bootstrap the first instance
                bootstrap = False
                guest.install_cluster(cluster_context['replication_user'],
                                      cluster_configuration,
                                      bootstrap)

            self._check_cluster_for_root(context,
                                         existing_instances,
                                         new_instances)

            # apply the new config to all instances
            for instance in existing_instances + new_instances:
                guest = self.get_guest(instance)
                # render the conf.d/cluster.cnf configuration
                cluster_configuration = self._render_cluster_config(
                    context,
                    instance,
                    ",".join(existing_cluster_ips + new_cluster_ips),
                    cluster_context['cluster_name'],
                    cluster_context['replication_user'])
                guest.write_cluster_configuration_overrides(
                    cluster_configuration)

            for instance in new_instances:
                guest = self.get_guest(instance)
                guest.cluster_complete()

        timeout = Timeout(CONF.cluster_usage_timeout)
        try:
            _grow_cluster()
            self.reset_task()
        except Timeout as t:
            if t is not timeout:
                raise  # not my timeout
            LOG.exception(_("Timeout for growing cluster."))
            self.update_statuses_on_failure(
                cluster_id, status=inst_tasks.InstanceTasks.GROWING_ERROR)
        except Exception:
            LOG.exception(_("Error growing cluster %s.") % cluster_id)
            self.update_statuses_on_failure(
                cluster_id, status=inst_tasks.InstanceTasks.GROWING_ERROR)
        finally:
            timeout.cancel()

        LOG.debug("End grow_cluster for id: %s." % cluster_id)

    def shrink_cluster(self, context, cluster_id, removal_instance_ids):
        LOG.debug("Begin Galera shrink_cluster for id: %s." % cluster_id)

        def _shrink_cluster():
            removal_instances = [Instance.load(context, instance_id)
                                 for instance_id in removal_instance_ids]
            for instance in removal_instances:
                Instance.delete(instance)

            # wait for instances to be deleted
            def all_instances_marked_deleted():
                non_deleted_instances = DBInstance.find_all(
                    cluster_id=cluster_id, deleted=False).all()
                non_deleted_ids = [db_instance.id for db_instance
                                   in non_deleted_instances]
                return not bool(
                    set(removal_instance_ids).intersection(
                        set(non_deleted_ids))
                )
            try:
                LOG.info(_("Deleting instances (%s)") % removal_instance_ids)
                utils.poll_until(all_instances_marked_deleted,
                                 sleep_time=2,
                                 time_out=CONF.cluster_delete_time_out)
            except PollTimeOut:
                LOG.error(_("timeout for instances to be marked as deleted."))
                return

            db_instances = DBInstance.find_all(cluster_id=cluster_id).all()
            leftover_instances = [Instance.load(context, db_inst.id)
                                  for db_inst in db_instances
                                  if db_inst.id not in removal_instance_ids]
            leftover_cluster_ips = [self.get_ip(instance) for instance in
                                    leftover_instances]

            # Get config changes for left over instances
            rnd_cluster_guest = self.get_guest(leftover_instances[0])
            cluster_context = rnd_cluster_guest.get_cluster_context()

            # apply the new config to all leftover instances
            for instance in leftover_instances:
                guest = self.get_guest(instance)
                # render the conf.d/cluster.cnf configuration
                cluster_configuration = self._render_cluster_config(
                    context,
                    instance,
                    ",".join(leftover_cluster_ips),
                    cluster_context['cluster_name'],
                    cluster_context['replication_user'])
                guest.write_cluster_configuration_overrides(
                    cluster_configuration)

        timeout = Timeout(CONF.cluster_usage_timeout)
        try:
            _shrink_cluster()
            self.reset_task()
        except Timeout as t:
            if t is not timeout:
                raise  # not my timeout
            LOG.exception(_("Timeout for shrinking cluster."))
            self.update_statuses_on_failure(
                cluster_id, status=inst_tasks.InstanceTasks.SHRINKING_ERROR)
        except Exception:
            LOG.exception(_("Error shrinking cluster %s.") % cluster_id)
            self.update_statuses_on_failure(
                cluster_id, status=inst_tasks.InstanceTasks.SHRINKING_ERROR)
        finally:
            timeout.cancel()

        LOG.debug("End shrink_cluster for id: %s." % cluster_id)
