# Copyright 2012 OpenStack Foundation
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


"""
Routes all the requests to the task manager.
"""

from oslo_log import log as logging
import oslo_messaging as messaging

from trove.common import cfg
from trove.common import exception
import trove.common.rpc.version as rpc_version
from trove.common.strategies.cluster import strategy
from trove.guestagent import models as agent_models
from trove import rpc

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class API(object):
    """API for interacting with the task manager."""

    def __init__(self, context):
        self.context = context
        super(API, self).__init__()

        target = messaging.Target(topic=CONF.taskmanager_queue,
                                  version=rpc_version.RPC_API_VERSION)

        self.version_cap = rpc_version.VERSION_ALIASES.get(
            CONF.upgrade_levels.taskmanager)
        self.client = self.get_client(target, self.version_cap)

    def get_client(self, target, version_cap, serializer=None):
        return rpc.get_client(target,
                              version_cap=version_cap,
                              serializer=serializer)

    def _transform_obj(self, obj_ref):
        # Turn the object into a dictionary and remove the mgr
        if "__dict__" in dir(obj_ref):
            obj_dict = obj_ref.__dict__
            # We assume manager contains a object due to the *clients
            if obj_dict.get('manager'):
                del obj_dict['manager']
            return obj_dict
        raise ValueError("Could not transform %s" % obj_ref)

    def _delete_heartbeat(self, instance_id):
        agent_heart_beat = agent_models.AgentHeartBeat()
        try:
            heartbeat = agent_heart_beat.find_by_instance_id(instance_id)
            heartbeat.delete()
        except exception.ModelNotFoundError as e:
            LOG.error(e.message)

    def resize_volume(self, new_size, instance_id):
        LOG.debug("Making async call to resize volume for instance: %s"
                  % instance_id)

        cctxt = self.client.prepare(version=self.version_cap)
        cctxt.cast(self.context, "resize_volume",
                   new_size=new_size,
                   instance_id=instance_id)

    def resize_flavor(self, instance_id, old_flavor, new_flavor):
        LOG.debug("Making async call to resize flavor for instance: %s" %
                  instance_id)

        cctxt = self.client.prepare(version=self.version_cap)
        cctxt.cast(self.context, "resize_flavor",
                   instance_id=instance_id,
                   old_flavor=self._transform_obj(old_flavor),
                   new_flavor=self._transform_obj(new_flavor))

    def reboot(self, instance_id):
        LOG.debug("Making async call to reboot instance: %s" % instance_id)

        cctxt = self.client.prepare(version=self.version_cap)
        cctxt.cast(self.context, "reboot", instance_id=instance_id)

    def restart(self, instance_id):
        LOG.debug("Making async call to restart instance: %s" % instance_id)

        cctxt = self.client.prepare(version=self.version_cap)
        cctxt.cast(self.context, "restart", instance_id=instance_id)

    def detach_replica(self, instance_id):
        LOG.debug("Making async call to detach replica: %s" % instance_id)

        cctxt = self.client.prepare(version=self.version_cap)
        cctxt.cast(self.context, "detach_replica", instance_id=instance_id)

    def promote_to_replica_source(self, instance_id):
        LOG.debug("Making async call to promote replica to source: %s" %
                  instance_id)
        cctxt = self.client.prepare(version=self.version_cap)
        cctxt.cast(self.context, "promote_to_replica_source",
                   instance_id=instance_id)

    def eject_replica_source(self, instance_id):
        LOG.debug("Making async call to eject replica source: %s" %
                  instance_id)
        cctxt = self.client.prepare(version=self.version_cap)
        cctxt.cast(self.context, "eject_replica_source",
                   instance_id=instance_id)

    def migrate(self, instance_id, host):
        LOG.debug("Making async call to migrate instance: %s" % instance_id)

        cctxt = self.client.prepare(version=self.version_cap)
        cctxt.cast(self.context, "migrate", instance_id=instance_id, host=host)

    def delete_instance(self, instance_id):
        LOG.debug("Making async call to delete instance: %s" % instance_id)

        cctxt = self.client.prepare(version=self.version_cap)
        cctxt.cast(self.context, "delete_instance", instance_id=instance_id)

    def create_backup(self, backup_info, instance_id):
        LOG.debug("Making async call to create a backup for instance: %s" %
                  instance_id)

        cctxt = self.client.prepare(version=self.version_cap)
        cctxt.cast(self.context, "create_backup",
                   backup_info=backup_info,
                   instance_id=instance_id)

    def delete_backup(self, backup_id):
        LOG.debug("Making async call to delete backup: %s" % backup_id)

        cctxt = self.client.prepare(version=self.version_cap)
        cctxt.cast(self.context, "delete_backup", backup_id=backup_id)

    def create_instance(self, instance_id, name, flavor,
                        image_id, databases, users, datastore_manager,
                        packages, volume_size, backup_id=None,
                        availability_zone=None, root_password=None,
                        nics=None, overrides=None, slave_of_id=None,
                        cluster_config=None, volume_type=None):

        LOG.debug("Making async call to create instance %s " % instance_id)

        cctxt = self.client.prepare(version=self.version_cap)
        cctxt.cast(self.context, "create_instance",
                   instance_id=instance_id, name=name,
                   flavor=self._transform_obj(flavor),
                   image_id=image_id,
                   databases=databases,
                   users=users,
                   datastore_manager=datastore_manager,
                   packages=packages,
                   volume_size=volume_size,
                   backup_id=backup_id,
                   availability_zone=availability_zone,
                   root_password=root_password,
                   nics=nics,
                   overrides=overrides,
                   slave_of_id=slave_of_id,
                   cluster_config=cluster_config,
                   volume_type=volume_type)

    def create_cluster(self, cluster_id):
        LOG.debug("Making async call to create cluster %s " % cluster_id)

        cctxt = self.client.prepare(version=self.version_cap)
        cctxt.cast(self.context, "create_cluster",
                   cluster_id=cluster_id)

    def grow_cluster(self, cluster_id, new_instance_ids):
        LOG.debug("Making async call to grow cluster %s " % cluster_id)

        cctxt = self.client.prepare(version=self.version_cap)
        cctxt.cast(self.context, "grow_cluster",
                   cluster_id=cluster_id, new_instance_ids=new_instance_ids)

    def shrink_cluster(self, cluster_id, instance_ids):
        LOG.debug("Making async call to shrink cluster %s " % cluster_id)

        cctxt = self.client.prepare(version=self.version_cap)
        cctxt.cast(self.context, "shrink_cluster",
                   cluster_id=cluster_id, instance_ids=instance_ids)

    def delete_cluster(self, cluster_id):
        LOG.debug("Making async call to delete cluster %s " % cluster_id)

        cctxt = self.client.prepare(version=self.version_cap)
        cctxt.cast(self.context, "delete_cluster",
                   cluster_id=cluster_id)


def load(context, manager=None):
    if manager:
        task_manager_api_class = (strategy.load_taskmanager_strategy(manager)
                                  .task_manager_api_class)
    else:
        task_manager_api_class = API
    return task_manager_api_class(context)
