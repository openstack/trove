# Copyright [2015] Hewlett-Packard Development Company, L.P.
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
from trove.common.i18n import _
from trove.common.strategies.cluster import base
from trove.common.strategies.cluster.experimental.vertica.api import \
    VerticaCluster
from trove.instance.models import DBInstance
from trove.instance.models import Instance
from trove.taskmanager import api as task_api
import trove.taskmanager.models as task_models


LOG = logging.getLogger(__name__)
CONF = cfg.CONF
USAGE_SLEEP_TIME = CONF.usage_sleep_time  # seconds.


class VerticaTaskManagerStrategy(base.BaseTaskManagerStrategy):

    @property
    def task_manager_api_class(self):
        return VerticaTaskManagerAPI

    @property
    def task_manager_cluster_tasks_class(self):
        return VerticaClusterTasks


class VerticaClusterTasks(task_models.ClusterTasks):

    def create_cluster(self, context, cluster_id):
        LOG.debug("Begin create_cluster for id: %s.", cluster_id)

        def _create_cluster():

            # Fetch instances by cluster_id against instances table.
            db_instances = DBInstance.find_all(cluster_id=cluster_id,
                                               deleted=False).all()
            instance_ids = [db_instance.id for db_instance in db_instances]

            # Wait for cluster members to get to cluster-ready status.
            if not self._all_instances_ready(instance_ids, cluster_id):
                return

            LOG.debug("All members ready, proceeding for cluster setup.")
            instances = [Instance.load(context, instance_id) for instance_id
                         in instance_ids]

            member_ips = [self.get_ip(instance) for instance in instances]
            guests = [self.get_guest(instance) for instance in instances]

            # Users to be configured for password-less SSH.
            authorized_users_without_password = ['root', 'dbadmin']

            # Configuring password-less SSH for cluster members.
            # Strategy for setting up SSH:
            # get public keys for user from member-instances in cluster,
            # combine them, finally push it back to all instances,
            # and member instances add them to authorized keys.
            LOG.debug("Configuring password-less SSH on cluster members.")
            try:
                for user in authorized_users_without_password:
                    pub_key = [guest.get_public_keys(user) for guest in guests]
                    for guest in guests:
                        guest.authorize_public_keys(user, pub_key)

                LOG.debug("Installing cluster with members: %s.", member_ips)
                for db_instance in db_instances:
                    if db_instance['type'] == 'master':
                        master_instance = Instance.load(context,
                                                        db_instance.id)
                        self.get_guest(master_instance).install_cluster(
                            member_ips)
                        break

                LOG.debug("Finalizing cluster configuration.")
                for guest in guests:
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
        finally:
            timeout.cancel()

        LOG.debug("End create_cluster for id: %s.", cluster_id)

    def grow_cluster(self, context, cluster_id, new_instance_ids):

        def _grow_cluster():
            LOG.debug("begin grow_cluster for Vertica cluster %s", cluster_id)

            db_instances = DBInstance.find_all(cluster_id=cluster_id,
                                               deleted=False).all()

            instance_ids = [db_instance.id for db_instance in db_instances]

            # Wait for new cluster members to get to cluster-ready status.
            if not self._all_instances_ready(new_instance_ids, cluster_id):
                return

            new_insts = [Instance.load(context, instance_id)
                         for instance_id in new_instance_ids]

            existing_instances = [Instance.load(context, instance_id)
                                  for instance_id
                                  in instance_ids
                                  if instance_id not in new_instance_ids]

            existing_guests = [self.get_guest(i) for i in existing_instances]
            new_guests = [self.get_guest(i) for i in new_insts]
            all_guests = new_guests + existing_guests

            authorized_users_without_password = ['root', 'dbadmin']
            new_ips = [self.get_ip(instance) for instance in new_insts]

            for user in authorized_users_without_password:
                pub_key = [guest.get_public_keys(user) for guest in all_guests]
                for guest in all_guests:
                    guest.authorize_public_keys(user, pub_key)

            for db_instance in db_instances:
                if db_instance['type'] == 'master':
                    LOG.debug("Found 'master' instance, calling grow on guest")
                    master_instance = Instance.load(context,
                                                    db_instance.id)
                    self.get_guest(master_instance).grow_cluster(new_ips)
                    break

            for guest in new_guests:
                guest.cluster_complete()

        timeout = Timeout(CONF.cluster_usage_timeout)

        try:
            _grow_cluster()
            self.reset_task()
        except Timeout as t:
            if t is not timeout:
                raise  # not my timeout
            LOG.exception(_("Timeout for growing cluster."))
            self.update_statuses_on_failure(cluster_id)
        except Exception:
            LOG.exception(_("Error growing cluster %s."), cluster_id)
            self.update_statuses_on_failure(cluster_id)
        finally:
            timeout.cancel()

    def shrink_cluster(self, context, cluster_id, instance_ids):
        def _shrink_cluster():
            db_instances = DBInstance.find_all(cluster_id=cluster_id,
                                               deleted=False).all()

            all_instance_ids = [db_instance.id for db_instance in db_instances]

            remove_instances = [Instance.load(context, instance_id)
                                for instance_id in instance_ids]

            left_instances = [Instance.load(context, instance_id)
                              for instance_id
                              in all_instance_ids
                              if instance_id not in instance_ids]

            remove_member_ips = [self.get_ip(instance)
                                 for instance in remove_instances]

            k = VerticaCluster.k_safety(len(left_instances))

            for db_instance in db_instances:
                if db_instance['type'] == 'master':
                    master_instance = Instance.load(context,
                                                    db_instance.id)
                    if self.get_ip(master_instance) in remove_member_ips:
                        raise RuntimeError(_("Cannot remove master instance!"))
                    LOG.debug("Marking cluster k-safety: %s", k)
                    self.get_guest(master_instance).mark_design_ksafe(k)
                    self.get_guest(master_instance).shrink_cluster(
                        remove_member_ips)
                    break

            for r in remove_instances:
                Instance.delete(r)

        timeout = Timeout(CONF.cluster_usage_timeout)
        try:
            _shrink_cluster()
            self.reset_task()
        except Timeout as t:
            if t is not timeout:
                raise
            LOG.exception(_("Timeout for shrinking cluster."))
            self.update_statuses_on_failure(cluster_id)
        finally:
            timeout.cancel()

        LOG.debug("end shrink_cluster for Vertica cluster id %s", self.id)


class VerticaTaskManagerAPI(task_api.API):

    def _cast(self, method_name, version, **kwargs):
        LOG.debug("Casting %s", method_name)
        cctxt = self.client.prepare(version=version)
        cctxt.cast(self.context, method_name, **kwargs)
