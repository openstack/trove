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

from mock import Mock, patch

from trove.cluster import models
from trove.common.strategies.cluster.experimental.mongodb.api import (
    MongoDbCluster)
from trove.datastore import models as datastore_models
from trove.tests.unittests import trove_testtools


class TestClusterModel(trove_testtools.TestCase):

    @patch.object(datastore_models.Datastore, 'load')
    @patch.object(datastore_models.DatastoreVersion, 'load_by_uuid')
    @patch.object(models.DBCluster, 'find_by')
    def test_load(self, mock_find_by, mock_load_dsv_by_uuid, mock_ds_load):
        context = Mock()
        id = Mock()

        dsv = Mock()
        dsv.manager = 'mongodb'
        mock_load_dsv_by_uuid.return_value = dsv
        cluster = models.Cluster.load(context, id)
        self.assertTrue(isinstance(cluster, MongoDbCluster))
