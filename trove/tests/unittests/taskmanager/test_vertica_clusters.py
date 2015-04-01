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

import datetime

import testtools
from mock import Mock
from mock import patch

from trove.cluster.models import ClusterTasks as ClusterTaskStatus
from trove.cluster.models import DBCluster
from trove.common.strategies.cluster.experimental.vertica.taskmanager import \
    VerticaClusterTasks as ClusterTasks
from trove.datastore import models as datastore_models
from trove.instance.models import BaseInstance
from trove.instance.models import DBInstance
from trove.instance.models import Instance
from trove.instance.models import InstanceServiceStatus
from trove.instance.models import InstanceTasks
from trove.taskmanager.models import ServiceStatuses


class VerticaClusterTasksTest(testtools.TestCase):
    def setUp(self):
        super(VerticaClusterTasksTest, self).setUp()
        self.cluster_id = "1232"
        self.cluster_name = "Cluster-1234"
        self.tenant_id = "6789"
        self.db_cluster = DBCluster(ClusterTaskStatus.NONE,
                                    id=self.cluster_id,
                                    created=str(datetime.date),
                                    updated=str(datetime.date),
                                    name=self.cluster_name,
                                    task_id=ClusterTaskStatus.NONE._code,
                                    tenant_id=self.tenant_id,
                                    datastore_version_id="1",
                                    deleted=False)
        self.dbinst1 = DBInstance(InstanceTasks.NONE, id="1", name="member1",
                                  compute_instance_id="compute-1",
                                  task_id=InstanceTasks.NONE._code,
                                  task_description=
                                  InstanceTasks.NONE._db_text,
                                  volume_id="volume-1",
                                  datastore_version_id="1",
                                  cluster_id=self.cluster_id,
                                  type="member")
        self.dbinst2 = DBInstance(InstanceTasks.NONE, id="2", name="member2",
                                  compute_instance_id="compute-2",
                                  task_id=InstanceTasks.NONE._code,
                                  task_description=
                                  InstanceTasks.NONE._db_text,
                                  volume_id="volume-2",
                                  datastore_version_id="1",
                                  cluster_id=self.cluster_id,
                                  type="member")
        self.dbinst3 = DBInstance(InstanceTasks.NONE, id="3", name="member3",
                                  compute_instance_id="compute-3",
                                  task_id=InstanceTasks.NONE._code,
                                  task_description=
                                  InstanceTasks.NONE._db_text,
                                  volume_id="volume-3",
                                  datastore_version_id="1",
                                  cluster_id=self.cluster_id,
                                  type="member")
        mock_ds1 = Mock()
        mock_ds1.name = 'vertica'
        mock_dv1 = Mock()
        mock_dv1.name = '7.1'
        self.clustertasks = ClusterTasks(Mock(),
                                         self.db_cluster,
                                         datastore=mock_ds1,
                                         datastore_version=mock_dv1)

    @patch.object(ClusterTasks, 'update_statuses_on_failure')
    @patch.object(InstanceServiceStatus, 'find_by')
    def test_all_instances_ready_bad_status(self,
                                            mock_find, mock_update):
        (mock_find.return_value.
         get_status.return_value) = ServiceStatuses.FAILED
        ret_val = self.clustertasks._all_instances_ready(["1", "2", "3", "4"],
                                                         self.cluster_id)
        mock_update.assert_called_with(self.cluster_id, None)
        self.assertEqual(False, ret_val)

    @patch.object(InstanceServiceStatus, 'find_by')
    def test_all_instances_ready(self, mock_find):
        (mock_find.return_value.
         get_status.return_value) = ServiceStatuses.RUNNING
        ret_val = self.clustertasks._all_instances_ready(["1", "2", "3", "4"],
                                                         self.cluster_id)
        self.assertEqual(True, ret_val)

    @patch.object(ClusterTasks, 'reset_task')
    @patch.object(ClusterTasks, 'get_guest')
    @patch.object(ClusterTasks, 'get_ip')
    @patch.object(ClusterTasks, '_all_instances_ready')
    @patch.object(Instance, 'load')
    @patch.object(DBInstance, 'find_all')
    @patch.object(datastore_models.Datastore, 'load')
    @patch.object(datastore_models.DatastoreVersion, 'load_by_uuid')
    def test_create_cluster(self, mock_dv, mock_ds, mock_find_all, mock_load,
                            mock_ready, mock_ip, mock_guest, mock_reset_task):
        mock_find_all.return_value.all.return_value = [self.dbinst1]
        mock_load.return_value = BaseInstance(Mock(),
                                              self.dbinst1, Mock(),
                                              InstanceServiceStatus(
                                                  ServiceStatuses.NEW))
        mock_ip.return_value = "10.0.0.2"
        self.clustertasks.create_cluster(Mock(), self.cluster_id)
        mock_guest.return_value.install_cluster.assert_called_with(['10.0.0.2']
                                                                   )
        mock_reset_task.assert_called()
        mock_guest.return_value.cluster_complete.assert_called()
