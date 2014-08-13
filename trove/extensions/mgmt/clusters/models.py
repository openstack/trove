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


from trove.cluster import models as cluster_models
from trove.instance import models as instance_models


class MgmtCluster(cluster_models.Cluster):
    def __init__(self, context, db_info, datastore=None,
                 datastore_version=None):
        super(MgmtCluster, self).__init__(context, db_info, datastore,
                                          datastore_version)

    @classmethod
    def load(cls, context, id):
        db_cluster = cluster_models.DBCluster.find_by(id=id)
        return cls(context, db_cluster)

    @classmethod
    def load_all(cls, context, deleted=None):
        args = {}
        if deleted is not None:
            args['deleted'] = deleted
        db_infos = cluster_models.DBCluster.find_all(**args)
        clusters = [cls(context, db_info) for db_info in db_infos]
        return clusters

    @property
    def instances(self):
        db_instances = instance_models.DBInstance.find_all(
            cluster_id=self.db_info.id, deleted=False)
        instances = [instance_models.load_any_instance(
            self.context, db_inst.id) for db_inst in db_instances]
        return instances
