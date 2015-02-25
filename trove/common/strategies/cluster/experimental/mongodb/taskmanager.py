# Copyright 2014 eBay Software Foundation
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


class MongoDbTaskManagerStrategy(base.BaseTaskManagerStrategy):

    @property
    def task_manager_api_class(self):
        return MongoDbTaskManagerAPI

    @property
    def task_manager_cluster_tasks_class(self):
        return MongoDbClusterTasks

    @property
    def task_manager_manager_actions(self):
        return {'add_shard_cluster': self._manager_add_shard}

    def _manager_add_shard(self, context, cluster_id, shard_id,
                           replica_set_name):
        cluster_tasks = task_models.ClusterTasks.load(
            context,
            cluster_id,
            MongoDbClusterTasks)
        cluster_tasks.add_shard_cluster(context, cluster_id, shard_id,
                                        replica_set_name)


class MongoDbClusterTasks(task_models.ClusterTasks):

    def update_statuses_on_failure(self, cluster_id, shard_id=None):

        if CONF.update_status_on_fail:
            if shard_id:
                db_instances = DBInstance.find_all(cluster_id=cluster_id,
                                                   shard_id=shard_id).all()
            else:
                db_instances = DBInstance.find_all(
                    cluster_id=cluster_id).all()

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

    def _all_instances_ready(self, instance_ids, cluster_id,
                             shard_id=None):

        def _all_status_ready(ids):
            LOG.debug("Checking service status of instance ids: %s" % ids)
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
            LOG.debug("Instances are ready, exiting polling for: %s" % ids)
            return True

        def _instance_ids_with_failures(ids):
            LOG.debug("Checking for service status failures for "
                      "instance ids: %s" % ids)
            failed_instance_ids = []
            for instance_id in ids:
                status = InstanceServiceStatus.find_by(
                    instance_id=instance_id).get_status()
                if (status == ServiceStatuses.FAILED or
                   status == ServiceStatuses.FAILED_TIMEOUT_GUESTAGENT):
                        failed_instance_ids.append(instance_id)
            return failed_instance_ids

        LOG.debug("Polling until service status is ready for "
                  "instance ids: %s" % instance_ids)
        try:
            utils.poll_until(lambda: instance_ids,
                             lambda ids: _all_status_ready(ids),
                             sleep_time=USAGE_SLEEP_TIME,
                             time_out=CONF.usage_timeout)
        except PollTimeOut:
            LOG.exception(_("Timeout for all instance service statuses "
                            "to become ready."))
            self.update_statuses_on_failure(cluster_id, shard_id)
            return False

        failed_ids = _instance_ids_with_failures(instance_ids)
        if failed_ids:
            LOG.error(_("Some instances failed to become ready: %s") %
                      failed_ids)
            self.update_statuses_on_failure(cluster_id, shard_id)
            return False

        return True

    def _create_replica_set(self, members, cluster_id, shard_id=None):
        # randomly pick a member out of members (referred to as 'x'), then
        # for every other member append the ip/hostname to a list called
        # "member_hosts", then
        first_member = members[0]
        first_member_ip = self.get_ip(first_member)
        other_members = members[1:]
        other_member_ips = [self.get_ip(instance)
                            for instance in other_members]
        LOG.debug("first member: %s" % first_member_ip)
        LOG.debug("others members: %s" % other_member_ips)

        # assumption: add_members is a call not cast, so we don't have to
        # execute another command to see if the replica-set has initialized
        # correctly.
        LOG.debug("sending add_members (call) to %s" % first_member_ip)
        try:
            self.get_guest(first_member).add_members(other_member_ips)
        except Exception:
            LOG.exception(_("error adding members"))
            self.update_statuses_on_failure(cluster_id, shard_id)
            return False
        return True

    def _create_shard(self, query_routers, replica_set_name,
                      members, cluster_id, shard_id=None):
        a_query_router = query_routers[0]
        LOG.debug("calling add_shard on query_router: %s" % a_query_router)
        member_ip = self.get_ip(members[0])
        try:
            self.get_guest(a_query_router).add_shard(replica_set_name,
                                                     member_ip)
        except Exception:
            LOG.exception(_("error adding shard"))
            self.update_statuses_on_failure(cluster_id, shard_id)
            return False
        return True

    def create_cluster(self, context, cluster_id):
        LOG.debug("begin create_cluster for id: %s" % cluster_id)

        def _create_cluster():

            # fetch instances by cluster_id against instances table
            db_instances = DBInstance.find_all(cluster_id=cluster_id).all()
            instance_ids = [db_instance.id for db_instance in db_instances]
            LOG.debug("instances in cluster %s: %s" % (cluster_id,
                                                       instance_ids))

            if not self._all_instances_ready(instance_ids, cluster_id):
                return

            instances = [Instance.load(context, instance_id) for instance_id
                         in instance_ids]

            # filter query routers in instances into a new list: query_routers
            query_routers = [instance for instance in instances if
                             instance.type == 'query_router']
            LOG.debug("query routers: %s" %
                      [instance.id for instance in query_routers])
            # filter config servers in instances into new list: config_servers
            config_servers = [instance for instance in instances if
                              instance.type == 'config_server']
            LOG.debug("config servers: %s" %
                      [instance.id for instance in config_servers])
            # filter members (non router/configsvr) into a new list: members
            members = [instance for instance in instances if
                       instance.type == 'member']
            LOG.debug("members: %s" %
                      [instance.id for instance in members])

            # for config_server in config_servers, append ip/hostname to
            # "config_server_hosts", then
            # peel off the replica-set name and ip/hostname from 'x'
            config_server_ips = [self.get_ip(instance)
                                 for instance in config_servers]
            LOG.debug("config server ips: %s" % config_server_ips)

            LOG.debug("calling add_config_servers on query_routers")
            try:
                for query_router in query_routers:
                    (self.get_guest(query_router)
                     .add_config_servers(config_server_ips))
            except Exception:
                LOG.exception(_("error adding config servers"))
                self.update_statuses_on_failure(cluster_id)
                return

            if not self._create_replica_set(members, cluster_id):
                return

            replica_set_name = "rs1"
            if not self._create_shard(query_routers, replica_set_name,
                                      members, cluster_id):
                return
            # call to start checking status
            for instance in instances:
                self.get_guest(instance).cluster_complete()

        cluster_usage_timeout = CONF.cluster_usage_timeout
        timeout = Timeout(cluster_usage_timeout)
        try:
            _create_cluster()
            self.reset_task()
        except Timeout as t:
            if t is not timeout:
                raise  # not my timeout
            LOG.exception(_("timeout for building cluster."))
            self.update_statuses_on_failure(cluster_id)
        finally:
            timeout.cancel()

        LOG.debug("end create_cluster for id: %s" % cluster_id)

    def add_shard_cluster(self, context, cluster_id, shard_id,
                          replica_set_name):

        LOG.debug("begin add_shard_cluster for cluster %s shard %s"
                  % (cluster_id, shard_id))

        def _add_shard_cluster():

            db_instances = DBInstance.find_all(cluster_id=cluster_id,
                                               shard_id=shard_id).all()
            instance_ids = [db_instance.id for db_instance in db_instances]
            LOG.debug("instances in shard %s: %s" % (shard_id,
                                                     instance_ids))
            if not self._all_instances_ready(instance_ids, cluster_id,
                                             shard_id):
                return

            members = [Instance.load(context, instance_id)
                       for instance_id in instance_ids]

            if not self._create_replica_set(members, cluster_id, shard_id):
                return

            db_query_routers = DBInstance.find_all(cluster_id=cluster_id,
                                                   type='query_router',
                                                   deleted=False).all()
            query_routers = [Instance.load(context, db_query_router.id)
                             for db_query_router in db_query_routers]

            if not self._create_shard(query_routers, replica_set_name,
                                      members, cluster_id, shard_id):
                return

            for member in members:
                self.get_guest(member).cluster_complete()

        cluster_usage_timeout = CONF.cluster_usage_timeout
        timeout = Timeout(cluster_usage_timeout)
        try:
            _add_shard_cluster()
            self.reset_task()
        except Timeout as t:
            if t is not timeout:
                raise  # not my timeout
            LOG.exception(_("timeout for building shard."))
            self.update_statuses_on_failure(cluster_id, shard_id)
        finally:
            timeout.cancel()

        LOG.debug("end add_shard_cluster for cluster %s shard %s"
                  % (cluster_id, shard_id))


class MongoDbTaskManagerAPI(task_api.API):

    def mongodb_add_shard_cluster(self, cluster_id, shard_id,
                                  replica_set_name):
        LOG.debug("Making async call to add shard cluster %s " % cluster_id)
        cctxt = self.client.prepare(version=self.version_cap)
        cctxt.cast(self.context,
                   "mongodb_add_shard_cluster",
                   cluster_id=cluster_id,
                   shard_id=shard_id,
                   replica_set_name=replica_set_name)
