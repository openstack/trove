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
from oslo_log import log as logging

from trove.common import cfg
from trove.common.exception import PollTimeOut
from trove.common.i18n import _
from trove.common.instance import ServiceStatuses
from trove.common.strategies.cluster import base
from trove.common import utils
from trove.instance import models
from trove.instance.models import DBInstance
from trove.instance.models import Instance
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

    def create_cluster(self, context, cluster_id):
        LOG.debug("begin create_cluster for id: %s", cluster_id)

        def _create_cluster():

            # fetch instances by cluster_id against instances table
            db_instances = DBInstance.find_all(cluster_id=cluster_id).all()
            instance_ids = [db_instance.id for db_instance in db_instances]
            LOG.debug("instances in cluster %(cluster_id)s: %(instance_ids)s",
                      {'cluster_id': cluster_id, 'instance_ids': instance_ids})

            if not self._all_instances_ready(instance_ids, cluster_id):
                return

            LOG.debug("all instances in cluster %s ready.", cluster_id)

            instances = [Instance.load(context, instance_id) for instance_id
                         in instance_ids]

            # filter query routers in instances into a new list: query_routers
            query_routers = [instance for instance in instances if
                             instance.type == 'query_router']
            LOG.debug("query routers: %s",
                      [instance.id for instance in query_routers])
            # filter config servers in instances into new list: config_servers
            config_servers = [instance for instance in instances if
                              instance.type == 'config_server']
            LOG.debug("config servers: %s",
                      [instance.id for instance in config_servers])
            # filter members (non router/configsvr) into a new list: members
            members = [instance for instance in instances if
                       instance.type == 'member']
            LOG.debug("members: %s",
                      [instance.id for instance in members])

            # for config_server in config_servers, append ip/hostname to
            # "config_server_hosts", then
            # peel off the replica-set name and ip/hostname from 'x'
            config_server_ips = [self.get_ip(instance)
                                 for instance in config_servers]
            LOG.debug("config server ips: %s", config_server_ips)

            if not self._add_query_routers(query_routers,
                                           config_server_ips):
                return

            if not self._create_shard(query_routers[0], members):
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

        LOG.debug("end create_cluster for id: %s", cluster_id)

    def add_shard_cluster(self, context, cluster_id, shard_id,
                          replica_set_name):

        LOG.debug("begin add_shard_cluster for cluster %(cluster_id)s "
                  "shard %(shard_id)s", {'cluster_id': cluster_id,
                                         'shard_id': shard_id})

        def _add_shard_cluster():

            db_instances = DBInstance.find_all(cluster_id=cluster_id,
                                               shard_id=shard_id).all()
            instance_ids = [db_instance.id for db_instance in db_instances]
            LOG.debug("instances in shard %(shard_id)s: %(instance_ids)s",
                      {'shard_id': shard_id, 'instance_ids': instance_ids})
            if not self._all_instances_ready(instance_ids, cluster_id,
                                             shard_id):
                return

            members = [Instance.load(context, instance_id)
                       for instance_id in instance_ids]

            db_query_routers = DBInstance.find_all(cluster_id=cluster_id,
                                                   type='query_router',
                                                   deleted=False).all()
            query_routers = [Instance.load(context, db_query_router.id)
                             for db_query_router in db_query_routers]

            if not self._create_shard(query_routers[0], members):
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

        LOG.debug("end add_shard_cluster for cluster %(cluster_id)s "
                  "shard %(shard_id)s", {'cluster_id': cluster_id,
                                         'shard_id': shard_id})

    def grow_cluster(self, context, cluster_id, instance_ids):
        LOG.debug("begin grow_cluster for MongoDB cluster %s", cluster_id)

        def _grow_cluster():
            new_instances = [db_instance for db_instance in self.db_instances
                             if db_instance.id in instance_ids]
            new_members = [db_instance for db_instance in new_instances
                           if db_instance.type == 'member']
            new_query_routers = [db_instance for db_instance in new_instances
                                 if db_instance.type == 'query_router']
            instances = []
            if new_members:
                shard_ids = set([db_instance.shard_id for db_instance
                                 in new_members])
                query_router_id = self._get_running_query_router_id()
                if not query_router_id:
                    return
                for shard_id in shard_ids:
                    LOG.debug('growing cluster by adding shard %(shard_id)s '
                              'on query router %(router_id)s',
                              {'shard_id': shard_id,
                               'router_id': query_router_id})
                    member_ids = [db_instance.id for db_instance in new_members
                                  if db_instance.shard_id == shard_id]
                    if not self._all_instances_ready(
                        member_ids, cluster_id, shard_id
                    ):
                        return
                    members = [Instance.load(context, member_id)
                               for member_id in member_ids]
                    query_router = Instance.load(context, query_router_id)
                    if not self._create_shard(query_router, members):
                        return
                    instances.extend(members)
            if new_query_routers:
                query_router_ids = [db_instance.id for db_instance
                                    in new_query_routers]
                config_servers_ids = [db_instance.id for db_instance
                                      in self.db_instances
                                      if db_instance.type == 'config_server']
                LOG.debug('growing cluster by adding query routers '
                          '%(router)s, with config servers %(server)s',
                          {'router': query_router_ids,
                           'server': config_servers_ids})
                if not self._all_instances_ready(
                    query_router_ids, cluster_id
                ):
                    return
                query_routers = [Instance.load(context, instance_id)
                                 for instance_id in query_router_ids]
                config_servers_ips = [
                    self.get_ip(Instance.load(context, config_server_id))
                    for config_server_id in config_servers_ids
                ]
                if not self._add_query_routers(
                        query_routers, config_servers_ips,
                        admin_password=self.get_cluster_admin_password(context)
                ):
                    return
                instances.extend(query_routers)
            for instance in instances:
                self.get_guest(instance).cluster_complete()

        cluster_usage_timeout = CONF.cluster_usage_timeout
        timeout = Timeout(cluster_usage_timeout)
        try:
            _grow_cluster()
            self.reset_task()
        except Timeout as t:
            if t is not timeout:
                raise  # not my timeout
            LOG.exception(_("timeout for growing cluster."))
            self.update_statuses_on_failure(cluster_id)
        finally:
            timeout.cancel()

        LOG.debug("end grow_cluster for MongoDB cluster %s", self.id)

    def shrink_cluster(self, context, cluster_id, instance_ids):
        LOG.debug("begin shrink_cluster for MongoDB cluster %s", cluster_id)

        def _shrink_cluster():
            def all_instances_marked_deleted():
                non_deleted_instances = DBInstance.find_all(
                    cluster_id=cluster_id, deleted=False).all()
                non_deleted_ids = [db_instance.id for db_instance
                                   in non_deleted_instances]
                return not bool(
                    set(instance_ids).intersection(set(non_deleted_ids))
                )
            try:
                utils.poll_until(all_instances_marked_deleted,
                                 sleep_time=2,
                                 time_out=CONF.cluster_delete_time_out)
            except PollTimeOut:
                LOG.error(_("timeout for instances to be marked as deleted."))
                return

        cluster_usage_timeout = CONF.cluster_usage_timeout
        timeout = Timeout(cluster_usage_timeout)
        try:
            _shrink_cluster()
            self.reset_task()
        except Timeout as t:
            if t is not timeout:
                raise  # not my timeout
            LOG.exception(_("timeout for shrinking cluster."))
            self.update_statuses_on_failure(cluster_id)
        finally:
            timeout.cancel()

        LOG.debug("end shrink_cluster for MongoDB cluster %s", self.id)

    def get_cluster_admin_password(self, context):
        """The cluster admin's user credentials are stored on all query
        routers. Find one and get the guest to return the password.
        """
        instance = Instance.load(context, self._get_running_query_router_id())
        return self.get_guest(instance).get_admin_password()

    def _init_replica_set(self, primary_member, other_members):
        """Initialize the replica set by calling the primary member guest's
        add_members.
        """
        LOG.debug('initializing replica set on %s', primary_member.id)
        other_members_ips = []
        try:
            for member in other_members:
                other_members_ips.append(self.get_ip(member))
                self.get_guest(member).restart()
            self.get_guest(primary_member).prep_primary()
            self.get_guest(primary_member).add_members(other_members_ips)
        except Exception:
            LOG.exception(_("error initializing replica set"))
            self.update_statuses_on_failure(self.id,
                                            shard_id=primary_member.shard_id)
            return False
        return True

    def _create_shard(self, query_router, members):
        """Create a replica set out of the given member instances and add it as
        a shard to the cluster.
        """
        primary_member = members[0]
        other_members = members[1:]
        if not self._init_replica_set(primary_member, other_members):
            return False
        replica_set = self.get_guest(primary_member).get_replica_set_name()
        LOG.debug('adding replica set %(replica_set)s as shard %(shard_id)s '
                  'to cluster %(cluster_id)s',
                  {'replica_set': replica_set,
                   'shard_id': primary_member.shard_id, 'cluster_id': self.id})
        try:
            self.get_guest(query_router).add_shard(
                replica_set, self.get_ip(primary_member))
        except Exception:
            LOG.exception(_("error adding shard"))
            self.update_statuses_on_failure(self.id,
                                            shard_id=primary_member.shard_id)
            return False
        return True

    def _get_running_query_router_id(self):
        """Get a query router in this cluster that is in the RUNNING state."""
        for instance_id in [db_instance.id for db_instance in self.db_instances
                            if db_instance.type == 'query_router']:
            status = models.InstanceServiceStatus.find_by(
                instance_id=instance_id).get_status()
            if status == ServiceStatuses.RUNNING:
                return instance_id
        LOG.exception(_("no query routers ready to accept requests"))
        self.update_statuses_on_failure(self.id)
        return False

    def _add_query_routers(self, query_routers, config_server_ips,
                           admin_password=None):
        """Configure the given query routers for the cluster.
        If this is a new_cluster an admin user will be created with a randomly
        generated password, else the password needs to be retrieved from
        and existing query router.
        """
        LOG.debug('adding new query router(s) %(routers)s with config server '
                  'ips %(ips)s', {'routers': [i.id for i in query_routers],
                                  'ips': config_server_ips})
        for query_router in query_routers:
            try:
                LOG.debug("calling add_config_servers on query router %s",
                          query_router.id)
                guest = self.get_guest(query_router)
                guest.add_config_servers(config_server_ips)
                if not admin_password:
                    LOG.debug("creating cluster admin user")
                    admin_password = utils.generate_random_password()
                    guest.create_admin_user(admin_password)
                else:
                    guest.store_admin_password(admin_password)
            except Exception:
                LOG.exception(_("error adding config servers"))
                self.update_statuses_on_failure(self.id)
                return False
        return True


class MongoDbTaskManagerAPI(task_api.API):

    def mongodb_add_shard_cluster(self, cluster_id, shard_id,
                                  replica_set_name):
        LOG.debug("Making async call to add shard cluster %s ", cluster_id)
        version = task_api.API.API_BASE_VERSION
        cctxt = self.client.prepare(version=version)
        cctxt.cast(self.context,
                   "add_shard_cluster",
                   cluster_id=cluster_id,
                   shard_id=shard_id,
                   replica_set_name=replica_set_name)
