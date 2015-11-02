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

import datetime

from mock import Mock
from mock import patch

from trove.cluster.models import ClusterTasks as ClusterTaskStatus
from trove.cluster.models import DBCluster
from trove.common.exception import GuestError
from trove.common.strategies.cluster.experimental.pxc.taskmanager import (
    PXCClusterTasks as ClusterTasks)
from trove.common.strategies.cluster.experimental.pxc.taskmanager import (
    PXCTaskManagerStrategy as task_strategy)
from trove.datastore import models as datastore_models
from trove.instance.models import BaseInstance
from trove.instance.models import DBInstance
from trove.instance.models import Instance
from trove.instance.models import InstanceServiceStatus
from trove.instance.models import InstanceTasks
from trove.taskmanager.models import ServiceStatuses
from trove.tests.unittests import trove_testtools
from trove.tests.unittests.util import util


class PXCClusterTasksTest(trove_testtools.TestCase):
    def setUp(self):
        super(PXCClusterTasksTest, self).setUp()
        util.init_db()
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
                                  task_description=InstanceTasks.NONE._db_text,
                                  volume_id="volume-1",
                                  datastore_version_id="1",
                                  cluster_id=self.cluster_id,
                                  type="member")
        self.dbinst2 = DBInstance(InstanceTasks.NONE, id="2", name="member2",
                                  compute_instance_id="compute-2",
                                  task_id=InstanceTasks.NONE._code,
                                  task_description=InstanceTasks.NONE._db_text,
                                  volume_id="volume-2",
                                  datastore_version_id="1",
                                  cluster_id=self.cluster_id,
                                  type="member")
        self.dbinst3 = DBInstance(InstanceTasks.NONE, id="3", name="member3",
                                  compute_instance_id="compute-3",
                                  task_id=InstanceTasks.NONE._code,
                                  task_description=InstanceTasks.NONE._db_text,
                                  volume_id="volume-3",
                                  datastore_version_id="1",
                                  cluster_id=self.cluster_id,
                                  type="member")
        mock_ds1 = Mock()
        mock_ds1.name = 'pxc'
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
        self.assertFalse(ret_val)

    @patch.object(InstanceServiceStatus, 'find_by')
    def test_all_instances_ready(self, mock_find):
        (mock_find.return_value.
         get_status.return_value) = ServiceStatuses.INSTANCE_READY
        ret_val = self.clustertasks._all_instances_ready(["1", "2", "3", "4"],
                                                         self.cluster_id)
        self.assertTrue(ret_val)

    @patch.object(ClusterTasks, 'reset_task')
    @patch.object(ClusterTasks, '_all_instances_ready', return_value=False)
    @patch.object(Instance, 'load')
    @patch.object(DBInstance, 'find_all')
    @patch.object(datastore_models.Datastore, 'load')
    @patch.object(datastore_models.DatastoreVersion, 'load_by_uuid')
    def test_create_cluster_instance_not_ready(self, mock_dv, mock_ds,
                                               mock_find_all, mock_load,
                                               mock_ready, mock_reset_task):
        mock_find_all.return_value.all.return_value = [self.dbinst1]
        mock_load.return_value = BaseInstance(Mock(),
                                              self.dbinst1, Mock(),
                                              InstanceServiceStatus(
                                                  ServiceStatuses.NEW))
        self.clustertasks.create_cluster(Mock(), self.cluster_id)
        mock_reset_task.assert_called_with()

    @patch.object(ClusterTasks, 'update_statuses_on_failure')
    @patch.object(ClusterTasks, 'reset_task')
    @patch.object(ClusterTasks, 'get_ip')
    @patch.object(ClusterTasks, '_all_instances_ready')
    @patch.object(Instance, 'load')
    @patch.object(DBInstance, 'find_all')
    @patch.object(datastore_models.Datastore, 'load')
    @patch.object(datastore_models.DatastoreVersion, 'load_by_uuid')
    def test_create_cluster_fail(self, mock_dv, mock_ds, mock_find_all,
                                 mock_load, mock_ready, mock_ip,
                                 mock_reset_task, mock_update_status):
        mock_find_all.return_value.all.return_value = [self.dbinst1]
        mock_load.return_value = BaseInstance(Mock(),
                                              self.dbinst1, Mock(),
                                              InstanceServiceStatus(
                                                  ServiceStatuses.NEW))
        mock_ip.return_value = "10.0.0.2"
        guest_client = Mock()
        guest_client.install_cluster = Mock(side_effect=GuestError("Error"))
        with patch.object(ClusterTasks, 'get_guest',
                          return_value=guest_client):
            self.clustertasks.create_cluster(Mock(), self.cluster_id)
            mock_update_status.assert_called_with('1232')
            mock_reset_task.assert_called_with()


class PXCTaskManagerStrategyTest(trove_testtools.TestCase):

    def test_task_manager_cluster_tasks_class(self):
        percona_strategy = task_strategy()
        self.assertFalse(
            hasattr(percona_strategy.task_manager_cluster_tasks_class,
                    'rebuild_cluster'))
        self.assertTrue(callable(
            percona_strategy.task_manager_cluster_tasks_class.create_cluster))

    def test_task_manager_api_class(self):
        percona_strategy = task_strategy()
        self.assertFalse(hasattr(percona_strategy.task_manager_api_class,
                                 'add_new_node'))
