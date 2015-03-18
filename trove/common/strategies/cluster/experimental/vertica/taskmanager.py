#Copyright [2015] Hewlett-Packard Development Company, L.P.
#Licensed under the Apache License, Version 2.0 (the "License");
#you may not use this file except in compliance with the License.
#You may obtain a copy of the License at
#
#http://www.apache.org/licenses/LICENSE-2.0
#
#Unless required by applicable law or agreed to in writing, software
#distributed under the License is distributed on an "AS IS" BASIS,
#WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#See the License for the specific language governing permissions and
#limitations under the License.

from eventlet.timeout import Timeout

from trove.common import cfg
from trove.common.exception import PollTimeOut
from trove.common.instance import ServiceStatuses
from trove.common.remote import create_guest_client
from trove.common.strategies.cluster import base
from trove.common import utils
from trove.instance.models import DBInstance
from trove.instance.models import Instance
from trove.instance.models import InstanceServiceStatus
from trove.instance.tasks import InstanceTasks
from trove.common.i18n import _
from trove.openstack.common import log as logging
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

    def update_statuses_on_failure(self, cluster_id):

        if CONF.update_status_on_fail:
            db_instances = DBInstance.find_all(
                cluster_id=cluster_id, deleted=False).all()

            for db_instance in db_instances:
                db_instance.set_task_status(
                    InstanceTasks.BUILDING_ERROR_SERVER)
                db_instance.save()

    @classmethod
    def get_ip(cls, instance):
        return instance.get_visible_ip_addresses()[0]

    @classmethod
    def get_guest(cls, instance):
        return create_guest_client(instance.context, instance.db_info.id,
                                   instance.datastore_version.manager)

    def _all_instances_ready(self, instance_ids, cluster_id):

        def _all_status_ready(ids):
            LOG.debug("Checking service status of instance ids: %s." % ids)
            for instance_id in ids:
                status = InstanceServiceStatus.find_by(
                    instance_id=instance_id).get_status()
                if (status == ServiceStatuses.FAILED or
                   status == ServiceStatuses.FAILED_TIMEOUT_GUESTAGENT):
                        # if one has failed, no need to continue polling
                        LOG.debug("Instance %s in %s, exiting polling." % (
                            instance_id, status))
                        return True
                if (status != ServiceStatuses.RUNNING and
                   status != ServiceStatuses.BUILD_PENDING):
                        # if one is not in a ready state, continue polling
                        LOG.debug("Instance %s in %s, continue polling." % (
                            instance_id, status))
                        return False
            LOG.debug("Instances are ready, exiting polling for: %s." % ids)
            return True

        def _instance_ids_with_failures(ids):
            LOG.debug("Checking for service status failures for "
                      "instance ids: %s." % ids)
            failed_instance_ids = []
            for instance_id in ids:
                status = InstanceServiceStatus.find_by(
                    instance_id=instance_id).get_status()
                if (status == ServiceStatuses.FAILED or
                   status == ServiceStatuses.FAILED_TIMEOUT_GUESTAGENT):
                        failed_instance_ids.append(instance_id)
            return failed_instance_ids

        LOG.debug("Polling until service status is ready for "
                  "instance ids: %s." % instance_ids)
        try:
            utils.poll_until(lambda: instance_ids,
                             lambda ids: _all_status_ready(ids),
                             sleep_time=USAGE_SLEEP_TIME,
                             time_out=CONF.usage_timeout)
        except PollTimeOut:
            LOG.exception(_("Timeout for all instance service statuses "
                            "to become ready."))
            self.update_statuses_on_failure(cluster_id)
            return False

        failed_ids = _instance_ids_with_failures(instance_ids)
        if failed_ids:
            LOG.error(_("Some instances failed to become ready: %s.") %
                      failed_ids)
            self.update_statuses_on_failure(cluster_id)
            return False

        return True

    def create_cluster(self, context, cluster_id):
        LOG.debug("Begin create_cluster for id: %s." % cluster_id)

        def _create_cluster():

            # Fetch instances by cluster_id against instances table.
            db_instances = DBInstance.find_all(cluster_id=cluster_id).all()
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

                LOG.debug("Installing cluster with members: %s." % member_ips)
                guests[0].install_cluster(member_ips)

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

        LOG.debug("End create_cluster for id: %s." % cluster_id)


class VerticaTaskManagerAPI(task_api.API):

    def _cast(self, method_name, version, **kwargs):
        LOG.debug("Casting %s" % method_name)
        cctxt = self.client.prepare(version=version)
        cctxt.cast(self.context, method_name, **kwargs)
