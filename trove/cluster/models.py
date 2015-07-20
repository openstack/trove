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

from oslo_log import log as logging

from trove.cluster.tasks import ClusterTask
from trove.cluster.tasks import ClusterTasks
from trove.common import cfg
from trove.common import exception
from trove.common.i18n import _
from trove.common import remote
from trove.common.strategies.cluster import strategy
from trove.datastore import models as datastore_models
from trove.db import models as dbmodels
from trove.instance import models as inst_models
from trove.taskmanager import api as task_api


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


def persisted_models():
    return {
        'clusters': DBCluster,
    }


class DBCluster(dbmodels.DatabaseModelBase):
    _data_fields = ['id', 'created', 'updated', 'name', 'task_id',
                    'tenant_id', 'datastore_version_id', 'deleted',
                    'deleted_at']

    def __init__(self, task_status, **kwargs):
        """
        Creates a new persistable entity of the cluster.
        :param task_status: the current task of the cluster.
        :type task_status: trove.cluster.tasks.ClusterTask
        """
        kwargs["task_id"] = task_status.code
        kwargs["deleted"] = False
        super(DBCluster, self).__init__(**kwargs)
        self.task_status = task_status

    def _validate(self, errors):
        if ClusterTask.from_code(self.task_id) is None:
            errors['task_id'] = "Not valid."
        if self.task_status is None:
            errors['task_status'] = "Cannot be None."

    @property
    def task_status(self):
        return ClusterTask.from_code(self.task_id)

    @task_status.setter
    def task_status(self, task_status):
        self.task_id = task_status.code


class Cluster(object):
    DEFAULT_LIMIT = CONF.clusters_page_size

    def __init__(self, context, db_info, datastore=None,
                 datastore_version=None):
        self.context = context
        self.db_info = db_info
        self.ds = datastore
        self.ds_version = datastore_version
        if self.ds_version is None:
            self.ds_version = (datastore_models.DatastoreVersion.
                               load_by_uuid(self.db_info.datastore_version_id))
        if self.ds is None:
            self.ds = (datastore_models.Datastore.
                       load(self.ds_version.datastore_id))

    @classmethod
    def get_guest(cls, instance):
        return remote.create_guest_client(instance.context,
                                          instance.db_info.id,
                                          instance.datastore_version.manager)

    @classmethod
    def load_all(cls, context, tenant_id):
        db_infos = DBCluster.find_all(tenant_id=tenant_id,
                                      deleted=False)
        limit = int(context.limit or Cluster.DEFAULT_LIMIT)
        if limit > Cluster.DEFAULT_LIMIT:
            limit = Cluster.DEFAULT_LIMIT
        data_view = DBCluster.find_by_pagination('clusters', db_infos, "foo",
                                                 limit=limit,
                                                 marker=context.marker)
        next_marker = data_view.next_page_marker
        ret = [cls(context, db_info) for db_info in data_view.collection]
        return ret, next_marker

    @classmethod
    def load(cls, context, cluster_id, clazz=None):
        try:
            db_info = DBCluster.find_by(context=context, id=cluster_id,
                                        deleted=False)
        except exception.ModelNotFoundError:
            raise exception.ClusterNotFound(cluster=cluster_id)
        if not clazz:
            ds_version = (datastore_models.DatastoreVersion.
                          load_by_uuid(db_info.datastore_version_id))
            manager = ds_version.manager
            clazz = strategy.load_api_strategy(manager).cluster_class
        return clazz(context, db_info)

    def update_db(self, **values):
        self.db_info = DBCluster.find_by(id=self.id, deleted=False)
        for key in values:
            setattr(self.db_info, key, values[key])
        self.db_info.save()

    def reset_task(self):
        LOG.info(_("Setting task to NONE on cluster %s") % self.id)
        self.update_db(task_status=ClusterTasks.NONE)

    @property
    def id(self):
        return self.db_info.id

    @property
    def created(self):
        return self.db_info.created

    @property
    def updated(self):
        return self.db_info.updated

    @property
    def name(self):
        return self.db_info.name

    @property
    def task_id(self):
        return self.db_info.task_status.code

    @property
    def task_name(self):
        return self.db_info.task_status.name

    @property
    def task_description(self):
        return self.db_info.task_status.description

    @property
    def tenant_id(self):
        return self.db_info.tenant_id

    @property
    def datastore(self):
        return self.ds

    @property
    def datastore_version(self):
        return self.ds_version

    @property
    def deleted(self):
        return self.db_info.deleted

    @property
    def deleted_at(self):
        return self.db_info.deleted_at

    @property
    def instances(self):
        return inst_models.Instances.load_all_by_cluster_id(self.context,
                                                            self.db_info.id)

    @property
    def instances_without_server(self):
        return inst_models.Instances.load_all_by_cluster_id(
            self.context, self.db_info.id, load_servers=False)

    @classmethod
    def create(cls, context, name, datastore, datastore_version, instances):
        api_strategy = strategy.load_api_strategy(datastore_version.manager)
        return api_strategy.cluster_class.create(context, name, datastore,
                                                 datastore_version, instances)

    def validate_cluster_available(self, valid_states=[ClusterTasks.NONE]):
        if self.db_info.task_status not in valid_states:
            msg = (_("This action cannot be performed on the cluster while "
                     "the current cluster task is '%s'.") %
                   self.db_info.task_status.name)
            LOG.error(msg)
            raise exception.UnprocessableEntity(msg)

    def delete(self):

        self.validate_cluster_available([ClusterTasks.NONE,
                                         ClusterTasks.DELETING])

        db_insts = inst_models.DBInstance.find_all(cluster_id=self.id,
                                                   deleted=False).all()

        self.update_db(task_status=ClusterTasks.DELETING)

        for db_inst in db_insts:
            instance = inst_models.load_any_instance(self.context, db_inst.id)
            instance.delete()

        task_api.API(self.context).delete_cluster(self.id)

    @staticmethod
    def load_instance(context, cluster_id, instance_id):
        return inst_models.load_instance_with_guest(
            inst_models.DetailInstance, context, instance_id, cluster_id)

    @staticmethod
    def manager_from_cluster_id(context, cluster_id):
        db_info = DBCluster.find_by(context=context, id=cluster_id,
                                    deleted=False)
        ds_version = (datastore_models.DatastoreVersion.
                      load_by_uuid(db_info.datastore_version_id))
        return ds_version.manager


def is_cluster_deleting(context, cluster_id):
    cluster = Cluster.load(context, cluster_id)
    return (cluster.db_info.task_status == ClusterTasks.DELETING
            or cluster.db_info.task_status == ClusterTasks.SHRINKING_CLUSTER)


def validate_volume_size(size):
    if size is None:
        raise exception.VolumeSizeNotSpecified()
    max_size = CONF.max_accepted_volume_size
    if int(size) > max_size:
        msg = ("Volume 'size' cannot exceed maximum "
               "of %d Gb, %s cannot be accepted."
               % (max_size, size))
        raise exception.VolumeQuotaExceeded(msg)
